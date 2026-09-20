from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
import json
import mimetypes
import os
import threading

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .engine import Engine
from .models import LOCAL_MODEL, fingerprint, validate_url

ROOT = Path(__file__).resolve().parents[2]


class SettingsInput(BaseModel):
    chat_url: str | None = None
    chat_model: str | None = Field(default=None, max_length=200)
    chat_key: str | None = Field(default=None, max_length=1000)
    embedding_mode: Literal['local', 'api'] | None = None
    embedding_url: str | None = None
    embedding_model: str | None = Field(default=None, max_length=200)
    embedding_key: str | None = Field(default=None, max_length=1000)
    allow_external: bool | None = None
    reranker_enabled: bool | None = None
    reranker_device: Literal['auto', 'cuda', 'cpu'] | None = None
    reranker_model: str | None = Field(default=None, max_length=200)
    reranker_candidates: int | None = Field(default=None, ge=2, le=50)
    reranker_evidence: int | None = Field(default=None, ge=1, le=20)


class NameInput(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class ChatInput(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    kb_id: str = 'default'
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    conversation_id: str | None = None


class NoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=4000)
    content: str = Field(min_length=1, max_length=20000)
    citations: list[dict] = Field(default_factory=list, max_length=20)


class NoteUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20000)


def create_app(engine=None, run_worker=True):
    # Windows registry associations can incorrectly serve modules as text/plain.
    mimetypes.add_type('text/javascript', '.js')
    mimetypes.add_type('text/css', '.css')
    engine = engine or Engine(Path(os.environ.get('RAG_DATA_DIR', ROOT / 'data')))
    chat_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        if run_worker:
            engine.start()
        yield
        engine.close()

    app = FastAPI(title='知屿 · Personal Knowledge', lifespan=lifespan)
    app.state.engine = engine
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', 'testserver'])

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        origin = request.headers.get('origin')
        allowed = {'http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8765', 'http://localhost:8765'}
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and origin and origin not in allowed:
            return JSONResponse({'detail': '仅接受本地应用发起的操作。'}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    def document_or_404(doc_id):
        doc = engine.store.document(doc_id)
        if not doc:
            raise HTTPException(404, '资料不存在或已删除。')
        return doc

    def public_document(doc):
        value = {k: v for k, v in doc.items() if k not in {'path', 'hash', 'deleted'}}
        value['needs_reindex'] = doc['status'] == 'ready' and doc['fingerprint'] != fingerprint(engine.store.settings())
        return value

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'storage': 'Chroma', 'version': '0.1.0'}

    @app.get('/api/knowledge-bases')
    def knowledge_bases():
        return engine.store.kbs()

    @app.post('/api/knowledge-bases')
    def create_kb(payload: NameInput):
        if not payload.name.strip():
            raise ValueError('知识库名称不能为空。')
        return engine.store.create_kb(payload.name)

    @app.get('/api/documents')
    def documents(kb_id: str | None = None):
        return [public_document(doc) for doc in engine.store.documents(kb_id)]

    @app.post('/api/documents')
    async def upload(file: UploadFile = File(...), kb_id: str = Form('default')):
        try:
            content = await file.read(20 * 1024 * 1024 + 1)
            doc, duplicate = engine.upload(file.filename or 'unknown', content, kb_id)
            return {'document': public_document(doc), 'duplicate': duplicate}
        finally:
            await file.close()

    @app.get('/api/documents/{doc_id}')
    def detail(doc_id: str):
        return {**public_document(document_or_404(doc_id)), 'chunks': engine.store.chunks(doc_id)}

    @app.get('/api/documents/{doc_id}/file')
    def original(doc_id: str):
        doc = document_or_404(doc_id)
        return FileResponse(doc['path'], filename=doc['name'], media_type='application/octet-stream')

    @app.post('/api/documents/{doc_id}/retry')
    def retry(doc_id: str):
        document_or_404(doc_id)
        engine.retry(doc_id)
        return {'ok': True}

    @app.delete('/api/documents/{doc_id}')
    def delete(doc_id: str):
        document_or_404(doc_id)
        engine.delete_document(doc_id)
        return {'ok': True}

    @app.get('/api/settings')
    def settings():
        return engine.store.settings(public=True)

    @app.put('/api/settings')
    def save_settings(payload: SettingsInput):
        changes = payload.model_dump(exclude_none=True)
        for key in ['chat_url', 'embedding_url']:
            if changes.get(key):
                validate_url(changes[key].strip())
        config = {**engine.store.settings(), **changes}
        if config['embedding_mode'] == 'local':
            changes['embedding_model'] = LOCAL_MODEL
        result = engine.store.save_settings(changes)
        engine.store.execute("UPDATE documents SET status='queued',error='' WHERE status='waiting_config' AND deleted=0")
        engine.wake.set()
        return result

    @app.post('/api/settings/reindex')
    def reindex():
        engine.store.execute("UPDATE documents SET status='queued',error='' WHERE deleted=0 AND status NOT IN ('parsing','embedding','indexing')")
        engine.wake.set()
        return {'ok': True}

    @app.get('/api/notes')
    def notes(query: str | None = None):
        return engine.store.notes(query.strip() if query else None)

    @app.post('/api/notes')
    def create_note(payload: NoteInput):
        return engine.store.create_note(payload.title, payload.question, payload.content, payload.citations)

    @app.get('/api/notes/{note_id}')
    def note(note_id: str):
        value = engine.store.note(note_id)
        if not value:
            raise HTTPException(404, '笔记不存在。')
        return value

    @app.patch('/api/notes/{note_id}')
    def update_note(note_id: str, payload: NoteUpdate):
        if not engine.store.note(note_id):
            raise HTTPException(404, '笔记不存在。')
        return engine.store.update_note(note_id, payload.title, payload.content)

    @app.delete('/api/notes/{note_id}')
    def delete_note(note_id: str):
        if not engine.store.note(note_id):
            raise HTTPException(404, '笔记不存在。')
        engine.store.delete_note(note_id)
        return {'ok': True}

    @app.get('/api/conversations')
    def conversations():
        return engine.store.conversations()

    @app.get('/api/conversations/{conversation_id}')
    def conversation(conversation_id: str):
        rows = engine.store.query('SELECT * FROM conversations WHERE id=?', (conversation_id,))
        if not rows:
            raise HTTPException(404, '会话不存在。')
        return {**rows[0], 'messages': engine.store.messages(conversation_id)}

    @app.delete('/api/conversations/{conversation_id}')
    def delete_conversation(conversation_id: str):
        with engine.store.connection() as db:
            db.execute('DELETE FROM messages WHERE conversation_id=?', (conversation_id,))
            db.execute('DELETE FROM conversations WHERE id=?', (conversation_id,))
        return {'ok': True}

    @app.post('/api/chat')
    def chat(payload: ChatInput):
        if not payload.question.strip():
            raise ValueError('请输入问题。')
        if not any(k['id'] == payload.kb_id for k in engine.store.kbs()):
            raise ValueError('知识库不存在。')
        if payload.conversation_id and not engine.store.query('SELECT id FROM conversations WHERE id=? AND kb_id=?', (payload.conversation_id, payload.kb_id)):
            raise ValueError('会话不存在或不属于当前知识库。')
        if not chat_lock.acquire(blocking=False):
            raise HTTPException(409, '已有回答正在生成，请等待或取消后再试。')

        async def events():
            try:
                yield 'event: status\ndata: "正在检索资料…"\n\n'
                async for event in engine.answer(payload.question.strip(), payload.kb_id, payload.document_ids, payload.conversation_id):
                    yield f'event: {event["event"]}\ndata: {json.dumps(event["data"], ensure_ascii=False)}\n\n'
            finally:
                chat_lock.release()
        return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    dist = ROOT / 'dist'
    if (dist / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/sample.md')
    def sample():
        return FileResponse(ROOT / 'public' / 'sample.md', media_type='text/markdown', filename='知屿示例资料.md')

    @app.get('/{path:path}')
    def frontend(path: str):
        if path.startswith('api/'):
            raise HTTPException(404, '接口不存在。')
        if (dist / 'index.html').exists():
            return FileResponse(dist / 'index.html')
        return JSONResponse({'message': '前端开发地址：http://localhost:5173；或运行 npm run build 后访问此服务。'})

    return app
