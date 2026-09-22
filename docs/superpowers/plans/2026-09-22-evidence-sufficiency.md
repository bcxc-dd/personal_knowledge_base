# Evidence Sufficiency and Refusal Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify each RAG question as supported, partial, or insufficient so the application answers only evidence-backed subquestions and refuses fully unsupported requests without calling the chat model.

**Architecture:** Add a deterministic backend `EvidenceAssessor` after retrieval. It splits only explicit multi-part questions into independently answerable core subquestions, scores each against the retrieved evidence using configured semantic and lexical gates, and returns a serializable assessment. `Engine.answer()` uses the assessment to filter citations and choose the model or fixed-refusal path; evaluation and the UI consume that same assessment instead of inferring sufficiency from whether retrieval returned chunks.

**Tech Stack:** Python 3 / FastAPI / SQLite / pytest; React 19 / TypeScript / Vite / Vitest.

**Spec:** `docs/superpowers/specs/2026-09-22-evidence-sufficiency-design.md`

## Global Constraints

- A single similarity number is never the sole support decision; it is one conservative gate in the composite rule.
- `partial` means at least one independently answerable core subquestion is sufficiently supported and at least one other core subquestion is not; a lone keyword hit does not qualify.
- `insufficient` skips `ModelClient.stream`, returns no answer citations, and still exposes diagnostic retrieval information.
- `partial` sends only evidence for sufficient subquestions to the model and requires an explicit `资料未支持的部分` section.
- Persist the assessment with assistant messages so conversation replay shows the same state.
- Preserve all 20 automatic AI Infra positive cases; do not change routing in `src/app.tsx` or place page business logic there.

## Review Focus

- A question containing two nouns but requesting one concept (for example, `AI Infra 包含计算和存储吗？`) must remain one core subquestion rather than becoming a false `partial`; cover in Task 1 parser tests.
- An exact lexical hit in a table of contents or incidental mention must not become sufficient without the semantic/evidence gate; cover in Task 1 evidence tests.
- A reranker fallback must not turn rank position into confidence; cover in Task 1 assessment tests.
- A fully unsupported question may still retrieve nearest chunks, but must make zero chat-model calls and persist empty citations; cover in Task 2 integration tests.
- Older SQLite databases lacking the new message metadata column must open and return a safe default assessment; cover in Task 2 migration tests.

---

### Task 1: Implement deterministic evidence assessment

**Files:**
- Create: `backend/app/evidence.py`
- Create: `backend/app/terms.py`
- Modify: `backend/app/engine.py:18-50`
- Test: `backend/tests/test_evidence.py`
- Modify: `backend/app/store.py:8-14`

**Interfaces:**
- Consumes: `question: str`, `selected: Sequence[dict]`, `diagnostics: dict`, and `config: dict` from `Engine.retrieve()`.
- Produces: `EvidenceAssessment(status: Literal['supported', 'partial', 'insufficient'], reason: str, supported_subquestions: tuple[SubquestionAssessment, ...], unsupported_subquestions: tuple[str, ...], evidence_chunk_ids: tuple[str, ...])` and `EvidenceAssessment.to_dict() -> dict`.
- Exposes: `assess_evidence(question, selected, diagnostics, config) -> EvidenceAssessment`; later tasks call this exact function.

- [ ] **Step 1: Write failing parser and assessment tests**

```python
from app.evidence import assess_evidence, split_core_subquestions


def hit(chunk_id, text, similarity=0.82, lexical=True):
    return {'chunk_id': chunk_id, 'text': text, 'vector_similarity': similarity,
            'lexical_match': lexical, 'selected': True}


def test_explicit_respective_question_is_split_into_independent_subquestions():
    assert split_core_subquestions('预填充和解码分别做什么？') == ('预填充做什么？', '解码做什么？')


def test_single_question_with_two_nouns_is_not_split():
    assert split_core_subquestions('AI Infra 包含计算和存储吗？') == ('AI Infra 包含计算和存储吗？',)


def test_partial_requires_one_supported_and_one_unsupported_core_subquestion():
    result = assess_evidence('什么是 AI Infra？它包含哪些主要部分？',
        [hit('definition', 'AI Infra 是支撑 AI 训练和推理的基础设施。')],
        {'fallback': False}, {'evidence_min_similarity': 0.55})
    assert result.status == 'partial'
    assert [part.question for part in result.supported_subquestions] == ['什么是 AI Infra？']
    assert result.unsupported_subquestions == ('它包含哪些主要部分？',)


def test_unrelated_nearest_neighbor_is_insufficient_even_when_retrieval_is_nonempty():
    result = assess_evidence('虚构缩写 ZZQ 是什么？',
        [hit('nearby', 'AI Infra 是支撑 AI 训练和推理的基础设施。', 0.84, False)],
        {'fallback': True}, {'evidence_min_similarity': 0.55})
    assert result.status == 'insufficient'
    assert result.evidence_chunk_ids == ()
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `pytest backend/tests/test_evidence.py -v`

Expected: FAIL because module `app.evidence` does not exist.

- [ ] **Step 3: Implement the smallest deterministic assessor**

```python
@dataclass(frozen=True)
class SubquestionAssessment:
    question: str
    supported: bool
    reason: str
    evidence_chunk_ids: tuple[str, ...]


def assess_evidence(question, selected, diagnostics, config):
    parts = tuple(_assess_part(part, selected, diagnostics, config)
                  for part in split_core_subquestions(question))
    supported = tuple(part for part in parts if part.supported)
    unsupported = tuple(part.question for part in parts if not part.supported)
    status = 'supported' if len(supported) == len(parts) else ('partial' if supported else 'insufficient')
    ids = tuple(dict.fromkeys(chunk_id for part in supported for chunk_id in part.evidence_chunk_ids))
    return EvidenceAssessment(status, _reason(status, parts), supported, unsupported, ids)
```

Move `acronym_terms`, `latin_technical_terms`, `chinese_technical_terms`, and `lexical_terms` from `engine.py` into `terms.py`; import and re-export `lexical_terms` in `engine.py` so existing retrieval tests keep their import path. This prevents an `evidence.py -> engine.py -> evidence.py` circular import. Implement `split_core_subquestions()` conservatively: split separate Chinese interrogative sentences (`？`, `?`, `。` followed by an interrogative clause), and the explicit `A 和 B 分别 <same predicate>` pattern. Do not split an ordinary conjunction. In `_assess_part`, import controlled terms from `terms.py`, require a meaningful lexical/text match when terms exist, and otherwise require at least one selected hit at or above `evidence_min_similarity`; accept reranker data only as a supplementary explanation and never as a confidence gate when `diagnostics['fallback']` is true. A sufficient part returns only the chunk IDs satisfying its gates.

Add `evidence_min_similarity: 0.55` to `DEFAULTS`; it is intentionally the one user-adjustable conservative threshold, while the composite conditions remain internal.

- [ ] **Step 4: Add boundary tests required by review focus**

```python
def test_incidental_lexical_mention_without_definition_or_support_is_insufficient():
    result = assess_evidence('什么是 MHA？', [hit('toc', '第 3 章介绍 MHA', 0.20)],
        {'fallback': False}, {'evidence_min_similarity': 0.55})
    assert result.status == 'insufficient'


def test_fallback_does_not_use_rerank_rank_as_evidence():
    result = assess_evidence('ZZQ 是什么？', [hit('top', '无关内容', 0.12, False)],
        {'fallback': True, 'provider': 'vector'}, {'evidence_min_similarity': 0.55})
    assert result.status == 'insufficient'
```

- [ ] **Step 5: Run Task 1 tests**

Run: `pytest backend/tests/test_evidence.py -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/app/evidence.py backend/app/terms.py backend/app/engine.py backend/app/store.py backend/tests/test_evidence.py
git commit -m "feat: assess retrieval evidence sufficiency"
```

### Task 2: Apply assessment in answering and persist it

**Files:**
- Modify: `backend/app/engine.py:15-16,261-312`
- Modify: `backend/app/store.py:25-31,153-163`
- Modify: `backend/tests/test_rag.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `assess_evidence()` from Task 1.
- Produces: `sources` event payload with `{citations, retrieval_diagnostics, evidence_assessment}` and `done` payload with that `evidence_assessment`.
- Persists: `messages.evidence_assessment` JSON, exposed by `Store.messages()` as `message['evidence_assessment']`.

- [ ] **Step 1: Write failing engine tests for all three answer branches**

```python
def test_insufficient_answer_skips_chat_model_and_returns_no_citations(tmp_path):
    engine = make_engine(tmp_path)
    engine.retrieve = lambda *args, **kwargs: RetrievalResult(
        [{'chunk_id': 'near', 'document_id': 'doc', 'text': '无关内容', 'name': 'x', 'location': '1', 'vector_similarity': .2}],
        {'items': [], 'fallback': True})
    calls = []
    engine.models.stream = lambda *args: calls.append(args)
    events = answer_events(engine, 'ZZQ 是什么？', 'default', [], None)
    done = next(event['data'] for event in events if event['event'] == 'done')
    assert calls == []
    assert done['evidence_assessment']['status'] == 'insufficient'
    assert done['citations'] == []


def test_partial_answer_streams_only_supported_evidence_and_names_gap(tmp_path):
    engine = make_engine(tmp_path)
    definition = {'chunk_id': 'definition', 'document_id': 'doc', 'name': 'infra.txt',
                  'location': '第 11 页', 'text': 'AI Infra 是支撑训练和推理的基础设施。',
                  'vector_similarity': .90, 'lexical_match': True}
    nearby = {'chunk_id': 'nearby', 'document_id': 'doc', 'name': 'infra.txt',
              'location': '第 12 页', 'text': '无关的临近段落。', 'vector_similarity': .20}
    engine.retrieve = lambda *args, **kwargs: RetrievalResult([definition, nearby],
        {'items': [definition, nearby], 'fallback': False})
    captured = []
    async def stream(messages, config):
        captured.extend(messages)
        yield '仅说明定义。[1]\n\n## 资料未支持的部分\n- 它包含哪些主要部分？'
    engine.models.stream = stream
    events = answer_events(engine, '什么是 AI Infra？它包含哪些主要部分？', 'default', [], None)
    sources = next(event['data'] for event in events if event['event'] == 'sources')
    assert sources['evidence_assessment']['status'] == 'partial'
    assert [item['chunk_id'] for item in sources['citations']] == ['definition']
    assert 'AI Infra 是支撑训练和推理的基础设施。' in captured[-1]['content']
    assert '无关的临近段落。' not in captured[-1]['content']
    assert '资料未支持的部分' in captured[0]['content']
```

Add a supported-case assertion that the normal model branch still streams and emits `status == 'supported'`.

- [ ] **Step 2: Run the branch tests to verify they fail**

Run: `pytest backend/tests/test_rag.py -k "insufficient_answer or partial_answer or supported_answer" -v`

Expected: FAIL because answer events do not yet contain `evidence_assessment` and the model is still called for nearest-neighbor results.

- [ ] **Step 3: Integrate assessment and branch-specific citation handling**

```python
assessment = assess_evidence(normalized_question, hits, retrieved.diagnostics, config)
retrieved.diagnostics['evidence_assessment'] = assessment.to_dict()
answer_hits = [hit for hit in hits if hit['chunk_id'] in assessment.evidence_chunk_ids]
citations = [{**hit, 'id': index + 1} for index, hit in enumerate(answer_hits)]
yield {'event': 'sources', 'data': {
    'citations': citations, 'retrieval_diagnostics': retrieved.diagnostics,
    'evidence_assessment': assessment.to_dict(),
}}
if assessment.status == 'insufficient':
    content = '现有资料不足以回答这个问题。' + _format_assessment_reason(assessment)
else:
    messages = _answer_messages(normalized_question, evidence, history,
        partial=assessment.status == 'partial',
        unsupported=assessment.unsupported_subquestions)
```

For `partial`, `_answer_messages()` must instruct the model to answer only the supported subquestions from the provided citations, then add a `## 资料未支持的部分` heading and list `assessment.unsupported_subquestions`; it must not let the model invent missing content. For `supported`, retain the current system prompt and citation validation. Preserve raw retrieval items in diagnostics in every state, but send empty answer citations for `insufficient`.

Extend the SQLite initialization safely: after `CREATE TABLE IF NOT EXISTS messages`, inspect `PRAGMA table_info(messages)` and run `ALTER TABLE messages ADD COLUMN evidence_assessment TEXT NOT NULL DEFAULT '{}'` only when absent. Change the exact signature to `add_message(self, conversation_id, role, content, citations=None, status='complete', evidence_assessment=None)` and parse the field in `messages()`, returning `{}` for existing/null malformed data. Pass the final assessment into assistant persistence in both complete and interrupted paths.

- [ ] **Step 4: Add migration, API stream, and history replay tests**

```python
def test_store_migrates_existing_messages_table_without_assessment_column(tmp_path):
    db = sqlite3.connect(tmp_path / 'knowledge.sqlite3')
    db.execute('CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, '
               'content TEXT, citations TEXT, status TEXT, created_at TEXT)')
    db.execute("INSERT INTO messages VALUES ('m1', 'c1', 'assistant', '旧回答', '[]', 'complete', 'now')")
    db.commit(); db.close()
    assert Store(tmp_path).messages('c1')[0]['evidence_assessment'] == {}


def test_chat_api_returns_insufficient_assessment_with_empty_sources(tmp_path):
    client, engine = client_for(tmp_path)
    engine.retrieve = lambda *args, **kwargs: RetrievalResult(
        [{'chunk_id': 'near', 'document_id': 'doc', 'text': '无关内容', 'name': 'x',
          'location': '1', 'vector_similarity': .1}], {'items': [], 'fallback': True})
    response = client.post('/api/chat', json={'question': 'ZZQ 是什么？', 'kb_id': 'default', 'document_ids': []})
    assert '"status": "insufficient"' in response.text
    assert '"citations": []' in response.text
```

Use actual SQLite setup and the existing `TestClient`; do not mock the storage migration. In the existing persistence test, assert the saved assistant message has `evidence_assessment['status'] == 'supported'`.

- [ ] **Step 5: Run backend branch and API tests**

Run: `pytest backend/tests/test_rag.py backend/tests/test_api.py -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/app/engine.py backend/app/store.py backend/tests/test_rag.py backend/tests/test_api.py
git commit -m "feat: refuse answers without sufficient evidence"
```

### Task 3: Expose threshold through validated settings

**Files:**
- Modify: `backend/app/main.py:21-34`
- Modify: `backend/tests/test_api.py`
- Modify: `src/types/index.ts:9-17`
- Modify: `src/pages/Settings/index.tsx:23`

**Interfaces:**
- Consumes: persisted `evidence_min_similarity` default from Task 1.
- Produces: `GET /api/settings` and `PUT /api/settings` field `evidence_min_similarity: number`, constrained to `0.0 <= value <= 1.0`.
- Produces: `ModelSettings['evidence_min_similarity']` and a number input in the Settings page.

- [ ] **Step 1: Write a failing settings validation test**

```python
def test_evidence_similarity_threshold_is_saved_and_range_validated(tmp_path):
    client, _ = client_for(tmp_path)
    with client:
        saved = client.put('/api/settings', json={'evidence_min_similarity': 0.63})
        assert saved.status_code == 200
        assert saved.json()['evidence_min_similarity'] == 0.63
        assert client.put('/api/settings', json={'evidence_min_similarity': 1.01}).status_code == 422
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest backend/tests/test_api.py::test_evidence_similarity_threshold_is_saved_and_range_validated -v`

Expected: FAIL because `SettingsInput` ignores the new field.

- [ ] **Step 3: Add API, types, and a concise user-facing setting**

```python
class SettingsInput(BaseModel):
    evidence_min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
```

```tsx
<label>最低相关性阈值
  <input type="number" min="0" max="1" step="0.01"
    value={c.evidence_min_similarity}
    onChange={e => m.change('evidence_min_similarity', Number(e.target.value))} />
  <small>用于拦截明显无关的近邻结果；系统仍会结合术语和证据覆盖判断。</small>
</label>
```

Place this in a new “回答证据” settings card, not the reranker card. Update the TypeScript interface exactly with `evidence_min_similarity: number`; the existing generic `change` hook requires no structural change.

- [ ] **Step 4: Run backend validation and frontend compilation**

Run: `pytest backend/tests/test_api.py::test_evidence_similarity_threshold_is_saved_and_range_validated -v; npm run build`

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add backend/app/main.py backend/tests/test_api.py src/types/index.ts src/pages/Settings/index.tsx
git commit -m "feat: configure evidence relevance threshold"
```

### Task 4: Make evaluation assess support rather than raw retrieval emptiness

**Files:**
- Modify: `backend/app/evaluation.py:13-25,108-170`
- Modify: `scripts/evaluate_retrieval.py:10-75`
- Modify: `backend/tests/test_evaluation.py`
- Modify: `docs/evaluations/ai-infra-retrieval-v1.json`
- Create: `docs/evaluations/evidence-sufficiency-v1.json`
- Modify: `docs/evaluations/ai-infra-retrieval-v1-baseline.md`

**Interfaces:**
- Consumes: `assessment: EvidenceAssessment` from Task 1 for every suite case.
- Produces: case result fields `evidence_status`, `unsupported_subquestions`, and assessment-aware pass/fail; summary fields `false_refusal_rate`, `partial_handling`, and `insufficient_refusal_rate`.
- Produces: calibration report recording default threshold and per-case verdicts.

- [ ] **Step 1: Write failing assessment-aware evaluation tests**

```python
def test_insufficient_diagnostic_passes_when_nearest_chunk_is_classified_insufficient():
    case = EvaluationCase('q25', 'ZZQ 是什么？', 'insufficient_evidence', (), (), (), True, 'diagnostic')
    assessment = {'status': 'insufficient', 'unsupported_subquestions': ['ZZQ 是什么？']}
    result = evaluate_case(case, [{'chunk_id': 'near'}], [], [], assessment)
    assert result['passed'] is True
    assert result['evidence_status'] == 'insufficient'


def test_positive_case_is_a_false_refusal_when_assessment_is_insufficient():
    result = evaluate_case(mha_case(), [], [], [], {'status': 'insufficient', 'unsupported_subquestions': ['MHA 是什么？']})
    assert result['failure_stage'] == 'false_refusal'
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest backend/tests/test_evaluation.py -k "assessment or false_refusal" -v`

Expected: FAIL because `evaluate_case` has no assessment argument.

- [ ] **Step 3: Integrate the shared assessor into runner and summaries**

```python
assessment = assess_evidence(case.question, list(retrieved), retrieved.diagnostics, engine.store.settings())
result = evaluate_case(case, list(retrieved), retrieved.diagnostics.get('items', []), indexed_chunks,
                       assessment.to_dict())
```

Update `evaluate_case()` so `expect_no_evidence=True` passes only when `assessment['status'] == 'insufficient'`, even if retrieval returned diagnostics. For positive automatic cases, fail as `false_refusal` before retrieval-anchor checks when the status is `insufficient`. For partial calibration cases, require expected supported and unsupported subquestions explicitly; extend `EvaluationCase`/JSON validation with optional non-empty `expected_evidence_status`, `expected_supported_subquestions`, and `expected_unsupported_subquestions` fields only for the new cases.

Append three calibration cases without changing the existing 25-case suite contract: create `docs/evaluations/evidence-sufficiency-v1.json` with one fully unrelated question, one single accidental-neighbor probe, and one two-part question with exactly one expected supported subquestion. Make the runner accept this suite’s document binding and validate its stated case count rather than hardcoding 25 globally. Record the actual chosen threshold and all three new expected verdicts in `ai-infra-retrieval-v1-baseline.md` after running against the user’s indexed PDF.

- [ ] **Step 4: Run unit tests and the no-answer calibration command**

Run: `pytest backend/tests/test_evaluation.py -v; python scripts/evaluate_retrieval.py --suite docs/evaluations/ai-infra-retrieval-v1.json --output test-results/ai-infra-evidence.json`

Expected: unit tests PASS; runner creates JSON with all 20 automatic positives supported and diagnostic refusal results. If the local indexed document is unavailable, leave no fabricated report, report the blocker, and run the deterministic unit tests only.

- [ ] **Step 5: Commit Task 4**

```bash
git add backend/app/evaluation.py scripts/evaluate_retrieval.py backend/tests/test_evaluation.py docs/evaluations
git commit -m "test: calibrate evidence sufficiency evaluation"
```

### Task 5: Render assessment state and diagnostics in chat

**Files:**
- Modify: `src/types/index.ts:8-11`
- Modify: `src/pages/Chat/hooks/useChat.ts:43-53`
- Modify: `src/pages/Chat/components/RetrievalDiagnostics/index.tsx`
- Modify: `src/pages/Chat/components/RetrievalDiagnostics/style/index.module.scss`
- Modify: `src/pages/Chat/index.tsx:22`
- Test: `src/services/stream.test.ts`

**Interfaces:**
- Consumes: `EvidenceAssessment` received in `sources` and `done` SSE payloads or loaded in persisted `Message` data.
- Produces: `Message['evidence_assessment']` and visible labels for `supported`, `partial`, and `insufficient`.

- [ ] **Step 1: Write a failing status-label test**

```ts
import { evidenceStatusLabel } from './index';

it('labels insufficient diagnostic candidates as non-sources', () => {
  expect(evidenceStatusLabel({
    status: 'insufficient', reason: '没有满足条件的证据。',
    supported_subquestions: [], unsupported_subquestions: ['ZZQ 是什么？'],
  })).toBe('资料不足：候选片段仅用于诊断，不作为回答来源');
});
```

Create this test as `src/pages/Chat/components/RetrievalDiagnostics/index.test.ts` and keep the existing stream parser tests unchanged; no browser-testing dependency is needed.

- [ ] **Step 2: Run it to verify it fails if event payload processing is not typed**

Run: `npm test -- src/pages/Chat/components/RetrievalDiagnostics/index.test.ts`

Expected: FAIL because `evidenceStatusLabel` is not exported.

- [ ] **Step 3: Add message types and UI behavior**

```ts
export interface EvidenceAssessment {
  status: 'supported' | 'partial' | 'insufficient';
  reason: string;
  supported_subquestions: Array<{ question: string; reason: string; evidence_chunk_ids: string[] }>;
  unsupported_subquestions: string[];
}
export interface Message {
  id: string; role: 'user' | 'assistant'; content: string; citations: Citation[];
  status: string; retrieval_diagnostics?: RetrievalDiagnostics;
  evidence_assessment?: EvidenceAssessment;
}
```

In `useChat`, copy `data.evidence_assessment` into the pending message on both `sources` and `done`. Export `evidenceStatusLabel(assessment?: EvidenceAssessment): string` from `RetrievalDiagnostics/index.tsx`, returning the exact test string for `insufficient`, `部分资料支持` for `partial`, and `资料充分支持` for `supported`. In `Chat/index.tsx`, render a compact `资料不足` notice containing the backend reason for `insufficient`; for `partial`, rely on the mandated model heading and add a small `部分资料支持` badge. Update `RetrievalDiagnostics` to show the assessment status/reason before its candidate list; it must still render when candidate items exist but citations are empty, and describe candidates as diagnostics rather than sources.

- [ ] **Step 4: Run frontend tests and production build**

Run: `npm test; npm run build`

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add src/types/index.ts src/pages/Chat
git commit -m "feat: show evidence sufficiency in chat"
```

### Task 6: Verify the complete feature and update project documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/evaluations/ai-infra-retrieval-v1-baseline.md`

**Interfaces:**
- Consumes: completed backend, evaluator, and UI feature from Tasks 1–5.
- Produces: documented behavior and reproducible verification results without committing generated `test-results/` artifacts.

- [ ] **Step 1: Write documentation acceptance checklist before final verification**

```markdown
## 证据充分度

- `supported`：资料充分支持所有核心子问题。
- `partial`：仅回答有充分证据的核心子问题，并列出资料未支持的部分。
- `insufficient`：不调用回答模型，直接提示资料不足。
```

Add this to README with the Settings location and the evaluator command. In the baseline report, add a table with the three metric names, numerator/denominator, threshold value, suite version, and run date; never claim a result if no matching indexed PDF was available.

- [ ] **Step 2: Run all automated verification**

Run: `pytest -q; npm test; npm run build`

Expected: all backend tests PASS, all frontend tests PASS, and production build succeeds.

- [ ] **Step 3: Run final static and repository checks**

Run: `git diff --check; git status --short; git log --oneline -6`

Expected: no whitespace errors; generated `test-results/` remains untracked/ignored; only intended documentation changes are present before commit.

- [ ] **Step 4: Commit Task 6**

```bash
git add README.md docs/evaluations/ai-infra-retrieval-v1-baseline.md
git commit -m "docs: document evidence sufficiency behavior"
```
