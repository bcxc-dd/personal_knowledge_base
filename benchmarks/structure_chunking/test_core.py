import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from benchmarks.structure_chunking.core import blockify_page, legacy_chunks, structure_chunks, score_query


class FakeTokenizer:
    def encode(self, value, add_special_tokens=True):
        return type("Encoded", (), {"ids": list(value) + (["CLS", "SEP"] if add_special_tokens else [])})()


def test_block_snapshot_preserves_source_spans_and_formula():
    source = "二、推荐条件\n第一段正文跨\n行结束。\ng_i =\n  0.2, x_i >= 300\n其中 x_i 是成绩。\n"
    blocks, _ = blockify_page("policy", 9, source, [])
    assert all(source[b["source_start"]:b["source_end"]] == b["source_text"] for b in blocks)
    assert any(b["block_type"] == "Heading" for b in blocks)
    assert any(b["block_type"] == "Equation" and b["verified"] is False for b in blocks)
    assert any(b["normalized_text"] == "第一段正文跨行结束。" for b in blocks)


def test_legacy_chunks_use_production_splitter_exactly():
    source = "甲" * 480 + "。" + "乙" * 180
    chunks = legacy_chunks("doc", [{"page": 1, "text": source}])
    from app.parsing import Section, split_sections
    expected = split_sections([Section(source, "第 1 页")], size=400, overlap=60)
    assert [(c["text"], c["page"]) for c in chunks] == [(c["text"], 1) for c in expected]


def test_structure_chunks_attach_heading_and_repeat_table_columns():
    source = ("二、推荐条件\n竞赛等级 第一等次 第二等次 第三等次\n"
              "Ⅱ级甲等 0.06 0.05 0.04\nⅡ级乙等 0.04 0.03 0.02\n")
    blocks, _ = blockify_page("policy", 9, source, [])
    chunks = structure_chunks("policy", [{"page": 9, "text": source, "blocks": blocks}], FakeTokenizer(), 70)
    assert not any(c["text"].strip() == "二、推荐条件" for c in chunks)
    assert any("第二等次：0.05" in c["text"] and "Ⅱ级甲等" in c["text"] for c in chunks)
    assert all(c["token_count"] <= 70 for c in chunks)
    assert all(c["source_block_ids"] for c in chunks)


def test_multi_fact_evidence_rank_and_failure_taxonomy():
    query = {"id": "q", "document_key": "doc", "facts": [
        {"id": "a", "all_terms": ["甲做了A"]},
        {"id": "b", "all_terms": ["乙做了B"]},
    ]}
    chunks = [{"id": "a", "document_key": "doc", "text": "甲做了A"},
              {"id": "b", "document_key": "doc", "text": "乙做了B"}]
    ranked = [chunks[0], chunks[1]]
    result = score_query(query, chunks, ranked, {"doc": "甲做了A。乙做了B。"})
    assert result["first_full_evidence_rank"] == 2
    assert result["evidence_at_1"] is False and result["evidence_at_3"] is True
    assert result["mrr"] == 0.5 and result["failure_type"] == "SUCCESS"
    missing = score_query(query, chunks[:1], chunks[:1], {"doc": "甲做了A。乙做了B。"})
    assert missing["failure_type"] == "CHUNKING_FAILURE"


def test_piecewise_formula_is_not_heading_or_table_prefix():
    source = ("二、推免综合评价分计算\n—9—\n其中 x_i 表示分数。\n"
              "g_i =\n0.2, x_i >= 300\n0.1 * (x_i / X_i), X_i > x_i\n"
              "竞赛等级 第一等次 第二等次 第三等次\nⅡ级甲等 0.06 0.05 0.04\n")
    blocks, _ = blockify_page("policy", 9, source, [])
    assert not any(b["block_type"] == "Heading" and b["normalized_text"].startswith("0.1") for b in blocks)
    assert any(b["block_type"] == "Equation" and "0.1 *" in b["source_text"] for b in blocks)
    chunks = structure_chunks("policy", [{"page": 9, "text": source, "blocks": blocks}], FakeTokenizer(), 100)
    table = next(c for c in chunks if "第二等次：0.05" in c["text"])
    assert "0.1 *" not in table["text"]
    assert "二、推免综合评价分计算" in table["text"]
    assert "—9—" not in "\n".join(c["text"] for c in chunks)


def test_chinese_chapter_heading_and_mixed_latin_section_heading():
    source = "第 1 章 初识 AI Infra\n前言介绍本章。\n1.1 AI Infra 为什么重要\n正文内容。\n"
    blocks, _ = blockify_page("book", 11, source, ["12 端边云协同"])
    assert [b["block_type"] for b in blocks] == ["Heading", "Paragraph", "Heading", "Paragraph"]
    assert blocks[-1]["section_path"] == ["第 1 章 初识 AI Infra", "1.1 AI Infra 为什么重要"]
    chunks = structure_chunks("book", [{"page": 11, "text": source, "blocks": blocks}], FakeTokenizer(), 100)
    assert all("12 端边云协同" not in c["text"] for c in chunks)


def test_unverified_formula_is_parsing_failure_even_if_glyphs_match():
    query = {"id": "formula", "document_key": "doc", "risk": "unverified_formula_structure",
             "facts": [{"id": "equation", "all_terms": ["B*", "bW", "2β"]}]}
    chunk = {"id": "c", "document_key": "doc", "text": "B* = bW Π\n2β"}
    score = score_query(query, [chunk], [chunk], {"doc": chunk["text"]})
    assert score["failure_type"] == "PARSING_FAILURE"
    assert score["first_full_evidence_rank"] is None
    assert score["mrr"] == 0
