"""Separate historical Chinese chapter-question probe; excluded from frozen scores."""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.production_retrieval.run import (
    OUT, ROOT, CachedModelClient, Engine, Reranker, Store, VectorStore,
    assess_evidence, build_query_plan, normalize_question, read_config,
)


def main() -> None:
    source = json.loads((ROOT / "docs/evaluations/ai-infra-answerability-v2.json").read_text(encoding="utf-8"))
    query = next(q for q in source["cases"] if q["id"] == "q18")
    question = normalize_question(query["question"])
    plan = build_query_plan(question)
    store = Store(OUT / "isolated_store")
    vectors = VectorStore(OUT / "isolated_chroma")
    engine = Engine.__new__(Engine)
    engine.store = store
    engine.vectors = vectors
    engine.models = CachedModelClient(ROOT / "data/models")
    engine.reranker = Reranker(ROOT / "data/models")
    with store.connection() as db:
        docs = db.execute("SELECT id, name FROM documents WHERE status='ready' ORDER BY id").fetchall()
    ai_doc = next(row["id"] for row in docs if "AI-Infra" in row["name"])
    retrieved = engine.retrieve(question, "default", [ai_doc], read_config(), question, plan)
    d = retrieved.diagnostics
    selected = [hit for hit in d["items"] if hit.get("selected")]
    context = d["context_items"]
    expanded = [*selected, *context]
    assessed = assess_evidence(question, [{**hit, "id": i + 1} for i, hit in enumerate(expanded)], plan)
    expected_suffixes = {1774, 1775, 1776, 1969, 1970, 1971}
    def pack(hits):
        return [{"chunk_id": h["chunk_id"], "location": h["location"],
                 "context_reason": h.get("context_reason"), "text": h["text"]}
                for h in hits]
    actual_suffixes = {int(h["chunk_id"].rsplit(":", 1)[-1]) for h in expanded}
    out = {"status": "supplementary_historical_probe_not_in_frozen_13",
           "question": question, "source_review": "docs/evaluations/2026-09-29-ai-infra-full-manual-review.md",
           "required_facts": query["core_subquestions"][0]["required_facts"],
           "selected": pack(selected), "context": pack(context),
           "assessment": assessed.to_dict(), "historical_evidence_suffixes": sorted(expected_suffixes),
           "observed_historical_evidence_suffixes": sorted(actual_suffixes & expected_suffixes)}
    target = OUT / "context-expansion-q18.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"selected": len(selected), "context": len(context),
                      "observed_historical_evidence_suffixes": out["observed_historical_evidence_suffixes"],
                      "assessment": out["assessment"], "output": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
