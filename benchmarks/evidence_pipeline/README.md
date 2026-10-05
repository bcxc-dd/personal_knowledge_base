# Evidence Selection & Sufficiency benchmark

This benchmark uses the validated Chinese P0 snapshot in `test-results/production-retrieval-ablation-2026-10-01-v2/`. It does not modify production code, user data, the live SQLite/Chroma index, or the running service. It refuses to overwrite an existing `metrics.json`.

Run from `D:\rag` with the project virtual environment:

```powershell
.venv\Scripts\python.exe -m pytest benchmarks/evidence_pipeline/test_evidence_core.py -q
.venv\Scripts\python.exe -m benchmarks.evidence_pipeline.run
.venv\Scripts\python.exe -m benchmarks.evidence_pipeline.verify
```

The validated output directory is `test-results/evidence-pipeline-2026-10-01-v1/` (gitignored). Its `report.md` gives the result. `query-traces.jsonl` includes per-query full selected/expanded/final text and `assess_evidence()` inputs, outputs and benchmark-derived reasons. `lexical-routes.jsonl` includes raw SQL Top-100 and all D1/D2/D3 candidates. `metrics.json`, `manifest.json`, and `verification.json` permit independent audit.

S6/S8/S10 replay the **same frozen actual CUDA rerank order** and call production selection, context, and assessment functions with only the selection limit changed. A1 bypasses assessment only for the benchmark; context expansion is zero on all fixed queries. D2/D3 alter only the per-location cap on the current SQL route and run the same CUDA reranker and downstream functions. Both `run.py` and `verify.py` require the P0 code, query, chunks, source hashes, and configuration to remain frozen.

The one formula parse-failure query remains in traces and is excluded from the 13-answerable-question means. The diagnostic `benchmark_derived_reason` is not a field returned by production `EvidenceAssessment`.
