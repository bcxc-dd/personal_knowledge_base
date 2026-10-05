import json

import pytest

from benchmarks.evidence_annotation_v2.freeze_test_dataset import (
    CANDIDATE_DIR, CHECK_FIELDS, freeze_test, signoff_template, sha256,
)


def test_unsigned_template_cannot_freeze(tmp_path):
    template = signoff_template()
    assert len(template['decisions']) == 21
    assert all(d['decision'] is None for d in template['decisions'])
    path = tmp_path / 'unsigned.json'
    path.write_text(json.dumps(template, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ValueError, match='Human signoff missing'):
        freeze_test(path, tmp_path / 'frozen')
    assert not (tmp_path / 'frozen').exists()


def test_signed_fixture_freezes_without_matcher_and_refuses_overwrite(tmp_path):
    template = signoff_template()
    template['state'] = 'HUMAN_SIGNED'
    template['human_signoff_source'] = 'test fixture only'
    for d in template['decisions']:
        d['decision'] = 'CONFIRMED'
        d['reviewer'] = 'test-only-human-fixture'
        d['reviewed_at'] = '2026-10-03T00:00:00Z'
        d['parser_status'] = 'PASS'
        d['checks'] = {key: True for key in CHECK_FIELDS}
        d['hard_negative_labels'] = d['proposed_hard_negative_labels']
        d['review_notes'] = 'test fixture only'
        if d['case_id'] in {'T03','A04','F03','F04'}:
            d['decision'] = 'CORRECTED'
        if d['case_id']=='T03':
            d['corrections']={'positive_evidence_ids':['technical:35']}
        if d['case_id']=='A04':
            d['corrections']={'positive_evidence_ids':['paper:44']}
        if d['case_id']=='F03':
            d['corrections']={'positive_evidence_ids':['tables:4','tables:5'],
                              'hard_negative_evidence_ids':['tables:5'],
                              'metric_group':'MULTI_CHUNK_DIAGNOSTIC',
                              'aggregation_category':'MULTI_CHUNK_DIAGNOSTIC'}
            d['hard_negative_labels']={'tables:5':'PARTIAL'}
        if d['case_id']=='F04':
            d['corrections']={'positive_evidence_ids':['tables:5']}
    path = tmp_path / 'synthetic-signed.json'
    path.write_text(json.dumps(template, ensure_ascii=False), encoding='utf-8')
    source_sha = sha256(CANDIDATE_DIR / 'test-candidate-review.json')
    out = tmp_path / 'frozen'
    manifest = freeze_test(path, out)
    assert manifest['number_of_queries'] == 21
    assert manifest['number_of_positive_pairs'] == 21
    assert manifest['number_of_hard_negative_pairs'] == 21
    assert manifest['parser_pass_count'] == 21
    assert manifest['main_query_count'] == 20
    assert manifest['multi_chunk_diagnostic_query_count'] == 1
    assert manifest['parser_failure_count'] == 0
    assert manifest['dataset_sha256'] == sha256(out / 'test-frozen-v1.json')
    sheet = (out / 'final-review-sheet.md').read_text(encoding='utf-8')
    assert 'F03' in sheet and 'MULTI_CHUNK_DIAGNOSTIC' in sheet
    assert 'tables:4, tables:5' in sheet and 'tables:5=PARTIAL' in sheet
    assert '待核' not in sheet
    assert sha256(CANDIDATE_DIR / 'test-candidate-review.json') == source_sha
    with pytest.raises(FileExistsError):
        freeze_test(path, out)
