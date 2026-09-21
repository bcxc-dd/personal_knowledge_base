# AI-Infra Retrieval Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable, AI-Infra-only retrieval evaluation suite that produces actionable diagnostics, supports an explicit answer-generation pass, and protects confirmed retrieval fixes with fast regression tests.

**Architecture:** A pure `app.evaluation` module owns the versioned suite schema, validation, matching, diagnostic classification, and report aggregation. A thin `scripts/evaluate_retrieval.py` adapter opens the existing local `Engine`, validates the real indexed PDF, calls `Engine.retrieve`, and writes JSON reports under the already ignored `test-results/` directory. The suite stays in `docs/evaluations/` so it is reviewable independently of runtime data.

**Tech Stack:** Python 3.10+, FastAPI application modules, SQLite/Chroma through the existing `Engine`, `pytest`, JSON, `asyncio`.

**Spec:** `docs/superpowers/specs/2026-09-21-ai-infra-retrieval-evaluation-design.md`

## Global Constraints

- Evaluate only the locally uploaded document named `AI-Infra-Book.pdf`; do not include the sample Markdown or Mamba papers.
- The suite contains exactly 25 Chinese learning-understanding questions across definition, mechanism, comparison, summary, acronym, and insufficient-evidence categories.
- Bind every case to the PDF SHA-256 recorded in the local document row; reject a missing, changed, non-ready, or fingerprint-mismatched index before scoring.
- The default command runs retrieval only and must not invoke the configured Chat Completions provider.
- Answer generation is opt-in and sends only a question plus retrieved evidence, never the whole PDF.
- Reports are written under ignored `test-results/`; no keys, user conversations, or generated answers are committed.
- Keep normal `pytest` tests deterministic with fixtures; the full real-PDF suite is a manual/release check, not part of default `pytest`.
- Preserve the existing MHA exact-acronym retrieval regression.

## Review Focus

- Changed AI-Infra PDF with the same filename: abort before evaluating, stating both expected and actual SHA-256; test in Task 2.
- A target anchor exists in SQLite but is absent from all retrieval candidates: classify it as `not_recalled`, rather than a ranking failure; test in Task 3.
- A target occurs in candidates but not among the selected evidence: classify it as `not_selected`; test in Task 3.
- A no-evidence question unexpectedly returns selected evidence: mark it failed instead of treating empty expectations as automatically successful; test in Task 3.
- `--with-answer` is absent: never call `Engine.answer`; test in Task 4.

---

## File Structure

- `backend/app/evaluation.py` — JSON suite parsing, typed case/result structures, evidence matching, diagnostic classification, aggregation, and JSON-safe report creation. It has no filesystem, Chroma, or provider dependency.
- `backend/tests/test_evaluation.py` — deterministic unit tests for suite validation, result classification, aggregation, and answer-mode behavior.
- `docs/evaluations/ai-infra-retrieval-v1.json` — committed, human-reviewable 25-case Chinese learning suite and its expected document hash.
- `scripts/evaluate_retrieval.py` — CLI adapter for the user’s local `data/` directory; validates document/index preconditions, executes the suite, optionally obtains answers, and writes a timestamped report.
- `README.md` — concise command examples, output location, provider-cost warning for answer mode, and manual-review workflow.
- `backend/tests/test_rag.py` — only if Task 5 confirms a production retrieval strategy change; contains the smallest deterministic regression fixture for the confirmed failure.
- `backend/app/engine.py` — only if Task 5 confirms a production retrieval strategy change; receives the smallest strategy change justified by the baseline report.

## Task 1: Define the Evaluation Domain Model and Suite Validation

**Files:**
- Create: `backend/app/evaluation.py`
- Create: `backend/tests/test_evaluation.py`

**Interfaces:**
- Consumes: JSON objects with top-level `version`, `document_name`, `document_sha256`, and `cases`.
- Produces: `EvaluationSuite`, `EvaluationCase`, `load_suite(path: Path) -> EvaluationSuite`, and `validate_suite(suite: EvaluationSuite) -> None`.
- `EvaluationCase` fields: `id: str`, `question: str`, `category: str`, `expected_locations: tuple[str, ...]`, `expected_terms: tuple[str, ...]`, `must_cover: tuple[str, ...]`, `expect_no_evidence: bool`.

- [ ] **Step 1: Write failing validation tests**

```python
from pathlib import Path
import json
import pytest
from app.evaluation import load_suite


def write_suite(path, cases, sha='a' * 64):
    path.write_text(json.dumps({
        'version': 1, 'document_name': 'AI-Infra-Book.pdf',
        'document_sha256': sha, 'cases': cases,
    }, ensure_ascii=False), encoding='utf-8')


def test_load_suite_requires_exactly_25_unique_chinese_cases(tmp_path):
    path = tmp_path / 'suite.json'
    write_suite(path, [{'id': 'q1', 'question': '什么是 AI Infra？', 'category': 'definition',
                        'expected_locations': ['第 11 页'], 'expected_terms': ['AI Infra'],
                        'must_cover': ['基础设施'], 'expect_no_evidence': False}] * 25)
    with pytest.raises(ValueError, match='唯一'):
        load_suite(path)


def test_load_suite_rejects_non_sha256_and_invalid_no_evidence_case(tmp_path):
    path = tmp_path / 'suite.json'
    write_suite(path, [{'id': f'q{i}', 'question': '测试问题', 'category': 'definition',
                        'expected_locations': ['第 1 页'], 'expected_terms': [],
                        'must_cover': [], 'expect_no_evidence': False} for i in range(25)], sha='bad')
    with pytest.raises(ValueError, match='SHA-256'):
        load_suite(path)
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_evaluation.py -q`

Expected: FAIL because `app.evaluation` does not exist.

- [ ] **Step 3: Implement the immutable suite types and strict loader**

```python
@dataclass(frozen=True)
class EvaluationCase:
    id: str
    question: str
    category: str
    expected_locations: tuple[str, ...]
    expected_terms: tuple[str, ...]
    must_cover: tuple[str, ...]
    expect_no_evidence: bool


@dataclass(frozen=True)
class EvaluationSuite:
    version: int
    document_name: str
    document_sha256: str
    cases: tuple[EvaluationCase, ...]


def load_suite(path: Path) -> EvaluationSuite:
    raw = json.loads(path.read_text(encoding='utf-8'))
    suite = EvaluationSuite(...)
    validate_suite(suite)
    return suite
```

Require version `1`, `AI-Infra-Book.pdf`, a lowercase 64-character SHA-256, exactly 25 unique IDs, nonempty Chinese questions, allowed categories (`definition`, `mechanism`, `comparison`, `summary`, `acronym`, `insufficient_evidence`), and consistent expectations: normal cases require at least one location or term; insufficient-evidence cases require no expected locations or terms and set `expect_no_evidence` to true.

- [ ] **Step 4: Extend tests for valid data and constraint failures**

```python
def test_load_suite_returns_immutable_cases_for_valid_suite(tmp_path):
    path = tmp_path / 'suite.json'
    cases = [
        {'id': f'q{i:02}', 'question': f'解释概念{i}', 'category': 'definition',
         'expected_locations': ['第 11 页'], 'expected_terms': ['概念'],
         'must_cover': ['概念'], 'expect_no_evidence': False}
        for i in range(24)
    ] + [{'id': 'q25', 'question': '书中是否提供某未出现指标？',
          'category': 'insufficient_evidence', 'expected_locations': [],
          'expected_terms': [], 'must_cover': [], 'expect_no_evidence': True}]
    write_suite(path, cases)
    suite = load_suite(path)
    assert len(suite.cases) == 25
    assert suite.cases[-1].expect_no_evidence is True
```

- [ ] **Step 5: Run focused tests and commit**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_evaluation.py -q`

Expected: PASS.

```powershell
git add backend/app/evaluation.py backend/tests/test_evaluation.py
git commit -m "feat: add retrieval evaluation suite validation"
```

## Task 2: Commit the AI-Infra Learning Evaluation Suite

**Files:**
- Create: `docs/evaluations/ai-infra-retrieval-v1.json`
- Modify: `backend/tests/test_evaluation.py`

**Interfaces:**
- Consumes: `load_suite(Path('docs/evaluations/ai-infra-retrieval-v1.json'))` from Task 1.
- Produces: one versioned 25-case suite whose `document_sha256` is copied from the local SQLite `documents.hash` row for `AI-Infra-Book.pdf` at authoring time.

- [ ] **Step 1: Write a failing suite-content test**

```python
def test_committed_ai_infra_suite_has_balanced_learning_coverage():
    suite = load_suite(Path('docs/evaluations/ai-infra-retrieval-v1.json'))
    categories = {case.category for case in suite.cases}
    assert len(suite.cases) == 25
    assert categories == {'definition', 'mechanism', 'comparison', 'summary', 'acronym', 'insufficient_evidence'}
    assert all('AI-Infra-Book.pdf' == suite.document_name for _ in suite.cases)
```

- [ ] **Step 2: Run the test to verify failure**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_evaluation.py::test_committed_ai_infra_suite_has_balanced_learning_coverage -q`

Expected: FAIL because the committed suite does not exist.

- [ ] **Step 3: Create the 25 reviewed cases and bind the real PDF hash**

Read the local SQLite document row without printing any settings or secrets:

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
from pathlib import Path
import sys
sys.path.insert(0, 'backend')
from app.store import Store
doc = next(d for d in Store(Path('data')).documents('default') if d['name'] == 'AI-Infra-Book.pdf')
print(doc['hash'])
'@ | .venv\Scripts\python.exe -
```

Create JSON entries using that exact hash and the following question inventory. Set location anchors after confirming the current extracted chunks; preserve the wording and category so future reports remain comparable.

| IDs | Category | Required questions / coverage |
| --- | --- | --- |
| q01–q05 | definition | AI Infra 的含义与组成；上下文；推理实例；预填充与解码；KV 缓存。 |
| q06–q10 | mechanism | 一次生成请求的处理过程；权重驻留为何重要；从任务到硬件的六层；数量级估算如何约束设计；长上下文为何改变资源需求。 |
| q11–q14 | comparison | 训练与推理的差异；prefill 与 decode 的负载差异；CPU 主存、GPU 显存与片上存储的职责；可编程性变化前后的应用表达。 |
| q15–q18 | summary | 第 1 章核心观点；第 2 章学习目标；第 8 章推理优化主线；第 10 章训练系统主线。 |
| q19–q22 | acronym | MHA；GQA；MQA；KV cache 的英文缩写、含义与和注意力/上下文的关系。 |
| q23–q25 | insufficient_evidence | 书中未给出的特定公司内部 GPU 集群数量；未出现的某产品精确单价；未定义的虚构缩写 `ZZQ`。 |

For q01–q05 use page anchors in the Chapter 1/2 chunks, including page 11 for AI Infra/context, page 14 for request/prefill/decode/KV cache, and page 44 for MHA. For every other normal case, inspect its matching chunks and store the actual `第 N 页` locations plus the 1–3 terms that demonstrate the required concept. Ensure `must_cover` names the concepts a human reviewer should look for, without treating it as an automatic semantic grader.

- [ ] **Step 4: Run the committed-suite test and JSON validation**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_evaluation.py -q`

Expected: PASS, including strict schema validation and all six categories.

- [ ] **Step 5: Commit the reviewed baseline suite**

```powershell
git add docs/evaluations/ai-infra-retrieval-v1.json backend/tests/test_evaluation.py
git commit -m "docs: add AI Infra retrieval evaluation suite"
```

## Task 3: Implement Retrieval Matching, Failure Classification, and Report Aggregation

**Files:**
- Modify: `backend/app/evaluation.py`
- Modify: `backend/tests/test_evaluation.py`

**Interfaces:**
- Consumes: `EvaluationCase`, `selected: list[dict]`, `candidates: list[dict]`, and `indexed_chunks: list[dict]`.
- Produces: `evaluate_case(case, selected, candidates, indexed_chunks) -> dict` with `passed`, `match_reason`, `failure_stage`, `selected_ids`, `candidate_ids`, and selected evidence summaries; `summarize(results) -> dict` with total/pass counts and category counts.

- [ ] **Step 1: Write failing classification tests**

```python
from app.evaluation import evaluate_case

def case(**overrides):
    return EvaluationCase('q1', '什么是 MHA？', 'acronym', ('第 44 页',), ('MHA',), ('多头注意力',), False)

def test_classifies_anchor_existing_but_not_recalled():
    result = evaluate_case(case(), selected=[], candidates=[], indexed_chunks=[
        {'chunk_id': 'target', 'location': '第 44 页', 'text': 'MHA 定义'}])
    assert result['passed'] is False
    assert result['failure_stage'] == 'not_recalled'

def test_classifies_candidate_ranked_out_of_final_evidence():
    target = {'chunk_id': 'target', 'location': '第 44 页', 'text': 'MHA 定义'}
    result = evaluate_case(case(), selected=[], candidates=[target], indexed_chunks=[target])
    assert result['failure_stage'] == 'not_selected'
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_evaluation.py -q`

Expected: FAIL because `evaluate_case` does not exist.

- [ ] **Step 3: Implement matching and diagnostic rules**

Use a case-insensitive term predicate and exact normalized location predicate. A normal case passes if at least one selected item matches an expected location or contains an expected term. An insufficient-evidence case passes only when `selected` is empty. Determine the failure stage in this order:

```python
if case.expect_no_evidence:
    return 'unexpected_evidence' if selected else None
if not any(matches(case, item) for item in indexed_chunks):
    return 'not_parsed'
if not any(matches(case, item) for item in candidates):
    return 'not_recalled'
if not any(matches(case, item) for item in selected):
    return 'not_selected'
return None
```

Copy only safe evidence fields (`chunk_id`, `document_id`, `name`, `location`, `text`, `vector_rank`, `vector_similarity`, `lexical_match`, `rerank_rank`, `rerank_score`, `selected`) into report records. Preserve the existing retriever diagnostics under a separate `retrieval_diagnostics` object.

- [ ] **Step 4: Add aggregation and edge-case tests**

```python
def test_no_evidence_case_fails_when_retrieval_returns_a_chunk():
    no_evidence = EvaluationCase('q25', 'ZZQ 是什么？', 'insufficient_evidence', (), (), (), True)
    result = evaluate_case(no_evidence, [{'chunk_id': 'x', 'location': '第 11 页', 'text': 'AI Infra'}], [], [])
    assert result['passed'] is False
    assert result['failure_stage'] == 'unexpected_evidence'

def test_summary_groups_pass_rate_by_category():
    summary = summarize([{'category': 'definition', 'passed': True}, {'category': 'definition', 'passed': False}])
    assert summary['total'] == 2
    assert summary['passed'] == 1
    assert summary['by_category']['definition'] == {'total': 2, 'passed': 1}
```

- [ ] **Step 5: Run tests and commit**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_evaluation.py -q`

Expected: PASS.

```powershell
git add backend/app/evaluation.py backend/tests/test_evaluation.py
git commit -m "feat: add retrieval evaluation diagnostics"
```

## Task 4: Add the Local Evaluation CLI and Explicit Answer Mode

**Files:**
- Create: `scripts/evaluate_retrieval.py`
- Modify: `backend/tests/test_evaluation.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `--suite docs/evaluations/ai-infra-retrieval-v1.json`, optional `--data-dir`, optional `--output`, and optional `--with-answer` CLI flags.
- Produces: exit code `0` with a timestamped JSON report when all preconditions hold; exit code `2` and a Chinese actionable message on precondition or suite errors.
- Imports: `Engine`, `fingerprint`, `load_suite`, `evaluate_case`, `summarize`.

- [ ] **Step 1: Write failing CLI tests with a fake engine**

```python
def test_default_run_never_calls_answer(monkeypatch, tmp_path):
    engine = FakeEngine(ready_ai_infra_document())
    monkeypatch.setattr(evaluate_retrieval, 'open_engine', lambda _: engine)
    exit_code = evaluate_retrieval.main(['--suite', str(valid_suite_path(tmp_path)), '--output', str(tmp_path / 'report.json')])
    assert exit_code == 0
    assert engine.answer_calls == 0

def test_changed_document_hash_returns_exit_code_2(monkeypatch, tmp_path, capsys):
    engine = FakeEngine({**ready_ai_infra_document(), 'hash': 'b' * 64})
    monkeypatch.setattr(evaluate_retrieval, 'open_engine', lambda _: engine)
    assert evaluate_retrieval.main(['--suite', str(valid_suite_path(tmp_path))]) == 2
    assert 'SHA-256' in capsys.readouterr().err
```

`FakeEngine` must expose `store.documents`, `store.chunks`, `store.settings`, `retrieve`, and async `answer`; make `answer` increment `answer_calls` before yielding a `done` event. Do not load the real local embedding model in these tests.

- [ ] **Step 2: Run CLI tests to verify failure**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_evaluation.py -q`

Expected: FAIL because `scripts/evaluate_retrieval.py` does not exist.

- [ ] **Step 3: Implement preflight, retrieval execution, and JSON output**

Implement `main(argv: list[str] | None = None) -> int` using `argparse`. Resolve the default data directory from `RAG_DATA_DIR` or `data`, find exactly one non-deleted document with the suite name, compare its `hash`, require `status == 'ready'`, and require `fingerprint(document_settings) == document['fingerprint']`. For each case call:

```python
retrieved = engine.retrieve(case.question, document['kb_id'], [document['id']])
result = evaluate_case(case, list(retrieved), retrieved.diagnostics['items'], engine.store.chunks(document['id']))
result['retrieval_diagnostics'] = retrieved.diagnostics
```

Write a UTF-8 JSON object containing suite metadata, document ID/hash, timestamp, `summary`, and `results`. Default output is `test-results/ai-infra-retrieval-YYYYMMDD-HHMMSS.json`; create its parent directory. Never include settings or keys in the object.

- [ ] **Step 4: Implement explicit answer generation and its tests**

When and only when `--with-answer` is supplied, collect `Engine.answer(case.question, document['kb_id'], [document['id']], None)` with `asyncio.run`, extract the `done` event’s `content`, `citations`, and `warning`, and attach an `answer_review` object:

```python
{'content': content, 'citations': citations, 'warning': warning,
 'clarity_score': None, 'citation_fit_score': None, 'review_notes': ''}
```

Add a test asserting the fake engine’s `answer_calls == 25` when `--with-answer` is supplied, and that the report contains unset manual score fields. Keep generated reports ignored via the existing `test-results/` entry in `.gitignore`.

- [ ] **Step 5: Document commands and manual review**

Add this README section near “验证”:

```powershell
# 仅检索：不会调用回答服务
.venv\Scripts\python.exe scripts\evaluate_retrieval.py

# 检索并生成 25 个回答：会调用当前配置的回答服务并产生费用
.venv\Scripts\python.exe scripts\evaluate_retrieval.py --with-answer
```

Explain that reports are in `test-results/`, a changed PDF requires updating the suite deliberately after review, and human reviewers fill `clarity_score` and `citation_fit_score` rather than relying on automatic answer grading.

- [ ] **Step 6: Run focused tests and a retrieval-only real-data smoke check, then commit**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_evaluation.py -q`

Expected: PASS.

Run: `.venv\Scripts\python.exe scripts\evaluate_retrieval.py`

Expected: exit code `0` and a new `test-results/ai-infra-retrieval-*.json` report; it must contain no `answer_review` fields by default.

```powershell
git add scripts/evaluate_retrieval.py backend/tests/test_evaluation.py README.md
git commit -m "feat: add local retrieval evaluation runner"
```

## Task 5: Establish the Baseline and Produce Evidence for a Focused Remediation Plan

**Files:**
- Create: `docs/evaluations/ai-infra-retrieval-v1-baseline.md`

**Interfaces:**
- Consumes: the Task 4 report and its `failure_stage` fields.
- Produces: a reviewed baseline summary and a concrete remediation brief for each repeated retrieval-stage failure. The brief is the required input to a separate focused implementation plan; it prevents inventing production behavior before the real-document baseline exists.

- [ ] **Step 1: Run and preserve the retrieval-only baseline**

Run: `.venv\Scripts\python.exe scripts\evaluate_retrieval.py --output test-results/ai-infra-baseline.json`

Expected: a 25-case report with total and category metrics. Do not run `--with-answer` in this step.

- [ ] **Step 2: Write the baseline analysis and remediation briefs**

Create `docs/evaluations/ai-infra-retrieval-v1-baseline.md` with the date, PDF hash, command, total/category metrics, and every failing ID grouped by `failure_stage`. For each repeated `not_recalled` or `not_selected` group, include the exact question IDs, target locations/terms, selected evidence, candidate evidence, and the smallest allowed remediation direction:

- `not_parsed`: investigate parsing/chunking in a dedicated follow-up; do not alter retrieval.
- `not_recalled`: evaluate an explicit concept alias or a narrowly scoped lexical expansion; reject broad arbitrary Chinese substring matching.
- `not_selected`: evaluate preserving a matching candidate in the final evidence set.
- `unexpected_evidence`: replace or refine the no-evidence question; do not weaken production retrieval to force an empty result.

For one-off failures, document them as individual observations rather than applying a broad code change. State that the existing MHA regression remains mandatory for any retrieval change.

- [ ] **Step 3: Commit the reproducible baseline**

```powershell
git add docs/evaluations/ai-infra-retrieval-v1-baseline.md
git commit -m "docs: record AI Infra retrieval baseline"
```

## Task 6: Final Verification and Optional Answer Quality Review

**Files:**
- Modify: `docs/evaluations/ai-infra-retrieval-v1-baseline.md`

**Interfaces:**
- Consumes: Task 4 runner, the Task 5 baseline report, and the user-configured Chat Completions provider only after the user explicitly chooses to spend provider calls.
- Produces: verified final command evidence and, if requested, a manual answer-quality record.

- [ ] **Step 1: Verify all automated work without calling the provider**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: PASS.

Run: `npm test`

Expected: PASS.

Run: `npm run build`

Expected: PASS.

Run: `.venv\Scripts\python.exe scripts\evaluate_retrieval.py`

Expected: exit code `0`; verify each report result contains retrieval diagnostics and no `answer_review` field.

- [ ] **Step 2: Ask the user before the cost-bearing answer pass**

State that `--with-answer` will make 25 calls to the configured answer provider and ask whether to run it now. Do not substitute a mock or silently run it.

- [ ] **Step 3: If the user approves, run answer mode and review the report**

Run: `.venv\Scripts\python.exe scripts\evaluate_retrieval.py --with-answer`

Expected: 25 `answer_review` records, each with `content`, `citations`, unset `clarity_score`/`citation_fit_score`, and empty `review_notes`.

Manually assign clarity and citation-fit scores after reading each response. Update `docs/evaluations/ai-infra-retrieval-v1-baseline.md` only with aggregate counts and notable failure IDs, never generated answer bodies.

- [ ] **Step 4: Commit final review metadata if answer mode was approved**

```powershell
git add docs/evaluations/ai-infra-retrieval-v1-baseline.md
git commit -m "docs: record AI Infra answer quality review"
```

If answer mode was not approved, make no additional commit and report that retrieval evaluation completed without paid answer generation.
