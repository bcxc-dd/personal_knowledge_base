# Chunking Degradation Diagnosis → Hybrid Retrieval Benchmark

**Objective:** Explain the seven named B/C512 changes from source spans and complete chunk text, then test whether BM25 and unweighted RRF improve answer-bearing retrieval on the frozen Chinese B corpus. The user's pasted 2026-10-01 request is the approved scope and execution method.

**Scope:** No production code, database, Chroma index, parser, embedding, service, or frozen query/gold modification. English MambaIRv2 is excluded. Reuse `test-results/structure-chunking-zh-2026-10-01-v2/` as immutable input. New output is an ignored directory under `test-results/`.

## Phase A: explain chunk effects before Phase B

1. Recover exact B source offsets by replaying production `split_sections`; verify every recovered text against frozen B chunks. Map C512 `source_block_ids` to Block spans and identify all chunks containing each gold fact, including outside Top-50.
2. Save a case JSON for the seven required queries with question, facts, B/C ranks, full chunk text, source spans, block IDs, token counts, and query-term density. Include the split C256 evidence for `ai-q21`.
3. Write a report grounded in those artifacts. Label supported failure patterns and mark unsupported taxonomy classes as unproven. Decide whether local technical windows and policy/compare-specific structure have enough evidence to justify later adaptive research.
4. Verify source reconstruction and report completeness. **Do not start Phase B until the Phase A report exists and has been reviewed against source chunks.**

## Phase B: controlled retrieval comparison on B chunks

1. Build a deterministic Chinese lexical tokenizer from Unicode NFKC, Han unigrams/bigrams, Latin terms, and decimal numbers; freeze it before scoring. Implement standard BM25 with `k1=1.2`, `b=0.75`; test term matching and deterministic ties.
2. H0: reuse frozen B Chroma dense Top-50. H1: BM25-only on the exact same 2319 B chunks. H2: unweighted RRF `k=60` over Dense/BM25 Top-20 each and Top-50 each. Keep the 14 fixed Chinese queries, with the unresolved formula scored `PARSING_FAILURE`; primary retrieval metrics use the 13 answerable questions.
3. Save full ranked Top-50 per group, per-query evidence ranks, Recall@1/3/5/10/20/50, MRR, candidate overlap, dense-only/BM25-only relevant hits, rescued and degraded cases, latency, serialized lexical index size, and settings/hash manifest.
4. Review every first matched evidence chunk and all rank reversals. Compare results to the predefined success gate: higher Evidence@5, nonlower MRR, no important policy/technical regressions, multiple independent rescues, and acceptable cost. Do not tune BM25 boosts, fusion weights, parser, chunks, embedding, or queries after seeing results.

## Verification and reporting

- Benchmark unit tests first (RED → GREEN), then run existing benchmark tests and relevant project tests.
- Recompute source/gold hashes and assert B chunk count/content equal frozen baseline; assert 14 queries × 50 ranks per group.
- Update `docs/project-roadmap.md` and `docs/mvp-progress.md` with evidence, limitations, next step, and no build/restart/index change.
