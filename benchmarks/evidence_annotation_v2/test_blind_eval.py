import pytest

from benchmarks.evidence_annotation_v2.blind_eval import (
    STRUCTURED_FIELDS, _score, classification, run_blind,
)


def test_classification_counts_false_acceptance_and_rejection():
    rows = [
        {'gold':'FULL','predicted':'FULL'},
        {'gold':'FULL','predicted':'NONE'},
        {'gold':'PARTIAL','predicted':'FULL'},
        {'gold':'NONE','predicted':'PARTIAL'},
        {'gold':'NONE','predicted':'NONE'},
    ]
    got = classification(rows)
    assert got['n'] == 5
    assert got['accuracy'] == 2/5
    assert got['confusion']['FULL']['NONE'] == 1
    assert got['false_acceptance']['PARTIAL_TO_FULL'] == 1
    assert got['false_acceptance']['NONE_TO_PARTIAL'] == 1
    assert got['false_rejection']['FULL_TO_NONE'] == 1


def test_blind_run_refuses_unfrozen_input_without_calling_matchers(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_blind(tmp_path/'not-frozen', tmp_path/'results')
    assert not (tmp_path/'results').exists()


def test_multi_chunk_diagnostic_is_not_in_single_chunk_main_metric():
    blank = {key:'NOT_OBSERVABLE' for key in STRUCTURED_FIELDS}
    rows = [
        {'gold':'FULL','document_slug':'policy','query_type':'WH','pair_type':'positive',
         'metric_group':'MAIN_SINGLE_CHUNK',
         'E0':{'predicted_answerability':'FULL'},'E4':{'predicted_answerability':'FULL'},
         'structured':{'E0':blank,'E4':blank}},
        {'gold':'FULL','document_slug':'tables','query_type':'COMPARISON','pair_type':'positive',
         'metric_group':'MULTI_CHUNK_DIAGNOSTIC',
         'E0':{'predicted_answerability':'NONE'},'E4':{'predicted_answerability':'NONE'},
         'structured':{'E0':blank,'E4':blank}},
    ]
    scored = _score(rows)
    assert scored['E0']['overall']['n'] == 1
    assert scored['E0']['multi_chunk_diagnostic']['n'] == 1
