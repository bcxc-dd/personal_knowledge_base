from benchmarks.evidence_annotation_v2.candidate_review import build_review


def test_candidate_review_is_independent_and_pending():
    review, evidence = build_review()
    cases = review['cases']
    assert len(cases) == 21
    assert len({c['case_id'] for c in cases}) == 21
    assert {c['document_slug'] for c in cases} == {'policy', 'technical', 'paper', 'tables'}
    assert all(c['human_review_state'] == 'PENDING' for c in cases)
    assert all(c['split'] == 'TEST_CANDIDATE' for c in cases)
    assert all(c['parser_status'] in {'PASS', 'FAIL', 'AMBIGUOUS'} for c in cases)
    assert all(c['required_facts'] and c['positive_evidence_ids'] and c['expected_facts'] for c in cases)
    assert all(c['answerability'] == 'FULL' for c in cases)
    assert all(c['relation_status'] == 'ENTAILS' or c['relation_status'] == 'CONTRADICTS_QUERY_PROPOSITION' for c in cases)
    assert all(c['document_sha256'] and c['pdf_page'] and c['expected_answer'] for c in cases)
    assert sum(bool(c['query_rewrite_from']) for c in cases) >= 3
    assert len(evidence['hard_negative_pairs']) == 21
    for case in cases:
        assert case['hard_negative_evidence_ids']
        for chunk_id in case['positive_evidence_ids'] + case['hard_negative_evidence_ids']:
            assert chunk_id in evidence['chunks']
        assert not (len(case['positive_evidence_ids']) == 1 and
                    case['positive_evidence_ids'][0] in case['hard_negative_evidence_ids'])


def test_real_same_document_negative_pairs_and_table_binding():
    review, evidence = build_review()
    by_id = {c['case_id']: c for c in review['cases']}
    for pair in evidence['hard_negative_pairs']:
        case = by_id[pair['case_id']]
        chunk = evidence['chunks'][pair['chunk_id']]
        assert chunk['document_id'] == case['document_id']
        assert pair['reason']
        assert pair['answerability'] in {'PARTIAL', 'NONE'}
    assert by_id['P04']['positive_evidence_ids'] == ['policy:8']
    assert by_id['P04']['aggregation_category'] == 'COMPOUND_SINGLE_CHUNK'
    assert by_id['P04']['hard_negative_evidence_ids'] == ['policy:9']
    assert all(by_id[i]['structured_gold'] for i in ('A05', 'F01', 'F02', 'F03', 'F04', 'F05', 'T04'))
    assert all(by_id[i]['polarity_gold']['expected_polarity'] == 'NO' for i in ('P03', 'P06'))
    assert 'tables:5' in by_id['F04']['parser_validation']['checked_chunks']
    assert 'tables:6' in by_id['F04']['parser_validation']['checked_chunks']
    assert by_id['A05']['expected_facts'][0]['value'] == 0.0744
    assert by_id['A05']['expected_facts'][1]['value'] == 0.0729
    assert by_id['F03']['expected_facts'][0]['value'] == 99000
    assert by_id['F03']['expected_facts'][1]['value'] == 114000
