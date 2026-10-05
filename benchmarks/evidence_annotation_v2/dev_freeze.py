"""Apply the user's explicit 2026-10-03 review to the legacy DEV draft.

This module does not run evidence matchers or create a TEST split.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'test-results/evidence-matching-v2-2026-10-03/dataset-v2.json'
OUTPUT_DIR = ROOT / 'test-results/evidence-annotation-freeze-2026-10-03'
OUTPUT = OUTPUT_DIR / 'dataset-v2-dev-frozen.json'
MANIFEST = OUTPUT_DIR / 'dev-freeze-manifest.json'
SCHEMA = ROOT / 'docs/evaluations/evidence-annotation-v2-schema.md'
USER_REVIEW = Path(r'C:\Users\luck\.codex\attachments\d5bfc805-3105-4cd1-b691-fe0528143e52\已粘贴的文本.txt')
REVIEW_DATE = '2026-10-03'
GPA_CASES = frozenset({
    'gpa-real', 'gpa-newline', 'gpa-ranking-negative',
    'gpa-other-metric', 'gpa-exception-scope', 'gpa-synthetic-positive',
})
REVISED_CASES = GPA_CASES | {'csp-no-output', 'gqa-mqa-swapped', 'negated-definition'}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def amend_cases(source: dict) -> dict:
    if len(source['cases']) != 36 or len({r['case_id'] for r in source['cases']}) != 36:
        raise ValueError('Expected exactly 36 distinct DEV cases')
    if not REVISED_CASES <= {r['case_id'] for r in source['cases']}:
        raise ValueError('Explicitly reviewed cases are missing')
    payload = copy.deepcopy(source)
    payload['schema'] = 'evidence-matching-v2-dev-frozen'
    payload['schema_version'] = '2.0'
    payload['review_state'] = 'HUMAN_REVIEWED_DEV_FROZEN'
    payload['review_date'] = REVIEW_DATE
    payload['review_provenance'] = 'user_attachment_d5bfc805-3105-4cd1-b691-fe0528143e52'
    payload['split_policy'] = 'All 36 cases are DEV; TEST_FROZEN is empty'
    for row in payload['cases']:
        case_id = row['case_id']
        if row.get('split') != 'DEV' or row.get('human_review_state') != 'PENDING':
            raise ValueError(f'Unexpected pre-freeze state: {case_id}')
        row['reviewer_kind'] = 'human_user'
        row['human_review_state'] = 'RELABELLED' if case_id in REVISED_CASES else 'CONFIRMED'
        row['review_date'] = REVIEW_DATE
        if case_id in GPA_CASES:
            required = row['required_facts']
            if len(required) != 1 or required[0]['target'].get('scope') != '普通推免推荐条件':
                raise ValueError(f'Unexpected GPA scope: {case_id}')
            required[0]['target']['scope'] = '推免推荐条件'
            for field in ('covered_facts', 'missing_facts'):
                for fact in row[field]:
                    if fact['fact_id'] == required[0]['fact_id']:
                        fact['target']['scope'] = '推免推荐条件'
            row['review_notes'] = '用户复核：query 未限定普通推免，required fact 范围改为推免推荐条件。'
        elif case_id == 'csp-no-output':
            row['query'] = 'CSP考试成绩达到300分时，g_i的具体取值是多少？'
            row['query_plan_v1'] = None  # The old derived plan belongs to the old query.
            row['review_notes'] = '用户复核：明确询问具体取值；证据仅述计算依据，保留 NONE/MISSING_FACT。旧 query_plan_v1 失效。'
        elif case_id == 'gqa-mqa-swapped':
            row['expected_answer'] = '按该片段，GQA所有Q头共用一组KV，MQA按组共享不同KV。'
            row['review_notes'] = '用户复核：expected_answer 仅表述证据；原书冲突留在关系及 canonical_reference。'
        elif case_id == 'negated-definition':
            row['evidence_text'] = (
                'AI Infra并不是支撑AI训练和推理的基础设施。\n'
                '该片段同时声称，AI Infra的主要组成包括计算设备、存储与互联，以及组织这些资源的软件。'
            )
            row['review_notes'] = '用户复核：消除否定句与组成句的语法歧义；保留 PARTIAL/NEGATED。'
        else:
            row['review_notes'] = '用户复核：现有 v2 标注字段直接确认，未作内容修订。'
        required_ids = {f['fact_id'] for f in row['required_facts']}
        covered_ids = {f['fact_id'] for f in row['covered_facts']}
        missing_ids = {f['fact_id'] for f in row['missing_facts']}
        if covered_ids & missing_ids or covered_ids | missing_ids != required_ids:
            raise ValueError(f'Fact partition mismatch: {case_id}')
    return payload


def freeze_dev(source_path: Path = SOURCE, output_path: Path = OUTPUT,
               manifest_path: Path = MANIFEST) -> dict:
    if output_path.exists() or manifest_path.exists():
        raise FileExistsError('Frozen DEV output already exists; refusing overwrite')
    source = json.loads(source_path.read_text(encoding='utf-8'))
    frozen = amend_cases(source)
    manifest = {
        'state': 'HUMAN_REVIEWED_DEV_FROZEN',
        'schema_version': frozen['schema_version'],
        'review_date': REVIEW_DATE,
        'review_provenance': frozen['review_provenance'],
        'source_dataset_sha256': sha256(source_path),
        'case_count': 36,
        'confirmed_count': 27,
        'relabelled_count': 9,
        'test_frozen_count': 0,
    }
    if SCHEMA.exists():
        manifest['schema_doc_sha256'] = sha256(SCHEMA)
    if USER_REVIEW.exists():
        manifest['user_review_sha256'] = sha256(USER_REVIEW)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('x', encoding='utf-8') as f:
        json.dump(frozen, f, ensure_ascii=False, indent=2)
    manifest['dataset_sha256'] = sha256(output_path)
    manifest['dataset_bytes'] = output_path.stat().st_size
    with manifest_path.open('x', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


if __name__ == '__main__':
    print(json.dumps(freeze_dev(), ensure_ascii=False, indent=2))
