"""Contracts for the isolated production retrieval experiment."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from benchmarks.production_retrieval.core import (
    existing_lexical_tokens, score_layer, stage_event, source_page,
)
from app.engine import diverse_lexical_hits


def test_existing_tokenizer_is_distinct_from_chinese_ngram():
    from benchmarks.hybrid_retrieval.core import chinese_terms

    text = "推免绩点需要达到3.2，MQA共用KV"
    assert existing_lexical_tokens(text)
    assert existing_lexical_tokens(text) != chinese_terms(text)


def test_source_page_requires_production_location_format():
    assert source_page("第 9 页") == 9
    assert source_page("第 24 页") == 24
    assert source_page("bad") is None


def test_layer_scoring_respects_page_and_fact_group():
    query = {"document_key": "promotion", "facts": [{"id": "x", "source_pages": [9],
             "all_terms": ["团队", "最低为0分"]}]}
    corpus = [{"id": "B:0", "document_key": "promotion", "page": 9, "text": "团队最低为0分"}]
    wrong_page = [{"chunk_id": "B:0", "document_id": "doc", "location": "第 8 页", "text": "团队最低为0分"}]
    good = [{**wrong_page[0], "location": "第 9 页"}]
    assert score_layer(query, wrong_page, corpus, {"doc": "promotion"})["first_full_evidence_rank"] is None
    assert score_layer(query, good, corpus, {"doc": "promotion"})["first_full_evidence_rank"] == 1


def test_stage_event_detects_rank_and_filter_changes():
    assert stage_event(12, 3, "FUSION") == "FUSION_RESCUE"
    assert stage_event(2, 18, "RERANK") == "RERANK_DEGRADE"
    assert stage_event(2, None, "ASSESSMENT") == "EVIDENCE_FILTER_DROP"
    assert stage_event(None, 4, "CONTEXT") == "CONTEXT_RESCUE"


def test_location_dedup_can_remove_answer_bearing_chunk_on_same_page():
    query = {"document_key": "ai", "facts": [{"id": "comparison", "source_pages": [44],
             "all_terms": ["GQA每组共享", "MQA所有头共用"]}]}
    corpus = [{"id": "doc:1", "document_key": "ai", "page": 44, "text": "GQA每组共享"},
              {"id": "doc:2", "document_key": "ai", "page": 44,
               "text": "GQA每组共享，MQA所有头共用"}]
    raw = [{"chunk_id": row["id"], "document_id": "doc", "location": "第 44 页",
            "text": row["text"]} for row in corpus]
    selected = diverse_lexical_hits(raw, 20)
    assert [r["chunk_id"] for r in selected] == ["doc:1"]
    assert score_layer(query, selected, corpus, {"doc": "ai"})["first_full_evidence_rank"] is None
    assert score_layer(query, raw, corpus, {"doc": "ai"})["first_full_evidence_rank"] == 2
