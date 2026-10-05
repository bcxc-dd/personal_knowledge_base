# Chinese Structure-aware Chunking Benchmark

This is an isolated B/C experiment. It reads the existing SQLite database in read-only mode, parses the two Chinese PDFs, applies the same stored page correction to both sides, and writes only under `test-results/`. It does not update the production chunks, Chroma directory, ingestion code, or service.

Run from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest benchmarks/structure_chunking/test_core.py -q
.venv\Scripts\python.exe benchmarks/structure_chunking/run.py
.venv\Scripts\python.exe benchmarks/structure_chunking/rescore.py
```

The default output is `test-results/structure-chunking-zh-2026-10-01-v2/`. A completed output directory is immutable to the runner. Set `CHUNK_BENCHMARK_OUTPUT` to a new path below `test-results/` for another run. The frozen dataset is `docs/evaluations/structure-chunking-zh-v1.json`.

`metrics.json` preserves the automatic lexical-anchor result. `audited-metrics.json` separately marks the unverified pypdf fraction question as `PARSING_FAILURE`. The latter is the report's source of truth for Evidence Recall@K and MRR. Full text and ranks are in `retrieval/*.jsonl`; source-spanned Blocks are in `snapshot/*.jsonl`.
