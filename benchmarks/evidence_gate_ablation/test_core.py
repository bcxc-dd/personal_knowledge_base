from benchmarks.evidence_gate_ablation.core import plan_pair


def sample():
    case = {'case_id': 'X01', 'query': '甲的分值是多少？', 'source_title': '样本资料',
            'document_id': 'doc1', 'expected_answer': '不能传给模型的 gold',
            'expected_facts': [{'value': 999}]}
    unit = {'unit_id': 'X01:positive:x:1', 'case_id': 'X01',
            'chunk_ids': ['x:1'], 'evidence_text': '甲的分值为 5 分。',
            'evidence_metadata': [{'chunk_id': 'x:1', 'page': 2}],
            'answerability': 'FULL'}
    row = {'unit_id': unit['unit_id'], 'case_id': case['case_id'], 'query': case['query'],
           'chunk_ids': ['x:1'], 'E0': {'predicted_answerability': 'NONE',
                                     'missing': ['甲的分值是多少？']}}
    return case, unit, row


def test_none_hard_veto_refuses_but_advisory_uses_same_evidence_without_gold():
    case, unit, row = sample()
    hard, advisory = plan_pair(case, unit, row)
    assert hard['variant'] == 'hard_veto' and hard['mode'] == 'forced_refusal'
    assert hard['messages'] is None and '资料不足' in hard['forced_answer']
    assert advisory['variant'] == 'advisory' and advisory['mode'] == 'model'
    prompt = str(advisory['messages'])
    assert case['query'] in prompt and unit['evidence_text'] in prompt
    assert case['source_title'] in prompt and '第 2 页' in prompt
    assert '999' not in prompt and case['expected_answer'] not in prompt
    assert '可能误判' in prompt


def test_partial_hard_veto_passes_source_with_missing_note():
    case, unit, row = sample()
    row['E0'] = {'predicted_answerability': 'PARTIAL', 'missing': ['乙的分值']}
    hard, advisory = plan_pair(case, unit, row)
    assert hard['mode'] == advisory['mode'] == 'model'
    assert '乙的分值' in str(hard['messages'])
    assert '乙的分值' not in str(advisory['messages'])
    assert unit['evidence_text'] in str(hard['messages'])
    assert unit['evidence_text'] in str(advisory['messages'])


def test_plan_rejects_mismatched_frozen_identity():
    case, unit, row = sample()
    row['chunk_ids'] = ['x:2']
    try:
        plan_pair(case, unit, row)
    except ValueError as exc:
        assert 'identity' in str(exc)
    else:
        raise AssertionError('mismatched input was accepted')
