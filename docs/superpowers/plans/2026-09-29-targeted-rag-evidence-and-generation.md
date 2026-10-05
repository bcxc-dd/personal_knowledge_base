# Targeted RAG Evidence and Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the observed evidence gaps in q05/q09/q10/q12/q17 and the generation omission in q16 without introducing a broad retrieval subsystem.

**Architecture:** Keep the current vector, lexical, rerank, context, assessment, and generation stages. Recover narrowly justified evidence through query interpretation, bounded candidate/context selection, and chapter summary detection. Give the generator a concise coverage instruction only when the supplied evidence supports it.

**Tech Stack:** Python, FastAPI backend, SQLite, Chroma, local reranker, pytest, calibrated PDF evaluation snapshot.

**Spec:** `docs/evaluations/ai-infra-answerability-v2.json` and `docs/evaluations/2026-09-28-failure-layer-small-optimizations.md`.

## Global Constraints

- Preserve existing uncommitted work and user data.
- Do not add BM25, HyDE, new models, or index rebuilding.
- Keep source filtering grounded in actual document text and avoid PDF page or chunk IDs in product rules.
- Preserve q23–q25 insufficiency behavior and the six calibrated fixtures.

## Review Focus

- An unrelated chapter mention must not trigger chapter summary expansion.
- Technical query rewrites must not fabricate evidence from a different document.
- Candidate recovery must remain bounded and not flood the generator with unrelated context.
- A paragraph continuation across a page must retain source location and document identity.
- Generator coverage guidance must allow explicit uncertainty when evidence is missing.

---

### Task 1: Chapter outline evidence for q17

**Files:** `backend/app/context.py`, `backend/tests/test_rag.py`.

- [x] Write a failing test for a “第 N 章…主线” question that adds its own chapter summary but excludes another chapter.
- [x] Run the targeted test and confirm failure.
- [x] Add “主线” to chapter overview detection and run the targeted test.

### Task 2: Recover missing source facts for q05/q09/q10/q12

**Files:** `backend/app/query_plan.py`, `backend/app/engine.py`, `backend/app/context.py`, and focused tests.

- [x] Probe each case against the unchanged PDF/index to confirm which evidence appears after a bounded query or candidate expansion.
- [x] Add failing tests that describe required evidence properties and negative controls, without using PDF chunk IDs in product code.
- [x] Implement the smallest per-stage change and run targeted tests after each change.

### Task 3: q16 answer coverage

**Files:** `backend/app/engine.py`, focused tests.

- [x] Verify q16 input evidence includes resource categories and changing workload factors.
- [x] Add a focused prompt-contract test for chapter resource questions and a non-chapter control.
- [x] Add concise source-based coverage guidance and test actual generation.

### Task 4: End-to-end regression and documentation

**Files:** `docs/evaluations/`, `docs/mvp-progress.md`, `docs/project-roadmap.md`.

- [x] Run backend tests and calibrated snapshot evaluation, including q23–q25 and fixtures.
- [x] Generate targeted real answers and manually check required facts and citations against the PDF.
- [x] Restart the backend if product code changed and verify health/version.
- [x] Record evidence, unresolved cases, and next step without claiming stage A completion.
