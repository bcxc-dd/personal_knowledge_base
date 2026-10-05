"""Build a new annotation dataset without touching the frozen v1 artifacts."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.evidence_annotation_v2.annotations import MAIN, STRESS, REQUIREMENTS
from benchmarks.evidence_annotation_v2.freeze import V1, V2, sha

ANSWERABILITY = {"FULL", "PARTIAL", "NONE"}
RELATIONS = {"ENTAILS", "CONTRADICTS_QUERY_PROPOSITION", "WRONG_METRIC", "WRONG_SCOPE",
             "WRONG_VALUE", "MISSING_FACT", "STALE_OR_REVOKED", "NEGATED", "RELATION_SWAPPED",
             "TABLE_MAPPING_ERROR", "SOURCE_CONTRADICTS_CANONICAL"}
REVIEW = {"CONFIRMED", "RELABELLED", "AMBIGUOUS", "REMOVE_FROM_MAIN_SET"}
QUERY_TYPES = {"WH", "YES_NO", "COMPARISON", "DEFINITION", "NUMERIC_LOOKUP", "CONDITION", "COMPOUND"}


def verify_v1_freeze():
    manifest = json.loads((V2 / "v1-freeze.json").read_text(encoding="utf-8"))
    for name, spec in manifest["files"].items():
        path = V1 / name
        if sha(path) != spec["sha256"] or path.stat().st_size != spec["size"]:
            raise RuntimeError(f"Frozen v1 artifact changed: {name}")
    return manifest


def build_record(case_id: str, source: dict, origin: str) -> dict:
    annotation = (MAIN if origin == "main" else STRESS)[case_id]
    required = copy.deepcopy(REQUIREMENTS[annotation["requirement_set"]])
    ids = [fact["fact_id"] for fact in required]
    covered_ids = annotation["covered_fact_ids"]
    covered = [fact for fact in required if fact["fact_id"] in covered_ids]
    missing = [fact for fact in required if fact["fact_id"] not in covered_ids]
    return {
        "case_id": case_id, "query": source["query"],
        "query_plan_v1": source.get("query_plan"), "query_type": annotation["query_type"],
        "evidence_text": source["evidence_text"],
        "evidence_metadata": source.get("evidence_metadata", []),
        "evidence_provenance": source.get("provenance", "agent_authored_controlled_fixture"),
        "old_gold_label": source["gold_label"], "old_reason": source.get("reason"),
        "answerability": annotation["answerability"],
        "required_facts": required, "covered_facts": covered, "missing_facts": missing,
        "relation_status": annotation["relation_status"], "risk_flags": annotation["risk_flags"],
        "expected_answer": annotation["expected_answer"],
        "expected_facts": copy.deepcopy(annotation["expected_facts"]),
        "canonical_reference": copy.deepcopy(annotation["canonical_reference"]),
        "review_reason": annotation["review_reason"],
        "review_status": annotation["review_status"],
        "reviewer_kind": "agent_proposed", "human_review_state": "PENDING",
        "split": "DEV", "origin": origin,
        "metric_group": "PRIMARY_DEV" if origin == "main" and annotation["main_metric_eligible"] else "DIAGNOSTIC_DEV",
        "label_changed_from_v1": {"SUPPORTED": "FULL", "PARTIAL": "PARTIAL", "NOT_SUPPORTED": "NONE"}[source["gold_label"]] != annotation["answerability"],
    }


def validate_record(record: dict):
    if record["answerability"] not in ANSWERABILITY or record["relation_status"] not in RELATIONS:
        raise ValueError(f"Invalid answerability/relation: {record['case_id']}")
    if record["query_type"] not in QUERY_TYPES or record["review_status"] not in REVIEW:
        raise ValueError(f"Invalid query/review type: {record['case_id']}")
    required = {f["fact_id"] for f in record["required_facts"]}
    covered = {f["fact_id"] for f in record["covered_facts"]}
    missing = {f["fact_id"] for f in record["missing_facts"]}
    expected = {f["fact_id"] for f in record["expected_facts"]}
    if len(required) != len(record["required_facts"]):
        raise ValueError(f"Duplicate required fact: {record['case_id']}")
    if covered & missing or covered | missing != required or expected != covered:
        raise ValueError(f"Fact partition/value mismatch: {record['case_id']}")
    count = len(covered)
    label = "FULL" if count == len(required) else "PARTIAL" if count else "NONE"
    if label != record["answerability"]:
        raise ValueError(f"Answerability disagrees with fact coverage: {record['case_id']}")
    if record["query_type"] == "YES_NO" and record["answerability"] == "FULL":
        if not any(f.get("answer") in {"YES", "NO"} for f in record["expected_facts"]):
            raise ValueError(f"YES_NO without polarity: {record['case_id']}")
    for fact in record["expected_facts"]:
        typ = fact["fact_type"]
        fields = {"numeric_requirement": {"metric", "operator", "value", "scope"},
                  "conditional_value": {"condition", "output"},
                  "relation": {"subject", "relation"},
                  "table_lookup": {"row", "column", "value"}}.get(typ, set())
        if not fields <= fact.keys():
            raise ValueError(f"Incomplete structured fact: {record['case_id']}/{fact['fact_id']}")
    if record["split"] != "DEV" or record["human_review_state"] != "PENDING":
        raise ValueError(f"False independent/human status: {record['case_id']}")
    if record["review_status"] == "REMOVE_FROM_MAIN_SET" and record["metric_group"] == "PRIMARY_DEV":
        raise ValueError(f"Removed case still scored in primary: {record['case_id']}")
    if not record["expected_answer"] or not record["review_reason"]:
        raise ValueError(f"Missing answer/reason: {record['case_id']}")


def main():
    verify_v1_freeze()
    path = V2 / "dataset-v2.json"
    if path.exists():
        raise RuntimeError("v2 dataset already exists; refusing overwrite")
    source = json.loads((V1 / "dataset.json").read_text(encoding="utf-8"))
    stress = json.loads((V1 / "stress.json").read_text(encoding="utf-8"))
    source_main = {r["case_id"]: r for r in source["cases"]}
    source_stress = {r["case_id"]: r for r in stress["rows"]}
    if set(source_main) != set(MAIN) or set(source_stress) != set(STRESS):
        raise RuntimeError("v1 source and explicit v2 annotations differ")
    rows = [build_record(cid, source_main[cid], "main") for cid in source_main]
    rows += [build_record(cid, source_stress[cid], "stress") for cid in source_stress]
    for row in rows:
        validate_record(row)
    payload = {"schema": "evidence-matching-v2", "core_question": "Can this evidence alone answer the user's explicit information need?",
               "source_of_truth": "evidence_content_for_answerability; canonical truth tracked separately",
               "review_state": "AGENT_PROPOSED_PENDING_USER_REVIEW",
               "split_policy": "all 31 original + 5 stress are DEV/diagnostic; TEST_FROZEN is empty",
               "v1_freeze_sha256": sha(V2 / "v1-freeze.json"),
               "cases": rows}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(rows), "primary_dev": sum(r["metric_group"] == "PRIMARY_DEV" for r in rows),
                      "relabelled_main": sum(r["label_changed_from_v1"] for r in rows if r["origin"] == "main"),
                      "sha256": sha(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
