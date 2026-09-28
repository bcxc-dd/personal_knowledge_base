from app.reranker import Reranker


def _candidates():
    return [{'chunk_id': 'a', 'text': 'first'}, {'chunk_id': 'b', 'text': 'second'}]


def _install_fake_model(monkeypatch, session_providers):
    from fastembed.rerank.cross_encoder import onnx_text_cross_encoder

    class Session:
        def get_providers(self):
            return session_providers

    class Model:
        def __init__(self, *args, **kwargs):
            self.model = Session()

        def rerank(self, question, texts, batch_size):
            return [0.1, 0.9]

    monkeypatch.setattr(onnx_text_cross_encoder, 'OnnxTextCrossEncoder', Model)


def test_cuda_rerank_loads_runtime_and_reports_actual_device_after_cache(monkeypatch, tmp_path):
    import onnxruntime as ort

    preloads = []
    monkeypatch.setattr(ort, 'get_available_providers', lambda: ['CUDAExecutionProvider', 'CPUExecutionProvider'])
    monkeypatch.setattr(ort, 'preload_dlls', lambda **kwargs: preloads.append(kwargs))
    _install_fake_model(monkeypatch, ['CUDAExecutionProvider', 'CPUExecutionProvider'])
    reranker = Reranker(tmp_path)
    config = {'reranker_enabled': True, 'reranker_device': 'cuda'}

    first = reranker.rank('question', _candidates(), config)
    second = reranker.rank('question', _candidates(), config)

    assert preloads == [{'directory': ''}]
    assert first.provider == second.provider == 'local-reranker'
    assert first.device == second.device == 'cuda'
    assert [item['chunk_id'] for item in second.items] == ['b', 'a']


def test_cuda_rerank_does_not_claim_gpu_when_session_uses_cpu(monkeypatch, tmp_path):
    import onnxruntime as ort

    monkeypatch.setattr(ort, 'get_available_providers', lambda: ['CUDAExecutionProvider', 'CPUExecutionProvider'])
    monkeypatch.setattr(ort, 'preload_dlls', lambda **kwargs: None)
    _install_fake_model(monkeypatch, ['CPUExecutionProvider'])

    result = Reranker(tmp_path).rank(
        'question', _candidates(), {'reranker_enabled': True, 'reranker_device': 'cuda'}
    )

    assert result.provider == 'rrf'
    assert result.fallback is True
    assert 'CUDAExecutionProvider' in result.error
