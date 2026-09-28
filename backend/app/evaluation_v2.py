"""Calibrated evaluation records. Semantic judgments are left for review."""

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re

from .evaluation import SHA256_PATTERN, _evidence


@dataclass(frozen=True)
class CalibratedSuite:
    version: int
    document_name: str
    document_sha256: str
    cases: tuple[dict, ...]
    fixtures: tuple[dict, ...]
    sources: dict


def load_calibrated_suite(path: Path) -> CalibratedSuite:
    raw = json.loads(path.read_text(encoding='utf-8'))
    if raw.get('schema') != 'ai-infra-gold-rubric' or raw.get('version') != 2:
        raise ValueError('需要 AI Infra v2 金标准。')
    if raw.get('document_name') != 'AI-Infra-Book.pdf' or not SHA256_PATTERN.fullmatch(raw.get('document_sha256', '')):
        raise ValueError('文档名称或 SHA-256 无效。')
    cases = raw.get('cases')
    sources = raw.get('sources')
    fixtures = raw.get('assessment_fixtures')
    if not isinstance(cases, list) or len(cases) != 25 or not isinstance(sources, dict) or not isinstance(fixtures, list):
        raise ValueError('v2 题目、原文定位或受控用例结构无效。')
    ids = [case.get('id') for case in cases]
    if len(set(ids)) != 25:
        raise ValueError('v2 题目 ID 必须唯一。')
    valid_answerability = {'supported', 'underspecified', 'not_found_in_extracted_text'}
    for case in cases:
        if not case.get('question') or case.get('corpus_answerability') not in valid_answerability:
            raise ValueError(f"题目 {case.get('id')} 的问题或语料标签无效。")
        cores = case.get('core_subquestions')
        if not isinstance(cores, list) or (case['corpus_answerability'] == 'supported' and not cores):
            raise ValueError(f"题目 {case['id']} 缺少核心子问题。")
        for core in cores:
            if not core.get('id') or not core.get('required_facts') or not core.get('evidence_refs'):
                raise ValueError(f"题目 {case['id']} 的核心子问题缺少事实或 evidence_refs。")
            if not set(core['evidence_refs']) <= sources.keys():
                raise ValueError(f"题目 {case['id']} 的 evidence_refs 指向不存在的原文。")
    return CalibratedSuite(raw['version'], raw['document_name'], raw['document_sha256'],
                           tuple(cases), tuple(fixtures), sources)


def build_case_record(case, sources, done=None, error=None):
    """Keep each runtime stage distinct; do not infer semantic correctness."""
    diagnostics = sources.get('retrieval_diagnostics') or {}
    ranked = diagnostics.get('items') or []
    input_evidence = sources.get('citations') or []
    assessment = sources.get('evidence_assessment') or {}
    content = (done or {}).get('content', '')
    citation_evidence = lambda item: {**_evidence(item), 'id': item['id']} if 'id' in item else _evidence(item)
    return {
        'id': case['id'],
        'question': case['question'],
        'corpus_answerability': case['corpus_answerability'],
        'expected_behavior': case['required_behavior'],
        'retrieval': {
            'vector_items': [_evidence(item) for item in diagnostics.get('vector_items') or []],
            'lexical_items': [_evidence(item) for item in diagnostics.get('lexical_items') or []],
            'ranked_items': [_evidence(item) for item in ranked],
            'selected_items': [_evidence(item) for item in ranked if item.get('selected')],
            'context_items': [_evidence(item) for item in diagnostics.get('context_items') or []],
            'provider': diagnostics.get('provider'),
            'device': diagnostics.get('device'),
            'fallback': diagnostics.get('fallback'),
            'error': diagnostics.get('error'),
            'rrf_k': diagnostics.get('rrf_k'),
        },
        'assessment': assessment,
        'answer': {
            'status': 'error' if error else 'done' if done else 'not_run',
            'content': content,
            'input_evidence': [citation_evidence(item) for item in input_evidence],
            'returned_citations': [citation_evidence(item) for item in (done or {}).get('citations', [])],
            'used_citation_ids': sorted({int(value) for value in re.findall(r'\[(\d+)\]', content)}),
            'warning': (done or {}).get('warning', ''),
            'error': error,
        },
        'review': {
            'status': 'pending',
            'core_subquestions': [
                {'id': core['id'], 'question': core['question'], 'required_facts': core['required_facts'],
                 'gold_evidence_refs': core['evidence_refs'], 'candidate_support': None,
                 'selected_support': None, 'input_support': None, 'answer_correct': None,
                 'supporting_chunk_ids': [], 'notes': ''}
                for core in case['core_subquestions']
            ],
            'gold_evidence_status': None,
            'assessment_correct': None,
            'answer_faithful': None,
            'citation_support': None,
            'missing_parts_disclosed': None,
            'notes': '',
        },
    }


def summarize_run(results):
    rows = list(results)
    return {
        'total': len(rows),
        'corpus_groups': dict(Counter(row['corpus_answerability'] for row in rows)),
        'assessment_statuses': dict(Counter(row['assessment'].get('status', 'missing') for row in rows)),
        'answer_statuses': dict(Counter(row['answer']['status'] for row in rows)),
        'review_pending': sum(row['review']['status'] == 'pending' for row in rows),
        'reranker_fallbacks': sum(bool(row['retrieval']['fallback']) for row in rows),
    }
