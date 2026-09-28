import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('probe_coverage_blind', Path('scripts/probe_coverage_blind.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def item(number, location='第 40 页', text='正文', source='lexical'):
    return {'chunk_id': f'doc:{number}', 'document_id': 'doc', 'name': 'book.pdf',
            'location': location, 'text': text, 'retrieval_sources': [source]}


def test_pool_includes_bounded_existing_candidates_and_same_page_neighbor():
    ranked = [item(185, text='续段')] + [item(i, location=f'第 {i} 页') for i in range(20)]
    ranked[0]['lexical_rank'] = 6
    context = item(146, location='第 30 页', source='context')
    record = {'retrieval': {'ranked_items': ranked, 'context_items': [context]}}

    pool = probe.candidate_pool(record, [item(184), item(186, location='第 41 页')])

    ids = [row['chunk_id'] for row in pool]
    assert 'doc:185' in ids and 'doc:184' in ids and 'doc:146' in ids
    assert 'doc:186' not in ids
    assert pool[ids.index('doc:184')]['probe_source'] == 'same_page_neighbor'
    assert len(ids) <= 22


def test_selection_prompt_does_not_include_gold_or_ask_for_answer():
    messages = probe.selection_messages('为什么复用 KV？', [item(77)], [item(185)])

    assert len(messages) == 2
    assert '为什么复用 KV？' in messages[1]['content']
    assert 'doc:185' in messages[1]['content']
    assert 'doc:77' in messages[1]['content']
    assert '不要回答用户问题' in messages[0]['content']
    assert '金标准' not in str(messages)


def test_selection_accepts_only_two_existing_candidate_ids():
    pool = [item(184), item(185)]

    assert probe.parse_selection('{"add_chunk_ids":["doc:184","doc:185"]}', pool) == ['doc:184', 'doc:185']
    with pytest.raises(ValueError, match='候选'):
        probe.parse_selection('{"add_chunk_ids":["doc:999"]}', pool)
    with pytest.raises(ValueError, match='最多'):
        probe.parse_selection('{"add_chunk_ids":["doc:184","doc:185","doc:184"]}', pool)
