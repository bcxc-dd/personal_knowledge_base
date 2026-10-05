"""Run the frozen Chinese-only B/C dense retrieval benchmark; never writes production data."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from tokenizers import Tokenizer

from app.models import LOCAL_MODEL, ModelClient
from app.parsing import parse_file
from app.pdf_review import apply_pdf_corrections, text_hash
from benchmarks.structure_chunking.core import blockify_page, legacy_chunks, score_query, structure_chunks, _norm

DATASET = ROOT / "docs/evaluations/structure-chunking-zh-v1.json"
OUT = ROOT / os.environ.get("CHUNK_BENCHMARK_OUTPUT", "test-results/structure-chunking-zh-2026-10-01-v2")
DB = ROOT / "data/knowledge.sqlite3"
TOK = ROOT / "data/models/models--Qdrant--bge-small-zh-v1.5/snapshots/46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59/tokenizer.json"


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_corpus(dataset):
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    corpus = {}
    provenance = {}
    for d in dataset["documents"]:
        if d["role"] != "primary":
            continue
        docs = [dict(r) for r in conn.execute("SELECT * FROM documents WHERE hash=? AND deleted=0 AND status='ready'", (d["sha256"],))]
        if len(docs) != 1:
            raise RuntimeError(f"Expected exactly one ready source for {d['key']}, found {len(docs)}")
        doc = docs[0]
        path = Path(doc["path"])
        if sha(path) != d["sha256"]:
            raise RuntimeError(f"PDF hash changed: {path}")
        begin = time.perf_counter()
        sections = parse_file(path, ".pdf")
        corrections = [dict(r) for r in conn.execute("SELECT * FROM pdf_page_corrections WHERE document_id=? ORDER BY page_number", (doc["id"],))]
        sections = apply_pdf_corrections(sections, corrections, doc["hash"])
        pages = []
        section_path = []
        for number, section in enumerate(sections, 1):
            blocks, section_path = blockify_page(d["key"], number, section.text, section_path)
            pages.append({"page": number, "text": section.text, "blocks": blocks})
        if len(pages) != d["pages"]:
            raise RuntimeError(f"Page count mismatch for {d['key']}")
        corpus[d["key"]] = pages
        provenance[d["key"]] = {
            "document_id": doc["id"], "pdf_path": str(path), "pdf_sha256": d["sha256"],
            "page_count": len(pages), "parse_seconds": round(time.perf_counter() - begin, 3),
            "page_corrections": [{"page": c["page_number"], "updated_at": c["updated_at"],
                                  "corrected_text_sha256": text_hash(c["corrected_text"])} for c in corrections],
        }
        jsonl(OUT / f"snapshot/{d['key']}-pages.jsonl", pages)
        print(f"SNAPSHOT {d['key']} pages={len(pages)} blocks={sum(len(p['blocks']) for p in pages)}", flush=True)
    conn.close()
    return corpus, provenance


def check_parity(corpus, provenance):
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out = {}
    for key, pages in corpus.items():
        old = [dict(r) for r in conn.execute("SELECT ordinal,text,location FROM chunks WHERE document_id=? ORDER BY ordinal", (provenance[key]["document_id"],))]
        new = legacy_chunks(key, pages)
        mismatches = [i for i, (a, b) in enumerate(zip(old, new)) if a["text"] != b["text"] or a["location"] != f'第 {b["page"]} 页']
        out[key] = {"stored_count": len(old), "recomputed_count": len(new),
                    "exact_match": len(old) == len(new) and not mismatches,
                    "first_mismatch_ordinals": mismatches[:10]}
    conn.close()
    return out


def validate_gold(dataset, corpus):
    rows = []
    for q in dataset["queries"]:
        pages = corpus[q["document_key"]]
        for fact in q["facts"]:
            source = "\n".join(pages[p - 1]["text"] for p in fact["source_pages"])
            missing = [term for term in fact["all_terms"] if _norm(term) not in _norm(source)]
            rows.append({"query_id": q["id"], "fact_id": fact["id"], "source_pages": fact["source_pages"], "missing_terms": missing})
    dump(OUT / "gold-source-validation.json", rows)
    return rows


def make_variants(corpus, tokenizer):
    variants = {}
    for name in ("B", "C256", "C384", "C512"):
        start = time.perf_counter()
        rows = []
        for key, pages in corpus.items():
            if name == "B":
                rows.extend(legacy_chunks(key, pages))
            else:
                rows.extend(structure_chunks(key, pages, tokenizer, min(int(name[1:]), 510)))
        for i, row in enumerate(rows):
            row["id"] = f"{name}:{i}"
            row["token_count"] = len(tokenizer.encode(row["text"], add_special_tokens=True).ids)
        jsonl(OUT / f"chunks/{name}.jsonl", rows)
        variants[name] = rows
        print(f"CHUNKS {name} count={len(rows)} seconds={time.perf_counter()-start:.1f}", flush=True)
    return variants


def benchmark(dataset, corpus, variants, tokenizer):
    import chromadb
    from chromadb.config import Settings

    client = ModelClient(ROOT / "data/models")
    config = {"embedding_mode": "local", "embedding_model": LOCAL_MODEL}
    queries = dataset["queries"]
    query_vecs = client.embed([q["question"] for q in queries], config, query=True)
    cache = {}
    results = {}
    for name, chunks in variants.items():
        started = time.perf_counter()
        vector_dir = OUT / "vectors" / name
        db = chromadb.PersistentClient(path=str(vector_dir), settings=Settings(anonymized_telemetry=False))
        col = db.get_or_create_collection("benchmark", embedding_function=None, metadata={"hnsw:space": "cosine"})
        for offset in range(0, len(chunks), 16):
            batch = chunks[offset:offset + 16]
            unknown = [c["text"] for c in batch if c["text"] not in cache]
            if unknown:
                vectors = client.embed(unknown, config, query=False)
                cache.update(zip(unknown, vectors))
            col.upsert(ids=[c["id"] for c in batch], documents=[c["text"] for c in batch],
                       embeddings=[cache[c["text"]] for c in batch],
                       metadatas=[{"document_key": c["document_key"], "page": c["page"]} for c in batch])
            if offset and offset % 1024 == 0:
                print(f"INDEX {name} {offset}/{len(chunks)}", flush=True)
        indexed_at = time.perf_counter()
        by_id = {c["id"]: c for c in chunks}
        query_results = []
        for q, vector in zip(queries, query_vecs):
            response = col.query(query_embeddings=[vector], n_results=min(50, col.count()), include=["distances"])
            ranked = [{**by_id[cid], "rank": rank, "distance": float(dist)}
                      for rank, (cid, dist) in enumerate(zip(response["ids"][0], response["distances"][0]), 1)]
            score = score_query(q, chunks, ranked,
                                {q["document_key"]: "\n".join(p["text"] for p in corpus[q["document_key"]])})
            query_results.append({"query_id": q["id"], "question": q["question"], **score,
                                  "ranked": [{"rank": r["rank"], "chunk_id": r["id"], "document_key": r["document_key"],
                                              "page": r["page"], "distance": r["distance"], "text": r["text"]} for r in ranked]})
        jsonl(OUT / f"retrieval/{name}.jsonl", query_results)
        vector_bytes = sum(p.stat().st_size for p in vector_dir.rglob("*") if p.is_file())
        results[name] = {"chunks": len(chunks), "avg_tokens": sum(c["token_count"] for c in chunks) / len(chunks),
                         "max_tokens": max(c["token_count"] for c in chunks), "index_seconds": indexed_at - started,
                         "retrieval_seconds": time.perf_counter() - indexed_at, "vector_bytes": vector_bytes,
                         "per_query": [{k: v for k, v in r.items() if k != "ranked"} for r in query_results]}
        print(f"RETRIEVAL {name} seconds={time.perf_counter()-indexed_at:.1f}", flush=True)
        del db
    return results


def main():
    started = time.perf_counter()
    if (OUT / "metrics.json").exists():
        raise RuntimeError(f"Completed output already exists; refusing to overwrite frozen benchmark: {OUT}")
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    corpus, provenance = read_corpus(dataset)
    parity = check_parity(corpus, provenance)
    gold = validate_gold(dataset, corpus)
    dump(OUT / "manifest.json", {"dataset_sha256": sha(DATASET), "model": LOCAL_MODEL,
                                  "tokenizer_sha256": sha(TOK), "corpus": provenance,
                                  "production_chunk_parity": parity, "gold_terms_missing": [x for x in gold if x["missing_terms"]],
                                  "controls": {"parser": "pypdf effective text + same correction", "embedding": LOCAL_MODEL,
                                               "vector_store": "Chroma cosine separate persistent directories",
                                               "retrieval": "dense only global top-50", "query_count": len(dataset["queries"])}})
    if any(not row["exact_match"] for row in parity.values()):
        print("WARNING baseline parity mismatch; inspect manifest", flush=True)
    if any(row["missing_terms"] for row in gold):
        print("WARNING gold anchors missing from indicated source pages; inspect gold-source-validation", flush=True)
    tokenizer = Tokenizer.from_file(str(TOK))
    variants = make_variants(corpus, tokenizer)
    results = benchmark(dataset, corpus, variants, tokenizer)
    metrics = {}
    for name, data in results.items():
        rows = data["per_query"]
        metrics[name] = {"chunk_count": data["chunks"], "avg_tokens": data["avg_tokens"], "max_tokens": data["max_tokens"],
                         "index_seconds": data["index_seconds"], "retrieval_seconds": data["retrieval_seconds"],
                         "vector_bytes": data["vector_bytes"], "mrr": sum(r["mrr"] for r in rows) / len(rows),
                         **{f"evidence_recall_at_{k}": sum(r[f"evidence_at_{k}"] for r in rows) / len(rows) for k in (1, 3, 5, 10, 20, 50)},
                         "per_query": rows}
    dump(OUT / "metrics.json", metrics)
    print(f"DONE seconds={time.perf_counter()-started:.1f} output={OUT}", flush=True)


if __name__ == "__main__":
    main()
