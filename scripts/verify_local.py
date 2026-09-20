"""Real local Embedding + Chroma persistence and stopped-process backup smoke test.

Creates only verification data under test-results; never opens user SQLite data.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def child(action, directory):
    from app.engine import Engine
    from app.models import ModelClient
    engine = Engine(directory, models=ModelClient(ROOT / 'data' / 'models'))
    if action == 'create':
        doc, _ = engine.upload('verification.txt', '原型评审在十月十二日下午两点举行，负责人是林然。'.encode(), 'default')
        engine.process_document(doc['id'])
        assert engine.store.document(doc['id'])['status'] == 'ready'
    docs = engine.store.documents()
    assert len(docs) == 1
    hits = engine.retrieve('谁负责原型评审？', 'default', [])
    assert hits and '林然' in hits[0]['text']
    print(json.dumps({'action': action, 'documents': len(docs), 'top_source': hits[0]['name'], 'retrieval_verified': True}, ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) == 3:
        child(sys.argv[1], Path(sys.argv[2]))
    else:
        target = ROOT / 'test-results' / f'local-{int(time.time())}'
        original = target / 'original'
        restored = target / 'restored'
        subprocess.run([sys.executable, __file__, 'create', str(original)], check=True)
        # The creating process has fully stopped, so SQLite and Chroma are consistent.
        shutil.copytree(original, restored)
        subprocess.run([sys.executable, __file__, 'restore', str(restored)], check=True)
        print('Local embedding, process restart and backup restore verified.')
