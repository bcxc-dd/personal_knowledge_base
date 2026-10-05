# Production Retrieval Ablation & BM25 Replacement Benchmark

## Scope and frozen inputs

Read only the existing Chinese v1 query/gold dataset and frozen 2319 B chunks. Snapshot the current production Chroma collection into an isolated directory, plus a temporary SQLite Store populated with the same two Chinese documents and exact production chunk IDs, rowids, text and page metadata. Never include English documents in eligible candidates; never write production `data/`, service, index, parser or chunker. Preserve the one known formula parsing failure as a diagnostic query, excluded from answerable-query means.

## Reproduction gates

1. Hash-check dataset and B chunks against the prior manifest; verify 2319 unique chunks, PDF hashes/correction hashes, and page/text parity. Load production retrieval settings by a read-only SQLite connection, retaining only nonsecret fields.
2. Make a read-only production Chroma snapshot (SQLite backup and file copies), then use production `VectorStore` against the copy. Assert that all 2319 scoped vector IDs, texts and pages exactly match the frozen B chunks. The earlier independent B Chroma had approximate-search drift, so it is unsuitable for reproducing P0.
3. Execute actual `Engine.retrieve` against the isolated Store and frozen vector adapter for P0. Require actual CUDA reranker provider (no silent fallback). Reconstruct the exact `answer()` citation-filtering step with `assess_evidence`, without invoking generation or writing conversations.
4. Independently replay P0 from production `QueryPlan`, SQL `search_chunks_exact`, `diverse_lexical_hits`, `fuse_candidates`, `Reranker.rank`, `select_evidence_items`, context helpers and `assess_evidence`; assert selected/context/assessment parity with `Engine.retrieve` for all fixed questions.

## Controlled arms

- P0/P5: full current path; P3: current dense+substring+RRF before reranker/postprocessing; P4: P3 plus reranker; P1/P2: vector-only or substring-only with identical downstream stages and candidate budgets.
- L0: current SQL substring top-100 then location diversity to 20. L1: identical SQL output but first 20 without location diversity. Record lost gold chunk IDs and pages.
- B0a: BM25 using current project `lexical_terms` for corpus and the same QueryPlan terms for query. B0b: BM25 using fixed NFKC Han unigrams/bigrams + whole Latin identifiers/decimals, again on exactly the same QueryPlan terms. No page dedup. Both use k1=1.2,b=0.75, 20 lexical candidates, same RRF k=60 and downstream configuration.

## Evaluation

For each question/arm, persist route ranks, fused Top-40, post-rerank order, selected evidence, context additions, assessment status/IDs, and final answer citations. Score facts with existing frozen source-page and all-terms gold; manually review first matches and boundary cases. Report Evidence Recall@1/3/5/10/20/50 and MRR at candidate, selected and answer-context layers. At short layers @K above list length means 'any evidence in this layer', with candidate budget explicitly recorded. Attribute unique/rescue/degrade/drop events to the exact adjacent stage. Collect per-stage timing, peak tracked allocations, BM25 index size and actual reranker device. Do not tune RRF weights or reranker.

## Build steps

1. Write benchmark regression tests for the isolation/parity and scoring contracts; observe failing tests before implementation.
2. Implement snapshot loader, SQLite clone and vector adapter under `benchmarks/production_retrieval/` only.
3. Run P0 reproduction and save a checkpoint report before the remaining arms.
4. Run P1–P5, L0/L1 and B0a/B0b. Freeze JSONL outputs and manifest hashes. Inspect failure cases and create a Chinese report with migration decision.
5. Verify benchmark tests and backend tests using `.venv/Scripts/python.exe`, check artifact hashes, then update roadmap/progress. No production build or restart.

## Decision rule

Direct migration only if B0 improves P0 at selected and final answer context layers, MRR is not worse, multiple independent normative/numeric evidence units improve, technical evidence does not materially regress, and latency/storage are acceptable. Otherwise identify the actual bottleneck and keep production unchanged.
