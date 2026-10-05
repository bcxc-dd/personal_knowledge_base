"""Behavior checks for the isolated evidence-pipeline benchmark helpers."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from benchmarks.evidence_pipeline.core import (
    classify_failure, diversity, filter_effect, gold_coverage, limit_by_location,
)


def test_page_cap_preserves_score_order_and_distinct_chunks():
    raw = [
        {"chunk_id": "a", "location": "第 9 页", "lexical_score": 3},
        {"chunk_id": "a", "location": "第 9 页", "lexical_score": 3},
        {"chunk_id": "b", "location": "第 9 页", "lexical_score": 2},
        {"chunk_id": "c", "location": "第 9 页", "lexical_score": 1},
        {"chunk_id": "d", "location": "第 2 页", "lexical_score": 1},
    ]
    assert [x["chunk_id"] for x in limit_by_location(raw, 1, 20)] == ["a", "d"]
    assert [x["chunk_id"] for x in limit_by_location(raw, 2, 20)] == ["a", "b", "d"]
    assert [x["chunk_id"] for x in limit_by_location(raw, 3, 3)] == ["a", "b", "c"]


def test_gold_coverage_requires_correct_document_page_and_all_terms():
    query = {"document_key": "policy", "facts": [
        {"id": "rule", "source_pages": [9], "all_terms": ["团队", "最低为0分"]},
        {"id": "score", "source_pages": [9], "all_terms": ["Ⅱ级甲等", "0.05"]},
    ]}
    hits = [
        {"document_key": "policy", "page": 8, "text": "团队最低为0分"},
        {"document_key": "other", "page": 9, "text": "Ⅱ级甲等0.05"},
        {"document_key": "policy", "page": 9, "text": "团队，最低为0 分"},
    ]
    assert gold_coverage(query, hits) == {"found": ["rule"], "fraction": 0.5,
                                          "fact_bearing_hits": 1, "hit_precision": 1 / 3}


def test_failure_taxonomy_keeps_distinct_last_loss_stage():
    assert classify_failure(False, None, None, None, None, None, None, None) == "PARSING_FAILURE"
    assert classify_failure(True, 2, None, None, None, None, None, None) == "LOCATION_DEDUP_DROP"
    assert classify_failure(True, None, None, 16, 8, None, None, None) == "SELECTION_CUTOFF"
    assert classify_failure(True, None, None, 16, 1, 1, 1, None) == "EVIDENCE_FILTER_DROP"
    assert classify_failure(True, None, None, None, None, None, None, None) == "RETRIEVAL_FAILURE"
    assert classify_failure(True, None, None, 3, 18, None, None, None) == "RANKING_FAILURE"
    assert classify_failure(True, None, None, 3, 3, 3, 3, 3) == "SUCCESS"


def test_filter_rescue_requires_removal_of_non_gold_text_without_losing_facts():
    query = {"document_key": "policy", "facts": [
        {"id": "rule", "source_pages": [9], "all_terms": ["团队", "最低为0分"]},
    ]}
    selected = [{"document_key": "policy", "page": 9, "text": "团队最低为0分"},
                {"document_key": "policy", "page": 8, "text": "无关材料"}]
    assert filter_effect(query, selected, selected[:1]) == "FILTER_RESCUE"
    assert filter_effect(query, selected, []) == "FILTER_DROP"
    assert filter_effect(query, selected, selected) == "FILTER_NEUTRAL"


def test_diversity_reports_same_page_concentration_and_near_duplicates():
    hits = [{"location": "第 9 页", "text": "团队成员扣减0.01分"},
            {"location": "第 9 页", "text": "团队成员扣减0.01分"},
            {"location": "第 2 页", "text": "绩点门槛3.2"}]
    result = diversity(hits)
    assert result == {"candidate_count": 3, "unique_pages": 2,
                      "same_page_chunk_ratio": 1 / 3, "max_chunks_per_page": 2,
                      "same_page_near_duplicate_pairs": 1}
