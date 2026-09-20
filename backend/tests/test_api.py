import importlib.util
import json
import pytest
from fastapi.testclient import TestClient
from test_rag import make_engine


def client_for(tmp_path):
    assert importlib.util.find_spec('app.main') is not None, 'HTTP application is missing'
    from app.main import create_app
    engine = make_engine(tmp_path)
    return TestClient(create_app(engine=engine, run_worker=False)), engine


def test_upload_api_rejects_invalid_and_exposes_no_disk_path(tmp_path):
    client, engine = client_for(tmp_path)
    with client:
        bad = client.post('/api/documents', files={'file': ('bad.exe', b'bad')})
        assert bad.status_code == 400
        result = client.post('/api/documents', files={'file': ('../notes.txt', b'hello world')})
        assert result.status_code == 200
        doc = result.json()['document']
        assert doc['name'] == 'notes.txt' and 'path' not in doc
        engine.process_document(doc['id'])
        detail = client.get('/api/documents/' + doc['id']).json()
        assert detail['chunks'][0]['text'] == 'hello world'
        assert client.delete('/api/documents/' + doc['id']).status_code == 200
        assert client.get('/api/documents/' + doc['id']).status_code == 404


def test_settings_keys_never_return_and_blank_preserves_key(tmp_path):
    client, _ = client_for(tmp_path)
    with client:
        response = client.put('/api/settings', json={'chat_model': 'another', 'chat_key': None})
        assert response.status_code == 200
        assert response.json()['chat_key_set']
        assert 'private-key' not in response.text
        invalid = client.put('/api/settings', json={'chat_url': 'https://user:secret@example.com/v1'})
        assert invalid.status_code == 400


def test_chat_endpoint_streams_and_persists_sources(tmp_path):
    client, engine = client_for(tmp_path)
    doc, _ = engine.upload('a.txt', '缓存设置为 30 分钟。'.encode(), 'default')
    engine.process_document(doc['id'])
    with client:
        result = client.post('/api/chat', json={'question': '缓存多久', 'kb_id': 'default', 'document_ids': []})
        assert result.status_code == 200
        assert 'event: done' in result.text
        conversations = client.get('/api/conversations').json()
        messages = client.get('/api/conversations/' + conversations[0]['id']).json()['messages']
        assert len(messages) == 2
        assert messages[1]['citations'][0]['name'] == 'a.txt'
        assert client.delete('/api/conversations/' + conversations[0]['id']).status_code == 200
        assert client.get('/api/conversations').json() == []


def test_cross_origin_mutations_are_blocked(tmp_path):
    client, _ = client_for(tmp_path)
    with client:
        response = client.put('/api/settings', headers={'Origin': 'https://untrusted.example'}, json={'chat_url': 'https://attacker.test'})
        assert response.status_code == 403


def test_production_assets_have_executable_mime_and_sample_is_markdown(tmp_path, monkeypatch):
    import mimetypes
    from app import main
    # Windows registry may identify JS as text/plain. Modules must override it.
    mimetypes.add_type('text/plain', '.js')
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<html>app</html>')
    (dist / 'assets' / 'app.js').write_text('export const ready = true;')
    (tmp_path / 'public').mkdir()
    (tmp_path / 'public' / 'sample.md').write_text('# sample knowledge', encoding='utf-8')
    monkeypatch.setattr(main, 'ROOT', tmp_path)
    client = TestClient(main.create_app(engine=make_engine(tmp_path / 'store'), run_worker=False))
    with client:
        assert client.get('/assets/app.js').headers['content-type'].startswith(('text/javascript', 'application/javascript'))
        assert client.get('/sample.md').text.startswith('# sample')
