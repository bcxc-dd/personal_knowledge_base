"""Freeze agent-curated provisional cases with real B chunks and QueryPlans."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.query_plan import build_query_plan
from benchmarks.evidence_matching.cases import CASES
from benchmarks.production_retrieval.run import load_inputs

OUT = ROOT / "test-results/evidence-matching-2026-10-03-v2"


def main():
    if (OUT / "dataset.json").exists():
        raise RuntimeError("Frozen matching dataset exists; refusing overwrite")
    _, chunks, docs, _ = load_inputs()
    by_id = {f"{docs[c['document_key']]['id']}:{c['ordinal']}": c for c in chunks}
    rows = []
    for item in CASES:
        source = item["evidence"]
        if isinstance(source, list):
            if not all(cid in by_id for cid in source):
                raise RuntimeError(f"Unknown source chunk in {item['case_id']}")
            evidence_text = "\n\n".join(by_id[cid]["text"] for cid in source)
            evidence_metadata = [{"chunk_id": cid, "page": by_id[cid]["page"],
                                  "document_key": by_id[cid]["document_key"]} for cid in source]
            provenance = "frozen_verified_pdf_chunk"
        else:
            evidence_text = source
            evidence_metadata = []
            provenance = "agent_authored_controlled_fixture"
        if len(evidence_text) < 8:
            raise RuntimeError(f"Evidence too short: {item['case_id']}")
        rows.append({**{k: v for k, v in item.items() if k != "evidence"},
                     "query_plan": build_query_plan(item["query"]).to_dict(),
                     "evidence_text": evidence_text,
                     "evidence_metadata": evidence_metadata,
                     "provenance": provenance,
                     "annotation_status": "agent_provisional_pending_human_review"})
    if len({r["case_id"] for r in rows}) != len(rows):
        raise RuntimeError("Duplicate case_id")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "dataset.json"
    path.write_text(json.dumps({"schema": "evidence-matching-v1",
                                "label_semantics": "SUPPORTED iff supplied evidence supports all specific queried facts; PARTIAL iff it supports a nonempty proper subset; NOT_SUPPORTED if none or if it contradicts a required claim.",
                                "annotation_method": "Agent-curated provisional labels on previously reviewed real Chinese B chunks and explicitly marked agent-written contrast fixtures. Independent human review is required before using scores as migration evidence; QueryPlan is computed by frozen production code and saved.",
                                "cases": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(rows), "labels": dict(Counter(r["gold_label"] for r in rows)),
                      "splits": dict(Counter(r["split"] for r in rows)),
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
