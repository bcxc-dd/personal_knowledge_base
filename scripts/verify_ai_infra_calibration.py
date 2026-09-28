"""Read-only audit of the calibrated gold data; not a RAG quality evaluation."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    folder = root / 'docs' / 'evaluations'
    gold = json.loads((folder / 'ai-infra-answerability-v2.json').read_text(encoding='utf-8'))
    old = json.loads((folder / 'ai-infra-retrieval-v1.json').read_text(encoding='utf-8'))
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    check(hashlib.sha256(args.pdf.read_bytes()).hexdigest() == gold['document_sha256'], 'PDF hash mismatch')
    if errors:
        raise SystemExit('\n'.join(errors))
    reader = PdfReader(args.pdf)
    check(len(reader.pages) == gold['pdf_page_count'], 'PDF page count mismatch')
    texts = [page.extract_text() or '' for page in reader.pages]
    normalize = lambda text: re.sub(r'\s+', '', text)
    normalized = [normalize(text) for text in texts]
    checks = 0

    def check_excerpt(label, page, text):
        nonlocal checks
        checks += 1
        check(1 <= page <= len(texts) and normalize(text) in normalized[page - 1], f'{label}: anchor absent on page {page}: {text}')

    check([(c['id'], c['question']) for c in gold['cases']] == [(c['id'], c['question']) for c in old['cases']], 'Original IDs/questions changed')
    cases = {case['id']: case for case in gold['cases']}
    check(len(cases) == len(gold['cases']) == 25, 'Expected 25 unique cases')
    for ref, source in gold['sources'].items():
        for anchor in source['anchors']:
            check_excerpt(ref, source['page'], anchor)
    for case in gold['cases']:
        cores = case['core_subquestions']
        check(len({core['id'] for core in cores}) == len(cores), f"{case['id']}: duplicate core ID")
        if case['corpus_answerability'] == 'supported':
            check(bool(cores), f"{case['id']}: missing cores")
        for core in cores:
            check(bool(core['required_facts']) and bool(core['evidence_refs']), f"{case['id']}: empty facts/evidence")
            check(set(core['evidence_refs']) <= set(gold['sources']), f"{case['id']}: invalid evidence reference")
    for fixture in gold['assessment_fixtures']:
        cores = {core['id'] for core in cases[fixture['case_id']]['core_subquestions']}
        supported, unsupported = set(fixture['supported_core_ids']), set(fixture['unsupported_core_ids'])
        check(not supported & unsupported and supported | unsupported == cores, f"{fixture['id']}: invalid partition")
        expected = 'supported' if supported == cores else 'partial' if supported else 'insufficient'
        check(fixture['expected_status'] == expected, f"{fixture['id']}: inconsistent status")
        for excerpt in fixture['excerpts']:
            check_excerpt(fixture['id'], excerpt['page'], excerpt['text'])
    zzq_pages = [i + 1 for i, text in enumerate(texts) if 'zzq' in normalize(text).lower()]
    check(not zzq_pages, f'ZZQ found on pages {zzq_pages}; review q25')
    result = {
        'audit': 'source_and_structure_only_not_model_quality',
        'pdf_sha256': gold['document_sha256'],
        'pdf_pages': len(texts),
        'original_cases': len(cases),
        'corpus_groups': dict(Counter(case['corpus_answerability'] for case in gold['cases'])),
        'controlled_fixtures': len(gold['assessment_fixtures']),
        'anchor_checks': checks,
        'zzq_matching_pages': zzq_pages,
        'errors': errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
