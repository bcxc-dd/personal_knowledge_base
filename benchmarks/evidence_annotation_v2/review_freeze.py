"""Create an immutable, human-reviewable DEV package from the v2 draft.

This module never runs either matcher and never marks a case human-confirmed.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "test-results/evidence-matching-v2-2026-10-03/dataset-v2.json"
OUTPUT = ROOT / "test-results/evidence-annotation-freeze-2026-10-03"
SCHEMA_DOC = ROOT / "docs/evaluations/evidence-annotation-v2-schema.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_record(source: dict) -> dict:
    if source.get("human_review_state") != "PENDING":
        raise ValueError(f"Unexpected human review state: {source.get('case_id')}")
    refs = source.get("evidence_metadata") or []
    primary = refs[0] if refs else {}
    chunk_id = primary.get("chunk_id")
    risk = source.get("risk_flags") or []
    attention = []
    if source.get("query_type") == "YES_NO" and source.get("relation_status") == "CONTRADICTS_QUERY_PROPOSITION":
        attention.append("YES_NO_CONTRADICTION")
    if "SOURCE_CONTRADICTS_CANONICAL" in risk or source.get("relation_status") == "SOURCE_CONTRADICTS_CANONICAL":
        attention.append("CANONICAL_CONTRADICTION")
    if source.get("relation_status") == "NEGATED":
        attention.append("NEGATION")
    if source.get("relation_status") == "STALE_OR_REVOKED":
        attention.append("STALE_RULE")
    if any(f.get("fact_type") == "table_lookup" for f in source.get("required_facts", [])):
        attention.append("TABLE_MAPPING")
    if source.get("answerability") == "PARTIAL":
        attention.append("PARTIAL_SUPPORT")
    if source.get("label_changed_from_v1"):
        attention.append("RELABELLED_FROM_V1")

    keys = ("case_id", "query", "query_type", "answerability", "required_facts",
            "covered_facts", "missing_facts", "expected_facts", "expected_answer",
            "relation_status", "risk_flags", "canonical_reference", "evidence_text")
    row = {key: source.get(key) for key in keys}
    row.update({
        "old_v1_label": source.get("old_gold_label"),
        "document_id": chunk_id.split(":", 1)[0] if chunk_id else None,
        "page": primary.get("page"), "chunk_id": chunk_id,
        "provenance": {"source_kind": source.get("evidence_provenance"), "evidence_refs": refs},
        "split": source.get("metric_group"),
        "review_state": "NEEDS_HUMAN_REVIEW",
        "review_reason": source.get("review_reason"),
        "proposed_review_action": source.get("review_status"),
        "review_attention": attention,
        "human_decision": None, "human_correction": None,
        "origin": source.get("origin"),
    })
    if row["split"] not in {"PRIMARY_DEV", "DIAGNOSTIC_DEV"}:
        raise ValueError(f"Unexpected DEV split: {row['case_id']}")
    return row


def markdown(rows: list[dict]) -> str:
    out = ["# Evidence Annotation v2 — 人工复核表", "",
           "> 这 36 条全是 DEV；以下标签是 agent 建议，未获人工签核。请逐条填写 human_decision / human_correction；任何 `CONFIRMED` 建议都不表示人工确认。", "",
           "| 项目 | 数量 |", "|---|---:|",
           f"| 全部待复核 | {len(rows)} |",
           f"| PRIMARY_DEV | {sum(r['split'] == 'PRIMARY_DEV' for r in rows)} |",
           f"| DIAGNOSTIC_DEV | {sum(r['split'] == 'DIAGNOSTIC_DEV' for r in rows)} |", ""]
    for row in rows:
        out.extend([f"## {row['case_id']} · {row['split']}", "",
                    f"**复核状态：{row['review_state']}**　**重点：{', '.join(row['review_attention']) or '常规'}**", "",
                    f"- Query：{row['query']}",
                    f"- 旧 v1：`{row['old_v1_label']}`；建议 v2：`{row['answerability']}`；关系：`{row['relation_status']}`",
                    f"- 来源：document_id=`{row['document_id']}`，page=`{row['page']}`，chunk_id=`{row['chunk_id']}`，provenance=`{row['provenance']['source_kind']}`",
                    f"- 建议回答：{row['expected_answer']}",
                    f"- 建议理由：{row['review_reason']}", "",
                    "**Evidence**", "", "<pre>", html.escape(row["evidence_text"] or ""), "</pre>", ""])
        for key in ("required_facts", "covered_facts", "missing_facts", "expected_facts", "risk_flags", "canonical_reference"):
            out.extend([f"**{key}**", "", "```json", json.dumps(row[key], ensure_ascii=False, indent=2), "```", ""])
        out.extend(["**人工决定（待填写）：** `CONFIRM / CORRECT / EXCLUDE`", "",
                    "**修订与依据（待填写）：**", "", "---", ""])
    return "\n".join(out)


def write_package(source_path: Path = SOURCE, output_dir: Path = OUTPUT) -> dict:
    if output_dir.exists():
        raise FileExistsError(output_dir)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    rows = [review_record(item) for item in source["cases"]]
    if len(rows) != 36 or len({r["case_id"] for r in rows}) != 36:
        raise ValueError("Expected 36 distinct legacy DEV cases")
    output_dir.mkdir(parents=True)
    json_path = output_dir / "review-rows.json"
    md_path = output_dir / "review-sheet.md"
    json_path.write_text(json.dumps({"schema": "evidence-annotation-v2-review", "review_state": "PENDING_HUMAN_SIGNOFF", "cases": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown(rows), encoding="utf-8")
    manifest = {"state": "SCHEMA_DRAFT_FROZEN_FOR_REVIEW; GOLD_NOT_SIGNED",
                "source_dataset_sha256": sha256(source_path),
                "review_rows_sha256": sha256(json_path), "review_sheet_sha256": sha256(md_path),
                "case_count": len(rows), "test_frozen_count": 0}
    if SCHEMA_DOC.exists():
        manifest["schema_doc_sha256"] = sha256(SCHEMA_DOC)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(write_package(), ensure_ascii=False, indent=2))
