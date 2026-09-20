# Local Reranking, Retrieval Visualization, and Review Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional local GPU/CPU reranking stage with transparent similarity diagnostics, and add editable review notes that remain outside retrieval.

**Architecture:** Keep Chroma vector retrieval as the candidate generator and introduce a `Reranker` adapter between retrieval and answer generation. Return query diagnostics as transient response metadata. Store review notes and citation snapshots in independent SQLite tables and expose them through dedicated API routes and pages.

**Tech Stack:** FastAPI, SQLite, Chroma, Python local inference (CUDA when available, CPU fallback), React + TypeScript, React Router, SCSS Modules, existing Markdown renderer.

**Spec:** `docs/superpowers/specs/2026-09-19-rerank-review-notes-design.md`

## Global Constraints

- Notes are for reading and review only; they never enter Chroma, retrieval, or answer evidence.
- Reranking is optional and must fall back to vector results when unavailable or failing.
- Initial retrieval parameters are 20 candidates and 6 final evidence chunks, configurable on the backend.
- Distinguish vector similarity and rerank scores; neither is an answer-probability claim.
- Preserve stable document, chunk, and citation identifiers and current citation validation behavior.
- Follow the repository page structure: every page and component keeps its own `index.tsx`, `hooks/`, and `style/` directories.

## Review Focus

- CUDA unavailable or GPU memory exhausted: one retry with a smaller batch, then CPU or vector-only fallback with visible status.
- Reranker model load or inference failure: answer still completes using vector results and diagnostics identify the fallback.
- Empty, deleted, or not-ready documents: no stale candidates appear in final evidence or diagnostics.
- Citation source deleted after a note is saved: note keeps the snapshot and labels the live source deleted.
- Notes must never become retrievable evidence, including after editing or service restart.

---

### Task 1: Reranker adapter and configuration

**Files:**
- Create: `backend/app/reranker.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/store.py`
- Modify: `backend/requirements.in`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_reranker.py`

**Interfaces:**
- Produces `RerankResult(items: list[dict], provider: str, device: str, fallback: bool, error: str | None)`.
- Produces `Reranker.rank(question: str, candidates: list[dict], config: dict) -> RerankResult`.
- Produces settings fields for enabled state, model name, device preference, candidate limit, and evidence limit.

- [ ] **Step 1: Write failing adapter tests**

```python
def test_reranker_returns_ranked_scores_with_cpu_fake_model():
    result = Reranker(model=FakeCrossEncoder()).rank("缓存何时失效", candidates, config)
    assert [item["chunk_id"] for item in result.items] == ["b", "a"]
    assert result.device == "cpu"
    assert result.fallback is False

def test_reranker_reports_fallback_when_model_raises():
    result = Reranker(model=RaisingModel()).rank("问题", candidates, config)
    assert result.fallback is True
    assert result.error
    assert [item["chunk_id"] for item in result.items] == ["a", "b"]
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_reranker.py -q`

Expected: FAIL because the adapter and result contract do not yet exist.

- [ ] **Step 3: Implement the adapter**

Keep model loading lazy. Use a cross-encoder-compatible local model behind a small protocol so tests do not download weights. Select CUDA only when requested and available; catch load/inference errors and return original candidate order with `fallback=True`.

- [ ] **Step 4: Add persisted configuration and dependency pins**

Add the reranker settings using the existing settings migration pattern. Do not store model weights in SQLite. Add only the inference dependency required by the chosen adapter and keep the CPU path importable on machines without CUDA.

- [ ] **Step 5: Run the focused tests and the existing backend suite**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_reranker.py backend/tests/test_api.py -q`

Expected: PASS.

### Task 2: Retrieval pipeline and diagnostics metadata

**Files:**
- Modify: `backend/app/engine.py`
- Modify: `backend/app/vectors.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_rag.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- `Engine.retrieve(...) -> RetrievalResult` with `hits` and `diagnostics`.
- `diagnostics` contains `candidate_count`, `items`, `provider`, `device`, `fallback`, and `error`.
- SSE `sources` event includes final citations plus `retrieval_diagnostics`; existing clients remain valid when diagnostics are absent.

- [ ] **Step 1: Write failing retrieval tests**

```python
def test_retrieve_uses_rerank_and_limits_final_evidence(engine, monkeypatch):
    monkeypatch.setattr(engine.reranker, "rank", fake_rank)
    result = engine.retrieve("问题", kb_id, [], config)
    assert result.diagnostics["candidate_count"] == 20
    assert len(result.hits) == 6
    assert result.diagnostics["items"][0]["selected"] is True

def test_retrieve_fallback_exposes_vector_path(engine, monkeypatch):
    monkeypatch.setattr(engine.reranker, "rank", failing_rank)
    result = engine.retrieve("问题", kb_id, [], config)
    assert result.diagnostics["fallback"] is True
    assert result.diagnostics["provider"] == "vector"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_rag.py -q`

Expected: FAIL because retrieval currently returns only a list and has no reranker.

- [ ] **Step 3: Implement candidate expansion and ranking**

Request up to 20 vector candidates, remove ineligible/deleted documents, call `Reranker.rank`, select the first 6, and retain per-item vector score, rerank score, vector rank, rerank rank, and selected state. Preserve the old vector-only behavior when disabled.

- [ ] **Step 4: Thread diagnostics through SSE without changing citation validation**

Emit diagnostics with the `sources` event. Keep citation numbering based only on final selected hits, so the model cannot cite non-selected candidates.

- [ ] **Step 5: Run backend regression tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests -q`

Expected: all existing tests and new retrieval tests pass.

### Task 3: Similarity diagnostics UI

**Files:**
- Modify: `src/types/index.ts`
- Modify: `src/services/api.ts`
- Modify: `src/services/stream.ts`
- Modify: `src/pages/Chat/hooks/useChat.ts`
- Modify: `src/pages/Chat/index.tsx`
- Create: `src/pages/Chat/components/RetrievalDiagnostics/index.tsx`
- Create: `src/pages/Chat/components/RetrievalDiagnostics/style/index.module.scss`
- Test: `src/services/stream.test.ts`

**Interfaces:**
- `RetrievalDiagnostics` mirrors the backend metadata and is optional for backward compatibility.
- `RetrievalDiagnostics` component receives `{ diagnostics, onSelectSource }` and renders collapsed-by-default analysis.

- [ ] **Step 1: Write failing stream parsing test**

```ts
it('keeps retrieval diagnostics from the sources event', async () => {
  const result = await consumeSse(sourceWithDiagnostics)
  expect(result.diagnostics?.items[0].selected).toBe(true)
  expect(result.diagnostics?.fallback).toBe(false)
})
```

- [ ] **Step 2: Run the focused front-end test and verify failure**

Run: `npm test -- src/services/stream.test.ts`

Expected: FAIL because the SSE client drops diagnostics.

- [ ] **Step 3: Add typed metadata and parsing**

Extend DTOs and the stream event reducer without breaking old `sources` payloads. Store diagnostics per assistant message so expanding an older message simply shows “暂无检索分析”。

- [ ] **Step 4: Implement the collapsed diagnostics component**

Show candidate count, provider/device/fallback status, and a sortable list or compact horizontal bars. Label vector similarity and rerank score separately, emphasize selected evidence, and allow clicking a row to reuse the existing source selection behavior.

- [ ] **Step 5: Run front-end tests and build**

Run: `npm test -- src/services/stream.test.ts && npm run build`

Expected: PASS and a successful production build.

### Task 4: Review note persistence and API

**Files:**
- Modify: `backend/app/store.py`
- Modify: `backend/app/main.py`
- Create: `backend/app/notes.py`
- Test: `backend/tests/test_notes.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- `Store.create_note(title, question, content, citations) -> note`.
- `Store.notes(query: str | None) -> list[note]`.
- `Store.update_note(note_id, title, content) -> note` and `Store.delete_note(note_id)`.
- API routes: `GET /api/notes`, `POST /api/notes`, `GET /api/notes/{id}`, `PATCH /api/notes/{id}`, `DELETE /api/notes/{id}`.

- [ ] **Step 1: Write failing persistence tests**

```python
def test_note_keeps_citation_snapshot_after_document_delete(store):
    note = store.create_note("缓存复习", "问题", "回答", citations)
    store.delete_document(citations[0]["document_id"])
    saved = store.note(note["id"])
    assert saved["citations"][0]["text"] == citations[0]["text"]
    assert saved["citations"][0]["deleted"] is True

def test_note_is_not_in_retrieval(engine):
    note = store.create_note("标题", "问题", "独有内容", [])
    assert all(hit["document_id"] != note["id"] for hit in engine.retrieve("独有内容", kb_id, []).hits)
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_notes.py -q`

Expected: FAIL because note tables and routes do not exist.

- [ ] **Step 3: Add SQLite schema and store methods**

Create `notes` and `note_citations` tables in the existing schema migration path. Store citation snapshots as JSON or normalized rows, while resolving live document state only when reading a note. Do not insert notes into chunks or vector collections.

- [ ] **Step 4: Add validated API routes**

Require non-empty title/content, cap field lengths consistently with existing API validation, return 404 for unknown notes, and preserve citation snapshots on update.

- [ ] **Step 5: Run backend tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests -q`

Expected: PASS.

### Task 5: Review notes UI

**Files:**
- Modify: `src/app.tsx`
- Create: `src/pages/Notes/index.tsx`
- Create: `src/pages/Notes/hooks/useNotes.ts`
- Create: `src/pages/Notes/style/index.module.scss`
- Create: `src/pages/Notes/components/NoteEditor/index.tsx`
- Create: `src/pages/Notes/components/NoteEditor/style/index.module.scss`
- Modify: `src/pages/Chat/index.tsx`
- Modify: `src/pages/Chat/hooks/useChat.ts`
- Test: `src/services/api.test.ts`

**Interfaces:**
- Chat save action calls `POST /api/notes` only after a completed answer.
- Notes page consumes list/detail/update/delete API methods and existing Markdown renderer.

- [ ] **Step 1: Write failing API client tests**

```ts
it('creates a note from a completed assistant answer', async () => {
  await createNote({ title: '缓存复习', question: '问题', content: '回答', citations: [] })
  expect(fetchMock).toHaveBeenCalledWith('/api/notes', expect.objectContaining({ method: 'POST' }))
})
```

- [ ] **Step 2: Run focused test and verify failure**

Run: `npm test -- src/services/api.test.ts`

Expected: FAIL because note API methods and page components do not exist.

- [ ] **Step 3: Add API methods and save action**

Expose “保存为笔记” only on completed assistant messages with content. Submit the question, answer, and citation snapshots; show success/error feedback without altering the conversation.

- [ ] **Step 4: Build the notes page and editor**

Add a configured route and navigation entry. Render a list sorted by update time, a title search field, Markdown preview/edit controls, save/delete actions, and citation links that reuse document detail navigation. Mark deleted live sources clearly while retaining snapshots.

- [ ] **Step 5: Run front-end tests and build**

Run: `npm test && npm run build`

Expected: PASS and successful build.

### Task 6: End-to-end verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/mvp-progress.md`
- Create: `scripts/benchmark_rerank.py`
- Test: `backend/tests/test_rag.py`

- [ ] **Step 1: Add regression coverage for fallback and note isolation**

Run the existing controlled provider tests with reranking disabled, enabled, and forced to fail. Verify citations reference only selected hits and notes never change retrieval results.

- [ ] **Step 2: Add a local benchmark script**

Implement `scripts/benchmark_rerank.py` to run a supplied JSONL question set twice, report recall-at-6 proxy labels, latency, device, fallback count, and peak GPU memory when CUDA is available. Do not send content to external services.

- [ ] **Step 3: Run the complete verification set**

Run: `.venv\Scripts\python.exe -m pytest -q`; `npm test`; `npm run build`; `.venv\Scripts\python.exe scripts/verify_local.py`.

Expected: all tests pass, build succeeds, and local persistence/restart verification remains green.

- [ ] **Step 4: Update user documentation**

Document model download, CUDA/CPU behavior, candidate/evidence defaults, diagnostics interpretation, note isolation, and the benchmark command. State that similarity scores are relative diagnostics, not correctness probabilities.
