"""Read-only source-span and evidence inspection for the frozen chunking B/C run."""
from __future__ import annotations

import json
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from benchmarks.structure_chunking.core import _norm

SOURCE = ROOT / "test-results/structure-chunking-zh-2026-10-01-v2"
OUT = ROOT / "test-results/chunk-diagnosis-zh-2026-10-01"
TOKENIZER = ROOT / "data/models/models--Qdrant--bge-small-zh-v1.5/snapshots/46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59/tokenizer.json"
FOCUS = ("ai-q04", "ai-q21", "ai-q01", "ai-q19", "ai-q20", "policy-awards", "policy-team")


def legacy_spans(document_key: str, pages: list[dict], size: int = 400, overlap: int = 60) -> list[dict]:
    """Replay production boundaries and retain exact page-local character offsets."""
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("invalid chunk size or overlap")
    result = []
    for page in pages:
        source = page["text"]
        start = 0
        while start < len(source):
            end = min(start + size, len(source))
            if end < len(source):
                candidates = [source.rfind(mark, start + size // 2, end) for mark in ("\n", "。", "！", "？", ". ")]
                boundary = max(candidates)
                if boundary > start:
                    end = boundary + 1
            raw = source[start:end]
            value = raw.strip()
            if value:
                trimmed_start = start + len(raw) - len(raw.lstrip())
                trimmed_end = end - (len(raw) - len(raw.rstrip()))
                result.append({"id": f"B:{len(result)}", "document_key": document_key, "page": page["page"],
                               "start": trimmed_start, "end": trimmed_end, "text": value})
            if end == len(source):
                break
            start = max(start + 1, end - overlap)
    return result


def all_legacy_spans(corpus: dict[str, list[dict]], size: int = 400, overlap: int = 60) -> dict[str, dict]:
    result = {}
    for key, pages in corpus.items():
        for span in legacy_spans(key, pages, size, overlap):
            span["id"] = f"B:{len(result)}"
            result[span["id"]] = span
    return result


def fact_chunk_ids(document_key: str, fact: dict, chunks: list[dict]) -> list[str]:
    """A fact is intact only when every anchor occurs in one chunk on a gold page."""
    return [row["id"] for row in chunks
            if row["document_key"] == document_key
            and row["page"] in fact["source_pages"]
            and all(_norm(term) in _norm(row["text"]) for term in fact["all_terms"])]


def select_fact_evidence(query: dict, chunks: list[dict], ranked: list[dict]) -> dict[str, dict]:
    ranks = {row["chunk_id"]: row["rank"] for row in ranked}
    by_id = {row["id"]: row for row in chunks}
    chosen = {}
    for fact in query["facts"]:
        matches = fact_chunk_ids(query["document_key"], fact, chunks)
        if not matches:
            chosen[fact["id"]] = {"chunk_id": None, "rank": None, "matching_count": 0}
            continue
        best = min(matches, key=lambda cid: (ranks.get(cid, 10**9), by_id[cid]["ordinal"]))
        chosen[fact["id"]] = {"chunk_id": best, "rank": ranks.get(best), "matching_count": len(matches)}
    return chosen


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def _detail(row: dict, span: dict | None, blocks: dict[str, dict], anchor_tokens: int) -> dict:
    refs = [blocks[bid] for bid in row.get("source_block_ids", [])]
    return {"chunk_id": row["id"], "document_key": row["document_key"], "page": row["page"],
            "token_count": row["token_count"], "anchor_token_proxy": anchor_tokens,
            "anchor_token_share_proxy": round(anchor_tokens / row["token_count"], 4),
            "text": row["text"], "source_span": {"start": span["start"], "end": span["end"]} if span else None,
            "source_block_ids": row.get("source_block_ids", []),
            "source_blocks": [{"block_id": b["block_id"], "block_type": b["block_type"],
                               "source_start": b["source_start"], "source_end": b["source_end"],
                               "source_text": b["source_text"], "normalized_text": b["normalized_text"]}
                              for b in refs]}


def main():
    from tokenizers import Tokenizer

    dataset_path = ROOT / "docs/evaluations/structure-chunking-zh-v1.json"
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    if hashlib.sha256(dataset_path.read_bytes()).hexdigest() != manifest["dataset_sha256"]:
        raise RuntimeError("Frozen dataset changed")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    queries = {q["id"]: q for q in dataset["queries"]}
    pages = {key: _load_jsonl(SOURCE / f"snapshot/{key}-pages.jsonl") for key in ("ai_infra", "promotion")}
    blocks = {block["block_id"]: block for doc_pages in pages.values() for page in doc_pages for block in page["blocks"]}
    chunks = {variant: _load_jsonl(SOURCE / f"chunks/{variant}.jsonl") for variant in ("B", "C256", "C512")}
    retrieval = {variant: {r["query_id"]: r for r in _load_jsonl(SOURCE / f"retrieval/{variant}.jsonl")}
                 for variant in chunks}
    audited = json.loads((SOURCE / "audited-metrics.json").read_text(encoding="utf-8"))["variants"]
    spans = all_legacy_spans(pages)
    if len(spans) != len(chunks["B"]):
        raise RuntimeError("B source span count differs from frozen chunks")
    for chunk in chunks["B"]:
        span = spans[chunk["id"]]
        if (chunk["document_key"], chunk["page"], chunk["text"]) != (span["document_key"], span["page"], span["text"]):
            raise RuntimeError(f"B span mismatch: {chunk['id']}")
        page_source = pages[chunk["document_key"]][chunk["page"] - 1]["text"]
        if page_source[span["start"]:span["end"]] != chunk["text"]:
            raise RuntimeError(f"B source offset mismatch: {chunk['id']}")

    tokenizer = Tokenizer.from_file(str(TOKENIZER))
    cases = []
    for qid in FOCUS:
        query = queries[qid]
        anchor_text = "；".join(dict.fromkeys(term for fact in query["facts"] for term in fact["all_terms"]))
        anchor_tokens = len(tokenizer.encode(anchor_text, add_special_tokens=False).ids)
        case = {"query_id": qid, "question": query["question"], "document_key": query["document_key"],
                "gold_facts": query["facts"], "anchor_token_proxy_explanation":
                "Tokens in the preregistered gold anchor phrases divided by chunk tokens; a density proxy, not semantic share.",
                "variants": {}}
        for variant in (("B", "C256", "C512") if qid == "ai-q21" else ("B", "C512")):
            rows = chunks[variant]
            by_id = {r["id"]: r for r in rows}
            ranked = retrieval[variant][qid]["ranked"]
            selected = select_fact_evidence(query, rows, ranked)
            detail = {}
            for fact in query["facts"]:
                chosen = selected[fact["id"]]
                chunk = by_id.get(chosen["chunk_id"])
                detail[fact["id"]] = {**chosen, "chunk": _detail(chunk, spans.get(chunk["id"]), blocks, anchor_tokens)
                                       if chunk else None}
            scored = next(r for r in audited[variant]["per_query"] if r["query_id"] == qid)
            candidate_page_chunks = []
            if qid == "ai-q21" and variant == "C256":
                terms = [term for fact in query["facts"] for term in fact["all_terms"]]
                candidate_page_chunks = [
                    {"chunk_id": r["id"], "page": r["page"], "token_count": r["token_count"],
                     "matched_anchors": [t for t in terms if _norm(t) in _norm(r["text"])], "text": r["text"]}
                    for r in rows if r["document_key"] == query["document_key"]
                    and r["page"] in {p for fact in query["facts"] for p in fact["source_pages"]}
                    and any(_norm(t) in _norm(r["text"]) for t in terms)]
            case["variants"][variant] = {"first_full_evidence_rank": scored["first_full_evidence_rank"],
                                           "failure_type": scored["failure_type"], "fact_evidence": detail,
                                           "partial_page_chunks": candidate_page_chunks}
        cases.append(case)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Phase A: frozen B/C evidence chunks", "", "Full texts and page-local source offsets for the seven required cases.", ""]
    for case in cases:
        lines += [f"## {case['query_id']}：{case['question']}", "", f"Gold facts: `{json.dumps(case['gold_facts'], ensure_ascii=False)}`", ""]
        for variant, result in case["variants"].items():
            rank = result["first_full_evidence_rank"] or ">50 / no complete evidence unit"
            lines += [f"### {variant} · rank {rank} · {result['failure_type']}", ""]
            for fact_id, item in result["fact_evidence"].items():
                row = item["chunk"]
                if not row:
                    lines += [f"- `{fact_id}`: no complete chunk; {item['matching_count']} matches", ""]
                    continue
                lines += [f"**{fact_id}** — chunk `{row['chunk_id']}`, page {row['page']}, rank {item['rank'] or '>50'}, "
                          f"{row['token_count']} tokens, anchor proxy {row['anchor_token_share_proxy']:.1%}, "
                          f"source span {row['source_span']}, blocks `{row['source_block_ids']}`", "", "```text", row["text"], "```", ""]
            if result["partial_page_chunks"]:
                lines += ["Partial matches for C256:", ""]
                for row in result["partial_page_chunks"]:
                    lines += [f"- `{row['chunk_id']}` ({row['token_count']} tokens), anchors {row['matched_anchors']}", "", "```text", row["text"], "```", ""]
    (OUT / "cases.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Phase A artifacts: {OUT}; cases={len(cases)}; B source spans={len(spans)}")


if __name__ == "__main__":
    main()
