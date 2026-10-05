"""Re-score saved Top-50 with reviewed source limitations; no re-indexing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from benchmarks.structure_chunking.core import score_query

OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "test-results/structure-chunking-zh-2026-10-01-v2"
DATASET = json.loads((ROOT / "docs/evaluations/structure-chunking-zh-v1.json").read_text(encoding="utf-8"))


def load_jsonl(path):
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def aggregate(rows):
    return {"n": len(rows), "mrr": sum(r["mrr"] for r in rows) / len(rows),
            **{f"evidence_recall_at_{k}": sum(r[f"evidence_at_{k}"] for r in rows) / len(rows)
               for k in (1, 3, 5, 10, 20, 50)},
            "failure_counts": {kind: sum(r["failure_type"] == kind for r in rows)
                               for kind in ("SUCCESS", "EVIDENCE_ABSENT", "PARSING_FAILURE", "CHUNKING_FAILURE",
                                            "RETRIEVAL_FAILURE", "RANKING_FAILURE", "GENERATION_FAILURE")}}


def main():
    corpus = {}
    for doc in DATASET["documents"]:
        if doc["role"] == "primary":
            corpus[doc["key"]] = "\n".join(p["text"] for p in load_jsonl(OUT / f"snapshot/{doc['key']}-pages.jsonl"))
    output = {"method": "source-page evidence anchors and same-document Top-50; formula structure manually marked PARSING_FAILURE",
              "formula_review": {"query_id": "ai-batch-formula", "reason": "pypdf page 24 yields numerator and denominator on separate lines without a verified fraction relation; lexical glyph matches do not answer the formula question"},
              "variants": {}}
    for variant in ("B", "C256", "C384", "C512"):
        chunks = load_jsonl(OUT / f"chunks/{variant}.jsonl")
        retrieval = {r["query_id"]: r for r in load_jsonl(OUT / f"retrieval/{variant}.jsonl")}
        per_query = []
        for q in DATASET["queries"]:
            original = retrieval[q["id"]]
            score = score_query(q, chunks, original["ranked"], corpus)
            per_query.append({"query_id": q["id"], "question": q["question"],
                              "source_pages": sorted({p for f in q["facts"] for p in f["source_pages"]}),
                              "raw_lexical_rank": original["first_full_evidence_rank"], **score})
        clean = [r for r in per_query if r["query_id"] != "ai-batch-formula"]
        output["variants"][variant] = {"all_14": aggregate(per_query), "answerable_13": aggregate(clean),
                                       "per_query": per_query}
    target = OUT / "audited-metrics.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
