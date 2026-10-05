import importlib.util
import asyncio
import json

import pytest


def make_engine(tmp_path, chat_payloads=None):
    assert importlib.util.find_spec('app.engine') is not None, 'RAG engine is missing'
    from app.engine import Engine
    from app.models import ModelClient
    import httpx

    def provider(request):
        payload = json.loads(request.content)
        if request.url.path.endswith('/embeddings'):
            vectors = [[1.0, 0.0, 0.0] if '缓存' in t else [0.0, 1.0, 0.0] for t in payload['input']]
            return httpx.Response(200, json={'data': [{'index': i, 'embedding': v} for i, v in enumerate(vectors)]})
        if chat_payloads is not None:
            chat_payloads.append(payload)
        text = '缓存设置为 30 分钟。[1]'
        event = {'choices': [{'delta': {'content': text}, 'finish_reason': None}]}
        done = {'choices': [{'delta': {}, 'finish_reason': 'stop'}]}
        return httpx.Response(200, text=f'data: {json.dumps(event)}\n\ndata: {json.dumps(done)}\n\ndata: [DONE]\n\n')

    models = ModelClient(tmp_path / 'models', transport=httpx.MockTransport(provider))
    engine = Engine(tmp_path, models=models)
    engine.store.save_settings({'embedding_mode': 'api', 'embedding_url': 'https://model.test/v1', 'embedding_model': 'test-embed', 'chat_url': 'https://model.test/v1', 'chat_model': 'test-chat', 'chat_key': 'private-key', 'embedding_key': 'embed-secret', 'allow_external': True})
    return engine


def answer_events(engine, *args):
    async def collect():
        return [event async for event in engine.answer(*args)]
    return asyncio.run(collect())


def test_requirement_answer_shares_query_plan_across_retrieval_and_evidence(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('2027届推免细则.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': 0, 'location': '第 2 页',
         'text': '二、推荐条件。申请者须通过全部应修必修课程，必修课程平均学分绩点大于等于3.2。'},
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.vectors.search = lambda *args, **kwargs: []

    events = answer_events(engine, '推免是否有绩点要求  ', 'default', [doc['id']], None)
    sources = next(event['data'] for event in events if event['event'] == 'sources')

    assert sources['evidence_assessment']['status'] == 'supported'
    assert [hit['chunk_id'] for hit in sources['citations']] == [f'{doc["id"]}:0']
    assert sources['retrieval_diagnostics']['lexical_candidate_count'] == 1
    assert sources['retrieval_diagnostics']['query_plan']['metric'] == '绩点'


def test_partial_eligibility_answer_tells_model_which_basis_is_missing(tmp_path):
    payloads = []
    engine = make_engine(tmp_path, payloads)
    doc, _ = engine.upload('奖学金细则.txt', b'placeholder', 'default')
    from app.models import fingerprint
    body = '奖学金申请条件：平均成绩达到80分，所有课程合格。'
    engine.store.replace_chunks(doc['id'], [{'ordinal': 0, 'location': '第 1 页', 'text': body}])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False})
    engine.vectors.search = lambda *args, **kwargs: [
        {'chunk_id': f'{doc["id"]}:0', 'document_id': doc['id'], 'name': doc['name'],
         'location': '第 1 页', 'text': body, 'distance': 0.1},
    ]

    events = answer_events(engine, '怎样拿到奖学金申请资格？', 'default', [doc['id']], None)
    sources = next(event['data'] for event in events if event['event'] == 'sources')

    assert sources['evidence_assessment']['status'] == 'partial'
    assert [hit['chunk_id'] for hit in sources['citations']] == [f'{doc["id"]}:0']
    assert '缺少完整条件或甄选依据' in payloads[0]['messages'][-1]['content']


def test_requirement_retrieval_uses_original_and_one_rewrite_without_history_terms(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('2027届推免细则.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False})
    embedded = []

    def embed(texts, config, query=False):
        embedded.extend(texts)
        return [[1.0, 0.0] for _ in texts]

    engine.models.embed = embed
    engine.vectors.search = lambda *args, **kwargs: []

    result = engine.retrieve('奖学金怎么申请？\n推免是否有绩点要求？', 'default', [doc['id']],
                             current_question='推免是否有绩点要求？')

    assert len(embedded) == 2
    assert embedded[0] == '推免是否有绩点要求？'
    assert '奖学金' not in ' '.join(embedded)
    assert result.diagnostics['query_plan']['lexical_terms'][:2] == ['推免', '绩点']


def test_unrecognized_query_keeps_one_vector_embedding(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('technical.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    embedded = []
    engine.models.embed = lambda texts, config, query=False: embedded.extend(texts) or [[1.0, 0.0] for _ in texts]
    engine.vectors.search = lambda *args, **kwargs: []

    engine.retrieve('什么是 KV Cache？', 'default', [doc['id']])

    assert embedded == ['什么是 KV Cache？']


def test_rewritten_vector_query_can_recover_a_passage_missed_by_original(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('2027届推免细则.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 2})
    engine.models.embed = lambda texts, config, query=False: [[float(i), 1.0] for i in range(len(texts))]

    def search(fp, vector, eligible, limit):
        chunk = 'unrelated' if vector[0] == 0.0 else 'gpa-rule'
        body = ('学院设立推免工作小组，负责宣传工作。' if chunk == 'unrelated'
                else '推荐条件：必修课程平均学分绩点大于等于3.2。')
        return [{'chunk_id': f'{doc["id"]}:{chunk}', 'document_id': doc['id'],
                 'name': doc['name'], 'location': '第 2 页', 'text': body, 'distance': 0.1}]

    engine.vectors.search = search
    engine.store.search_chunks_exact = lambda *args, **kwargs: []

    hits = engine.retrieve('推免是否有绩点要求？', 'default', [doc['id']])

    assert {hit['chunk_id'] for hit in hits} == {f'{doc["id"]}:unrelated', f'{doc["id"]}:gpa-rule'}
    assert hits.diagnostics['vector_query_count'] == 2


@pytest.mark.parametrize('question,expected', [
    ('书中给出了某特定公司内部 GPU 集群的精确数量吗？', ('公司', '集群', '时间')),
    ('书中给出了某个未指名产品的精确单价吗？', ('产品', '规格', '计价', '时间')),
])
def test_unspecified_target_answer_asks_for_details_without_citing_neighbor(tmp_path, question, expected):
    engine = make_engine(tmp_path)
    events = answer_events(engine, question, 'default', [], None)
    done = next(event['data'] for event in events if event['event'] == 'done')

    assert done['citations'] == []
    assert done['evidence_assessment']['status'] == 'insufficient'
    assert all(word in done['content'] for word in expected)
    assert '现有资料不足以回答：' not in done['content']


def test_upload_dedup_processing_retrieval_and_delete(tmp_path):
    engine = make_engine(tmp_path)
    doc, duplicate = engine.upload('缓存.txt', '缓存设置为 30 分钟。'.encode(), 'default')
    assert not duplicate
    other, duplicate = engine.upload('重复.txt', '缓存设置为 30 分钟。'.encode(), 'default')
    assert duplicate and other['id'] == doc['id']
    engine.process_document(doc['id'])
    assert engine.store.document(doc['id'])['status'] == 'ready'
    hits = engine.retrieve('缓存多久', 'default', [])
    assert hits[0]['document_id'] == doc['id']
    assert hits[0]['text'] == '缓存设置为 30 分钟。'
    engine.delete_document(doc['id'])
    assert engine.retrieve('缓存多久', 'default', []) == []
    assert engine.store.document(doc['id']) is None


def test_scope_and_model_change_never_leak_old_vectors(tmp_path):
    engine = make_engine(tmp_path)
    kb = engine.store.create_kb('私人')
    doc, _ = engine.upload('私有.txt', '缓存设置为 30 分钟。'.encode(), kb['id'])
    engine.process_document(doc['id'])
    assert engine.retrieve('缓存多久', 'default', []) == []
    assert len(engine.retrieve('缓存多久', kb['id'], [])) == 1
    engine.store.save_settings({'embedding_model': 'new-model'})
    assert engine.retrieve('缓存多久', kb['id'], []) == []


def test_rerank_selects_its_highest_scored_fused_evidence(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('paper.txt', '算法思想 创新点 实验结果'.encode(), 'default')
    from app.models import fingerprint
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': True, 'reranker_evidence': 2})
    candidates = [
        {'chunk_id': 'top', 'document_id': doc['id'], 'text': '算法思想', 'distance': 0.01, 'name': 'paper.txt', 'location': '1'},
        {'chunk_id': 'middle', 'document_id': doc['id'], 'text': '创新点', 'distance': 0.2, 'name': 'paper.txt', 'location': '2'},
        {'chunk_id': 'low', 'document_id': doc['id'], 'text': '实验结果', 'distance': 0.4, 'name': 'paper.txt', 'location': '3'},
    ]
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: candidates
    engine.reranker.rank = lambda question, items, config: type('R', (), {'items': list(reversed(items)), 'provider': 'test', 'device': 'cpu', 'fallback': False, 'error': None})()
    result = engine.retrieve('算法思想和创新点', 'default', [])
    assert [item['chunk_id'] for item in result] == ['low', 'middle']


def test_disabled_rerank_uses_final_evidence_limit_directly(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('paper.txt', '算法思想 创新点 实验结果'.encode(), 'default')
    from app.models import fingerprint
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_candidates': 20, 'reranker_evidence': 2})
    seen = {}
    candidates = [{'chunk_id': str(i), 'document_id': doc['id'], 'text': str(i), 'distance': i / 10, 'name': 'paper.txt', 'location': str(i)} for i in range(2)]
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    def search(*args, **kwargs):
        seen['limit'] = kwargs['limit']
        return candidates
    engine.vectors.search = search
    result = engine.retrieve('算法思想', 'default', [])
    assert seen['limit'] == 2
    assert len(result) == 2
    assert result.diagnostics['provider'] == 'rrf'
    assert result.diagnostics['rrf_k'] == 60


def test_eligibility_retrieval_keeps_condition_section_from_candidate_pool(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('award.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': True, 'reranker_evidence': 6})
    candidates = [
        {'chunk_id': f'{doc["id"]}:{i}', 'document_id': doc['id'], 'name': 'award.txt',
         'location': f'第 {i + 1} 页', 'text': f'奖学金申请流程与排序，第 {i} 条说明。',
         'distance': i / 20}
        for i in range(10)
    ]
    candidates[6]['text'] = '1.选择条件2后计分，这只是表格说明，不是申请条件章节。'
    candidates.append({
        'chunk_id': f'{doc["id"]}:10', 'document_id': doc['id'], 'name': 'award.txt',
        'location': '第 11 页', 'text': '二、申请条件\n平均成绩应达到80分，申请人须无不及格课程。',
        'distance': 0.6,
    })
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: candidates
    engine.store.search_chunks_exact = lambda *args, **kwargs: []
    engine.reranker.rank = lambda question, items, config: type('R', (), {
        'items': items, 'provider': 'test', 'device': 'cpu', 'fallback': False, 'error': None,
    })()

    result = engine.retrieve('怎样获得奖学金申请资格？', 'default', [])

    assert f'{doc["id"]}:10' in {hit['chunk_id'] for hit in result}
    assert f'{doc["id"]}:6' not in {hit['chunk_id'] for hit in result}
    assert next(hit for hit in result.diagnostics['items'] if hit['chunk_id'] == f'{doc["id"]}:10')['selected']


def test_retrieval_coverage_uses_current_question_not_previous_turn(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('award.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': True, 'reranker_evidence': 1})
    candidates = [
        {'chunk_id': f'{doc["id"]}:0', 'document_id': doc['id'], 'name': 'award.txt',
         'location': '第 1 页', 'text': '评审委员会成员如下：主任张甲，委员李乙。', 'distance': 0.01},
        {'chunk_id': f'{doc["id"]}:1', 'document_id': doc['id'], 'name': 'award.txt',
         'location': '第 2 页', 'text': '二、申请条件\n平均成绩达到80分。', 'distance': 0.2},
    ]
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: candidates
    engine.store.search_chunks_exact = lambda *args, **kwargs: []
    engine.reranker.rank = lambda question, items, config: type('R', (), {
        'items': items, 'provider': 'test', 'device': 'cpu', 'fallback': False, 'error': None,
    })()

    result = engine.retrieve('怎么申请奖学金？\n评审委员会都有谁？', 'default', [],
                             current_question='评审委员会都有谁？')

    assert [hit['chunk_id'] for hit in result] == [f'{doc["id"]}:0']


def test_how_to_question_keeps_application_step_from_candidate_pool(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('award.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': True, 'reranker_evidence': 2})
    candidates = [
        {'chunk_id': f'{doc["id"]}:{i}', 'document_id': doc['id'], 'name': 'award.txt',
         'location': f'第 {i + 1} 页', 'text': f'奖学金资格和排名，第 {i} 条。',
         'distance': i / 20}
        for i in range(8)
    ]
    candidates[7]['text'] = '四、注意事项\n申请奖学金的学生必须递交书面申请，并选择一个类别。'
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: candidates
    engine.store.search_chunks_exact = lambda *args, **kwargs: []
    engine.reranker.rank = lambda question, items, config: type('R', (), {
        'items': items, 'provider': 'test', 'device': 'cpu', 'fallback': False, 'error': None,
    })()

    result = engine.retrieve('怎样获得奖学金申请资格？', 'default', [])

    assert f'{doc["id"]}:7' in {hit['chunk_id'] for hit in result}


def test_how_to_question_keeps_continuation_of_numbered_conditions(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('award.txt', b'placeholder', 'default')
    from app.models import fingerprint
    chunks = [
        ('第 7 页', '一、申请资格条件\n条件1.成绩达标。\n条件2.实践达标。\n条件3.竞赛达标。'),
        ('第 7 页', '条件4.可以通过科研成果申请，须由评审组认定。'),
        ('第 8 页', '成果必须与专业相关，申请人按评价分排名，择优获得名额。'),
    ]
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': i, 'location': location, 'text': body}
        for i, (location, body) in enumerate(chunks)
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 1})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: [{
        'chunk_id': f'{doc["id"]}:0', 'document_id': doc['id'], 'name': 'award.txt',
        'location': '第 7 页', 'text': chunks[0][1], 'distance': 0.01,
    }]

    result = engine.retrieve('怎样获得奖学金申请资格？', 'default', [])

    assert [hit['chunk_id'] for hit in result] == [f'{doc["id"]}:{i}' for i in range(3)]


def test_member_answer_context_excludes_other_group_in_same_chunk(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('committee.txt', b'placeholder', 'default')
    from app.models import fingerprint
    body = '评审委员会成员如下：主任张甲，委员李乙。\n监督委员会成员如下：主任王丙，委员赵丁。'
    engine.store.replace_chunks(doc['id'], [{'ordinal': 0, 'location': '第 1 页', 'text': body}])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 1})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: [{
        'chunk_id': f'{doc["id"]}:0', 'document_id': doc['id'], 'name': 'committee.txt',
        'location': '第 1 页', 'text': body, 'distance': 0.01,
    }]
    captured = []

    async def answer_from_supplied_context(messages, config):
        captured.append(messages[-1]['content'])
        yield '评审委员会主任是张甲，委员是李乙。[1]'

    engine.models.stream = answer_from_supplied_context

    events = answer_events(engine, '评审委员会都有谁？', 'default', [], None)

    assert any(event['event'] == 'done' for event in events)
    assert '评审委员会成员如下' in captured[0]
    assert '监督委员会成员如下' not in captured[0]


def test_exact_acronym_match_is_included_when_vector_results_miss_it(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('attention.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.replace_chunks(doc['id'], [
        {'id': 'vector-only', 'ordinal': 0, 'location': 'page 1', 'text': 'This unrelated cache setting is popular.'},
        {'id': 'mha-definition', 'ordinal': 1, 'location': 'page 44', 'text': 'Multi-Head Attention (MHA) gives every Q head its own K and V heads.'},
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 2})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: [{
        'chunk_id': f'{doc["id"]}:0', 'document_id': doc['id'], 'text': 'This unrelated cache setting is popular.',
        'distance': 0.01, 'name': 'attention.txt', 'location': 'page 1',
    }]

    result = engine.retrieve('What is MHA?', 'default', [])

    assert {item['chunk_id'] for item in result} == {f'{doc["id"]}:0', f'{doc["id"]}:1'}


def test_chapter_overview_expands_selected_intro_to_continuation_and_own_summary(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('book.txt', b'placeholder', 'default')
    from app.models import fingerprint
    chunks = [
        ('第 401 页', '第 10 章 训练系统\n训练状态包括权重、梯度、优化器状态和激活；显存容量限制放置方式。' * 2),
        ('第 401 页', '分片引入通信等待，训练持续数周还需保存 checkpoint，并衡量故障后的重复计算。'),
        ('第 401 页', '本章会比较训练容量、计算、通信和数据准备，并评估不同资源方案。'),
        ('第 420 页', '10.3 分布式训练的其他实现细节。'),
        ('第 446 页', '本章小结\nZeRO 减少状态复制，重计算与卸载换取显存，通信决定每步关键路径。'),
        ('第 446 页', '长期训练还需计算数据准备、checkpoint 和故障重做；RL 涉及策略版本与训推一致性。'),
        ('第 446 页', '最终比较显示 48 卡方案满足期限，32 卡方案不能按期完成。'),
        ('第 447 页', '第 11 章 推理系统\n下一章有自己的概述。'),
        ('第 500 页', '本章小结\n下一章的总结不属于训练系统。'),
    ]
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': index, 'location': location, 'text': text}
        for index, (location, text) in enumerate(chunks)
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 1})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: [{
        'chunk_id': f'{doc["id"]}:0', 'document_id': doc['id'], 'name': 'book.txt',
        'location': '第 401 页', 'text': chunks[0][1], 'distance': 0.01,
    }]

    result = engine.retrieve('第 10 章训练系统重点讨论哪些系统问题？', 'default', [])

    assert [item['chunk_id'] for item in result] == [f'{doc["id"]}:{i}' for i in (0, 1, 2, 4, 5, 6)]
    assert [item['chunk_id'] for item in result.diagnostics['context_items']] == [f'{doc["id"]}:{i}' for i in (1, 2, 4, 5, 6)]
    assert [item['chunk_id'] for item in result.diagnostics['items'] if item['selected']] == [f'{doc["id"]}:0']
    assert all(item['retrieval_sources'] == ['context'] for item in result.diagnostics['context_items'])


def test_chapter_overview_marks_selected_own_summary_without_relabelling_its_retrieval_source(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('book.txt', b'placeholder', 'default')
    from app.models import fingerprint
    chunks = [
        ('第 32 页', '第 2 章 模型架构\n本章从计算图推导存储容量、运算量和读写量，不能仅凭参数量估算资源。' * 2),
        ('第 32 页', '哪些权重能共享、哪些状态需长期保存、哪些结果只需暂存，决定后续资源分配。'),
        ('第 82 页', '本章小结\n矩阵尺寸决定权重容量，batch 和上下文长度改变运算与状态读写量。'),
        ('第 83 页', '第 3 章 推理负载\n下一章开始。'),
        ('第 99 页', '本章小结\n下一章的结论不属于模型架构。'),
    ]
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': index, 'location': location, 'text': body}
        for index, (location, body) in enumerate(chunks)
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 2})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: [
        {'chunk_id': f'{doc["id"]}:{ordinal}', 'document_id': doc['id'], 'name': 'book.txt',
         'location': chunks[ordinal][0], 'text': chunks[ordinal][1], 'distance': 0.01 + ordinal * 0.001}
        for ordinal in (0, 2)
    ]

    result = engine.retrieve('第 2 章模型架构主要要解决什么资源问题？', 'default', [])

    assert [item['chunk_id'] for item in result] == [f'{doc["id"]}:{i}' for i in (0, 2, 1)]
    assert result[1]['chapter_evidence_role'] == 'chapter_summary'
    assert result[1]['retrieval_sources'] != ['context']
    assert result[2]['chapter_evidence_role'] == 'same_page'
    assert all(item['chunk_id'] != f'{doc["id"]}:4' for item in result)


def test_chapter_mainline_question_includes_own_summary_and_stops_at_next_chapter(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('book.txt', b'placeholder', 'default')
    from app.models import fingerprint
    chunks = [
        ('第 318 页', '第 8 章 推理优化\n本章组织请求、批处理、KV 管理和推测解码，在给定时间内返回更多正确答案。' * 2),
        ('第 318 页', '本章还会比较各方法的额外开销。'),
        ('第 354 页', '本章小结\n先检查内存是否足够，再判断能否按期完成，最后比较每个合格结果的 GPU 时间。'),
        ('第 355 页', '第 9 章 分布式推理\n下一章研究计算和状态的放置。'),
        ('第 360 页', '本章小结\n这一段属于第 9 章。'),
    ]
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': index, 'location': location, 'text': body}
        for index, (location, body) in enumerate(chunks)
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 1})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.store.search_chunks_exact = lambda *args, **kwargs: []
    engine.vectors.search = lambda *args, **kwargs: [{
        'chunk_id': f'{doc["id"]}:0', 'document_id': doc['id'], 'name': 'book.txt',
        'location': chunks[0][0], 'text': chunks[0][1], 'distance': 0.01,
    }]

    result = engine.retrieve('第 8 章推理优化的主线是什么？', 'default', [])

    assert [item['chunk_id'] for item in result] == [f'{doc["id"]}:{i}' for i in (0, 1, 2)]
    assert all(item['chunk_id'] not in {f'{doc["id"]}:3', f'{doc["id"]}:4'} for item in result)


def test_chapter_resource_question_adds_bounded_body_facts_for_named_factors(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('book.txt', b'placeholder', 'default')
    from app.models import fingerprint
    chunks = [
        ('第 32 页', '第 2 章 模型架构\n从计算图推导存储容量、运算量和读写量，分析共享权重、长期状态和临时数据。' * 2),
        ('第 40 页', '全注意力的运算量随上下文长度增长，比逐 token 投影增长更快。'),
        ('第 41 页', '每个上下文 token 要保存 KV；batch 增加时，每条独立请求各增加一份上下文状态。'),
        ('第 45 页', '将 KV 组数减半，KV 投影参数和状态容量减半，查询与上下文交互仍按查询头数累计。'),
        ('第 57 页', '专家总数决定参数集合；选中专家数和尺寸决定单 token 运算，batch 分派影响读取的专家权重。'),
        ('第 82 页', '本章小结\nbatch、上下文、KV 组织和专家激活改变不同资源项。'),
        ('第 83 页', '第 3 章 推理负载\n下一章讨论其他资源。'),
    ]
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': index, 'location': location, 'text': body}
        for index, (location, body) in enumerate(chunks)
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 1})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.store.search_chunks_exact = lambda *args, **kwargs: []
    engine.vectors.search = lambda *args, **kwargs: [{
        'chunk_id': f'{doc["id"]}:0', 'document_id': doc['id'], 'name': 'book.txt',
        'location': chunks[0][0], 'text': chunks[0][1], 'distance': 0.01,
    }]

    result = engine.retrieve('第 2 章模型架构主要要解决什么资源问题？', 'default', [])

    assert {item['chunk_id'] for item in result} == {f'{doc["id"]}:{i}' for i in range(6)}
    assert all(item['chunk_id'] != f'{doc["id"]}:6' for item in result)


def test_technical_coverage_selects_relevant_candidates_beyond_default_limit():
    from app.engine import select_evidence_items
    def hit(key, body):
        return {'chunk_id': key, 'document_id': 'doc', 'text': body}

    filler = [hit(f'f{i}', '泛泛介绍缓存和系统架构。') for i in range(6)]
    reuse = hit('reuse', '旧 token 的 K、V 在权重、位置不变时复用，避免重算；当前查询的注意力仍需计算。')
    unrelated = hit('other', '另一章谈 KV 在网络之间传输。')
    selected = select_evidence_items('为什么生成时复用 KV 缓存？', [*filler, unrelated, reuse], 6)
    assert [item['chunk_id'] for item in selected] == [*(f'f{i}' for i in range(6)), 'reuse']

    selected = select_evidence_items('长上下文怎样改变计算和存储需求？', [
        *filler,
        hit('growth', '全局 KV 随上下文增长，每个新 token 都要读取旧 KV；递推状态大小固定。'),
        hit('calculation', 'decode 只处理新 token，旧 token 的 KV 从缓存读取，当前查询的注意力仍要执行。'),
        unrelated,
    ], 6)
    assert [item['chunk_id'] for item in selected[6:]] == ['growth', 'calculation']
    math_notation = hit('math_kv', 'decode 只处理新 token，旧 token 的 𝐾、𝑉 从缓存读取，当前查询的注意力仍要执行。')
    assert select_evidence_items('长上下文怎样改变计算和存储需求？', [*filler, math_notation], 6)[-1] == math_notation
    first_decode = hit('first_decode', '输入越长，第一次 decode 要访问的上下文就越多，上下文交互的运算量随长度增长。')
    assert select_evidence_items('长上下文怎样改变计算和存储需求？', [*filler, first_decode], 6)[-1] == first_decode

    selected = select_evidence_items('prefill 和 decode 的负载特点有什么差异？', [
        *filler,
        hit('old_kv', 'prefill 同时处理多个 token，decode 只对新 token 计算，旧 token 的 KV 从缓存读取。'),
        unrelated,
    ], 6)
    assert [item['chunk_id'] for item in selected[6:]] == ['old_kv']
    assert select_evidence_items('缓存在哪里？', [*filler, reuse], 6) == filler


def test_chapter_overview_stops_when_next_chapter_starts_inside_a_chunk(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('book.txt', b'placeholder', 'default')
    from app.models import fingerprint
    chunks = [
        ('第 32 页', '第 2 章 模型架构\n本章从计算图推导存储容量、运算量和读写量，' * 3),
        ('第 32 页', '上一章末尾。\n第 3 章 推理负载\n下一章讨论模型架构之外的请求负载和资源问题。'),
        ('第 33 页', '本章小结\n这是第 3 章的结论。'),
    ]
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': index, 'location': location, 'text': body}
        for index, (location, body) in enumerate(chunks)
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 2})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.store.search_chunks_exact = lambda *args, **kwargs: []
    engine.vectors.search = lambda *args, **kwargs: [
        {'chunk_id': f'{doc["id"]}:{index}', 'document_id': doc['id'], 'name': 'book.txt',
         'location': chunks[index][0], 'text': chunks[index][1], 'distance': 0.01 + index * 0.001}
        for index in (0, 1)
    ]

    result = engine.retrieve('第 2 章模型架构主要要解决什么资源问题？', 'default', [])
    from app.evidence import assess_evidence
    assessment = assess_evidence('第 2 章模型架构主要要解决什么资源问题？', result)

    assert 'chapter_evidence_role' not in result[1]
    assert result.diagnostics['context_items'] == []
    assert assessment.evidence_chunk_ids == (f'{doc["id"]}:0',)


def test_non_overview_query_does_not_expand_chapter_context(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('book.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': 0, 'location': '第 401 页', 'text': '第 10 章 训练系统\n训练权重和梯度。'},
        {'ordinal': 1, 'location': '第 401 页', 'text': '后续片段。'},
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 1})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: [{
        'chunk_id': f'{doc["id"]}:0', 'document_id': doc['id'], 'name': 'book.txt',
        'location': '第 401 页', 'text': '第 10 章 训练系统\n训练权重和梯度。', 'distance': 0.01,
    }]

    result = engine.retrieve('训练权重是什么？', 'default', [])

    assert [item['chunk_id'] for item in result] == [f'{doc["id"]}:0']


def test_steps_question_bridges_selected_same_page_chunk_gap(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('guide.txt', b'placeholder', 'default')
    from app.models import fingerprint
    chunks = [
        ('第 14 页', '一次请求的处理过程\n应用组织输入，服务入口接收请求，路由器选择执行实例。入口接收的上下文包括用户输入、历史对话和检索到的参考材料。'),
        ('第 14 页', '入口接收的上下文包括用户输入、历史对话和检索到的参考材料。入口检查请求后，文本转换为 token；调度器把请求放入队列并组成 batch。CPU 运行时向 GPU 提交程序，GPU 执行算子并保存临时状态。'),
        ('第 14 页', 'CPU 运行时向 GPU 提交程序，GPU 执行算子并保存临时状态。结果沿连接返回。'),
        ('第 15 页', '另一页讨论模型的权重加载。'),
    ]
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': index, 'location': location, 'text': body}
        for index, (location, body) in enumerate(chunks)
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 2})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.store.search_chunks_exact = lambda *args, **kwargs: []
    engine.vectors.search = lambda *args, **kwargs: [
        {'chunk_id': f'{doc["id"]}:{index}', 'document_id': doc['id'], 'name': 'guide.txt',
         'location': chunks[index][0], 'text': chunks[index][1], 'distance': 0.01 + index * 0.001}
        for index in (0, 2)
    ]

    result = engine.retrieve('一次请求从应用到 GPU 经历哪些步骤？', 'default', [])

    assert [item['chunk_id'] for item in result] == [f'{doc["id"]}:{i}' for i in (0, 2, 1)]
    assert result[2]['context_reason'] == 'same_page_gap'
    assert [item['chunk_id'] for item in result.diagnostics['context_items']] == [f'{doc["id"]}:1']


def test_steps_question_does_not_bridge_across_page_boundary(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('guide.txt', b'placeholder', 'default')
    from app.models import fingerprint
    chunks = [
        ('第 14 页', '应用组织输入，路由器选择实例。'),
        ('第 14 页', '另一个主题的补充说明。'),
        ('第 15 页', 'CPU 向 GPU 提交程序，GPU 执行计算。'),
    ]
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': index, 'location': location, 'text': body}
        for index, (location, body) in enumerate(chunks)
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 2})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.store.search_chunks_exact = lambda *args, **kwargs: []
    engine.vectors.search = lambda *args, **kwargs: [
        {'chunk_id': f'{doc["id"]}:{index}', 'document_id': doc['id'], 'name': 'guide.txt',
         'location': chunks[index][0], 'text': chunks[index][1], 'distance': 0.01 + index * 0.001}
        for index in (0, 2)
    ]

    result = engine.retrieve('一次请求从应用到 GPU 经历哪些步骤？', 'default', [])

    assert [item['chunk_id'] for item in result] == [f'{doc["id"]}:0', f'{doc["id"]}:2']


def test_steps_question_does_not_bridge_unrelated_same_page_chunk(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('guide.txt', b'placeholder', 'default')
    from app.models import fingerprint
    chunks = [
        ('第 14 页', '一次 GPU 请求的流程：入口接收请求，然后路由器选择实例。'),
        ('第 14 页', 'GPU 价格与购买预算说明，按年度计算采购金额。'),
        ('第 14 页', '实例运行后 GPU 执行算子，最后向用户返回结果。'),
    ]
    engine.store.replace_chunks(doc['id'], [
        {'ordinal': index, 'location': location, 'text': body}
        for index, (location, body) in enumerate(chunks)
    ])
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 2})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.store.search_chunks_exact = lambda *args, **kwargs: []
    engine.vectors.search = lambda *args, **kwargs: [
        {'chunk_id': f'{doc["id"]}:{index}', 'document_id': doc['id'], 'name': 'guide.txt',
         'location': chunks[index][0], 'text': chunks[index][1], 'distance': 0.01 + index * 0.001}
        for index in (0, 2)
    ]

    result = engine.retrieve('一次 GPU 请求从入口到返回经历哪些步骤？', 'default', [])

    assert [item['chunk_id'] for item in result] == [f'{doc["id"]}:0', f'{doc["id"]}:2']


def test_lexical_terms_preserve_multiword_technical_phrase():
    from app.engine import lexical_terms

    assert lexical_terms('什么是 AI Infra？') == ['AI', 'AI Infra']


def test_lexical_terms_extract_chinese_technical_terms_without_question_words():
    from app.engine import lexical_terms

    assert lexical_terms('预填充和解码分别做什么？') == ['预填充', '解码']


def test_lexical_terms_do_not_leave_broken_question_suffixes():
    from app.engine import lexical_terms

    assert lexical_terms('怎么样可以保研？') == ['保研']
    assert lexical_terms('院推免小组都有谁') == ['院推免小组']
    assert '绩点' in lexical_terms('我的绩点是3.1，可以保研吗？')


def test_lexical_terms_do_not_remove_question_words_inside_content_words():
    from app.engine import lexical_terms

    assert any('申请奖学金' in term for term in lexical_terms('申请奖学金的条件是什么？'))


def test_lexical_terms_keep_content_across_common_question_grammar():
    from app.engine import lexical_terms

    assert '上下文' in lexical_terms('在模型调用中，上下文指什么？为什么它会影响执行？')
    assert '模型权重' in lexical_terms('为什么模型权重需要驻留在显存中？')
    assert '数量级估算' in lexical_terms('书中为什么强调先做数量级估算？')
    assert '推理优化' in lexical_terms('第 8 章推理优化的主线是什么？')


def test_normalize_bare_acronym_as_definition_request():
    from app.engine import normalize_question

    assert normalize_question(' MHA ') == 'MHA 是什么？请解释该术语的定义、机制和作用。'


def test_normalize_question_leaves_complete_and_non_acronym_inputs_unchanged():
    from app.engine import normalize_question

    assert normalize_question('MHA是什么') == 'MHA是什么'
    assert normalize_question('AI Infra') == 'AI Infra'
    assert normalize_question('A100') == 'A100'


def test_retrieval_preserves_two_lexical_evidence_items(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('infra.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 3})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: [
        {'chunk_id': 'vector-a', 'document_id': doc['id'], 'text': 'unrelated a', 'distance': 0.01, 'name': 'infra.txt', 'location': '第 2 页'},
        {'chunk_id': 'vector-b', 'document_id': doc['id'], 'text': 'unrelated b', 'distance': 0.02, 'name': 'infra.txt', 'location': '第 3 页'},
        {'chunk_id': 'vector-c', 'document_id': doc['id'], 'text': 'unrelated c', 'distance': 0.03, 'name': 'infra.txt', 'location': '第 4 页'},
    ]
    engine.store.search_chunks_exact = lambda *args, **kwargs: [
        {'chunk_id': 'definition', 'document_id': doc['id'], 'text': 'AI Infra 是基础设施', 'name': 'infra.txt', 'location': '第 11 页', 'lexical_score': 2},
        {'chunk_id': 'overview', 'document_id': doc['id'], 'text': 'AI Infra 包含六层', 'name': 'infra.txt', 'location': '第 13 页', 'lexical_score': 1},
    ]

    result = engine.retrieve('什么是 AI Infra？', 'default', [])

    assert {'definition', 'overview'} <= {item['chunk_id'] for item in result}


def test_retrieve_fuses_routes_without_fabricating_vector_metadata(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('infra.txt', b'placeholder', 'default')
    from app.models import fingerprint
    engine.store.update_document(doc['id'], status='ready', fingerprint=fingerprint(engine.store.settings()))
    engine.store.save_settings({'reranker_enabled': False, 'reranker_evidence': 3})
    engine.models.embed = lambda *args, **kwargs: [[1, 0, 0]]
    engine.vectors.search = lambda *args, **kwargs: [
        {'chunk_id': 'both', 'document_id': doc['id'], 'text': 'vector', 'distance': 0.1, 'name': 'infra.txt', 'location': '第 16 页'},
    ]
    engine.store.search_chunks_exact = lambda *args, **kwargs: [
        {'chunk_id': 'both', 'document_id': doc['id'], 'text': 'both', 'name': 'infra.txt', 'location': '第 16 页', 'lexical_score': 2},
        {'chunk_id': 'page-14', 'document_id': doc['id'], 'text': '预填充和解码', 'name': 'infra.txt', 'location': '第 14 页', 'lexical_score': 1},
    ]

    result = engine.retrieve('预填充和解码分别做什么？', 'default', [])

    page_14 = next(item for item in result.diagnostics['items'] if item['chunk_id'] == 'page-14')
    assert result[0]['chunk_id'] == 'both'
    assert page_14['vector_similarity'] is None
    assert page_14['retrieval_sources'] == ['lexical']
    assert result.diagnostics['vector_candidate_count'] == 1
    assert result.diagnostics['lexical_candidate_count'] == 2


def test_diverse_lexical_hits_keep_first_hit_per_page():
    from app.engine import diverse_lexical_hits

    hits = diverse_lexical_hits([
        {'chunk_id': 'cover', 'location': '第 1 页'},
        {'chunk_id': 'preface-a', 'location': '第 2 页'},
        {'chunk_id': 'preface-b', 'location': '第 2 页'},
        {'chunk_id': 'definition', 'location': '第 11 页'},
        {'chunk_id': 'overview', 'location': '第 13 页'},
    ], 4)

    assert [hit['chunk_id'] for hit in hits] == ['cover', 'preface-a', 'definition', 'overview']


def test_redacted_settings_and_unconfigured_upload(tmp_path):
    engine = make_engine(tmp_path)
    public = engine.store.settings(public=True)
    assert 'private-key' not in json.dumps(public)
    assert 'embed-secret' not in json.dumps(public)
    assert public['chat_key_set']
    engine.store.save_settings({'embedding_model': ''})
    doc, _ = engine.upload('a.txt', b'hello', 'default')
    engine.process_document(doc['id'])
    assert engine.store.document(doc['id'])['status'] == 'waiting_config'
    assert engine.store.chunks(doc['id'])[0]['text'] == 'hello'


def test_stream_saves_grounded_answer_and_sources(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('缓存.txt', '缓存设置为 30 分钟。'.encode(), 'default')
    engine.process_document(doc['id'])
    events = answer_events(engine, '缓存多久', 'default', [], None)
    result = next(e['data'] for e in events if e['event'] == 'done')
    assert '30 分钟' in result['content']
    assert result['citations'][0]['document_id'] == doc['id']
    history = engine.store.messages(result['conversation_id'])
    assert [m['role'] for m in history] == ['user', 'assistant']


def test_empty_knowledge_base_gives_no_evidence_response(tmp_path):
    engine = make_engine(tmp_path)
    events = answer_events(engine, '有什么计划', 'default', [], None)
    result = next(e['data'] for e in events if e['event'] == 'done')
    assert '资料' in result['content']
    assert result['citations'] == []


def test_restart_recovers_interrupted_ingestion(tmp_path):
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('a.txt', b'recover me', 'default')
    engine.store.update_document(doc['id'], status='embedding')
    engine.store.recover()
    assert engine.store.document(doc['id'])['status'] == 'queued'


def test_changed_same_name_requires_explicit_replacement(tmp_path):
    engine = make_engine(tmp_path)
    engine.upload('policy.txt', b'old policy', 'default')
    with pytest.raises(ValueError, match='同名'):
        engine.upload('policy.txt', b'new policy', 'default')
    assert len(engine.store.documents()) == 1


def test_cancelled_answer_closes_upstream_and_records_incomplete(tmp_path):
    import httpx
    from app.models import ModelClient
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('a.txt', '缓存设置为 30 分钟。'.encode(), 'default')
    engine.process_document(doc['id'])

    async def run():
        started = asyncio.Event()
        closed = asyncio.Event()

        class WaitingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                started.set()
                await asyncio.Event().wait()
                yield b''

            async def aclose(self):
                closed.set()

        def provider(request):
            if request.url.path.endswith('/embeddings'):
                return httpx.Response(200, json={'data': [{'index': 0, 'embedding': [1, 0, 0]}]})
            return httpx.Response(200, stream=WaitingStream())

        engine.models = ModelClient(tmp_path / 'cache', transport=httpx.MockTransport(provider))

        async def consume():
            return [event async for event in engine.answer('缓存多久', 'default', [], None)]

        task = asyncio.create_task(consume())
        # A non-async implementation fails immediately instead of reaching upstream.
        ready_task = asyncio.create_task(started.wait())
        done, _ = await asyncio.wait({task, ready_task}, timeout=3, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            ready_task.cancel()
            task.result()
        assert started.is_set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()
        convo = engine.store.conversations()[0]
        assert engine.store.messages(convo['id'])[-1]['status'] == 'interrupted'

    asyncio.run(run())
