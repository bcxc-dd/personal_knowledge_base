from dataclasses import dataclass
import json
import re
from pathlib import Path


ALLOWED_CATEGORIES = {
    'definition', 'mechanism', 'comparison', 'summary', 'acronym', 'insufficient_evidence',
}
ALLOWED_ASSESSMENT_MODES = {'automatic', 'manual_review', 'diagnostic'}
SHA256_PATTERN = re.compile(r'^[0-9a-f]{64}$')


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    question: str
    category: str
    expected_locations: tuple[str, ...]
    expected_terms: tuple[str, ...]
    must_cover: tuple[str, ...]
    expect_no_evidence: bool
    assessment_mode: str


@dataclass(frozen=True)
class EvaluationSuite:
    version: int
    document_name: str
    document_sha256: str
    cases: tuple[EvaluationCase, ...]


def _strings(value, field, case_id):
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f'题目 {case_id} 的 {field} 必须是非空字符串列表。')
    return tuple(item.strip() for item in value)


def _case(raw):
    if not isinstance(raw, dict):
        raise ValueError('评测题必须是对象。')
    case_id = raw.get('id')
    question = raw.get('question')
    category = raw.get('category')
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError('评测题缺少 ID。')
    if not isinstance(question, str) or not question.strip() or not re.search(r'[\u4e00-\u9fff]', question):
        raise ValueError(f'题目 {case_id} 必须是非空中文问题。')
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(f'题目 {case_id} 的 category 不受支持。')
    no_evidence = raw.get('expect_no_evidence')
    if not isinstance(no_evidence, bool):
        raise ValueError(f'题目 {case_id} 的 expect_no_evidence 必须是布尔值。')
    assessment_mode = raw.get('assessment_mode')
    if assessment_mode not in ALLOWED_ASSESSMENT_MODES:
        raise ValueError(f'题目 {case_id} 的 assessment_mode 不受支持。')
    return EvaluationCase(
        id=case_id.strip(), question=question.strip(), category=category,
        expected_locations=_strings(raw.get('expected_locations'), 'expected_locations', case_id),
        expected_terms=_strings(raw.get('expected_terms'), 'expected_terms', case_id),
        must_cover=_strings(raw.get('must_cover'), 'must_cover', case_id),
        expect_no_evidence=no_evidence,
        assessment_mode=assessment_mode,
    )


def validate_suite(suite):
    if suite.version != 1:
        raise ValueError('仅支持版本 1 的评测集。')
    if suite.document_name != 'AI-Infra-Book.pdf':
        raise ValueError('评测集只能绑定 AI-Infra-Book.pdf。')
    if not SHA256_PATTERN.fullmatch(suite.document_sha256):
        raise ValueError('document_sha256 必须是小写 64 位 SHA-256。')
    if len(suite.cases) != 25:
        raise ValueError('评测集必须包含恰好 25 道题。')
    if len({case.id for case in suite.cases}) != len(suite.cases):
        raise ValueError('评测题 ID 必须唯一。')
    for case in suite.cases:
        if case.category == 'insufficient_evidence' and not case.expect_no_evidence:
            raise ValueError(f'题目 {case.id} 必须标记为资料不足。')
        if case.expect_no_evidence:
            if case.expected_locations or case.expected_terms or case.must_cover:
                raise ValueError(f'题目 {case.id} 的资料不足题不能包含预期证据。')
        elif not case.expected_locations and not case.expected_terms:
            raise ValueError(f'题目 {case.id} 必须包含预期定位或术语。')
        if case.assessment_mode == 'diagnostic' and not case.expect_no_evidence:
            raise ValueError(f'题目 {case.id} 的诊断项必须标记为资料不足。')
        if case.expect_no_evidence and case.assessment_mode != 'diagnostic':
            raise ValueError(f'题目 {case.id} 的资料不足题必须作为诊断项。')


def load_suite(path: Path) -> EvaluationSuite:
    raw = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict):
        raise ValueError('评测集根节点必须是对象。')
    try:
        cases = tuple(_case(case) for case in raw['cases'])
        suite = EvaluationSuite(
            version=raw['version'], document_name=raw['document_name'],
            document_sha256=raw['document_sha256'], cases=cases,
        )
    except KeyError as exc:
        raise ValueError(f'评测集缺少字段：{exc.args[0]}。') from exc
    validate_suite(suite)
    return suite


def _matches(case, items):
    values = list(items)
    if case.expected_locations:
        locations = {str(item.get('location', '')).strip() for item in values}
        return all(location in locations for location in case.expected_locations)
    terms = tuple(term.lower() for term in case.expected_terms)
    return any(any(term in str(item.get('text', '')).lower() for term in terms) for item in values)


def _evidence(item):
    keys = ('chunk_id', 'document_id', 'name', 'location', 'text', 'vector_rank', 'vector_similarity',
            'lexical_match', 'rerank_rank', 'rerank_score', 'selected')
    return {key: item[key] for key in keys if key in item}


def evaluate_case(case, selected, candidates, indexed_chunks):
    selected = list(selected)
    candidates = list(candidates)
    if case.expect_no_evidence:
        passed = not selected
        stage = None if passed else 'unexpected_evidence'
        reason = '未检索到证据。' if passed else '资料不足题返回了证据。'
    else:
        selected_match = _matches(case, selected)
        if selected_match:
            passed, stage, reason = True, None, '最终证据命中预期锚点或术语。'
        elif not _matches(case, indexed_chunks):
            passed, stage, reason = False, 'not_parsed', '预期锚点或术语不在已索引片段中。'
        elif not _matches(case, candidates):
            passed, stage, reason = False, 'not_recalled', '预期证据未进入候选集合。'
        else:
            passed, stage, reason = False, 'not_selected', '预期证据进入候选但未进入最终证据。'
    return {
        'id': case.id, 'question': case.question, 'category': case.category, 'passed': passed,
        'assessment_mode': case.assessment_mode,
        'match_reason': reason, 'failure_stage': stage,
        'selected_ids': [item.get('chunk_id') for item in selected],
        'candidate_ids': [item.get('chunk_id') for item in candidates],
        'selected_evidence': [_evidence(item) for item in selected],
        'candidate_evidence': [_evidence(item) for item in candidates],
    }


def summarize(results):
    values = list(results)
    automatic = [result for result in values if result['assessment_mode'] == 'automatic']
    diagnostic = [result for result in values if result['assessment_mode'] == 'diagnostic']

    def score(items):
        by_category = {}
        for result in items:
            bucket = by_category.setdefault(result['category'], {'total': 0, 'passed': 0})
            bucket['total'] += 1
            bucket['passed'] += int(bool(result['passed']))
        return {
            'total': len(items),
            'passed': sum(bool(item['passed']) for item in items),
            'by_category': by_category,
        }

    manual_review = [result for result in values if result['assessment_mode'] == 'manual_review']
    return {
        'scored': score(automatic),
        'manual_review': {'total': len(manual_review), 'case_ids': [result['id'] for result in manual_review]},
        'diagnostic': score(diagnostic),
    }
