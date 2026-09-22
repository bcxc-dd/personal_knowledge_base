import json
import importlib.util
from pathlib import Path

import pytest

from app.evaluation import EvaluationCase, evaluate_case, load_suite, summarize


def load_runner():
    path = Path('scripts/evaluate_retrieval.py')
    spec = importlib.util.spec_from_file_location('evaluate_retrieval', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        'assessment_mode': 'automatic',
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
        'assessment_mode': 'diagnostic',
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
    return EvaluationCase(
        'q19', 'MHA 是什么？', 'acronym', ('第 44 页',), ('MHA',), ('多头注意力',), False, 'automatic',
    )


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
    case = EvaluationCase('q25', 'ZZQ 是什么？', 'insufficient_evidence', (), (), (), True, 'diagnostic')

    result = evaluate_case(case, [{'chunk_id': 'x', 'location': '第 11 页', 'text': 'AI Infra'}], [], [])

    assert result['passed'] is False
    assert result['failure_stage'] == 'unexpected_evidence'


def test_summary_scores_only_automatic_cases_and_separates_review_modes():
    summary = summarize([
        {'id': 'q01', 'category': 'definition', 'passed': True, 'assessment_mode': 'automatic'},
        {'id': 'q02', 'category': 'definition', 'passed': False, 'assessment_mode': 'automatic'},
        {'id': 'q15', 'category': 'summary', 'passed': True, 'assessment_mode': 'manual_review'},
        {'id': 'q25', 'category': 'insufficient_evidence', 'passed': False, 'assessment_mode': 'diagnostic'},
    ])

    assert summary['scored'] == {
        'total': 2,
        'passed': 1,
        'by_category': {'definition': {'total': 2, 'passed': 1}},
    }
    assert summary['manual_review'] == {'total': 1, 'case_ids': ['q15']}
    assert summary['diagnostic'] == {
        'total': 1,
        'passed': 0,
        'by_category': {'insufficient_evidence': {'total': 1, 'passed': 0}},
    }


def test_location_anchored_case_does_not_treat_cover_title_as_a_match():
    case = EvaluationCase(
        'q01', '什么是 AI Infra？', 'definition', ('第 11 页',), ('AI Infra',), ('定义',), False, 'automatic',
    )
    cover = {'chunk_id': 'cover', 'location': '第 1 页', 'text': '深入理解 AI Infra'}
    definition = {'chunk_id': 'definition', 'location': '第 11 页', 'text': 'AI Infra 是支撑 AI 训练和推理的基础设施。'}
    overview = {'chunk_id': 'overview', 'location': '第 13 页', 'text': '应用与任务、模型与负载。'}

    result = evaluate_case(case, [cover], [cover, definition, overview], [cover, definition, overview])

    assert result['passed'] is False
    assert result['failure_stage'] == 'not_selected'


def test_default_runner_arguments_do_not_enable_answer_generation():
    runner = load_runner()

    args = runner.parse_args([])

    assert args.with_answer is False
