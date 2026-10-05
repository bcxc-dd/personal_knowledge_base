"""Review package invariants for the existing DEV annotations."""
import pytest

from benchmarks.evidence_annotation_v2.review_freeze import review_record, write_package


def test_review_record_keeps_provenance_and_never_claims_human_signoff():
    source = {
        "case_id": "table-column-order", "query": "第二等次是多少？",
        "query_type": "NUMERIC_LOOKUP", "evidence_text": "第二等次 第一等次；Ⅱ级甲等 0.05 0.06",
        "evidence_metadata": [{"chunk_id": "doc:16", "page": 9, "document_key": "promotion"}],
        "evidence_provenance": "frozen_verified_pdf_chunk", "old_gold_label": "SUPPORTED",
        "answerability": "FULL", "required_facts": [{"fact_id": "cell", "fact_type": "table_lookup"}],
        "covered_facts": [{"fact_id": "cell", "fact_type": "table_lookup"}],
        "missing_facts": [], "expected_facts": [{"fact_id": "cell", "fact_type": "table_lookup", "row": "Ⅱ级甲等", "column": "第二等次", "value": 0.05}],
        "expected_answer": "0.05", "relation_status": "ENTAILS", "risk_flags": [],
        "canonical_reference": [], "review_reason": "列序", "metric_group": "DIAGNOSTIC_DEV",
        "review_status": "CONFIRMED", "human_review_state": "PENDING",
    }
    row = review_record(source)
    assert row["split"] == "DIAGNOSTIC_DEV"
    assert row["review_state"] == "NEEDS_HUMAN_REVIEW"
    assert row["proposed_review_action"] == "CONFIRMED"
    assert row["document_id"] == "doc"
    assert row["page"] == 9 and row["chunk_id"] == "doc:16"
    assert "TABLE_MAPPING" in row["review_attention"]


def test_review_package_refuses_overwrite_and_has_36_pending_rows(tmp_path):
    import json
    dataset = {"cases": [{"case_id": str(i), "query": "q", "evidence_text": "e", "query_type": "WH",
        "answerability": "NONE", "required_facts": [], "covered_facts": [], "missing_facts": [],
        "expected_facts": [], "expected_answer": "不足", "relation_status": "MISSING_FACT",
        "risk_flags": [], "canonical_reference": [], "review_reason": "测试", "old_gold_label": "NOT_SUPPORTED",
        "metric_group": "PRIMARY_DEV", "human_review_state": "PENDING", "review_status": "CONFIRMED"}
        for i in range(36)]}
    source = tmp_path / "dataset.json"
    source.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "out"
    write_package(source, output)
    rows = json.loads((output / "review-rows.json").read_text(encoding="utf-8"))["cases"]
    assert len(rows) == 36
    assert all(r["review_state"] == "NEEDS_HUMAN_REVIEW" for r in rows)
    with pytest.raises(FileExistsError):
        write_package(source, output)
