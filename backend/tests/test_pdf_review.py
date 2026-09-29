from pathlib import Path
import threading

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def make_text_pdf(path: Path, texts: list[str]) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
    })
    font_ref = writer._add_object(font)
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref}),
        })
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 20 250 Td ({text}) Tj ET'.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(path)
    return path.read_bytes()


def test_suspect_glyphs_flags_private_use_and_replacement_only():
    from app.pdf_review import has_suspect_glyphs

    assert has_suspect_glyphs('g_i = \uf03d 0.2')
    assert has_suspect_glyphs('g_i = \ufffd 0.2')
    assert not has_suspect_glyphs('g_i = 0.2 when x_i ≥ 300')


def test_read_pdf_page_returns_one_based_original_text_and_page_count(tmp_path):
    from app.pdf_review import read_pdf_page, text_hash

    path = tmp_path / 'two.pdf'
    make_text_pdf(path, ['First page', 'Second page'])

    assert read_pdf_page(path, 1) == ('First page', 2)
    assert read_pdf_page(path, 2) == ('Second page', 2)
    assert text_hash('First page') == '0bdbb750609ca61cb4a59ff84d565d437a5cd9a1abeb8abc0aaf243ceaec70b5'

    with pytest.raises(ValueError, match='页码'):
        read_pdf_page(path, 0)
    with pytest.raises(ValueError, match='页码'):
        read_pdf_page(path, 3)


def test_page_correction_replaces_only_matching_original_page():
    from app.parsing import Section, split_sections
    from app.pdf_review import apply_pdf_corrections, text_hash

    sections = [Section('Bad formula. Other requirement remains.', '第 1 页'),
                Section('Next page stays untouched.', '第 2 页')]
    correction = {'page_number': 1, 'source_hash': 'pdf-sha',
                  'raw_text_hash': text_hash(sections[0].text),
                  'corrected_text': 'g_i = 0.2 if x_i >= 300. Other requirement remains.'}

    result = apply_pdf_corrections(sections, [correction], 'pdf-sha')
    chunks = split_sections(result)

    assert result[0].text == correction['corrected_text']
    assert result[1].text == sections[1].text
    assert chunks[0]['location'] == '第 1 页'
    assert chunks[0]['text'].endswith('Other requirement remains.')

    with pytest.raises(ValueError, match='原文.*变化'):
        apply_pdf_corrections([Section('Changed extraction.', '第 1 页')], [correction], 'pdf-sha')
    with pytest.raises(ValueError, match='文件.*变化'):
        apply_pdf_corrections(sections, [correction], 'different-pdf-sha')


def test_pdf_correction_rebuild_replaces_old_vectors_and_revert_restores_original(tmp_path):
    from app.models import fingerprint
    from app.pdf_review import text_hash
    from test_rag import make_engine

    engine = make_engine(tmp_path / 'data')
    raw = ('Bad formula. ' * 45) + 'Other requirement remains.'
    pdf_path = tmp_path / 'sample.pdf'
    content = make_text_pdf(pdf_path, [raw])
    doc, _ = engine.upload('sample.pdf', content, 'default')
    engine.process_document(doc['id'])
    assert engine.store.document(doc['id'])['status'] == 'ready'
    old_chunks = engine.store.chunks(doc['id'])
    assert len(old_chunks) > 1

    corrected = 'CSP formula: g_i = 0.2 if x_i >= 300. Other requirement remains.'
    engine.set_pdf_correction(doc['id'], 1, doc['hash'], text_hash(raw), corrected,
                              [0.1, 0.2, 0.7, 0.4], None, None)
    assert engine.store.document(doc['id'])['status'] == 'queued'
    engine.process_document(doc['id'])
    assert engine.store.document(doc['id'])['status'] == 'ready'
    chunks = engine.store.chunks(doc['id'])
    assert len(chunks) == 1
    assert chunks[0]['text'] == corrected
    indexed = engine.vectors.collection(fingerprint(engine.store.settings())).get(
        where={'document_id': doc['id']}, include=['documents'])
    assert indexed['ids'] == [chunks[0]['id']]
    assert indexed['documents'] == [corrected]

    engine.retry(doc['id'])
    engine.process_document(doc['id'])
    assert engine.store.chunks(doc['id'])[0]['text'] == corrected
    engine.clear_pdf_correction(doc['id'], 1, engine.store.pdf_correction(doc['id'], 1)['updated_at'])
    engine.process_document(doc['id'])
    assert len(engine.store.chunks(doc['id'])) == len(old_chunks)
    assert engine.store.chunks(doc['id'])[0]['text'].startswith('Bad formula.')


def test_pdf_correction_uses_original_hash_and_delete_removes_saved_image(tmp_path):
    from app.pdf_review import text_hash
    from test_rag import make_engine

    engine = make_engine(tmp_path / 'data')
    pdf_path = tmp_path / 'sample.pdf'
    doc, _ = engine.upload('sample.pdf', make_text_pdf(pdf_path, ['Bad formula.']), 'default')
    engine.process_document(doc['id'])
    image = tmp_path / 'data' / 'review.png'
    image.write_bytes(b'screenshot')

    with pytest.raises(ValueError, match='哈希'):
        engine.set_pdf_correction(doc['id'], 1, doc['hash'], 'bad-hash', 'Good formula.', None, None, None)
    assert engine.store.document(doc['id'])['status'] == 'ready'

    engine.set_pdf_correction(doc['id'], 1, doc['hash'], text_hash('Bad formula.'),
                              'Good formula.', None, str(image), None)
    assert engine.store.pdf_correction(doc['id'], 1)['image_path'] == str(image)
    engine.delete_document(doc['id'])
    assert engine.store.pdf_correction(doc['id'], 1) is None
    assert not image.exists()


def test_worker_claim_waits_for_pending_correction_and_indexes_new_revision(tmp_path, monkeypatch):
    from app import engine as engine_module
    from app.pdf_review import text_hash
    from test_rag import make_engine

    engine = make_engine(tmp_path / 'data')
    doc, _ = engine.upload('sample.pdf', make_text_pdf(tmp_path / 'sample.pdf', ['Bad formula.']), 'default')
    engine.process_document(doc['id'])
    old = engine.set_pdf_correction(doc['id'], 1, doc['hash'], text_hash('Bad formula.'),
                                    'Old correction.', None, None, None)

    entered_read = threading.Event()
    release_read = threading.Event()
    parsing_claimed = threading.Event()
    failures = []
    original_read = engine_module.read_pdf_page
    original_update = engine.store.update_document

    def blocked_read(*args):
        entered_read.set()
        assert release_read.wait(5)
        return original_read(*args)

    def observed_update(doc_id, **fields):
        if fields.get('status') == 'parsing':
            parsing_claimed.set()
        return original_update(doc_id, **fields)

    def run(call):
        try:
            call()
        except Exception as exc:
            failures.append(exc)

    monkeypatch.setattr(engine_module, 'read_pdf_page', blocked_read)
    monkeypatch.setattr(engine.store, 'update_document', observed_update)
    setter = threading.Thread(target=lambda: run(lambda: engine.set_pdf_correction(
        doc['id'], 1, doc['hash'], text_hash('Bad formula.'), 'New correction.', None, None,
        old['updated_at'])))
    setter.start()
    assert entered_read.wait(5)
    worker = threading.Thread(target=lambda: run(lambda: engine.process_document(doc['id'])))
    worker.start()
    try:
        assert not parsing_claimed.wait(0.25), 'worker claimed the document while correction held mutation_lock'
    finally:
        release_read.set()
        setter.join(10)
        worker.join(10)
    assert not setter.is_alive() and not worker.is_alive() and not failures
    assert engine.store.document(doc['id'])['status'] == 'ready'
    assert engine.store.chunks(doc['id'])[0]['text'] == 'New correction.'
