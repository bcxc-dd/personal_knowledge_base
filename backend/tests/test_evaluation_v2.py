import json
import asyncio
import importlib.util
import shutil
from pathlib import Path

import pytest

from app.evaluation_v2 import build_case_record, load_calibrated_suite, summarize_run


GOLD = Path('docs/evaluations/ai-infra-answerability-v2.json')


def test_calibrated_suite_rejects_missing_core_evidence_reference(tmp_path):
    raw = json.loads(GOLD.read_text(encoding='utf-8'))
    raw['cases'][0]['core_subquestions'][0]['evidence_refs'] = ['does-not-exist']
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps(raw), encoding='utf-8')

    with pytest.raises(ValueError, match='evidence_refs'):
        load_calibrated_suite(path)


def test_record_separates_candidates_selected_and_answer_evidence():
    case = load_calibrated_suite(GOLD).cases[0]
    candidate = {'chunk_id': 'definition', 'location': '第 11 页', 'text': 'AI Infra 是基础设施',
                 'retrieval_sources': ['lexical'], 'fused_score': 1 / 61, 'selected': True}
    unrelated = {'chunk_id': 'unrelated', 'location': '第 16 页', 'text': '72 GPUs',
                 'retrieval_sources': ['vector'], 'fused_score': 1 / 62, 'selected': True}
    diagnostics = {'vector_items': [unrelated], 'lexical_items': [candidate],
                   'items': [candidate, unrelated], 'provider': 'rrf', 'fallback': False}
    assessment = {'status': 'partial', 'supported_subquestions': ['什么是 AI Infra？'],
                  'unsupported_subquestions': ['它包含哪些主要部分？'], 'evidence_chunk_ids': ['definition']}
    sources = {'citations': [{**candidate, 'id': 1}], 'retrieval_diagnostics': diagnostics,
               'evidence_assessment': assessment}
    done = {'content': 'AI Infra 是基础设施 [1]。', 'citations': sources['citations'],
            'evidence_assessment': assessment, 'warning': ''}

    result = build_case_record(case, sources, done=done)

    assert [row['chunk_id'] for row in result['retrieval']['vector_items']] == ['unrelated']
    assert [row['chunk_id'] for row in result['retrieval']['selected_items']] == ['definition', 'unrelated']
    assert [row['chunk_id'] for row in result['answer']['input_evidence']] == ['definition']
    assert result['answer']['input_evidence'][0]['id'] == 1
    assert result['answer']['used_citation_ids'] == [1]
    assert result['review']['status'] == 'pending'
    assert [row['id'] for row in result['review']['core_subquestions']] == ['definition', 'components']


def test_record_marks_expanded_context_separately_from_ranked_candidates():
    case = load_calibrated_suite(GOLD).cases[17]
    ranked = {'chunk_id': 'intro', 'location': '第 401 页', 'text': '第 10 章 训练系统',
              'retrieval_sources': ['vector'], 'selected': True}
    context = {'chunk_id': 'summary', 'location': '第 446 页', 'text': '本章小结',
               'retrieval_sources': ['context'], 'context_reason': 'chapter_summary', 'selected': True}
    sources = {'citations': [{**ranked, 'id': 1}, {**context, 'id': 2}],
               'retrieval_diagnostics': {'items': [ranked], 'context_items': [context]},
               'evidence_assessment': {'status': 'supported', 'evidence_chunk_ids': ['intro', 'summary']}}

    result = build_case_record(case, sources)

    assert [item['chunk_id'] for item in result['retrieval']['selected_items']] == ['intro']
    assert [item['chunk_id'] for item in result['retrieval']['context_items']] == ['summary']
    assert result['retrieval']['context_items'][0]['context_reason'] == 'chapter_summary'
    assert [item['chunk_id'] for item in result['answer']['input_evidence']] == ['intro', 'summary']


def test_unanswerable_nearest_neighbor_is_not_scored_as_answer_failure():
    case = load_calibrated_suite(GOLD).cases[-1]
    neighbor = {'chunk_id': 'near', 'text': 'MHA attention', 'selected': True}
    sources = {'citations': [], 'retrieval_diagnostics': {'vector_items': [neighbor],
               'lexical_items': [], 'items': [neighbor]}, 'evidence_assessment': {
                   'status': 'insufficient', 'supported_subquestions': [],
                   'unsupported_subquestions': [case['question']], 'evidence_chunk_ids': []}}
    done = {'content': '现有资料不足以回答', 'citations': [], 'warning': ''}

    result = build_case_record(case, sources, done=done)

    assert result['retrieval']['selected_items'][0]['chunk_id'] == 'near'
    assert result['answer']['input_evidence'] == []
    assert result['answer']['status'] == 'done'
    assert result['review']['status'] == 'pending'
    assert 'passed' not in result


def test_runtime_summary_does_not_invent_quality_metrics():
    case = load_calibrated_suite(GOLD).cases[0]
    record = build_case_record(case, {'citations': [], 'retrieval_diagnostics': {'items': []},
                                     'evidence_assessment': {'status': 'insufficient', 'evidence_chunk_ids': []}},
                               error='模型服务不可用')

    summary = summarize_run([record])

    assert summary['total'] == 1
    assert summary['answer_statuses'] == {'error': 1}
    assert summary['review_pending'] == 1
    assert 'accuracy' not in summary


def test_runner_uses_answer_sources_event_without_second_retrieval():
    spec = importlib.util.spec_from_file_location('evaluate_retrieval', 'scripts/evaluate_retrieval.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    case = load_calibrated_suite(GOLD).cases[0]

    class EngineWithAnswerOnly:
        def retrieve(self, *args):
            raise AssertionError('a second retrieval would change the measured evidence')

        async def answer(self, question, kb_id, document_ids, conversation_id):
            assert question == case['question']
            assert conversation_id is None
            yield {'event': 'sources', 'data': {'citations': [], 'retrieval_diagnostics': {'items': []},
                  'evidence_assessment': {'status': 'insufficient', 'evidence_chunk_ids': []}}}
            yield {'event': 'done', 'data': {'content': '现有资料不足以回答', 'citations': [], 'warning': ''}}

    record = asyncio.run(runner.run_calibrated_case(EngineWithAnswerOnly(), case, {'kb_id': 'default', 'id': 'doc'}, True))

    assert record['assessment']['status'] == 'insufficient'
    assert record['answer']['status'] == 'done'


def test_runner_releases_open_vector_snapshot_before_removal(tmp_path):
    spec = importlib.util.spec_from_file_location('evaluate_retrieval', 'scripts/evaluate_retrieval.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    from app.engine import Engine

    snapshot = tmp_path / 'snapshot'
    engine = Engine(snapshot)
    collection = engine.vectors.collection('eval-probe')
    collection.upsert(ids=['x'], documents=['text'], embeddings=[[1.0, 0.0, 0.0]])
    collection.query(query_embeddings=[[1.0, 0.0, 0.0]], n_results=1)

    runner.close_evaluation_engine(engine)
    shutil.rmtree(snapshot)

    assert not snapshot.exists()
