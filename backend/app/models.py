"""Real local embeddings and configurable HTTP model boundaries."""
import hashlib
import json
import math
import threading
from pathlib import Path
from urllib.parse import urlparse

import httpx

LOCAL_MODEL = 'BAAI/bge-small-zh-v1.5'


def fingerprint(config):
    source = [config['embedding_mode'], config['embedding_model'], config['embedding_url'] if config['embedding_mode'] == 'api' else '', 'chunk-v2-400-60']
    return hashlib.sha256(json.dumps(source).encode()).hexdigest()[:24]


def embedding_ready(config):
    return bool(config['embedding_model']) and (config['embedding_mode'] == 'local' or bool(config['embedding_url']) and config['allow_external'])


class ModelError(ValueError):
    pass


def validate_url(url):
    parts = urlparse(url)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('服务地址必须是 http(s) URL，不能包含账号、密钥或查询参数。')
    if parts.scheme == 'http' and parts.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('远程模型服务请使用 HTTPS；HTTP 仅用于本机服务。')


class ModelClient:
    def __init__(self, cache: Path, transport=None):
        self.cache = cache
        self.transport = transport
        self._local = None
        self._lock = threading.Lock()

    def client(self, key):
        return httpx.Client(headers={'Authorization': f'Bearer {key}'} if key else {}, timeout=httpx.Timeout(90, connect=15), transport=self.transport, follow_redirects=False)

    @staticmethod
    def check_response(response):
        if response.status_code >= 400:
            hints = {401: '密钥无效', 403: '没有访问权限', 404: '检查服务地址与模型名称', 429: '额度不足或请求过于频繁'}
            raise ModelError(f'模型服务返回 HTTP {response.status_code}：{hints.get(response.status_code, "服务暂不可用，请稍后重试")}。')

    def embed(self, texts, config, query=False):
        if config['embedding_mode'] == 'local':
            with self._lock:
                if self._local is None:
                    from fastembed import TextEmbedding
                    self._local = TextEmbedding(LOCAL_MODEL, cache_dir=str(self.cache), threads=2)
                # BGE's retrieval instruction is only used for query vectors.
                inputs = ['为这个句子生成表示以用于检索相关文章：' + t for t in texts] if query else texts
                return [v.tolist() for v in self._local.embed(inputs, batch_size=16)]
        if not embedding_ready(config):
            raise ModelError('请先配置向量模型，并允许将文本发送到所选服务。')
        validate_url(config['embedding_url'])
        try:
            with self.client(config['embedding_key']) as client:
                response = client.post(config['embedding_url'].rstrip('/') + '/embeddings', json={'model': config['embedding_model'], 'input': texts})
                self.check_response(response)
                rows = sorted(response.json()['data'], key=lambda r: r['index'])
                vectors = [row['embedding'] for row in rows]
                if [row['index'] for row in rows] != list(range(len(texts))) or not vectors or not vectors[0]:
                    raise ValueError()
                if any(len(v) != len(vectors[0]) or any(not isinstance(n, (int, float)) or not math.isfinite(n) for n in v) for v in vectors):
                    raise ValueError()
                return vectors
        except ModelError:
            raise
        except httpx.RequestError as exc:
            raise ModelError('无法连接向量服务，请检查网络和地址后重试。') from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelError('向量服务返回的数据格式不正确。') from exc

    async def stream(self, messages, config):
        if not config['chat_url'] or not config['chat_model']:
            raise ModelError('请先在设置中配置回答模型。')
        if not config['allow_external']:
            raise ModelError('请先在设置中允许将问题和检索片段发送到所选模型服务。')
        validate_url(config['chat_url'])
        payload = {'model': config['chat_model'], 'messages': messages, 'stream': True, 'max_tokens': 2400}
        if urlparse(config['chat_url']).hostname == 'api.deepseek.com':
            payload['thinking'] = {'type': 'disabled'}
        try:
            headers = {'Authorization': f'Bearer {config["chat_key"]}'} if config['chat_key'] else {}
            async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(90, connect=15), transport=self.transport, follow_redirects=False) as client:
                async with client.stream('POST', config['chat_url'].rstrip('/') + '/chat/completions', json=payload) as response:
                    self.check_response(response)
                    finished = False
                    async for line in response.aiter_lines():
                        if not line.startswith('data:'):
                            continue
                        raw = line[5:].strip()
                        if raw == '[DONE]':
                            finished = True
                            break
                        event = json.loads(raw)
                        if event.get('error'):
                            raise ModelError('模型服务中断了回答，请重试。')
                        for choice in event.get('choices', []):
                            if choice.get('finish_reason') == 'length':
                                raise ModelError('回答超过长度限制，请缩小问题范围后重试。')
                            if choice.get('finish_reason') == 'stop':
                                finished = True
                            text = choice.get('delta', {}).get('content')
                            if text:
                                yield text
                    if not finished:
                        raise ModelError('模型连接意外结束，回答未完成。')
        except ModelError:
            raise
        except httpx.RequestError as exc:
            raise ModelError('模型连接失败或超时，请检查网络后重试。') from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelError('回答服务返回了不兼容的数据。') from exc
