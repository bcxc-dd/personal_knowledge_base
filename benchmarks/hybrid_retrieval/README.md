# Chinese Hybrid Retrieval Benchmark

Run from `D:/rag` after the frozen structure chunking B output exists:

```powershell
.venv\Scripts\python.exe -m pytest benchmarks/hybrid_retrieval/test_hybrid_core.py -q
.venv\Scripts\python.exe benchmarks/hybrid_retrieval/run.py
```

The runner reads only `test-results/structure-chunking-zh-2026-10-01-v2/` and `docs/evaluations/structure-chunking-zh-v1.json`. It writes only to the ignored `test-results/hybrid-retrieval-zh-2026-10-01/` directory. It refuses to overwrite a completed run. No production parser, chunker, database, Chroma index or service is modified.

`metrics.json` contains all 14 queries and the 13 answerable-query subset; `query-results.jsonl` contains every Top-50 text and rank. The formula question remains `PARSING_FAILURE`. `report.md` explains the retrieval and product-migration limits.
