# Chinese Structure-aware Chunking Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare the current 400/60 page chunking with conservative structure-aware chunking on the same frozen Chinese PDF text and Block snapshot, using dense-only retrieval and auditable evidence labels.

**Architecture:** Read current PDFs and the existing page correction through a read-only SQLite connection. Freeze the effective page text and conservative source-spanned Blocks in an ignored benchmark output directory. Generate B and C chunks from the same snapshot, index each in its own isolated Chroma collection, then evaluate fixed Chinese queries by full evidence spans/fact groups rather than target-page hits.

**Tech Stack:** Python 3.11, pypdf 6.19.0, tokenizers, FastEmbed `BAAI/bge-small-zh-v1.5`, Chroma cosine, pytest.

**Spec:** User-approved in-chat design in the 2026-10-01 conversation; no production ingestion, model, retrieval, service, or index changes.

## Global Constraints

- Main corpus: Chinese AI-Infra-Book and Chinese promotion policy; exclude English MambaIRv2 and `sample.md`.
- Parser snapshot, page correction, query set, embedding, vector store, retrieval algorithm, and Top-K are fixed across B/C.
- B = production `split_sections(size=400, overlap=60)` on frozen effective page text. C = Block-aware rules at nominal 256/384/512 token targets.
- Do not invent formula meanings or use unverified LaTeX. No reranker, lexical retrieval, RRF, query rewrite, HyDE, or generation.
- Preserve the user's existing workspace changes and live `data/chroma`/SQLite; all benchmark output under ignored `test-results/structure-chunking-zh-2026-10-01/`.

## Review Focus

- The B snapshot must reproduce the current stored production chunks byte-for-byte where document/index versions match.
- The policy page 9 correction must be applied identically to B/C, with its source/revision hash recorded.
- Evidence scoring must require answer-bearing facts in chunk text, not page or mere keyword hits.
- No isolated heading, naked table number, or generated formula in C.
- 512 nominal target must not exceed the model's 512-token input ceiling.

## Tasks

### Task 1: Freeze corpus and gold questions

- [x] Save a Chinese-only dataset manifest with document SHA-256, correction provenance, fixed questions, fact groups, and expected source evidence.
- [x] Implement read-only corpus preparation and verify B chunks against the current SQLite snapshot.
- [x] Record baseline chunks, source pages, and corpus/query hashes.

### Task 2: Build and verify conservative Block model

- [x] Write failing tests for source span preservation, heading attachment, paragraph line repair, table row provenance, and unresolved equations.
- [x] Implement source-spanned `Document/Page/Block` snapshots from the same effective pypdf page text.
- [x] Run the tests and validate every non-furniture source character is accounted for or explicitly excluded.

### Task 3: Chunking variants

- [x] Write failing tests for B parity, token hard cap, no heading-only unit, table header/row repetition, and equation source preservation. Caption linking remains a benchmark limitation.
- [x] Implement B and C256/C384/C512 from the same Block snapshot; save all chunks and token counts.
- [x] Check no generated factual values are introduced by retrieval representation.

### Task 4: Dense-only isolated retrieval and evidence scoring

- [x] Write failing tests for multi-fact Evidence Recall@K, MRR, missing evidence, and failure taxonomy.
- [x] Embed/index each variant with identical model and isolated Chroma cosine settings; save full Top-50 ranks.
- [x] Score and manually audit every query's first adequate evidence and regression cases.

### Task 5: Report and project status

- [x] Report per-query B/C results, chunk counts, average tokens, Evidence Recall@1/3/5/10/20/50, MRR, wins/losses, failure taxonomy, latency/storage, and limitations.
- [x] Explain whether improvements justify production migration, separating benchmark evidence from product validation.
- [x] Update roadmap/progress with evidence and note no production build/restart/index rebuild.

## Completion Contract

The benchmark is complete only when all four variants have saved chunks and retrieval results for the frozen Chinese corpus, B parity is checked, all gold questions have a rank and failure category, the report identifies regressions, and the production workspace data remains unchanged.
