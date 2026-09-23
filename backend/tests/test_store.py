import sqlite3

from app.store import Store


def test_add_message_uses_named_columns_after_messages_schema_gains_metadata(tmp_path):
    store = Store(tmp_path)
    assert 'evidence_assessment' in {row['name'] for row in store.query('PRAGMA table_info(messages)')}
    conversation_id = store.create_conversation('问题', 'default')

    store.add_message(conversation_id, 'user', '问题')

    with sqlite3.connect(tmp_path / 'knowledge.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM messages').fetchone()[0] == 1
