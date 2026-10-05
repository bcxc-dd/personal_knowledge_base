"""Controlled H0/H1/H2 comparison on the frozen Chinese production B chunks."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from benchmarks.hybrid_retrieval.core import BM25Index, chinese_terms, rrf_rank
from benchmarks.structure_chunking.core import score_query

SOURCE = ROOT / "test-results/structure-chunking-zh-2026-10-01-v2"
OUT = ROOT / "test-results/hybrid-retrieval-zh-2026-10-01"
DATASET = ROOT / "docs/evaluations/structure-chunking-zh-v1.json"

CATEGORIES = {
    "ai-q01": "principle_explanation", "ai-q02": "principle_explanation", "ai-q03": "precise_concept",
    "ai-q04": "precise_concept", "ai-q19": "acronym_term", "ai-q20": "acronym_term",
    "ai-q21": "acronym_term", "ai-figure": "numeric_figure", "ai-batch-formula": "parser_limited",
    "policy-gpa": "policy_numeric", "policy-awards": "policy_clause", "policy-team": "policy_clause",
    "policy-table": "policy_numeric", "policy-csp": "policy_numeric",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate(rows: list[dict]) -> dict:
    return {"n": len(rows), "mrr": sum(r["mrr"] for r in rows) / len(rows),
            **{f"evidence_recall_at_{k}": sum(r[f"evidence_at_{k}"] for r in rows) / len(rows)
               for k in (1, 3, 5, 10, 20, 50)},
            "failure_counts": {kind: sum(r["failure_type"] == kind for r in rows)
                               for kind in ("SUCCESS", "EVIDENCE_ABSENT", "PARSING_FAILURE", "CHUNKING_FAILURE",
                                            "RETRIEVAL_FAILURE", "RANKING_FAILURE", "GENERATION_FAILURE")}}


def main():
    if (OUT / "metrics.json").exists():
        raise RuntimeError(f"Completed output already exists: {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    frozen_manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    if sha(DATASET) != frozen_manifest["dataset_sha256"]:
        raise RuntimeError("Frozen question set changed")
    if any(not row["exact_match"] for row in frozen_manifest["production_chunk_parity"].values()):
        raise RuntimeError("Frozen B chunks did not match production baseline")
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    queries = dataset["queries"]
    chunks = load_jsonl(SOURCE / "chunks/B.jsonl")
    if len(chunks) != 2319 or len({r["id"] for r in chunks}) != len(chunks):
        raise RuntimeError("Frozen B chunk count/IDs changed")
    by_id = {r["id"]: r for r in chunks}
    dense = {r["query_id"]: r for r in load_jsonl(SOURCE / "retrieval/B.jsonl")}
    audited = json.loads((SOURCE / "audited-metrics.json").read_text(encoding="utf-8"))["variants"]["B"]
    source_text = {key: "\n".join(p["text"] for p in load_jsonl(SOURCE / f"snapshot/{key}-pages.jsonl"))
                   for key in ("ai_infra", "promotion")}
    for query in queries:
        rows = dense[query["id"]]["ranked"]
        if len(rows) != 50 or any(row["text"] != by_id[row["chunk_id"]]["text"] for row in rows):
            raise RuntimeError(f"Frozen dense result changed: {query['id']}")

    tracemalloc.start()
    built_at = time.perf_counter()
    index = BM25Index(chunks, k1=1.2, b=0.75)
    build_seconds = time.perf_counter() - built_at
    _, peak_python_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    stored_at = time.perf_counter()
    index_path = OUT / "bm25-index.json.gz"
    with gzip.open(index_path, "wt", encoding="utf-8", compresslevel=6) as out:
        json.dump(index.serializable(), out, ensure_ascii=False, separators=(",", ":"))
    serialize_seconds = time.perf_counter() - stored_at

    variant_rows = {key: [] for key in ("H0_dense", "H1_bm25", "H2_rrf20", "H2_rrf50")}
    query_details = []
    timings = {key: [] for key in ("bm25_query_seconds", "rrf20_seconds", "rrf50_seconds")}
    for query in queries:
        qid = query["id"]
        dense_result = dense[qid]["ranked"]
        dense_ids = [row["chunk_id"] for row in dense_result]
        started = time.perf_counter()
        lexical_result = index.search(query["question"], limit=50)
        timings["bm25_query_seconds"].append(time.perf_counter() - started)
        lexical_ids = [row["id"] for row in lexical_result]
        started = time.perf_counter()
        rrf20_ids = rrf_rank(dense_ids, lexical_ids, top_n=20, limit=50, k=60)
        timings["rrf20_seconds"].append(time.perf_counter() - started)
        started = time.perf_counter()
        rrf50_ids = rrf_rank(dense_ids, lexical_ids, top_n=50, limit=50, k=60)
        timings["rrf50_seconds"].append(time.perf_counter() - started)

        lists = {"H0_dense": dense_ids, "H1_bm25": lexical_ids,
                 "H2_rrf20": rrf20_ids, "H2_rrf50": rrf50_ids}
        scores = {}
        ranked_output = {}
        for variant, ids in lists.items():
            ranked = [{**by_id[cid], "rank": rank} for rank, cid in enumerate(ids, 1)]
            score = score_query(query, chunks, ranked, source_text)
            scores[variant] = score
            variant_rows[variant].append({"query_id": qid, "category": CATEGORIES[qid], **score})
            ranked_output[variant] = [
                {"rank": rank, "chunk_id": cid, "document_key": by_id[cid]["document_key"],
                 "page": by_id[cid]["page"], "text": by_id[cid]["text"],
                 "score": next((r["score"] for r in lexical_result if r["id"] == cid), None) if variant == "H1_bm25"
                 else next((r["distance"] for r in dense_result if r["chunk_id"] == cid), None) if variant == "H0_dense" else None}
                for rank, cid in enumerate(ids, 1)]
        frozen = next(row for row in audited["per_query"] if row["query_id"] == qid)
        if scores["H0_dense"]["first_full_evidence_rank"] != frozen["first_full_evidence_rank"]:
            raise RuntimeError(f"H0 rank drift: {qid}")
        query_details.append({"query_id": qid, "question": query["question"], "category": CATEGORIES[qid],
                              "query_terms": sorted(set(chinese_terms(query["question"]))),
                              "dense_unique_candidate_count": len(set(dense_ids) - set(lexical_ids)),
                              "bm25_unique_candidate_count": len(set(lexical_ids) - set(dense_ids)),
                              "bm25_only_evidence": bool(scores["H1_bm25"]["evidence_at_50"] and not scores["H0_dense"]["evidence_at_50"]),
                              "dense_only_evidence": bool(scores["H0_dense"]["evidence_at_50"] and not scores["H1_bm25"]["evidence_at_50"]),
                              "scores": scores, "ranked": ranked_output})
        print(f"QUERY {qid} H0={scores['H0_dense']['first_full_evidence_rank']} H1={scores['H1_bm25']['first_full_evidence_rank']} H2-20={scores['H2_rrf20']['first_full_evidence_rank']} H2-50={scores['H2_rrf50']['first_full_evidence_rank']}", flush=True)

    with (OUT / "query-results.jsonl").open("w", encoding="utf-8") as out:
        for row in query_details:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    primary = {key: aggregate([row for row in rows if row["query_id"] != "ai-batch-formula"])
               for key, rows in variant_rows.items()}
    all14 = {key: aggregate(rows) for key, rows in variant_rows.items()}
    by_query = {row["query_id"]: row for row in query_details}
    rescued = [qid for qid, row in by_query.items() if qid != "ai-batch-formula"
               and not row["scores"]["H0_dense"]["evidence_at_5"]
               and row["scores"]["H2_rrf50"]["evidence_at_5"]]
    degraded = [qid for qid, row in by_query.items() if qid != "ai-batch-formula"
                and row["scores"]["H0_dense"]["evidence_at_5"]
                and not row["scores"]["H2_rrf50"]["evidence_at_5"]]
    metrics = {"answerable_13": primary, "all_14": all14,
               "per_query": [{"query_id": row["query_id"], "question": row["question"],
                              "category": row["category"], "dense_unique_candidate_count": row["dense_unique_candidate_count"],
                              "bm25_unique_candidate_count": row["bm25_unique_candidate_count"],
                              "bm25_only_evidence": row["bm25_only_evidence"], "dense_only_evidence": row["dense_only_evidence"],
                              "ranks": {key: value["first_full_evidence_rank"] for key, value in row["scores"].items()},
                              "failure_types": {key: value["failure_type"] for key, value in row["scores"].items()}}
                             for row in query_details],
               "rescued_top5_rrf50": rescued, "degraded_top5_rrf50": degraded,
               "bm25_only_evidence_queries": [r["query_id"] for r in query_details if r["bm25_only_evidence"]],
               "dense_only_evidence_queries": [r["query_id"] for r in query_details if r["dense_only_evidence"]],
               "resource": {"bm25_build_seconds": build_seconds, "bm25_serialize_seconds": serialize_seconds,
                            "bm25_index_bytes_gzip": index_path.stat().st_size, "bm25_peak_python_alloc_bytes": peak_python_bytes,
                            "bm25_query_seconds": timings["bm25_query_seconds"],
                            "rrf20_seconds": timings["rrf20_seconds"], "rrf50_seconds": timings["rrf50_seconds"],
                            "frozen_dense_retrieval_seconds_14_queries":
                            json.loads((SOURCE / "metrics.json").read_text(encoding="utf-8"))["B"]["retrieval_seconds"]}}
    (OUT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps({"dataset_sha256": sha(DATASET), "b_chunks_sha256": sha(SOURCE / "chunks/B.jsonl"),
                                                       "dense_results_sha256": sha(SOURCE / "retrieval/B.jsonl"),
                                                       "bm25_code_sha256": sha(ROOT / "benchmarks/hybrid_retrieval/core.py"),
                                                       "corpus_chunks": len(chunks), "query_count": len(queries),
                                                       "config": {"bm25_k1": 1.2, "bm25_b": 0.75,
                                                                  "tokenization": "NFKC+Han unigram/bigram+whole Latin identifiers+decimal numbers",
                                                                  "rrf_k": 60, "rrf_top_n": [20, 50],
                                                                  "dense": "frozen BGE-small-zh-v1.5 + Chroma cosine Top-50",
                                                                  "formula_risk": "PARSING_FAILURE"}},
                                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DONE {OUT}", flush=True)


if __name__ == "__main__":
    main()
