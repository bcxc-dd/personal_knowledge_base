"""Verify provenance, schema invariants and frozen historical output mapping."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.evidence_annotation_v2.build import validate_record, verify_v1_freeze
from benchmarks.evidence_annotation_v2.freeze import V1, V2, sha


def main():
    verify_v1_freeze()
    dataset_path, score_path, report_path = (V2 / name for name in ("dataset-v2.json", "rescore-v2.json", "report.md"))
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    result = json.loads(score_path.read_text(encoding="utf-8"))
    rows = dataset["cases"]
    if len(rows) != 36 or len({r["case_id"] for r in rows}) != 36:
        raise RuntimeError("Expected exactly 36 distinct DEV cases")
    if any(r["split"] != "DEV" or r["human_review_state"] != "PENDING" for r in rows):
        raise RuntimeError("False test or human status")
    for row in rows:
        validate_record(row)
    if result["dataset_sha256"] != sha(dataset_path) or result["v1_freeze_sha256"] != sha(V2 / "v1-freeze.json"):
        raise RuntimeError("v2 score source drift")
    if result["matcher_sha256"] != sha(ROOT / "benchmarks/evidence_matching/matchers.py"):
        raise RuntimeError("Matcher changed")
    predictions = {(r["case_id"], r["variant"]): r for r in result["predictions"]}
    if len(predictions) != 36 * 5:
        raise RuntimeError("Missing E0-E4 predictions")
    old = json.loads((V1 / "results.json").read_text(encoding="utf-8"))
    for row in old["rows"]:
        newer = predictions[(row["case_id"], row["variant"])]
        if newer["decision"]["predicted_label"] != row["predicted_label"]:
            raise RuntimeError(f"Historical prediction changed: {row['case_id']}/{row['variant']}")
    table = predictions[("table-column-order", "E4")]
    if table["predicted_answerability"] != "FULL" or table["fact_extraction_correct"] is not False:
        raise RuntimeError("Table value error was hidden")
    if sum(r["label_changed_from_v1"] for r in rows if r["origin"] == "main") != 6:
        raise RuntimeError("Relabel count drift")
    if sum(r["metric_group"] == "PRIMARY_DEV" for r in rows) != 27:
        raise RuntimeError("Primary diagnostic partition drift")
    report = report_path.read_text(encoding="utf-8")
    if "25/31" not in report or "0.05" not in report or "待人工确认" not in report:
        raise RuntimeError("Report omits migration-blocking facts")
    summary = {"status": "verified_agent_proposed_pending_human_review", "cases": len(rows),
               "predictions": len(predictions), "main_relabelled": 6,
               "splits": dict(Counter(r["split"] for r in rows)),
               "primary_dev": 27,
               "sha256": {"v1_freeze": sha(V2 / "v1-freeze.json"),
                          "v2_dataset": sha(dataset_path), "v2_rescore": sha(score_path),
                          "v2_report": sha(report_path),
                          "v2_annotation_code": sha(ROOT / "benchmarks/evidence_annotation_v2/annotations.py"),
                          "unchanged_e4_matcher": sha(ROOT / "benchmarks/evidence_matching/matchers.py")}}
    path = V2 / "verification.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
