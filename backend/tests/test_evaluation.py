import json
from pathlib import Path

import pytest

from app.evaluation import EvaluationCase, evaluate_case, load_suite, summarize


def write_suite(path, cases, sha='a' * 64):
    path.write_text(json.dumps({
        'version': 1,
        'document_name': 'AI-Infra-Book.pdf',
        'document_sha256': sha,
        'cases': cases,
    }, ensure_ascii=False), encoding='utf-8')


def normal_case(case_id):
    return {
        'id': case_id,
        'question': '什么是 AI Infra？',
        'category': 'definition',
        'expected_locations': ['第 11 页'],
        'expected_terms': ['AI Infra'],
        'must_cover': ['基础设施'],
        'expect_no_evidence': False,
    }


def test_load_suite_rejects_duplicate_case_ids(tmp_path):
    path = tmp_path / 'suite.json'
    write_suite(path, [normal_case('q01')] * 25)

    with pytest.raises(ValueError, match='唯一'):
        load_suite(path)


def test_load_suite_rejects_invalid_document_hash(tmp_path):
    path = tmp_path / 'suite.json'
    write_suite(path, [normal_case(f'q{i:02}') for i in range(25)], sha='not-a-sha')

    with pytest.raises(ValueError, match='SHA-256'):
        load_suite(path)


def test_load_suite_returns_immutable_cases_for_valid_suite(tmp_path):
    path = tmp_path / 'suite.json'
    cases = [normal_case(f'q{i:02}') for i in range(1, 25)] + [{
        'id': 'q25',
        'question': '书中是否定义了虚构缩写？',
        'category': 'insufficient_evidence',
        'expected_locations': [],
        'expected_terms': [],
        'must_cover': [],
        'expect_no_evidence': True,
    }]
    write_suite(path, cases)

    suite = load_suite(path)

    assert len(suite.cases) == 25
    assert suite.cases[-1].expect_no_evidence is True


def test_committed_ai_infra_suite_has_balanced_learning_coverage():
    suite = load_suite(Path('docs/evaluations/ai-infra-retrieval-v1.json'))

    assert len(suite.cases) == 25
    assert {case.category for case in suite.cases} == {
        'definition', 'mechanism', 'comparison', 'summary', 'acronym', 'insufficient_evidence',
    }


def mha_case():
    return EvaluationCase('q19', 'MHA 是什么？', 'acronym', ('第 44 页',), ('MHA',), ('多头注意力',), False)


def test_classifies_anchor_existing_but_not_recalled():
    target = {'chunk_id': 'target', 'location': '第 44 页', 'text': 'MHA 定义'}

    result = evaluate_case(mha_case(), selected=[], candidates=[], indexed_chunks=[target])

    assert result['passed'] is False
    assert result['failure_stage'] == 'not_recalled'


def test_classifies_candidate_ranked_out_of_final_evidence():
    target = {'chunk_id': 'target', 'location': '第 44 页', 'text': 'MHA 定义'}

    result = evaluate_case(mha_case(), selected=[], candidates=[target], indexed_chunks=[target])

    assert result['failure_stage'] == 'not_selected'


def test_no_evidence_case_fails_when_retrieval_returns_a_chunk():
    case = EvaluationCase('q25', 'ZZQ 是什么？', 'insufficient_evidence', (), (), (), True)

    result = evaluate_case(case, [{'chunk_id': 'x', 'location': '第 11 页', 'text': 'AI Infra'}], [], [])

    assert result['passed'] is False
    assert result['failure_stage'] == 'unexpected_evidence'


def test_summary_groups_pass_rate_by_category():
    summary = summarize([{'category': 'definition', 'passed': True}, {'category': 'definition', 'passed': False}])

    assert summary['total'] == 2
    assert summary['passed'] == 1
    assert summary['by_category']['definition'] == {'total': 2, 'passed': 1}
