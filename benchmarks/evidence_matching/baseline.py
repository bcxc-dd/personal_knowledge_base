"""Freeze E0 production assess_evidence on the provisional matching dataset."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.evidence import assess_evidence
from app.query_plan import build_query_plan
from benchmarks.evidence_matching.build_dataset import OUT


def citation(case):
    source = case["evidence_metadata"]
    return {"id": 1, "chunk_id": case["case_id"], "document_id": source[0]["chunk_id"].split(":")[0] if source else "controlled",
            "name": "2027届本科毕业生推免工作细则.pdf" if source and source[0]["document_key"] == "promotion"
                    else "AI-Infra-Book.pdf" if source else "受控对照片段",
            "location": f"第 {source[0]['page']} 页" if source else "受控样本",
            "text": case["evidence_text"]}


def main():
    path = OUT / "e0-baseline.json"
    if path.exists():
        raise RuntimeError("E0 baseline already exists; refusing overwrite")
    dataset = json.loads((OUT / "dataset.json").read_text(encoding="utf-8"))
    rows = []
    for case in dataset["cases"]:
        plan = build_query_plan(case["query"])
        if plan.to_dict() != case["query_plan"]:
            raise RuntimeError(f"QueryPlan drift: {case['case_id']}")
        source = citation(case)
        result = assess_evidence(case["query"], [source], plan).to_dict()
        rows.append({"case_id": case["case_id"], "gold_label": case["gold_label"],
                     "query_plan": plan.to_dict(), "assessment_input": [source],
                     "assessment_output": result,
                     "predicted_label": {"supported": "SUPPORTED", "partial": "PARTIAL",
                                         "insufficient": "NOT_SUPPORTED"}[result["status"]]})
    path.write_text(json.dumps({"dataset_sha256": hashlib.sha256((OUT / "dataset.json").read_bytes()).hexdigest(),
                                "cases": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(rows),
                      "predictions": dict(Counter(r["predicted_label"] for r in rows)),
                      "correct": sum(r["predicted_label"] == r["gold_label"] for r in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
