"""Schema invariants and semantic regressions for the v2 gold redesign."""
from benchmarks.evidence_annotation_v2.annotations import MAIN, STRESS
from benchmarks.evidence_annotation_v2.build import build_record, validate_record
from benchmarks.evidence_annotation_v2.score import fact_comparison, classification_one


def test_yes_no_contradiction_is_answerable():
    record = build_record("team-exception", {"case_id": "team-exception", "query": "所有团队成员都按完整分值计分，对吗？", "evidence_text": "除第一名外，其余扣减。", "gold_label": "NOT_SUPPORTED"}, "main")
    assert record["answerability"] == "FULL"
    assert record["relation_status"] == "CONTRADICTS_QUERY_PROPOSITION"
    assert record["expected_facts"][0]["answer"] == "NO"
    validate_record(record)


def test_csp_condition_only_is_none():
    record = build_record("csp-no-output", {"case_id": "csp-no-output", "query": "CSP达到300分如何计分？", "evidence_text": "达到300分以后计算", "gold_label": "PARTIAL"}, "main")
    assert record["answerability"] == "NONE"
    assert record["covered_facts"] == []
    assert [f["fact_id"] for f in record["missing_facts"]] == ["csp_output"]
    validate_record(record)


def test_table_column_gold_is_structured():
    record = build_record("table-column-order", {"case_id": "table-column-order", "query": "第二等次多少？", "evidence_text": "第二等次 第一等次；Ⅱ级甲等 0.05 0.06", "gold_label": "SUPPORTED"}, "stress")
    assert record["expected_facts"][0]["row"] == "Ⅱ级甲等"
    assert record["expected_facts"][0]["column"] == "第二等次"
    assert record["expected_facts"][0]["value"] == 0.05
    validate_record(record)


def test_all_legacy_cases_have_explicit_annotations():
    assert len(MAIN) == 31
    assert len(STRESS) == 5
    assert MAIN["gqa-mqa-swapped"]["main_metric_eligible"] is False
    assert STRESS["negated-mqa"]["answerability"] == "PARTIAL"


def test_table_value_error_is_not_hidden_by_full_status():
    record = build_record("table-column-order", {"case_id": "table-column-order", "query": "第二等次多少？", "evidence_text": "Ⅱ级甲等0.05", "gold_label": "SUPPORTED"}, "stress")
    comparison = fact_comparison(record, {"matched": ["Ⅱ级甲等", "第二等次"], "constraints": ["value=0.06"]})
    assert comparison["fact_extraction_correct"] is False


def test_v2_yes_no_relabel_changes_old_none_to_full_error():
    record = build_record("team-exception", {"case_id": "team-exception", "query": "所有成员都完整计分，对吗？", "evidence_text": "除第一名外都扣减", "gold_label": "NOT_SUPPORTED"}, "main")
    predictions = {(record["case_id"], "E4"): {"predicted_answerability": "NONE"}}
    result = classification_one([record], predictions, "E4")
    assert result["confusion"]["FULL"]["NONE"] == 1


def test_negated_mqa_extra_relation_is_extraction_error():
    record = build_record("negated-mqa", {"case_id": "negated-mqa", "query": "GQA和MQA区别？", "evidence_text": "MQA并不是所有Q共享，GQA每组共享", "gold_label": "NOT_SUPPORTED"}, "stress")
    comparison = fact_comparison(record, {"matched": ["GQA分组共享KV", "MQA所有Q共享一组KV"], "constraints": []})
    assert comparison["fact_extraction_correct"] is False
    assert any(f.get("reason") == "UNSUPPORTED_EXTRACTION" for f in comparison["fact_comparisons"])
