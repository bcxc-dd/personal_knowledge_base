import importlib.util
from pathlib import Path
import asyncio

import pytest


spec = importlib.util.spec_from_file_location('probe_coverage_upper_bound', Path('scripts/probe_coverage_upper_bound.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def _item(ordinal, document='book', source='lexical'):
    return {'chunk_id': f'{document}:{ordinal}', 'document_id': document, 'name': 'book.pdf',
            'location': '第 1 页', 'text': f'片段 {ordinal}', 'retrieval_sources': [source]}


def test_probe_adds_only_existing_candidate_evidence_with_source_label():
    initial = {**_item(1), 'id': 1}
    candidate = _item(185)
    record = {'answer': {'input_evidence': [initial]}, 'retrieval': {
        'ranked_items': [initial, candidate], 'context_items': []}}

    evidence = probe.build_probe_evidence(record, [185])

    assert [item['chunk_id'] for item in evidence] == ['book:1', 'book:185']
    assert evidence[1]['probe_source'] == 'ranked_candidate'
    assert evidence[1]['id'] == 2
    assert 'probe_source' not in initial


def test_probe_can_include_ranked_body_and_chapter_summary_without_duplicates():
    initial = {**_item(62), 'id': 1}
    ranked = _item(71)
    summary = _item(146, source='context')
    record = {'answer': {'input_evidence': [initial]}, 'retrieval': {
        'ranked_items': [initial, ranked], 'context_items': [summary]}}

    evidence = probe.build_probe_evidence(record, [71, 146, 62])

    assert [item['chunk_id'] for item in evidence] == ['book:62', 'book:71', 'book:146']
    assert [item.get('probe_source') for item in evidence] == [None, 'ranked_candidate', 'chapter_context']


def test_probe_refuses_unavailable_or_cross_document_supplement():
    initial = {**_item(1), 'id': 1}
    record = {'answer': {'input_evidence': [initial]}, 'retrieval': {
        'ranked_items': [initial, _item(185, document='other')], 'context_items': []}}

    with pytest.raises(ValueError, match='当前资料'):
        probe.build_probe_evidence(record, [185])


def test_probe_limits_supplements_to_two():
    initial = {**_item(1), 'id': 1}
    record = {'answer': {'input_evidence': [initial]}, 'retrieval': {
        'ranked_items': [initial, _item(2), _item(3), _item(4)], 'context_items': []}}

    with pytest.raises(ValueError, match='最多两个'):
        probe.build_probe_evidence(record, [2, 3, 4])


def test_probe_distinguishes_same_page_neighbor_from_existing_candidate():
    initial = {**_item(77), 'id': 1}
    candidate = _item(185)
    neighbor = _item(184)
    record = {'answer': {'input_evidence': [initial]}, 'retrieval': {
        'ranked_items': [initial, candidate], 'context_items': []}}

    evidence = probe.build_probe_evidence(record, [184, 185], adjacent_rows=[neighbor])

    assert [item['chunk_id'] for item in evidence] == ['book:77', 'book:184', 'book:185']
    assert [item['probe_source'] for item in evidence[1:]] == ['adjacent_context', 'ranked_candidate']


def test_probe_refuses_neighbor_on_another_page():
    initial = {**_item(77), 'id': 1}
    candidate = _item(185)
    neighbor = {**_item(184), 'location': '第 2 页'}
    record = {'answer': {'input_evidence': [initial]}, 'retrieval': {
        'ranked_items': [initial, candidate], 'context_items': []}}

    with pytest.raises(ValueError, match='当前资料'):
        probe.build_probe_evidence(record, [184], adjacent_rows=[neighbor])


def test_probe_prompt_contains_only_supplied_evidence_and_question():
    evidence = [{**_item(185), 'id': 7, 'text': '旧 token 不必重算；当前注意力仍需计算。'}]

    messages = probe.build_probe_messages('为什么复用 KV？', evidence)

    assert len(messages) == 2
    assert '[7] book.pdf / 第 1 页' in messages[1]['content']
    assert '旧 token 不必重算' in messages[1]['content']
    assert '问题：为什么复用 KV？' in messages[1]['content']
    assert '不编造引用' in messages[0]['content']


def test_probe_rejects_generated_citation_outside_evidence():
    class FakeModel:
        async def stream(self, messages, config):
            yield '避免重复计算 [99]。'

    with pytest.raises(ValueError, match='无效引用'):
        asyncio.run(probe.generate_probe_answer('为什么复用？', [{**_item(185), 'id': 7}], FakeModel(), {}))
