import importlib.util
from io import BytesIO
import json
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_pdf_review import make_text_pdf
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


def test_pdf_detail_marks_suspicious_chunks_and_pages_without_marking_text_files(tmp_path):
    client, engine = client_for(tmp_path)
    pdf, _ = engine.upload('sample.pdf', b'%PDF-1.7', 'default')
    engine.store.replace_chunks(pdf['id'], [
        {'ordinal': 0, 'location': '第 9 页', 'text': 'CSP g_i = \uf03d 0.2'},
        {'ordinal': 1, 'location': '第 10 页', 'text': '普通正文'},
    ])
    text, _ = engine.upload('sample.txt', b'plain', 'default')
    engine.store.replace_chunks(text['id'], [
        {'ordinal': 0, 'location': '第 1 段', 'text': '特殊字符 \uf03d'},
    ])
    with client:
        pdf_detail = client.get('/api/documents/' + pdf['id']).json()
        text_detail = client.get('/api/documents/' + text['id']).json()

    assert pdf_detail['suspicious_pages'] == [9]
    assert [c['suspected'] for c in pdf_detail['chunks']] == [True, False]
    assert text_detail['suspicious_pages'] == []
    assert not text_detail['chunks'][0].get('suspected', False)


def test_pdf_page_api_saves_reindexes_and_reverts_corrected_text(tmp_path):
    client, engine = client_for(tmp_path / 'data')
    content = make_text_pdf(tmp_path / 'sample.pdf', ['Bad formula. Other requirement.'])
    with client:
        doc = client.post('/api/documents', files={'file': ('sample.pdf', content, 'application/pdf')}).json()['document']
        engine.process_document(doc['id'])
        page_url = f'/api/documents/{doc["id"]}/pdf-pages/1'
        page = client.get(page_url).json()
        assert page['raw_text'] == 'Bad formula. Other requirement.'
        assert page['page_count'] == 1
        assert page['suspected'] is False
        assert page['correction'] is None and page['revision'] is None
        assert len(page['source_hash']) == len(page['raw_text_hash']) == 64
        assert client.get(page_url + '/correction-image').status_code == 404
        original = client.get(f'/api/documents/{doc["id"]}/file')
        assert original.headers['content-type'].startswith('application/pdf')
        assert 'inline' in original.headers['content-disposition']

        form = {key: page[key] for key in ('source_hash', 'raw_text_hash')}
        form.update(corrected_text='g_i = 0.2 if x_i >= 300. Other requirement.', expected_revision='')
        saved = client.put(page_url + '/correction', data=form)
        assert saved.status_code == 200
        assert engine.store.document(doc['id'])['status'] == 'queued'
        stale = client.put(page_url + '/correction', data={**form, 'corrected_text': 'Another formula.'})
        assert stale.status_code == 409

        engine.process_document(doc['id'])
        assert engine.store.document(doc['id'])['status'] == 'ready'
        assert client.get(f'/api/documents/{doc["id"]}').json()['chunks'][0]['text'] == form['corrected_text']
        current = client.get(page_url).json()
        assert current['correction'] == form['corrected_text']
        assert current['revision']
        assert client.delete(page_url + '/correction').status_code == 200
        engine.process_document(doc['id'])
        assert client.get(f'/api/documents/{doc["id"]}').json()['chunks'][0]['text'] == page['raw_text']


def test_pdf_page_api_rejects_invalid_page_text_hash_rectangle_and_processing(tmp_path):
    client, engine = client_for(tmp_path / 'data')
    content = make_text_pdf(tmp_path / 'sample.pdf', ['Bad formula.'])
    with client:
        pdf = client.post('/api/documents', files={'file': ('sample.pdf', content, 'application/pdf')}).json()['document']
        text = client.post('/api/documents', files={'file': ('sample.txt', b'hello')}).json()['document']
        engine.process_document(pdf['id'])
        url = f'/api/documents/{pdf["id"]}/pdf-pages/1'
        page = client.get(url).json()
        form = {'source_hash': page['source_hash'], 'raw_text_hash': page['raw_text_hash'],
                'corrected_text': 'Good formula.', 'expected_revision': ''}

        assert client.get(f'/api/documents/{pdf["id"]}/pdf-pages/0').status_code == 400
        assert client.get(f'/api/documents/{pdf["id"]}/pdf-pages/2').status_code == 400
        assert client.get(f'/api/documents/{text["id"]}/pdf-pages/1').status_code == 400
        assert client.put(url + '/correction', data={**form, 'source_hash': 'old'}).status_code == 400
        assert client.put(url + '/correction', data={**form, 'raw_text_hash': 'old'}).status_code == 400
        assert client.put(url + '/correction', data={**form, 'corrected_text': '  '}).status_code == 400
        assert client.put(url + '/correction', data={**form, 'corrected_text': 'x' * 100_001}).status_code == 400
        assert client.put(url + '/correction', data={**form, 'corrected_text': page['raw_text']}).status_code == 400
        assert client.put(url + '/correction', data={**form, 'rect': '[0.8,0.2,0.1,0.5]'}).status_code == 400
        assert client.put(url + '/correction', data={**form, 'rect': 'bad-json'}).status_code == 400
        engine.store.update_document(pdf['id'], status='embedding')
        assert client.put(url + '/correction', data=form).status_code == 409
        engine.store.update_document(pdf['id'], status='ready')
        assert engine.store.pdf_correction(pdf['id'], 1) is None


def test_pdf_correction_image_is_verified_served_and_cleaned_up(tmp_path):
    client, engine = client_for(tmp_path / 'data')
    content = make_text_pdf(tmp_path / 'sample.pdf', ['Bad formula.'])
    png = BytesIO()
    Image.new('RGB', (16, 16), 'white').save(png, format='PNG')
    with client:
        doc = client.post('/api/documents', files={'file': ('sample.pdf', content, 'application/pdf')}).json()['document']
        engine.process_document(doc['id'])
        url = f'/api/documents/{doc["id"]}/pdf-pages/1'
        page = client.get(url).json()
        form = {'source_hash': page['source_hash'], 'raw_text_hash': page['raw_text_hash'],
                'corrected_text': 'Good formula.', 'expected_revision': ''}
        assert client.put(url + '/correction', data=form,
                          files={'image': ('proof.png', b'not-a-png', 'image/png')}).status_code == 400
        assert client.put(url + '/correction', data=form,
                          files={'image': ('proof.png', b'x' * (2 * 1024 * 1024 + 1), 'image/png')}).status_code == 400
        assert not list((engine.root / 'review_images').glob('*')) if (engine.root / 'review_images').exists() else True

        saved = client.put(url + '/correction', data=form,
                           files={'image': ('proof.png', png.getvalue(), 'image/png')})
        assert saved.status_code == 200
        image = client.get(url + '/correction-image')
        assert image.status_code == 200 and image.content == png.getvalue()
        assert client.get(url).json()['has_image'] is True
        assert 'image_path' not in client.get(url).text
        image_path = engine.store.pdf_correction(doc['id'], 1)['image_path']
        assert image_path and (engine.root / 'review_images').exists()
        assert client.delete(f'/api/documents/{doc["id"]}').status_code == 200
        assert not list((engine.root / 'review_images').glob('*'))


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
