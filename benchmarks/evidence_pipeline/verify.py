"""Audit frozen inputs, every scored stage, and D1/D2/D3 lexical routes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from benchmarks.evidence_pipeline.core import gold_coverage, limit_by_location
from benchmarks.evidence_pipeline.run import (
    OUT, P0_OUT, ROOT, assert_frozen_inputs, enrich_many,
)
from benchmarks.production_retrieval.core import score_layer
from benchmarks.production_retrieval.run import (
    load_inputs, read_config, read_jsonl, sha, write_json, write_jsonl,
)
from app.query_plan import build_query_plan
from app.evidence import evidence_excerpt
from app.store import Store


def main():
    dataset, original, docs, _ = load_inputs()
    config = read_config()
    assert_frozen_inputs(dataset, original, docs, config)
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    if sha(P0_OUT / "manifest.json") != manifest["source_p0_manifest_sha256"]:
        raise RuntimeError("P0 manifest changed")
    if sha(P0_OUT / "p0-baseline.jsonl") != manifest["source_p0_baseline_sha256"]:
        raise RuntimeError("P0 baseline changed")
    traces = read_jsonl(OUT / "query-traces.jsonl")
    baseline = read_jsonl(P0_OUT / "p0-baseline.jsonl")
    if [r["query_id"] for r in traces] != [q["id"] for q in dataset["queries"]]:
        raise RuntimeError("Query count/order changed")
    chunks = [{**c, "id": f"{docs[c['document_key']]['id']}:{c['ordinal']}"} for c in original]
    by_id = {c["id"]: c for c in chunks}
    doc_by_id = {d["id"]: key for key, d in docs.items()}
    store = Store(P0_OUT / "isolated_store")
    routes = []
    for query, trace, p0 in zip(dataset["queries"], traces, baseline):
        plan = build_query_plan(trace["question"])
        if plan.to_dict() != trace["query_plan"] or trace["gold_facts"] != query["facts"]:
            raise RuntimeError(f"Query/gold drift: {query['id']}")
        raw = store.search_chunks_exact([d["id"] for d in docs.values()], plan.lexical_terms, limit=100)
        raw = enrich_many(raw, by_id, docs)
        groups = {f"D{cap}": limit_by_location(raw, cap, 20) for cap in (1, 2, 3)}
        if [h["chunk_id"] for h in groups["D1"]] != [h["chunk_id"] for h in p0["substring_l0"]]:
            raise RuntimeError(f"D1 lexical/P0 mismatch: {query['id']}")
        for name, hits in groups.items():
            count = {}
            for hit in hits:
                count[hit["location"]] = count.get(hit["location"], 0) + 1
            if len(hits) > 20 or max(count.values(), default=0) > int(name[1:]):
                raise RuntimeError(f"Cap violated: {query['id']}/{name}")
            score = score_layer(query, hits, chunks, doc_by_id)["first_full_evidence_rank"]
            if score != trace["arms"][name]["ranks"]["dedup_lexical"]:
                raise RuntimeError(f"Lexical score drift: {query['id']}/{name}")
        routes.append({"query_id": query["id"], "raw_sql_top100": raw, "by_cap": groups})
        for name, arm in trace["arms"].items():
            pipeline = arm["pipeline"]
            if name.endswith("_A1_bypass"):
                base = trace["arms"][name.split("_A1")[0]]["pipeline"]
                if [h["chunk_id"] for h in pipeline["answer"]] != [h["chunk_id"] for h in base["selected"]]:
                    raise RuntimeError(f"A1 bypass drift: {query['id']}/{name}")
                continue
            for layer in ("reranked", "selected", "expanded", "answer"):
                actual = score_layer(query, pipeline[layer], chunks, doc_by_id)
                if actual != arm["metrics"]["scores"][layer]:
                    raise RuntimeError(f"Score drift: {query['id']}/{name}/{layer}")
            for hit in pipeline["answer"]:
                if evidence_excerpt(trace["question"], hit["text"]) != hit["text"]:
                    raise RuntimeError(f"Answer excerpt differs from scored text: {query['id']}/{name}")
            for layer in ("selected", "expanded", "answer"):
                if gold_coverage(query, pipeline[layer]) != arm["metrics"]["coverage"][layer]:
                    raise RuntimeError(f"Gold coverage drift: {query['id']}/{name}/{layer}")
            if name == "S6":
                for layer in ("reranked", "selected", "context", "expanded", "answer"):
                    if [h["chunk_id"] for h in pipeline[layer]] != [h["chunk_id"] for h in p0["P0"]["stages"][layer]]:
                        raise RuntimeError(f"S6/P0 stage mismatch: {query['id']}/{layer}")
                if pipeline["assessment"] != p0["P0"]["assessment"]:
                    raise RuntimeError(f"S6/P0 assessment mismatch: {query['id']}")
    write_jsonl(OUT / "lexical-routes.jsonl", routes)
    write_json(OUT / "verification.json", {"queries": len(traces), "chunks": len(chunks),
                                             "source_p0_hash_verified": True,
                                             "production_code_and_settings_frozen": True,
                                             "s6_p0_all_stage_and_assessment_parity": True,
                                             "d1_p0_lexical_parity": True,
                                             "d2_d3_page_caps_verified": True,
                                             "scores_and_gold_coverage_recomputed": True,
                                             "answer_excerpt_equals_scored_text": True,
                                             "lexical_routes_saved": True})
    print("PASS 14 queries, 2319 chunks, S6/P0 parity, D1/D2/D3 caps, stage scores")


if __name__ == "__main__":
    main()
