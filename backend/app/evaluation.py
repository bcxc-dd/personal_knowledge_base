from dataclasses import dataclass
import json
import re
from pathlib import Path


ALLOWED_CATEGORIES = {
    'definition', 'mechanism', 'comparison', 'summary', 'acronym', 'insufficient_evidence',
}
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
    return EvaluationCase(
        id=case_id.strip(), question=question.strip(), category=category,
        expected_locations=_strings(raw.get('expected_locations'), 'expected_locations', case_id),
        expected_terms=_strings(raw.get('expected_terms'), 'expected_terms', case_id),
        must_cover=_strings(raw.get('must_cover'), 'must_cover', case_id),
        expect_no_evidence=no_evidence,
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
