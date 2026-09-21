from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import uuid

DEFAULTS = {
    'chat_url': 'https://api.deepseek.com', 'chat_model': 'deepseek-flash', 'chat_key': '',
    'embedding_mode': 'local', 'embedding_url': '', 'embedding_model': 'BAAI/bge-small-zh-v1.5',
    'embedding_key': '', 'allow_external': False,
    'reranker_enabled': False, 'reranker_device': 'auto', 'reranker_model': 'BAAI/bge-reranker-base',
    'reranker_candidates': 20, 'reranker_evidence': 8,
}


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


class Store:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'knowledge.sqlite3'
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS knowledge_bases (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, kb_id TEXT NOT NULL, name TEXT NOT NULL, suffix TEXT, size INTEGER,
                    hash TEXT, path TEXT, status TEXT, error TEXT DEFAULT '', chunk_count INTEGER DEFAULT 0,
                    fingerprint TEXT DEFAULT '', created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0
                );
                CREATE UNIQUE INDEX IF NOT EXISTS document_hash ON documents(kb_id, hash) WHERE deleted=0;
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, document_id TEXT, ordinal INTEGER, text TEXT, location TEXT
                );
                CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT, kb_id TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, citations TEXT, status TEXT, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, question TEXT NOT NULL, content TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS note_citations (
                    id TEXT PRIMARY KEY, note_id TEXT NOT NULL, citation_json TEXT NOT NULL, ordinal INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS notes_updated ON notes(updated_at);
            ''')
            db.execute('INSERT OR IGNORE INTO knowledge_bases VALUES (?, ?, ?)', ('default', '我的知识库', now()))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def query(self, sql, params=()):
        with self.connection() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]

    def execute(self, sql, params=()):
        with self.connection() as db:
            db.execute(sql, params)

    def settings(self, public=False):
        rows = self.query('SELECT value FROM settings WHERE id=1')
        config = {**DEFAULTS, **(json.loads(rows[0]['value']) if rows else {})}
        if public:
            for key in ['chat_key', 'embedding_key']:
                config[key + '_set'] = bool(config.pop(key))
        return config

    def save_settings(self, changes):
        config = self.settings()
        for key, value in changes.items():
            if key not in DEFAULTS or value is None:
                continue
            config[key] = value.strip() if isinstance(value, str) else value
        self.execute('INSERT INTO settings VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET value=excluded.value', (json.dumps(config),))
        return self.settings(public=True)

    def kbs(self):
        return self.query('SELECT k.*, (SELECT count(*) FROM documents d WHERE d.kb_id=k.id AND d.deleted=0) AS document_count FROM knowledge_bases k ORDER BY k.created_at')

    def create_kb(self, name):
        row = {'id': uid(), 'name': name.strip(), 'created_at': now()}
        self.execute('INSERT INTO knowledge_bases VALUES (:id,:name,:created_at)', row)
        return row

    def documents(self, kb_id=None):
        return self.query('SELECT * FROM documents WHERE deleted=0' + (' AND kb_id=?' if kb_id else '') + ' ORDER BY created_at DESC', (kb_id,) if kb_id else ())

    def document(self, doc_id):
        rows = self.query('SELECT * FROM documents WHERE id=? AND deleted=0', (doc_id,))
        return rows[0] if rows else None

    def update_document(self, doc_id, **fields):
        allowed = {'status', 'error', 'chunk_count', 'fingerprint', 'deleted'}
        assert set(fields) <= allowed
        fields['updated_at'] = now()
        self.execute('UPDATE documents SET ' + ','.join(f'{key}=?' for key in fields) + ' WHERE id=? AND deleted=0', (*fields.values(), doc_id))

    def replace_chunks(self, doc_id, chunks):
        with self.connection() as db:
            db.execute('DELETE FROM chunks WHERE document_id=?', (doc_id,))
            db.executemany('INSERT INTO chunks VALUES (?,?,?,?,?)', [(f'{doc_id}:{c["ordinal"]}', doc_id, c['ordinal'], c['text'], c['location']) for c in chunks])

    def chunks(self, doc_id):
        return self.query('SELECT * FROM chunks WHERE document_id=? ORDER BY ordinal', (doc_id,))

    def search_chunks_exact(self, document_ids, terms, limit=8):
        if not document_ids or not terms:
            return []
        matches = ' OR '.join('instr(lower(c.text), lower(?)) > 0' for _ in terms)
        score = ' + '.join(f'CASE WHEN instr(lower(c.text), lower(?)) > 0 THEN 1 ELSE 0 END' for _ in terms)
        document_placeholders = ','.join('?' for _ in document_ids)
        return self.query(
            f'''SELECT c.id AS chunk_id, c.document_id, c.text, c.location, d.name,
                       ({score}) AS lexical_score
                FROM chunks c JOIN documents d ON d.id=c.document_id
                WHERE c.document_id IN ({document_placeholders}) AND ({matches})
                ORDER BY lexical_score DESC, c.ordinal
                LIMIT ?''',
            (*terms, *document_ids, *terms, limit),
        )

    def recover(self):
        self.execute("UPDATE documents SET status='queued', error='' WHERE deleted=0 AND status IN ('parsing','embedding','indexing')")

    def conversations(self):
        return self.query('SELECT * FROM conversations ORDER BY created_at DESC')

    def create_conversation(self, question, kb_id):
        value = uid()
        self.execute('INSERT INTO conversations VALUES (?,?,?,?)', (value, question[:40], kb_id, now()))
        return value

    def add_message(self, conversation_id, role, content, citations=None, status='complete'):
        self.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?)', (uid(), conversation_id, role, content, json.dumps(citations or [], ensure_ascii=False), status, now()))

    def messages(self, conversation_id):
        messages = self.query('SELECT * FROM messages WHERE conversation_id=? ORDER BY rowid', (conversation_id,))
        for message in messages:
            message['citations'] = json.loads(message['citations'])
            for citation in message['citations']:
                if not self.document(citation['document_id']):
                    citation['deleted'] = True
                    citation['text'] = ''
        return messages

    def create_note(self, title, question, content, citations):
        note_id = uid(); timestamp = now()
        with self.connection() as db:
            db.execute('INSERT INTO notes VALUES (?,?,?,?,?,?)', (note_id, title.strip(), question, content, timestamp, timestamp))
            db.executemany('INSERT INTO note_citations VALUES (?,?,?,?)', [(uid(), note_id, json.dumps(c, ensure_ascii=False), i) for i, c in enumerate(citations)])
        return self.note(note_id)

    def notes(self, query=None):
        rows = self.query('SELECT * FROM notes' + (' WHERE title LIKE ?' if query else '') + ' ORDER BY updated_at DESC', (f'%{query}%',) if query else ())
        return [self._note(row) for row in rows]

    def note(self, note_id):
        rows = self.query('SELECT * FROM notes WHERE id=?', (note_id,))
        return self._note(rows[0]) if rows else None

    def _note(self, row):
        value = dict(row)
        refs = self.query('SELECT citation_json FROM note_citations WHERE note_id=? ORDER BY ordinal', (row['id'],))
        value['citations'] = [json.loads(ref['citation_json']) for ref in refs]
        for citation in value['citations']:
            if citation.get('document_id') and not self.document(citation['document_id']):
                citation['deleted'] = True
        return value

    def update_note(self, note_id, title, content):
        self.execute('UPDATE notes SET title=?, content=?, updated_at=? WHERE id=?', (title.strip(), content, now(), note_id))
        return self.note(note_id)

    def delete_note(self, note_id):
        with self.connection() as db:
            db.execute('DELETE FROM note_citations WHERE note_id=?', (note_id,))
            db.execute('DELETE FROM notes WHERE id=?', (note_id,))
