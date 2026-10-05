import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from benchmarks.structure_chunking.diagnose import legacy_spans, all_legacy_spans, fact_chunk_ids, select_fact_evidence


def test_legacy_spans_recover_overlap_offsets_without_search_ambiguity():
    source = "ABCDEFGHIJKLM"
    spans = legacy_spans("doc", [{"page": 3, "text": source}], size=5, overlap=2)
    assert [(s["start"], s["end"], s["text"]) for s in spans] == [
        (0, 5, "ABCDE"), (3, 8, "DEFGH"), (6, 11, "GHIJK"), (9, 13, "JKLM")]
    assert all(source[s["start"]:s["end"]] == s["text"] for s in spans)


def test_fact_chunk_ids_require_all_terms_same_source_page_and_document():
    fact = {"id": "f", "source_pages": [9], "all_terms": ["第二等次", "Ⅱ级甲等", "0.05"]}
    rows = [
        {"id": "right", "document_key": "promotion", "page": 9, "text": "Ⅱ级甲等 第二等次 0.05"},
        {"id": "wrong_page", "document_key": "promotion", "page": 8, "text": "Ⅱ级甲等 第二等次 0.05"},
        {"id": "split", "document_key": "promotion", "page": 9, "text": "Ⅱ级甲等 第二等次"},
        {"id": "wrong_doc", "document_key": "book", "page": 9, "text": "Ⅱ级甲等 第二等次 0.05"},
    ]
    assert fact_chunk_ids("promotion", fact, rows) == ["right"]


def test_select_fact_evidence_uses_ranked_match_then_full_corpus_fallback():
    query = {"document_key": "book", "facts": [
        {"id": "a", "source_pages": [2], "all_terms": ["甲定义"]},
        {"id": "b", "source_pages": [2], "all_terms": ["乙定义"]},
    ]}
    chunks = [{"id": "first", "document_key": "book", "page": 2, "text": "甲定义", "ordinal": 0},
              {"id": "ranked", "document_key": "book", "page": 2, "text": "甲定义", "ordinal": 1},
              {"id": "outside", "document_key": "book", "page": 2, "text": "乙定义", "ordinal": 2}]
    ranked = [{"chunk_id": "ranked", "rank": 7}]
    chosen = select_fact_evidence(query, chunks, ranked)
    assert chosen["a"] == {"chunk_id": "ranked", "rank": 7, "matching_count": 2}
    assert chosen["b"] == {"chunk_id": "outside", "rank": None, "matching_count": 1}


def test_all_legacy_spans_use_global_ids_across_documents():
    corpus = {"book": [{"page": 1, "text": "ABCDE"}], "policy": [{"page": 1, "text": "FGHIJ"}]}
    spans = all_legacy_spans(corpus, size=5, overlap=2)
    assert list(spans) == ["B:0", "B:1"]
    assert spans["B:1"]["document_key"] == "policy"
