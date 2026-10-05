from benchmarks.hybrid_retrieval.core import chinese_terms, BM25Index, rrf_rank


def test_chinese_terms_preserve_exact_acronyms_numbers_and_han_bigrams():
    terms = chinese_terms("Ⅱ级甲等，第二等次 0.05；MQA 的 KV 共享")
    assert {"ii", "级甲", "甲等", "第二", "二等", "等次", "0.05", "mqa", "kv", "共享"} <= set(terms)
    assert "0" not in terms and "05" not in terms


def test_bm25_ranks_exact_policy_value_above_generic_keyword_document():
    rows = [
        {"id": "generic", "text": "竞赛成绩按最高项计分。"},
        {"id": "answer", "text": "竞赛等级：Ⅱ级甲等；第二等次：0.05"},
        {"id": "other", "text": "竞赛等级：Ⅱ级乙等；第二等次：0.03"},
    ]
    index = BM25Index(rows)
    result = index.search("Ⅱ级甲等第二等次是多少分？", limit=3)
    assert [r["id"] for r in result][:2] == ["answer", "other"]
    assert result[0]["score"] > result[1]["score"]


def test_rrf_deduplicates_and_uses_stable_rank_ties():
    dense = ["a", "b", "c"]
    lexical = ["b", "a", "d"]
    assert rrf_rank(dense, lexical, top_n=2, limit=4, k=60) == ["a", "b"]
    assert rrf_rank(dense, lexical, top_n=3, limit=4, k=60) == ["a", "b", "c", "d"]
