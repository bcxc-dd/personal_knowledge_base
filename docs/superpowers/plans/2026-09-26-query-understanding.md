# Query Understanding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the reported GPA requirement refusal with a shared, bounded query plan for retrieval and evidence assessment.

**Architecture:** Parse the current user question once into a structured query plan. Keep the original question, use safe subject and metric terms for lexical search and one optional vector rewrite, and assess question-specific facts against retrieved passages.

**Tech Stack:** Python 3.10, pytest, existing SQLite/Chroma/ONNX pipeline.

**Spec:** `docs/superpowers/specs/2026-09-26-query-understanding-design.md`

## Global Constraints

- Preserve current uncommitted work and user data; do not rebuild the index or add model dependencies.
- Keep raw user text for answer generation; never add a year, GPA threshold, or policy conclusion in a rewrite.
- Limit extra vector work to one query on recognized rewrite cases; unknown cases keep existing behavior.

## Review Focus

- The reported exact question, including trailing spaces, must obtain the page 2 3.2 passage and a supported assessment.
- Unrelated scholarship rules and passages merely mentioning GPA must remain insufficient.
- Questions specifying another year must not borrow the 2027 rule.
- Previous promotion questions and AI Infra cases must retain their current evidence statuses.
- Multi-turn history must not inject obsolete terms into lexical search or alter the current question's evidence requirement.

---

### Task 1: Structured query plan

**Files:** Create `backend/app/query_plan.py`; test `backend/tests/test_query_plan.py`.

**Interfaces:** `build_query_plan(question: str) -> QueryPlan`; fields include original, intent, subject, metric, lexical_terms, vector_queries, required_facts.

- [x] Write tests for requirement question variants, omitted metric/subject, numeric/year preservation, and an unrelated technical question.
- [x] Run focused tests and confirm expected failures.
- [x] Implement deterministic parsing and bounded expansion with safe fallback.
- [x] Run focused tests and confirm green.

### Task 2: Shared evidence assessment

**Files:** Modify `backend/app/evidence.py`; test `backend/tests/test_evidence.py` and `backend/tests/test_promotion_regression.py`.

**Interfaces:** `assess_evidence(question, citations, query_plan=None)` uses `QueryPlan` for requirement lookup, while preserving existing callers.

- [x] Add failing tests with correct GPA rule, irrelevant policy, bare GPA mention, and year mismatch.
- [x] Confirm failures arise from the current false refusal or false support.
- [x] Implement requirement-specific evidence coverage from the plan.
- [x] Run focused tests to green.

### Task 3: Retrieval and answer integration

**Files:** Modify `backend/app/engine.py`; test `backend/tests/test_rag.py`.

**Interfaces:** `Engine.retrieve(..., query_plan=None)` uses plan terms and at most one extra vector query; `Engine.answer` builds one plan and passes it to retrieval and assessment.

- [x] Add failing integration tests for lexical terms, vector query count, and actual answer evidence gate.
- [x] Confirm expected failures.
- [x] Implement bounded query fusion, diagnostics, and shared plan flow.
- [x] Run focused tests to green.

### Task 4: Real document verification and project record

**Files:** Modify promotion regression fixture and documentation only as required; update `docs/evaluations/2026-09-26-promotion-regression-analysis.md`, `docs/mvp-progress.md`, `docs/project-roadmap.md`.

- [x] Run all backend tests and AI Infra offline statuses.
- [x] Run exact question in an isolated current-data snapshot, inspect answer and cited page.
- [x] Restart 8765 backend if tests and original PDF validation pass; check actual health and on-service answer behavior.
- [x] Record results, limitations, service version, and required build/reindex status.
