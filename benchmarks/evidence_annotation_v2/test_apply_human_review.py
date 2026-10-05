from collections import Counter

from benchmarks.evidence_annotation_v2.apply_human_review import build_signed_decisions


def test_explicit_17_confirm_4_correct_signoff():
    signed = build_signed_decisions('2026-10-03T12:21:18Z')
    assert signed['state'] == 'HUMAN_SIGNED'
    rows = {d['case_id']:d for d in signed['decisions']}
    assert Counter(d['decision'] for d in rows.values()) == {'CONFIRMED':17,'CORRECTED':4}
    assert rows['T03']['corrections']['positive_evidence_ids'] == ['technical:35']
    assert rows['A04']['corrections']['positive_evidence_ids'] == ['paper:44']
    assert rows['F03']['corrections']['positive_evidence_ids'] == ['tables:4','tables:5']
    assert rows['F03']['hard_negative_labels'] == {'tables:5':'PARTIAL'}
    assert rows['F03']['corrections']['metric_group'] == 'MULTI_CHUNK_DIAGNOSTIC'
    assert rows['F04']['corrections']['positive_evidence_ids'] == ['tables:5']
    assert all(d['parser_status']=='PASS' for d in rows.values())
