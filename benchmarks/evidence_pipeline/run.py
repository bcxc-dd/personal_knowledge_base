"""Isolated S/A/D evidence pipeline experiments on a frozen production P0."""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.context import chapter_context_hits, condition_context_hits, sequence_gap_context_hits
from app.engine import select_evidence_items
from app.evidence import (
    _roster_question, _substantive, _supports, _topic_terms,
    assess_evidence, is_eligibility_question, split_core_subquestions,
)
from app.query_plan import build_query_plan
from app.reranker import Reranker
from app.store import Store
from app.terms import lexical_terms
from benchmarks.evidence_pipeline.core import (
    classify_failure, diversity, filter_effect, gold_coverage, limit_by_location,
)
from benchmarks.production_retrieval.core import score_layer
from benchmarks.production_retrieval.run import (
    OUT as P0_OUT, ROOT, category, complete_pipeline, hit_ids, load_inputs,
    normalize_question, read_config, read_jsonl, sha, write_json, write_jsonl,
)

OUT = ROOT / "test-results/evidence-pipeline-2026-10-01-v1"
PRODUCTION_FILES = ("engine", "retrieval", "reranker", "evidence", "context", "store", "query_plan", "terms")
LIMITS = (6, 8, 10)
PAGE_CAPS = (1, 2, 3)


def assert_frozen_inputs(dataset, chunks, docs, config):
    manifest = json.loads((P0_OUT / "manifest.json").read_text(encoding="utf-8"))
    if sha(ROOT / "docs/evaluations/structure-chunking-zh-v1.json") != manifest["dataset_sha256"]:
        raise RuntimeError("Frozen query set changed")
    if sha(ROOT / "test-results/structure-chunking-zh-2026-10-01-v2/chunks/B.jsonl") != manifest["b_chunks_sha256"]:
        raise RuntimeError("Frozen B chunks changed")
    for name in PRODUCTION_FILES:
        if sha(ROOT / f"backend/app/{name}.py") != manifest["production_code_sha256"][name]:
            raise RuntimeError(f"Production retrieval code changed since P0: {name}")
    for key, doc in docs.items():
        if doc["hash"] != manifest["source_pdf_sha256"][key]:
            raise RuntimeError(f"Source PDF changed: {key}")
    for key, value in manifest["settings"].items():
        if config[key] != value:
            raise RuntimeError(f"Retrieval setting changed: {key}")
    if len(dataset["queries"]) != 14 or len(chunks) != 2319:
        raise RuntimeError("Expected frozen 14 questions and 2319 chunks")


def enrich(trace_hit, by_id, docs):
    chunk = by_id[trace_hit["chunk_id"]]
    doc = docs[chunk["document_key"]]
    return {**trace_hit, "text": chunk["text"], "name": doc["name"],
            "document_id": doc["id"], "document_key": chunk["document_key"],
            "page": chunk["page"], "token_count": chunk["token_count"]}


def enrich_many(hits, by_id, docs):
    return [enrich(hit, by_id, docs) for hit in hits]


def selection_pipeline(question, plan, ordered, limit, store):
    # These are the production functions. Upstream CUDA ranking is frozen.
    selected = select_evidence_items(question, copy.deepcopy(ordered), limit)
    context = [*chapter_context_hits(question, selected, store),
               *condition_context_hits(question, selected, store)]
    context.extend(sequence_gap_context_hits(question, selected, store, context))
    expanded = [*selected, *context]
    assessment_input = [{**hit, "id": i + 1} for i, hit in enumerate(expanded)]
    assessed = assess_evidence(question, assessment_input, plan)
    retained = set(assessed.evidence_chunk_ids)
    return {"reranked": ordered, "selected": selected, "context": context,
            "expanded": expanded, "answer": [hit for hit in expanded if hit["chunk_id"] in retained],
            "assessment_input": assessment_input, "assessment": assessed.to_dict()}


def assess_trace(question, plan, pipeline):
    hits = pipeline["assessment_input"]
    parts = split_core_subquestions(question)
    terms = list(_topic_terms(question))
    generic_terms = {part: list(lexical_terms(part)) for part in parts}
    branch = ("requirement" if plan.intent in {"requirement_lookup", "numeric_requirement_lookup"}
              else "roster" if _roster_question(question)
              else "eligibility" if is_eligibility_question(question) else "generic")
    per_hit = []
    retained = set(pipeline["assessment"]["evidence_chunk_ids"])
    for hit in hits:
        body = hit["text"]
        checks = [{"part": part, "supports": _supports(part, hit),
                   "literal_terms": generic_terms[part],
                   "literal_matches": [term for term in generic_terms[part] if term.casefold() in body.casefold()]}
                  for part in parts]
        if hit["chunk_id"] in retained:
            reason = "RETAINED"
        elif branch == "generic" and not _substantive(body):
            reason = "NON_SUBSTANTIVE_TEXT"
        elif branch == "generic" and all(not item["literal_matches"] for item in checks):
            reason = "NO_LITERAL_QUERY_TERM_MATCH"
        elif branch == "generic" and not any(item["supports"] for item in checks):
            reason = "GENERIC_SUPPORT_RULE_FALSE"
        else:
            reason = "NOT_RETAINED_BY_PRODUCTION_BRANCH"
        per_hit.append({"chunk_id": hit["chunk_id"], "source": hit["name"],
                        "page": hit["page"], "substantive": _substantive(body),
                        "topic_terms": terms, "part_checks": checks,
                        "retained": hit["chunk_id"] in retained,
                        "benchmark_derived_reason": reason})
    return {"production_branch": branch, "split_core_subquestions": list(parts),
            "selected_evidence_ids": hit_ids(pipeline["selected"]),
            "expanded_evidence_ids": hit_ids(pipeline["expanded"]),
            "assessment_input": hits, "assessment_output": pipeline["assessment"],
            "retained_evidence_ids": hit_ids(pipeline["answer"]),
            "rejected_evidence_ids": [h["chunk_id"] for h in hits if h["chunk_id"] not in retained],
            "per_hit_diagnostic": per_hit,
            "reason_note": "benchmark-derived; production EvidenceAssessment has no per-hit rejection reason"}


def score_pipeline(query, pipeline, chunks, doc_by_id, token_counts):
    layers = {name: score_layer(query, pipeline[name], chunks, doc_by_id)
              for name in ("reranked", "selected", "expanded", "answer")}
    coverage = {name: gold_coverage(query, pipeline[name])
                for name in ("selected", "expanded", "answer")}
    selected = pipeline["selected"]
    return {"scores": layers, "coverage": coverage,
            "selected_chunks": len(selected),
            "selected_tokens": sum(token_counts[h["chunk_id"]] for h in selected),
            "filter_event": filter_effect(query, pipeline["selected"], pipeline["answer"]),
            "assessment_status": pipeline["assessment"]["status"]}


def aggregate(traces, arm):
    rows = [row["arms"][arm]["metrics"] for row in traces if row["query_id"] != "ai-batch-formula"]
    result = {"n": len(rows)}
    for stage in ("reranked", "selected", "answer"):
        scores = [row["scores"][stage] for row in rows]
        result[stage] = {"mrr": sum(s["mrr"] for s in scores) / len(scores),
                         **{f"recall_at_{k}": sum(s[f"evidence_at_{k}"] for s in scores) / len(scores)
                            for k in (1, 3, 5, 10)}}
    result["average_selected_chunks"] = sum(row["selected_chunks"] for row in rows) / len(rows)
    result["average_selected_tokens"] = sum(row["selected_tokens"] for row in rows) / len(rows)
    result["average_selected_gold_fact_coverage"] = sum(row["coverage"]["selected"]["fraction"] for row in rows) / len(rows)
    result["average_final_gold_fact_coverage"] = sum(row["coverage"]["answer"]["fraction"] for row in rows) / len(rows)
    result["filter_events"] = dict(Counter(row["filter_event"] for row in rows))
    result["assessment_statuses"] = dict(Counter(row["assessment_status"] for row in rows))
    return result


def main():
    if (OUT / "metrics.json").exists():
        raise RuntimeError("Completed evidence benchmark exists; refusing overwrite")
    OUT.mkdir(parents=True, exist_ok=True)
    dataset, original_chunks, docs, _ = load_inputs()
    config = read_config()
    assert_frozen_inputs(dataset, original_chunks, docs, config)
    chunks = [{**c, "id": f"{docs[c['document_key']]['id']}:{c['ordinal']}"} for c in original_chunks]
    by_id = {chunk["id"]: chunk for chunk in chunks}
    token_counts = {cid: c["token_count"] for cid, c in by_id.items()}
    doc_by_id = {d["id"]: key for key, d in docs.items()}
    store = Store(P0_OUT / "isolated_store")
    reranker = Reranker(ROOT / "data/models")
    prior = read_jsonl(P0_OUT / "p0-baseline.jsonl")
    if [r["query_id"] for r in prior] != [q["id"] for q in dataset["queries"]]:
        raise RuntimeError("P0 rows no longer match query set")
    traces = []
    for query, baseline in zip(dataset["queries"], prior):
        question = normalize_question(query["question"])
        plan = build_query_plan(question)
        if plan.to_dict() != baseline["query_plan"]:
            raise RuntimeError(f"QueryPlan drift: {query['id']}")
        ordered = enrich_many(baseline["P0"]["stages"]["reranked"], by_id, docs)
        fused = enrich_many(baseline["P0"]["stages"]["fused"], by_id, docs)
        vector = enrich_many(baseline["vector"], by_id, docs)
        raw = store.search_chunks_exact([d["id"] for d in docs.values()], plan.lexical_terms, limit=100)
        raw = enrich_many(raw, by_id, docs)
        if hit_ids(limit_by_location(raw, 1, 20)) != [h["chunk_id"] for h in baseline["substring_l0"]]:
            raise RuntimeError(f"D1 lexical differs from P0: {query['id']}")
        arms = {}
        for limit in LIMITS:
            pipeline = selection_pipeline(question, plan, ordered, limit, store)
            metrics = score_pipeline(query, pipeline, chunks, doc_by_id, token_counts)
            if limit == 6:
                for layer in ("reranked", "selected", "context", "expanded", "answer"):
                    if hit_ids(pipeline[layer]) != [h["chunk_id"] for h in baseline["P0"]["stages"][layer]]:
                        raise RuntimeError(f"S6 stage differs from P0: {query['id']}/{layer}")
                if pipeline["assessment"] != baseline["P0"]["assessment"]:
                    raise RuntimeError(f"S6 assessment differs from P0: {query['id']}")
            name = f"S{limit}"
            arms[name] = {"pipeline": pipeline, "metrics": metrics,
                          "assessment_trace": assess_trace(question, plan, pipeline)}
            # A1 is the requested benchmark bypass. This frozen query set has no context expansion.
            bypass = {**pipeline, "answer": pipeline["selected"]}
            arms[name + "_A1_bypass"] = {"pipeline": {"selected": pipeline["selected"],
                                                        "answer": pipeline["selected"]},
                                          "metrics": score_pipeline(query, bypass, chunks, doc_by_id, token_counts)}
        for cap in PAGE_CAPS:
            lexical = limit_by_location(raw, cap, 20)
            name = f"D{cap}"
            if cap == 1:
                pipeline = {"fused": fused, **arms["S6"]["pipeline"]}
            else:
                pipeline = complete_pipeline(question, plan, copy.deepcopy(vector), copy.deepcopy(lexical),
                                             store, reranker, config)
                for layer in ("fused", "reranked", "selected", "context", "expanded", "answer"):
                    pipeline[layer] = enrich_many(pipeline[layer], by_id, docs)
                pipeline["assessment_input"] = [{**hit, "id": i + 1}
                                                for i, hit in enumerate(pipeline["expanded"])]
            metrics = score_pipeline(query, pipeline, chunks, doc_by_id, token_counts)
            fused_score = score_layer(query, pipeline["fused"], chunks, doc_by_id)
            lexical_score = score_layer(query, lexical, chunks, doc_by_id)
            raw_score = score_layer(query, raw, chunks, doc_by_id)
            ranks = {"raw_lexical": raw_score["first_full_evidence_rank"],
                     "dedup_lexical": lexical_score["first_full_evidence_rank"],
                     "dense": score_layer(query, vector, chunks, doc_by_id)["first_full_evidence_rank"],
                     "fused": fused_score["first_full_evidence_rank"],
                     **{stage: metrics["scores"][stage]["first_full_evidence_rank"] for stage in
                        ("reranked", "selected", "expanded", "answer")}}
            failure = classify_failure(query.get("risk") != "unverified_formula_structure",
                                       *(ranks[key] for key in ("raw_lexical", "dedup_lexical", "fused",
                                                                 "reranked", "selected", "expanded", "answer")))
            arms[name] = {"pipeline": pipeline, "metrics": metrics, "ranks": ranks,
                          "failure_type": failure,
                          "lexical_diversity": diversity(lexical),
                          "fused_diversity": diversity(pipeline["fused"]),
                          "assessment_trace": assess_trace(question, plan, pipeline)}
        if any(hit_ids(arms["S6"]["pipeline"][stage]) != hit_ids(arms["D1"]["pipeline"][stage])
               for stage in ("reranked", "selected", "expanded", "answer")):
            raise RuntimeError(f"D1 differs from S6/P0: {query['id']}")
        traces.append({"query_id": query["id"], "question": question,
                       "category": category(query["id"]), "query_plan": plan.to_dict(),
                       "gold_facts": query["facts"], "source_pdf_sha256": docs[query["document_key"]]["hash"],
                       "parser_correctness_status": "PARSING_FAILURE" if query.get("risk") == "unverified_formula_structure" else "SOURCE_AND_CHUNK_FACTS_VERIFIED",
                       "raw_lexical_diversity": diversity(raw), "arms": arms})
        print(f"{query['id']} S6={arms['S6']['metrics']['scores']['answer']['first_full_evidence_rank']} "
              f"S8={arms['S8']['metrics']['scores']['answer']['first_full_evidence_rank']} "
              f"S10={arms['S10']['metrics']['scores']['answer']['first_full_evidence_rank']} "
              f"D2={arms['D2']['metrics']['scores']['answer']['first_full_evidence_rank']} "
              f"D3={arms['D3']['metrics']['scores']['answer']['first_full_evidence_rank']}", flush=True)
    write_jsonl(OUT / "query-traces.jsonl", traces)
    arms_to_score = ["S6", "S8", "S10", "S6_A1_bypass", "S8_A1_bypass", "S10_A1_bypass", "D1", "D2", "D3"]
    metrics = {"by_arm": {arm: aggregate(traces, arm) for arm in arms_to_score},
               "by_query": [{"query_id": row["query_id"], "category": row["category"],
                             "arms": {name: {"ranks": data.get("ranks") or
                                                   {stage: score["first_full_evidence_rank"] for stage, score in data["metrics"]["scores"].items()},
                                             "selected_chunks": data["metrics"]["selected_chunks"],
                                             "selected_tokens": data["metrics"]["selected_tokens"],
                                             "gold_fact_coverage": {stage: c["fraction"] for stage, c in data["metrics"]["coverage"].items()},
                                             "assessment_status": data["metrics"]["assessment_status"],
                                             "filter_event": data["metrics"]["filter_event"],
                                             "failure_type": data.get("failure_type")}
                                      for name, data in row["arms"].items()}}
                            for row in traces]}
    write_json(OUT / "metrics.json", metrics)
    write_json(OUT / "manifest.json", {"source_p0_manifest_sha256": sha(P0_OUT / "manifest.json"),
                                         "source_p0_baseline_sha256": sha(P0_OUT / "p0-baseline.jsonl"),
                                         "dataset_sha256": sha(ROOT / "docs/evaluations/structure-chunking-zh-v1.json"),
                                         "chunks_sha256": sha(ROOT / "test-results/structure-chunking-zh-2026-10-01-v2/chunks/B.jsonl"),
                                         "source_pdf_sha256": {k: v["hash"] for k, v in docs.items()},
                                         "query_count": 14, "answerable_count": 13,
                                         "cuda_rerank_source": "frozen actual P0 CUDA ranks for S; same CUDA reranker for D2/D3",
                                         "selection_limits": list(LIMITS), "location_caps": list(PAGE_CAPS),
                                         "lexical_candidate_limit": 20, "assess_bypass": "selected evidence only; context=0 on all fixed 14 queries"})
    print(f"DONE {OUT}", flush=True)


if __name__ == "__main__":
    main()
