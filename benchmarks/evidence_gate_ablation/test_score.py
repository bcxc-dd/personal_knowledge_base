import pytest

from benchmarks.evidence_gate_ablation.score import summarize


def test_summarize_separates_main_and_diagnostic_and_counts_error_types():
    groups = {'X': 'MAIN_SINGLE_CHUNK', 'Y': 'MULTI_CHUNK_DIAGNOSTIC'}
    records = [
        {'unit_id': 'X:positive', 'variant': 'hard_veto', 'gold': 'FULL',
         'verdict': 'FALSE_REFUSAL', 'success': False, 'confidence': 'HIGH'},
        {'unit_id': 'X:positive', 'variant': 'advisory', 'gold': 'FULL',
         'verdict': 'FULL_CORRECT', 'success': True, 'confidence': 'MEDIUM'},
        {'unit_id': 'Y:negative', 'variant': 'hard_veto', 'gold': 'PARTIAL',
         'verdict': 'WRONG_FACT', 'success': False, 'confidence': 'HIGH'},
        {'unit_id': 'Y:negative', 'variant': 'advisory', 'gold': 'PARTIAL',
         'verdict': 'PARTIAL_BOUNDED', 'success': True, 'confidence': 'HIGH'},
    ]
    got = summarize(records, groups)
    assert got['MAIN_SINGLE_CHUNK']['hard_veto']['success'] == 0
    assert got['MAIN_SINGLE_CHUNK']['advisory']['success'] == 1
    assert got['MAIN_SINGLE_CHUNK']['advisory']['medium_confidence'] == 1
    assert got['MULTI_CHUNK_DIAGNOSTIC']['hard_veto']['wrong_fact'] == 1


def test_summarize_rejects_missing_case_group():
    with pytest.raises(ValueError, match='unknown case'):
        summarize([{'unit_id': 'X:positive', 'variant': 'advisory', 'gold': 'FULL',
                    'verdict': 'FULL_CORRECT', 'success': True, 'confidence': 'HIGH'}], {})
