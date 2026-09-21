import importlib.util
import asyncio
import json

import pytest


def make_engine(tmp_path):
    assert importlib.util.find_spec('app.engine') is not None, 'RAG engine is missing'
    from app.engine import Engine
    from app.models import ModelClient
    import httpx

    def provider(request):
        payload = json.loads(request.content)
        if request.url.path.endswith('/embeddings'):
            vectors = [[1.0, 0.0, 0.0] if '缓存' in t else [0.0, 1.0, 0.0] for t in payload['input']]
            return httpx.Response(200, json={'data': [{'index': i, 'embedding': v} for i, v in enumerate(vectors)]})
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


def test_rerank_preserves_vector_top_evidence(tmp_path):
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
    assert 'top' in {item['chunk_id'] for item in result}
    assert len(result) == 2


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
    assert result.diagnostics['provider'] == 'vector'


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
