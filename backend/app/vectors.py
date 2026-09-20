import threading
from pathlib import Path
import chromadb
from chromadb.config import Settings


class VectorStore:
    def __init__(self, path: Path):
        self.client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
        self.lock = threading.RLock()

    def collection(self, fingerprint):
        return self.client.get_or_create_collection('kb_' + fingerprint, embedding_function=None, metadata={'hnsw:space': 'cosine'})

    def upsert(self, fingerprint, doc, chunks, embeddings):
        with self.lock:
            self.collection(fingerprint).upsert(ids=[c['id'] for c in chunks], documents=[c['text'] for c in chunks], embeddings=embeddings, metadatas=[{'document_id': doc['id'], 'kb_id': doc['kb_id'], 'location': c['location'], 'name': doc['name']} for c in chunks])

    def search(self, fingerprint, vector, doc_ids, limit=6):
        if not doc_ids:
            return []
        with self.lock:
            collection = self.collection(fingerprint)
            if not collection.count():
                return []
            result = collection.query(query_embeddings=[vector], n_results=min(limit, collection.count()), where={'document_id': {'$in': doc_ids}}, include=['documents', 'metadatas', 'distances'])
            return [{'chunk_id': cid, 'text': text, 'distance': float(distance), **meta} for cid, text, meta, distance in zip(result['ids'][0], result['documents'][0], result['metadatas'][0], result['distances'][0])]

    def delete(self, doc_id):
        with self.lock:
            for collection in self.client.list_collections():
                self.client.get_collection(collection.name, embedding_function=None).delete(where={'document_id': doc_id})
