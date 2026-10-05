"""Score E0-E4 and replay frozen S6/S8 selection without running retrieval."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from benchmarks.evidence_matching.matchers import evaluate
from benchmarks.evidence_pipeline.core import gold_coverage

OUT = ROOT / "test-results/evidence-matching-2026-10-03-v2"
SOURCE = ROOT / "test-results/evidence-pipeline-2026-10-01-v1/query-traces.jsonl"
VARIANTS = ("E0", "E1", "E2", "E3", "E4")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score(rows):
    true_pos = sum(r["gold_label"] == "SUPPORTED" and r["predicted_label"] == "SUPPORTED" for r in rows)
    false_pos = sum(r["gold_label"] == "NOT_SUPPORTED" and r["predicted_label"] == "SUPPORTED" for r in rows)
    false_neg = sum(r["gold_label"] == "SUPPORTED" and r["predicted_label"] != "SUPPORTED" for r in rows)
    negative = sum(r["gold_label"] == "NOT_SUPPORTED" for r in rows)
    positive = sum(r["gold_label"] == "SUPPORTED" for r in rows)
    partial = [r for r in rows if r["gold_label"] == "PARTIAL"]
    precision = true_pos / (true_pos + false_pos) if true_pos + false_pos else 0.0
    recall = true_pos / positive if positive else 0.0
    return {"n": len(rows), "support_precision": precision, "support_recall": recall,
            "support_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "false_positive_rate": false_pos / negative if negative else 0.0,
            "false_negative_rate": false_neg / positive if positive else 0.0,
            "partial_accuracy": sum(r["predicted_label"] == "PARTIAL" for r in partial) / len(partial) if partial else None,
            "exact_label_accuracy": sum(r["gold_label"] == r["predicted_label"] for r in rows) / len(rows) if rows else 0.0,
            "confusion": {gold: {pred: sum(r["gold_label"] == gold and r["predicted_label"] == pred for r in rows)
                                 for pred in ("SUPPORTED", "PARTIAL", "NOT_SUPPORTED")}
                          for gold in ("SUPPORTED", "PARTIAL", "NOT_SUPPORTED")}}


def rank(query, hits):
    for i in range(1, len(hits) + 1):
        if gold_coverage(query, hits[:i])["fraction"] == 1:
            return i
    return None


def metrics_for_replay(rows):
    answerable = [r for r in rows if r["query_id"] != "ai-batch-formula"]
    ranks = [r["rank"] for r in answerable]
    return {"n": len(answerable), "evidence_at_5": sum(n is not None and n <= 5 for n in ranks) / len(ranks),
            "mrr": sum(1 / n if n else 0 for n in ranks) / len(ranks),
            "average_gold_fact_coverage": sum(r["gold_coverage"] for r in answerable) / len(answerable),
            "average_answer_chunks": sum(r["answer_chunks"] for r in answerable) / len(answerable),
            "average_answer_tokens": sum(r["answer_tokens"] for r in answerable) / len(answerable)}


def replay():
    records = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line]
    out = {}
    for arm in ("S6", "S8"):
        rows = []
        for record in records:
            pipe = record["arms"][arm]["pipeline"]
            source = pipe["assessment_input"]
            decisions = []
            for hit in source:
                case = {"case_id": hit["chunk_id"], "query": record["question"], "evidence_text": hit["text"],
                        "evidence_metadata": [{"chunk_id": hit["chunk_id"],
                                               "document_key": hit.get("document_key", ""),
                                               "page": hit.get("page")}]}
                decisions.append({"chunk_id": hit["chunk_id"], **evaluate(case, "E4")})
            retained = {d["chunk_id"] for d in decisions if d["predicted_label"] != "NOT_SUPPORTED"}
            new_answer = [hit for hit in source if hit["chunk_id"] in retained]
            old_answer = pipe["answer"]
            query = {"facts": record["gold_facts"],
                     "document_key": "promotion" if record["query_id"].startswith("policy-") else "ai_infra"}
            for variant, hits in (("E0", old_answer), ("E4", new_answer)):
                computed_rank = rank(query, hits)
                if variant == "E0" and record["query_id"] != "ai-batch-formula":
                    frozen_rank = record["arms"][arm]["metrics"]["scores"]["answer"]["first_full_evidence_rank"]
                    if computed_rank != frozen_rank:
                        raise RuntimeError(f"Frozen E0 score drift: {arm}/{record['query_id']} {computed_rank}!={frozen_rank}")
                rows.append({"query_id": record["query_id"], "question": record["question"], "arm": arm,
                             "variant": variant, "rank": computed_rank,
                             "gold_coverage": gold_coverage(query, hits)["fraction"],
                             "answer_chunks": len(hits),
                             "answer_tokens": sum(hit.get("token_count", 0) for hit in hits),
                             "answer_ids": [hit["chunk_id"] for hit in hits],
                             "decisions": decisions if variant == "E4" else []})
        out[arm] = {"rows": rows, "metrics": {v: metrics_for_replay([r for r in rows if r["variant"] == v]) for v in ("E0", "E4")}}
    return out


def main():
    destination = OUT / "results.json"
    if destination.exists():
        raise RuntimeError("Frozen benchmark result exists; refusing overwrite")
    dataset_path, baseline_path = OUT / "dataset.json", OUT / "e0-baseline.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if baseline["dataset_sha256"] != sha(dataset_path):
        raise RuntimeError("Dataset changed since E0 was frozen")
    frozen_e0 = {r["case_id"]: r["predicted_label"] for r in baseline["cases"]}
    rows = []
    for case in dataset["cases"]:
        for variant in VARIANTS:
            decision = evaluate(case, variant)
            if variant == "E0" and decision["predicted_label"] != frozen_e0[case["case_id"]]:
                raise RuntimeError(f"E0 drift: {case['case_id']}")
            rows.append({"case_id": case["case_id"], "split": case["split"], "category": case["category"],
                         "assessment_intent": case["assessment_intent"], "gold_label": case["gold_label"],
                         "variant": variant, **decision})
    by_variant = {v: [r for r in rows if r["variant"] == v] for v in VARIANTS}
    categories = sorted({r["category"] for r in rows})
    result = {"status": "PROVISIONAL_AGENT_LABELS_PENDING_HUMAN_REVIEW",
              "input_hashes": {"dataset": sha(dataset_path), "e0_baseline": sha(baseline_path),
                               "frozen_pipeline_traces": sha(SOURCE),
                               "isolated_matcher": sha(ROOT / "benchmarks/evidence_matching/matchers.py"),
                               "production_evidence_at_replay": sha(ROOT / "backend/app/evidence.py"),
                               "production_query_plan_at_replay": sha(ROOT / "backend/app/query_plan.py")},
              "rows": rows, "metrics": {v: {"all": score(by_variant[v]),
                                              "dev": score([r for r in by_variant[v] if r["split"] == "dev"]),
                                              "holdout_smoke_only": score([r for r in by_variant[v] if r["split"] == "holdout"]),
                                              "categories": {cat: score([r for r in by_variant[v] if r["category"] == cat]) for cat in categories}}
                                       for v in VARIANTS},
              "holdout_limitation": "Rules were tested against the five holdout examples during development; they are not independent holdout evidence.",
              "replay": replay()}
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"dataset_cases": len(dataset["cases"]),
                      "metrics": {v: result["metrics"][v]["all"] for v in VARIANTS},
                      "replay": {arm: content["metrics"] for arm, content in result["replay"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
