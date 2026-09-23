# Hybrid Retrieval Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make vector and lexical retrieval independent, fuse candidates with RRF, and refuse or qualify answers according to substantive evidence.

**Architecture:** Engine.retrieve collects bounded vector and lexical result lists independently, merges duplicate chunks with route metadata, ranks their union using RRF with k=60, then optionally reranks it. A deterministic evidence assessor classifies final citations as supported, partial, or insufficient; SSE, persistence, evaluation, and the UI carry that result.

**Tech Stack:** Python 3.10+, FastAPI/SSE, SQLite, Chroma, pytest, React 19, TypeScript, Vitest, Sass.

**Spec:** docs/superpowers/specs/2026-09-23-hybrid-retrieval-fusion-design.md

## Global Constraints

- Vector Top-K and lexical Top-K are independent routes; neither replaces the other before fusion.
- RRF is sum(1 / (60 + rank)); ranks start at one and missing route data is None/null, never zero.
- Reranking runs after RRF only; disabled or failed reranking preserves RRF ordering.
- Lexical evidence may support an answer only where its substantive body directly answers an independent core subquestion.
- partial means at least one independently answerable core subquestion is sufficiently supported and at least one other is not.
- Do not alter or commit docs/project-issues.md or data-dependent test-results.
- Keep src/app.tsx routing-only and preserve the existing page/component folder rules.

## Review Focus

- A lexical-only page 14 remains visible with vector_similarity null, rather than a zero vector score. Covered by Task 5.
- A chunk returned by both routes has both ranks, one merged result, and summed RRF score. Covered by Task 1.
- Reranker failure preserves RRF ordering and declares fallback. Covered by Task 2.
- Generic GPU text cannot prove a precise company cluster count. Covered by Task 3.
- A table-of-contents/title/reference hit cannot become usable definition evidence. Covered by Task 3.

---

### Task 1: Implement deterministic RRF candidate fusion

**Files:**
- Create: backend/app/retrieval.py
- Create: backend/tests/test_retrieval.py

**Interfaces:**
- Consumes: vector and lexical hit dictionaries containing chunk_id, document_id, text, name, location; vector hits add distance and lexical hits add lexical_score.
- Produces: fuse_candidates(vector_hits: list[dict], lexical_hits: list[dict], rrf_k: int = 60) -> list[dict]. Each result exposes nullable vector_rank, vector_similarity, lexical_rank, lexical_score, retrieval_sources, fused_score, and fused_rank.

- [ ] **Step 1: Write failing merge and nullability tests**

    from app.retrieval import fuse_candidates

    def hit(chunk_id, **extra):
        return {'chunk_id': chunk_id, 'document_id': 'doc', 'name': 'book.pdf',
                'location': 'page', 'text': 'body', **extra}

    def test_fuses_both_routes_and_keeps_lexical_only_vector_fields_null():
        items = fuse_candidates(
            [hit('both', distance=0.1), hit('vector', distance=0.2)],
            [hit('both', lexical_score=3), hit('lexical', lexical_score=2)],
        )
        both = next(item for item in items if item['chunk_id'] == 'both')
        lexical = next(item for item in items if item['chunk_id'] == 'lexical')
        assert both['retrieval_sources'] == ['lexical', 'vector']
        assert (both['vector_rank'], both['lexical_rank']) == (1, 1)
        assert both['fused_score'] == 2 / 61
        assert lexical['vector_rank'] is None
        assert lexical['vector_similarity'] is None
        assert lexical['fused_score'] == 1 / 62

Add vector-only and equal-score deterministic-order tests.

- [ ] **Step 2: Run the test to verify it fails**

Run: .venv\Scripts\python.exe -m pytest backend/tests/test_retrieval.py -v

Expected: FAIL with ModuleNotFoundError for app.retrieval.

- [ ] **Step 3: Implement deterministic fusion**

    RRF_K = 60

    def fuse_candidates(vector_hits, lexical_hits, rrf_k=RRF_K):
        merged = {}
        for source, hits in (('vector', vector_hits), ('lexical', lexical_hits)):
            for rank, raw in enumerate(hits, 1):
                item = merged.setdefault(raw['chunk_id'], {
                    **raw, 'vector_rank': None, 'vector_similarity': None,
                    'lexical_rank': None, 'lexical_score': None, 'retrieval_sources': [],
                })
                item['retrieval_sources'].append(source)
                if source == 'vector':
                    item['vector_rank'] = rank
                    item['vector_similarity'] = 1 - raw['distance']
                else:
                    item['lexical_rank'] = rank
                    item['lexical_score'] = raw['lexical_score']
        for item in merged.values():
            item['retrieval_sources'] = sorted(set(item['retrieval_sources']))
            item['fused_score'] = sum(1 / (rrf_k + rank) for rank in
                (item['vector_rank'], item['lexical_rank']) if rank is not None)
        items = sorted(merged.values(), key=lambda item: (-item['fused_score'], item['chunk_id']))
        for rank, item in enumerate(items, 1):
            item['fused_rank'] = rank
        return items

Do not mutate input lists or turn absent source values into zero.

- [ ] **Step 4: Run focused tests**

Run: .venv\Scripts\python.exe -m pytest backend/tests/test_retrieval.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

    git add backend/app/retrieval.py backend/tests/test_retrieval.py
    git commit -m "feat: fuse retrieval candidates with rrf"

### Task 2: Integrate independent dual retrieval and reranking

**Files:**
- Modify: backend/app/engine.py lines 21-219
- Modify: backend/app/reranker.py lines 31-45
- Modify: backend/tests/test_rag.py lines 63-163

**Interfaces:**
- Consumes: Task 1 fuse_candidates, VectorStore.search, Store.search_chunks_exact.
- Produces: RetrievalResult diagnostics with vector_candidate_count, lexical_candidate_count, candidate_count, rrf_k, vector_items, lexical_items, items, provider, device, fallback, and error.

- [ ] **Step 1: Write failing integration tests**

    def test_retrieve_fuses_before_evidence_selection(tmp_path):
        engine, doc = ready_engine(tmp_path)
        engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 2})
        engine.vectors.search = lambda *args, **kwargs: [vector_hit('v1'), vector_hit('both')]
        engine.store.search_chunks_exact = lambda *args, **kwargs: [lexical_hit('both'), lexical_hit('p14')]
        result = engine.retrieve('预填充和解码分别做什么？', 'default', [])
        assert result[0]['chunk_id'] == 'both'
        assert result.diagnostics['rrf_k'] == 60
        assert result.diagnostics['vector_candidate_count'] == 2
        assert result.diagnostics['lexical_candidate_count'] == 2
        assert next(x for x in result.diagnostics['items'] if x['chunk_id'] == 'p14')['vector_similarity'] is None

Add a reranker error test asserting fallback true and fused ranks [1, 2].

- [ ] **Step 2: Verify it fails**

Run: .venv\Scripts\python.exe -m pytest backend/tests/test_rag.py -k "fuses or reranker_failure" -v

Expected: FAIL because the old implementation appends lexical hits, gives them vector_rank 0, and uses replacement rules.

- [ ] **Step 3: Implement two independent routes followed by fusion**

In Engine.retrieve:

    vector_hits = self.vectors.search(fp, vectors[0], eligible, limit=candidate_limit)
    vector_hits = [item for item in vector_hits if self.store.document(item['document_id'])]
    lexical_hits = diverse_lexical_hits(
        self.store.search_chunks_exact(eligible, lexical_terms(question), limit=100),
        candidate_limit,
    )
    fused = fuse_candidates(vector_hits, lexical_hits)
    ranked = self.reranker.rank(question, fused, config)
    items = fused if ranked.fallback else ranked.items

Delete lexical vector_rank=0, the vector-preservation replacement loop, the lexical-replacement loop, and final sorting by vector rank. Select the first evidence_limit items. Reranker disabled/error behavior returns the supplied RRF order and provider rrf.

- [ ] **Step 4: Run regressions**

Run: .venv\Scripts\python.exe -m pytest backend/tests/test_rag.py backend/tests/test_retrieval.py -v

Expected: PASS, including acronym and phrase cases.

- [ ] **Step 5: Commit**

    git add backend/app/engine.py backend/app/reranker.py backend/tests/test_rag.py
    git commit -m "feat: retrieve independently and rank with rrf"

### Task 3: Implement substantive evidence assessment and refusal

**Files:**
- Create: backend/app/evidence.py
- Modify: backend/app/engine.py lines 221-275
- Modify: backend/app/store.py lines 37-166
- Create: backend/tests/test_evidence.py
- Modify: backend/tests/test_store.py
- Modify: backend/tests/test_rag.py lines 180-215

**Interfaces:**
- Consumes: assess_evidence(question: str, citations: list[dict]).
- Produces: EvidenceAssessment(status, supported_subquestions, unsupported_subquestions, usable_citation_ids). Assistant messages persist it in messages.evidence_assessment JSON and SSE includes it.

- [ ] **Step 1: Write failing q04/q23/title tests**

    from app.evidence import assess_evidence

    def test_lexical_only_prefill_decode_body_supports_both_parts():
        result = assess_evidence('预填充和解码分别做什么？', [{
            'id': 1, 'location': '第 14 页', 'retrieval_sources': ['lexical'],
            'vector_similarity': None,
            'text': '预填充阶段并行处理输入 token；解码阶段逐步生成下一个 token。',
        }])
        assert result.status == 'supported'
        assert result.usable_citation_ids == [1]

    def test_generic_gpu_text_does_not_prove_precise_cluster_count():
        result = assess_evidence('某公司内部 GPU 集群有多少张卡？', [
            {'id': 1, 'text': 'GPU 是人工智能训练常用的加速硬件。'}])
        assert result.status == 'insufficient'

    def test_table_of_contents_cannot_support_definition():
        result = assess_evidence('什么是 AI Infra？', [{'id': 1, 'text': '目录：第 1 章 AI Infra'}])
        assert result.status == 'insufficient'

Add a store migration test that starts from an old seven-column messages table and round-trips an explicit assessment.

- [ ] **Step 2: Verify it fails**

Run: .venv\Scripts\python.exe -m pytest backend/tests/test_evidence.py backend/tests/test_store.py -v

Expected: FAIL because app.evidence and the assessment persistence interface do not exist.

- [ ] **Step 3: Implement classification and answer boundary**

Implement EvidenceAssessment as a dataclass. Exclude title, contents, and reference-like text. Split explicit multi-part questions using markers such as 分别 and 以及. Require a direct body definition, mechanism, or relation for each subquestion; a generic word cannot satisfy missing number/company/time constraints.

Call the assessor after citations are selected. For insufficient, emit a fixed response listing unsupported points without calling the chat model. For partial, prompt with only usable citations and the unsupported points. For supported, prompt with usable citations. Include evidence_assessment in sources and done events; migrate and persist it through Store.

- [ ] **Step 4: Verify evidence and answer path**

Run: .venv\Scripts\python.exe -m pytest backend/tests/test_evidence.py backend/tests/test_store.py backend/tests/test_rag.py -v

Expected: PASS; q04-like lexical-only page 14 is supported, q23-like generic GPU is insufficient, and messages never have an SQLite column-count mismatch.

- [ ] **Step 5: Commit**

    git add backend/app/evidence.py backend/app/engine.py backend/app/store.py backend/tests/test_evidence.py backend/tests/test_store.py backend/tests/test_rag.py
    git commit -m "feat: assess evidence sufficiency before answering"

### Task 4: Report fused retrieval, evidence, and generation metrics

**Files:**
- Modify: backend/app/evaluation.py lines 108-158
- Modify: scripts/evaluate_retrieval.py lines 45-75
- Modify: backend/tests/test_evaluation.py
- Modify: README.md lines 82-108

**Interfaces:**
- Consumes: retrieval diagnostics plus assessment/answer events.
- Produces: report JSON retaining total, passed, by_category and adding retrieval_metrics, evidence_metrics, generation_metrics, RRF constant, and source provenance.

- [ ] **Step 1: Write failing summary test**

    def test_summary_separates_three_metric_groups():
        summary = summarize([
            {'category': 'definition', 'passed': True, 'evidence_status': 'supported',
             'answer_review': {'clarity_score': 4, 'citation_fit_score': 5}},
            {'category': 'definition', 'passed': False, 'evidence_status': 'insufficient',
             'answer_review': {'clarity_score': None, 'citation_fit_score': None}},
        ])
        assert summary['retrieval_metrics']['recall_at_evidence'] == 0.5
        assert summary['evidence_metrics']['supported_rate'] == 0.5
        assert summary['generation_metrics']['reviewed_count'] == 1

- [ ] **Step 2: Verify it fails**

Run: .venv\Scripts\python.exe -m pytest backend/tests/test_evaluation.py -v

Expected: FAIL because summarize currently has only legacy aggregate output.

- [ ] **Step 3: Implement observed-only reporting**

Retain legacy fields. New metrics derive only from evaluated results; no missing generation score may be fabricated. Serialize final evidence, route candidate lists, RRF constant, and assessment status per case. Document that --with-answer can cost money and needs manual scoring.

- [ ] **Step 4: Verify test and local retrieval-only report**

Run: .venv\Scripts\python.exe -m pytest backend/tests/test_evaluation.py -v

Expected: PASS.

Run: .venv\Scripts\python.exe scripts\evaluate_retrieval.py --data-dir D:\rag\data --output test-results\ai-infra-rrf-local.json

Expected: a report with three metric groups and route provenance. Do not commit it.

- [ ] **Step 5: Commit**

    git add backend/app/evaluation.py scripts/evaluate_retrieval.py backend/tests/test_evaluation.py README.md
    git commit -m "feat: report fused retrieval evaluation metrics"

### Task 5: Render vector, lexical, and final evidence separately

**Files:**
- Modify: src/types/index.ts lines 8-11
- Modify: src/pages/Chat/components/RetrievalDiagnostics/index.tsx
- Modify: src/pages/Chat/components/RetrievalDiagnostics/style/index.module.scss
- Create: src/pages/Chat/components/RetrievalDiagnostics/index.test.tsx

**Interfaces:**
- Consumes: source arrays and fused item fields from Task 2.
- Produces: expandable sections called 向量候选, 术语候选, 最终回答证据. A final evidence item traces to one or both source sections.

- [ ] **Step 1: Write failing lexical-only UI test**

    it('shows page 14 in term and final evidence without a fake vector score', async () => {
      render(<RetrievalDiagnostics data={{
        candidate_count: 2, vector_candidate_count: 1, lexical_candidate_count: 1,
        rrf_k: 60, provider: 'rrf', device: 'none', fallback: false,
        vector_items: [vectorPage16], lexical_items: [lexicalPage14], items: [lexicalPage14],
      }} />);
      await userEvent.click(screen.getByRole('button', { name: /查看检索分析/ }));
      expect(screen.getByText('术语候选')).toBeInTheDocument();
      expect(screen.getAllByText(/第 14 页/)).toHaveLength(2);
      expect(screen.queryByText(/向量相似度 0\.000/)).not.toBeInTheDocument();
    })

- [ ] **Step 2: Verify it fails**

Run: npm test -- --run src/pages/Chat/components/RetrievalDiagnostics/index.test.tsx

Expected: FAIL because the component uses one ungrouped list and renders absent vector similarity as 0.000.

- [ ] **Step 3: Implement typed grouped diagnostics**

Extend types with nullable route score/rank fields and vector_items/lexical_items. Backend diagnostics must populate those arrays before fusion. Render each group conditionally. Show vector score only when not null, lexical score only for lexical hits, and RRF data in final evidence. Maintain accessible labels and selected styling.

- [ ] **Step 4: Verify UI test and build**

Run: npm test -- --run src/pages/Chat/components/RetrievalDiagnostics/index.test.tsx src/services/stream.test.ts

Expected: PASS.

Run: npm run build

Expected: TypeScript and Vite build PASS.

- [ ] **Step 5: Commit**

    git add src/types/index.ts src/pages/Chat/components/RetrievalDiagnostics
    git commit -m "feat: show vector lexical and fused evidence"

### Task 6: Run the acceptance loop and prepare review

**Files:**
- Modify only if verification reveals a concrete defect in Tasks 1-5.
- Do not commit test-results or data.

**Interfaces:**
- Consumes: completed feature and docs/evaluations/ai-infra-retrieval-v1.json.
- Produces: reproducible command output and an uncommitted local evaluation report.

- [ ] **Step 1: Run complete automated verification**

Run: .venv\Scripts\python.exe -m pytest -q

Expected: all backend tests PASS.

Run: npm test

Expected: all frontend tests PASS.

Run: npm run build

Expected: production build PASS.

- [ ] **Step 2: Run real AI-Infra evaluation**

Run: .venv\Scripts\python.exe scripts\evaluate_retrieval.py --data-dir D:\rag\data --output test-results\ai-infra-rrf-final.json

Expected: q04 is supported with page 14 final evidence; q23, q24, q25 are insufficient; all 20 positives have no false refusal. If SHA or fingerprint is mismatched, report it and do not rewrite data or fabricate results.

- [ ] **Step 3: Check scope and diff**

Run: git diff --check; git status --short; git log --oneline master..HEAD

Expected: no whitespace errors; only intended files; docs/project-issues.md remains untracked and untouched.

- [ ] **Step 4: Record only a concrete verification defect**

If a command in Steps 1-3 fails, stop at the named failing test or build error, record its exact command and output in the review request, and return to the owning task. Do not create a speculative fix or an empty verification commit.
