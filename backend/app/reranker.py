from dataclasses import dataclass
from pathlib import Path
import threading

RERANKER_MODEL = 'BAAI/bge-reranker-base'

@dataclass
class RerankResult:
    items: list[dict]
    provider: str
    device: str
    fallback: bool = False
    error: str | None = None

class Reranker:
    def __init__(self, cache: Path, model=None):
        self.cache = cache
        self._model = model
        self._lock = threading.Lock()

    def _load(self, config):
        if self._model is not None:
            return self._model, 'cpu'
        from fastembed.rerank.cross_encoder.onnx_text_cross_encoder import OnnxTextCrossEncoder
        requested = config.get('reranker_device', 'auto')
        use_cuda = requested in {'auto', 'cuda'}
        model_name = config.get('reranker_model') or RERANKER_MODEL
        self._model = OnnxTextCrossEncoder(model_name, cache_dir=str(self.cache), cuda=use_cuda, threads=2)
        return self._model, 'cuda' if use_cuda else 'cpu'

    def rank(self, question, candidates, config):
        original = [dict(item) for item in candidates]
        if not config.get('reranker_enabled', True) or len(original) < 2:
            return RerankResult(original, 'vector', 'none')
        try:
            with self._lock:
                model, device = self._load(config)
                scores = list(model.rerank(question, [item['text'] for item in original], batch_size=min(16, len(original))))
            ranked = []
            for item, score in zip(original, scores):
                value = dict(item); value['rerank_score'] = float(score); ranked.append(value)
            ranked.sort(key=lambda item: item['rerank_score'], reverse=True)
            return RerankResult(ranked, 'local-reranker', device)
        except Exception as exc:
            return RerankResult(original, 'vector', 'none', True, str(exc)[:240])
