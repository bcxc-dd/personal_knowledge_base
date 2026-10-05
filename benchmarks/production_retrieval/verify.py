"""Audit frozen outputs and final answer-context text for the isolated run."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.evidence import evidence_excerpt
from app.store import Store
from benchmarks.production_retrieval.run import DATASET, OUT, SOURCE, load_inputs, read_jsonl, verify_sql_route, write_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    dataset, chunks, docs, _ = load_inputs()
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_sha256"] == sha(DATASET)
    assert manifest["b_chunks_sha256"] == sha(SOURCE / "chunks/B.jsonl")
    store = Store(OUT / "isolated_store")
    verify_sql_route(store, docs, dataset["queries"])
    p0 = read_jsonl(OUT / "p0-baseline.jsonl")
    traces = read_jsonl(OUT / "query-traces.jsonl")
    assert len(p0) == len(traces) == len(dataset["queries"]) == 14
    assert [r["query_id"] for r in p0] == [r["query_id"] for r in traces]
    text_by_id = {row["id"]: row["text"] for doc in docs.values() for row in store.chunks(doc["id"])}
    allowed_docs = {doc["id"] for doc in docs.values()}
    excerpt_changes = []
    formula_status = []
    for saved, row in zip(p0, traces):
        assert saved["P0"] == row["arms"]["P0"] == row["arms"]["P5"]
        assert row["arms"]["P0"]["stages"]["fused"] == row["arms"]["P3_fusion_only"]["stages"]["fused"]
        assert row["arms"]["P0"]["stages"]["reranked"] == row["arms"]["P4_plus_reranker"]["stages"]["reranked"]
        for route in row["routes"].values():
            assert all(hit["document_id"] in allowed_docs and hit["chunk_id"] in text_by_id for hit in route)
        for arm_name, arm in row["arms"].items():
            if "answer" not in arm["stages"]:
                continue
            selected = {h["chunk_id"] for h in arm["stages"]["expanded"]}
            answer = {h["chunk_id"] for h in arm["stages"]["answer"]}
            assert answer <= selected
            if row["query_id"] == "ai-batch-formula":
                formula_status.append(arm["scores"]["answer"]["failure_type"])
            for hit in arm["stages"]["answer"]:
                original = text_by_id[hit["chunk_id"]]
                excerpt = evidence_excerpt(row["question"], original)
                if excerpt != original:
                    excerpt_changes.append({"query_id": row["query_id"], "arm": arm_name,
                                            "chunk_id": hit["chunk_id"], "source_len": len(original),
                                            "prompt_len": len(excerpt)})
    assert all(status == "PARSING_FAILURE" for status in formula_status)
    if excerpt_changes:
        raise RuntimeError("Answer context excerpts differ; rescore the exact prompt evidence before reporting")
    write_json(OUT / "verification.json", {"queries": 14, "chinese_chunks": len(chunks),
                                             "p0_full_replay": True, "sql_top100_parity": True,
                                             "no_out_of_scope_candidate": True,
                                             "p3_p4_stage_parity": True,
                                             "formula_parser_failure_arms": len(formula_status),
                                             "answer_excerpt_changes": excerpt_changes,
                                             "benchmark_code_sha256": {name: sha(ROOT / f"benchmarks/production_retrieval/{name}.py")
                                                                       for name in ("core", "run", "measure", "verify")}})
    print("PASS 14 queries, 2319 scoped chunks, SQL/P0/P3/P4 parity, 0 answer excerpt changes")


if __name__ == "__main__":
    main()
