# Production retrieval ablation benchmark

This benchmark is isolated from the production ingestion, SQLite, Chroma, and running service. It reads production data to verify a snapshot, then evaluates the two approved Chinese PDFs and the frozen 14 Chinese queries on local copies. It never indexes, edits, or deletes production data.

## Inputs

- `docs/evaluations/structure-chunking-zh-v1.json`: query and manually reviewed evidence rubric.
- `test-results/structure-chunking-zh-2026-10-01-v2/`: frozen 400/60 B chunks, page snapshots, hashes.
- Current read-only production `data/knowledge.sqlite3` and `data/chroma`: exact B IDs, row IDs, text, pages, vectors, retrieval configuration.
- Project `.venv`, existing local BGE embedding and CUDA reranker models.

## Commands

Run from `D:\rag` with the project virtual environment:

```powershell
.venv\Scripts\python.exe -m pytest benchmarks/production_retrieval/test_ablation.py -q
.venv\Scripts\python.exe -m benchmarks.production_retrieval.run
.venv\Scripts\python.exe -m benchmarks.production_retrieval.measure
.venv\Scripts\python.exe -m benchmarks.production_retrieval.verify
.venv\Scripts\python.exe -m benchmarks.production_retrieval.probe_context_q18
```

`run.py` refuses to overwrite a completed `metrics.json`. For a fresh run, change `OUT` to a new versioned output directory and keep prior results for audit; do not delete or overwrite results in place. `probe_context_q18.py` is a separate historical chapter-context check and never changes the frozen 13-answerable-question means.

## Results

Validated run: `test-results/production-retrieval-ablation-2026-10-01-v2/` (gitignored). Start with `report.md`, then inspect `manifest.json`, `verification.json`, `metrics.json`, `query-traces.jsonl`, `case-audit.md`, and resource files. Candidate, selected, and final answer-context scores are separate. The formula parse-failure question remains visible in query traces but is excluded from the answerable-score denominator.

The preliminary `test-results/production-retrieval-ablation-2026-10-01/` run is invalid after an interrupted clone; its `INVALID-DO-NOT-USE.md` explains why.
