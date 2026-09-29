import sqlite3

from app.store import Store


def test_add_message_uses_named_columns_after_messages_schema_gains_metadata(tmp_path):
    store = Store(tmp_path)
    assert 'evidence_assessment' in {row['name'] for row in store.query('PRAGMA table_info(messages)')}
    conversation_id = store.create_conversation('问题', 'default')

    store.add_message(conversation_id, 'user', '问题')

    with sqlite3.connect(tmp_path / 'knowledge.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM messages').fetchone()[0] == 1


def test_pdf_correction_persists_after_store_reopen_and_queues_atomically(tmp_path):
    store = Store(tmp_path)
    store.execute('INSERT INTO documents(id,kb_id,name,suffix,hash,path,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
                  ('pdf-1', 'default', 'sample.pdf', '.pdf', 'source-sha', 'sample.pdf', 'ready', 'a', 'a'))

    correction = store.put_pdf_correction('pdf-1', 9, 'source-sha', 'raw-sha',
                                          'g_i = 0.2', [0.1, 0.2, 0.8, 0.5], None, None)
    reopened = Store(tmp_path)

    assert reopened.pdf_correction('pdf-1', 9)['corrected_text'] == 'g_i = 0.2'
    assert reopened.pdf_correction('pdf-1', 9)['updated_at'] == correction['updated_at']
    assert reopened.document('pdf-1')['status'] == 'queued'
    assert [row['page_number'] for row in reopened.pdf_corrections('pdf-1')] == [9]
