"""Real TCP regression: closing a browser stream must release the chat slot."""
import asyncio
import json
import socket
import threading
import time

import httpx
import uvicorn

from test_rag import make_engine


def test_browser_disconnect_releases_chat_slot(tmp_path):
    from app.main import create_app
    from app.models import ModelClient
    engine = make_engine(tmp_path)
    doc, _ = engine.upload('a.txt', '缓存设置为 30 分钟。'.encode(), 'default')
    engine.process_document(doc['id'])
    closed = threading.Event()

    class WaitingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
            await asyncio.Event().wait()
        async def aclose(self):
            closed.set()

    def provider(request):
        if request.url.path.endswith('/embeddings'):
            return httpx.Response(200, json={'data': [{'index': 0, 'embedding': [1, 0, 0]}]})
        return httpx.Response(200, stream=WaitingStream())

    engine.models = ModelClient(tmp_path / 'models', transport=httpx.MockTransport(provider))
    app = create_app(engine=engine, run_worker=False)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(.02)
        assert server.started
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5) as client:
            with client.stream('POST', '/api/chat', json={'question': '缓存多久'}) as response:
                assert response.status_code == 200
                for line in response.iter_lines():
                    if line.startswith('data:') and 'first' in line:
                        break
            assert closed.wait(2), 'upstream stream was not cancelled'
            # Give ASGI finalizers one event-loop turn, then verify next request.
            time.sleep(.05)
            with client.stream('POST', '/api/chat', json={'question': '缓存多久'}) as response:
                assert response.status_code == 200
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
