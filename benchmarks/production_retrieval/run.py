"""Isolated reproduction and ablation of the current Chinese production retrieval path."""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import shutil
import sqlite3
import sys
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.context import chapter_context_hits, condition_context_hits, sequence_gap_context_hits
from app.engine import Engine, diverse_lexical_hits, normalize_question, select_evidence_items
from app.evidence import assess_evidence
from app.models import ModelClient, fingerprint
from app.query_plan import build_query_plan
from app.reranker import Reranker
from app.retrieval import fuse_candidates
from app.store import DEFAULTS, Store, now
from app.vectors import VectorStore
from benchmarks.hybrid_retrieval.core import chinese_terms
from benchmarks.production_retrieval.core import BM25Index, existing_lexical_tokens, score_layer, stage_event

SOURCE = ROOT / "test-results/structure-chunking-zh-2026-10-01-v2"
DATASET = ROOT / "docs/evaluations/structure-chunking-zh-v1.json"
OUT = ROOT / "test-results/production-retrieval-ablation-2026-10-01-v2"
DOC_KEYS = ("ai_infra", "promotion")
CONFIG_FIELDS = ("embedding_mode", "embedding_model", "embedding_url", "reranker_enabled",
                 "reranker_device", "reranker_model", "reranker_candidates", "reranker_evidence")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def clone_vectors() -> Path:
    """Copy the live Chroma files; use SQLite backup for a consistent DB snapshot."""
    source = ROOT / "data/chroma"
    target = OUT / "isolated_chroma"
    target.mkdir(parents=True, exist_ok=True)
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in source.rglob("*") if p.is_file()}
    for entry in source.iterdir():
        if entry.is_dir():
            shutil.copytree(entry, target / entry.name, dirs_exist_ok=True)
    original = source / "chroma.sqlite3"
    db = sqlite3.connect(f"file:{original.as_posix()}?mode=ro", uri=True)
    copied = sqlite3.connect(target / "chroma.sqlite3")
    try:
        db.backup(copied)
    finally:
        copied.close()
        db.close()
    after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in source.rglob("*") if p.is_file()}
    if before != after:
        raise RuntimeError("Production Chroma changed while snapshotting; discard isolated copy")
    return target


class CachedModelClient:
    def __init__(self, cache: Path):
        self.base = ModelClient(cache)
        self.cache = {}

    def embed(self, texts, config, query=False):
        keys = [(bool(query), text) for text in texts]
        missing = [text for key, text in zip(keys, texts) if key not in self.cache]
        if missing:
            vectors = self.base.embed(missing, config, query=query)
            self.cache.update(zip([(bool(query), text) for text in missing], vectors))
        return [self.cache[key] for key in keys]


def load_inputs():
    frozen = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    hybrid = json.loads((ROOT / "test-results/hybrid-retrieval-zh-2026-10-01/manifest.json").read_text(encoding="utf-8"))
    if sha(DATASET) != frozen["dataset_sha256"] or sha(DATASET) != hybrid["dataset_sha256"]:
        raise RuntimeError("Query/gold set changed")
    chunks_path = SOURCE / "chunks/B.jsonl"
    if sha(chunks_path) != hybrid["b_chunks_sha256"]:
        raise RuntimeError("Frozen B chunks changed")
    chunks = read_jsonl(chunks_path)
    if len(chunks) != 2319 or len({c["id"] for c in chunks}) != 2319:
        raise RuntimeError("B corpus count or IDs changed")
    if any(not row["exact_match"] for row in frozen["production_chunk_parity"].values()):
        raise RuntimeError("B chunk production parity was not verified")
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    docs = {}
    for d in dataset["documents"]:
        if d["key"] not in DOC_KEYS:
            continue
        origin = frozen["corpus"][d["key"]]
        if sha(Path(origin["pdf_path"])) != d["sha256"]:
            raise RuntimeError(f"Source PDF changed: {d['key']}")
        docs[d["key"]] = {"id": origin["document_id"], "name": d["name"], "hash": d["sha256"]}
    if set(docs) != set(DOC_KEYS):
        raise RuntimeError("Only the two approved Chinese PDFs may enter this benchmark")
    for key in DOC_KEYS:
        pages = read_jsonl(SOURCE / f"snapshot/{key}-pages.jsonl")
        if len(pages) != frozen["corpus"][key]["page_count"]:
            raise RuntimeError(f"Page snapshot changed: {key}")
    return dataset, chunks, docs, frozen


def read_config():
    path = ROOT / "data/knowledge.sqlite3"
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        row = db.execute("SELECT value FROM settings WHERE id=1").fetchone()
        raw = json.loads(row[0]) if row else {}
    finally:
        db.close()
    config = {**DEFAULTS, **{key: raw[key] for key in CONFIG_FIELDS if key in raw}}
    if (config["embedding_mode"], config["embedding_model"], config["reranker_enabled"],
        config["reranker_device"], config["reranker_candidates"], config["reranker_evidence"]) != (
        "local", "BAAI/bge-small-zh-v1.5", True, "cuda", 20, 6):
        raise RuntimeError("Current production retrieval settings differ from frozen plan")
    return config


def clone_store(chunks, docs, config):
    store = Store(OUT / "isolated_store")
    fp = fingerprint(config)
    production = ROOT / "data/knowledge.sqlite3"
    source = sqlite3.connect(f"file:{production.as_posix()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    with store.connection() as db:
        # This is the isolated benchmark DB only. Clear any interrupted prior seed.
        db.execute("DELETE FROM chunks")
        db.execute("DELETE FROM documents")
        for key, doc in docs.items():
            db.execute("""INSERT OR REPLACE INTO documents
                       (id,kb_id,name,suffix,size,hash,path,status,chunk_count,fingerprint,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (doc["id"], "default", doc["name"], ".pdf", 0, doc["hash"], "", "ready",
                        sum(c["document_key"] == key for c in chunks), fp, now(), now()))
        for key, doc in docs.items():
            source_rows = source.execute("SELECT rowid, id, document_id, ordinal, text, location FROM chunks WHERE document_id=? ORDER BY ordinal",
                                         (doc["id"],)).fetchall()
            expected = [c for c in chunks if c["document_key"] == key]
            if len(source_rows) != len(expected):
                raise RuntimeError(f"Production chunk count changed: {key}")
            for row, chunk in zip(source_rows, expected):
                if (row["id"] != chunk["id"] or row["text"] != chunk["text"] or
                    row["location"] != f"第 {chunk['page']} 页" or row["ordinal"] != chunk["ordinal"]):
                    raise RuntimeError(f"Production B chunk parity changed: {key}/{chunk['ordinal']}")
            db.executemany("INSERT OR REPLACE INTO chunks(rowid,id,document_id,ordinal,text,location) VALUES (?,?,?,?,?,?)",
                           [(r["rowid"], r["id"], r["document_id"], r["ordinal"], r["text"], r["location"]) for r in source_rows])
    source.close()
    return store


def verify_sql_route(store, docs, queries):
    """Require cloned SQL lexical results to equal read-only production for every query."""
    production = ROOT / "data/knowledge.sqlite3"
    db = sqlite3.connect(f"file:{production.as_posix()}?mode=ro", uri=True)
    doc_ids = [d["id"] for d in docs.values()]
    try:
        for q in queries:
            terms = build_query_plan(normalize_question(q["question"])).lexical_terms
            if not terms:
                continue
            matches = " OR ".join("instr(lower(c.text), lower(?)) > 0" for _ in terms)
            score = " + ".join("CASE WHEN instr(lower(c.text), lower(?)) > 0 THEN 1 ELSE 0 END" for _ in terms)
            places = ",".join("?" for _ in doc_ids)
            sql = f"""SELECT c.id AS chunk_id, c.document_id, c.text, c.location, d.name,
                            ({score}) AS lexical_score
                     FROM chunks c JOIN documents d ON d.id=c.document_id
                     WHERE c.document_id IN ({places}) AND ({matches})
                     ORDER BY lexical_score DESC, c.ordinal LIMIT ?"""
            expected = [(r[0], r[5]) for r in db.execute(sql, (*terms, *doc_ids, *terms, 100))]
            actual = [(r["chunk_id"], r["lexical_score"]) for r in store.search_chunks_exact(doc_ids, terms, limit=100)]
            if expected != actual:
                raise RuntimeError(f"Isolated SQL lexical route differs from production: {q['id']}")
    finally:
        db.close()


def hit_ids(hits):
    return [hit["chunk_id"] for hit in hits]


def first_rank(hits, query, chunks, doc_by_id):
    return score_layer(query, hits, chunks, doc_by_id)["first_full_evidence_rank"]


def trace_hit(hit):
    return {key: hit.get(key) for key in ("chunk_id", "document_id", "location", "distance", "lexical_score",
                                          "vector_rank", "lexical_rank", "fused_rank", "fused_score",
                                          "rerank_rank", "rerank_score", "context_reason", "coverage_reason")
            if key in hit}


def trace_list(hits):
    return [trace_hit(hit) for hit in hits]


def complete_pipeline(question, plan, vector_hits, lexical_hits, store, reranker, config, *, use_reranker=True):
    started = time.perf_counter()
    fused = fuse_candidates(copy.deepcopy(vector_hits), copy.deepcopy(lexical_hits))
    fused_seconds = time.perf_counter() - started
    if use_reranker:
        started = time.perf_counter()
        reranked = reranker.rank(question, fused, config)
        rerank_seconds = time.perf_counter() - started
        skipped_for_single = len(fused) < 2 and reranked.provider == "rrf" and not reranked.fallback
        if not skipped_for_single and (reranked.provider != "local-reranker" or reranked.device != "cuda" or reranked.fallback):
            raise RuntimeError(f"Reranker not actual CUDA: {reranked.provider}/{reranked.device}/{reranked.error}")
        ordered = reranked.items
        for i, hit in enumerate(ordered, 1):
            hit["rerank_rank"] = i
    else:
        ordered = copy.deepcopy(fused)
        rerank_seconds = 0.0
    started = time.perf_counter()
    selected = select_evidence_items(question, ordered, int(config["reranker_evidence"]))
    for hit in selected:
        hit["selected"] = True
    context = [*chapter_context_hits(question, selected, store),
               *condition_context_hits(question, selected, store)]
    context.extend(sequence_gap_context_hits(question, selected, store, context))
    expanded = [*selected, *context]
    assessed = assess_evidence(question, [{**hit, "id": i + 1} for i, hit in enumerate(expanded)], plan)
    ids = set(assessed.evidence_chunk_ids)
    answer = [hit for hit in expanded if hit["chunk_id"] in ids]
    post_seconds = time.perf_counter() - started
    return {"fused": fused, "reranked": ordered, "selected": selected, "context": context,
            "expanded": expanded, "answer": answer, "assessment": assessed.to_dict(),
            "timing": {"fusion_s": fused_seconds, "rerank_s": rerank_seconds, "post_s": post_seconds}}


def from_production_result(question, plan, retrieved, vector_hits, lexical_hits, chunks, doc_by_id, store, config):
    diagnostic = retrieved.diagnostics
    fused = fuse_candidates(copy.deepcopy(vector_hits), copy.deepcopy(lexical_hits))
    if hit_ids(fused) != hit_ids(sorted(diagnostic["items"], key=lambda h: h["fused_rank"])):
        raise RuntimeError("P0 fused order differs from production diagnostics")
    ordered = diagnostic["items"]
    selected = [hit for hit in ordered if hit["selected"]]
    context = diagnostic["context_items"]
    expanded = [*selected, *context]
    if hit_ids(expanded) != hit_ids(retrieved):
        raise RuntimeError("P0 retrieve items differ from selected+context")
    replay = select_evidence_items(question, copy.deepcopy(ordered), int(config["reranker_evidence"]))
    if hit_ids(replay) != hit_ids(selected):
        raise RuntimeError("P0 selection replay changed")
    replay_context = [*chapter_context_hits(question, replay, store),
                      *condition_context_hits(question, replay, store)]
    replay_context.extend(sequence_gap_context_hits(question, replay, store, replay_context))
    if hit_ids(replay_context) != hit_ids(context):
        raise RuntimeError("P0 context replay changed")
    assessed = assess_evidence(question, [{**hit, "id": i + 1} for i, hit in enumerate(expanded)], plan)
    ids = set(assessed.evidence_chunk_ids)
    answer = [hit for hit in expanded if hit["chunk_id"] in ids]
    return {"fused": fused, "reranked": ordered, "selected": selected, "context": context,
            "expanded": expanded, "answer": answer, "assessment": assessed.to_dict(), "timing": {}}


def score_arm(query, arm, chunks, doc_by_id):
    return {layer: score_layer(query, hits, chunks, doc_by_id)
            for layer, hits in arm.items() if layer in ("fused", "reranked", "selected", "expanded", "answer")}


def pack_arm(arm, scores):
    return {"stages": {layer: trace_list(arm[layer]) for layer in ("fused", "reranked", "selected", "context", "expanded", "answer")},
            "assessment": arm["assessment"], "scores": scores, "timing": arm["timing"]}


def aggregate(rows, arm, layer):
    picked = [r["arms"][arm]["scores"][layer] for r in rows if r["query_id"] != "ai-batch-formula"]
    return {"n": len(picked), "mrr": sum(r["mrr"] for r in picked) / len(picked),
            **{f"recall_at_{k}": sum(r[f"evidence_at_{k}"] for r in picked) / len(picked)
               for k in (1, 3, 5, 10, 20, 50)}}


def main():
    if (OUT / "metrics.json").exists():
        raise RuntimeError("Completed benchmark already exists; refusing to overwrite")
    OUT.mkdir(parents=True, exist_ok=True)
    dataset, chunks, docs, frozen = load_inputs()
    config = read_config()
    chunks = [{**c, "benchmark_id": c["id"], "id": f"{docs[c['document_key']]['id']}:{c['ordinal']}"} for c in chunks]
    store = clone_store(chunks, docs, config)
    verify_sql_route(store, docs, dataset["queries"])
    print("GATE production SQL substring Top-100 parity: 14/14", flush=True)
    vectors = VectorStore(clone_vectors())
    models = CachedModelClient(ROOT / "data/models")
    reranker = Reranker(ROOT / "data/models")
    engine = Engine.__new__(Engine)
    engine.store, engine.vectors, engine.models, engine.reranker = store, vectors, models, reranker
    by_id = {c["id"]: c for c in chunks}
    doc_by_id = {row["id"]: key for key, row in docs.items()}
    queries = dataset["queries"]

    # Confirm the copied production collection has exactly the two approved Chinese documents' vectors.
    collection = vectors.collection(fingerprint(config))
    for key, doc in docs.items():
        rows = collection.get(where={"document_id": doc["id"]}, include=["documents", "metadatas"])
        expected = {c["id"]: c for c in chunks if c["document_key"] == key}
        if set(rows["ids"]) != set(expected):
            raise RuntimeError(f"Production vector IDs differ from frozen B chunks: {key}")
        for cid, text, meta in zip(rows["ids"], rows["documents"], rows["metadatas"]):
            if text != expected[cid]["text"] or meta["location"] != f"第 {expected[cid]['page']} 页":
                raise RuntimeError(f"Production vector text/page mismatch: {cid}")
    print("GATE production SQLite/Chroma snapshot B parity: 2319/2319", flush=True)

    # Phase A: call production Engine.retrieve on the isolated Store and assess exactly as answer() does.
    if (OUT / "p0-baseline.jsonl").exists():
        p0_rows = read_jsonl(OUT / "p0-baseline.jsonl")
        if [r["query_id"] for r in p0_rows] != [q["id"] for q in queries]:
            raise RuntimeError("Existing P0 checkpoint does not match frozen queries")
        print("GATE resumed P0 checkpoint: 14/14", flush=True)
    else:
        p0_rows = []
        for q in queries:
            question = normalize_question(q["question"])
            plan = build_query_plan(question)
            started = time.perf_counter()
            retrieved = engine.retrieve(question, "default", [d["id"] for d in docs.values()], config, question, plan)
            elapsed = time.perf_counter() - started
            if retrieved.diagnostics.get("provider") != "local-reranker" or retrieved.diagnostics.get("device") != "cuda" or retrieved.diagnostics.get("fallback"):
                raise RuntimeError(f"P0 not actual CUDA for {q['id']}: {retrieved.diagnostics}")
            vector_hits = retrieved.diagnostics["vector_items"]
            lexical_hits = retrieved.diagnostics["lexical_items"]
            p0 = from_production_result(question, plan, retrieved, vector_hits, lexical_hits, chunks, doc_by_id, store, config)
            scores = score_arm(q, p0, chunks, doc_by_id)
            p0_rows.append({"query_id": q["id"], "question": q["question"], "query_plan": plan.to_dict(),
                            "vector": trace_list(vector_hits), "substring_l0": trace_list(lexical_hits),
                            "P0": pack_arm(p0, scores), "retrieval_seconds": elapsed})
            print(f"P0 {q['id']} candidate={scores['fused']['first_full_evidence_rank']} selected={scores['selected']['first_full_evidence_rank']} answer={scores['answer']['first_full_evidence_rank']}", flush=True)
        write_jsonl(OUT / "p0-baseline.jsonl", p0_rows)
    write_json(OUT / "p0-checkpoint.json", {"status": "reproduced", "questions": len(p0_rows),
                                               "cuda": True, "chunk_count": len(chunks),
                                               "answerable_13": {layer: {"mrr": sum(r["P0"]["scores"][layer]["mrr"] for r in p0_rows if r["query_id"] != "ai-batch-formula") / 13,
                                                                                      **{f"recall_at_{k}": sum(r["P0"]["scores"][layer][f"evidence_at_{k}"] for r in p0_rows if r["query_id"] != "ai-batch-formula") / 13 for k in (1,3,5,10,20,50)}}
                                                                for layer in ("fused", "selected", "answer")}})

    # Phase B/C: the query plan, vectors, candidates limit, reranker and postprocessing stay fixed.
    tracemalloc.start()
    started = time.perf_counter()
    indexes = {"existing": BM25Index(chunks, existing_lexical_tokens),
               "ngram": BM25Index(chunks, chinese_terms)}
    build_seconds = time.perf_counter() - started
    _, peak_alloc = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    index_sizes = {}
    for name, index in indexes.items():
        path = OUT / f"bm25-{name}.json.gz"
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as out:
            json.dump(index.serializable(), out, ensure_ascii=False, separators=(",", ":"))
        index_sizes[name] = path.stat().st_size
    traces = []
    for q, saved in zip(queries, p0_rows):
        question = normalize_question(q["question"])
        plan = build_query_plan(question)
        vector_hits = [{**by_id[h["chunk_id"]], **h, "document_id": docs[by_id[h["chunk_id"]]["document_key"]]["id"],
                        "location": f"第 {by_id[h['chunk_id']]['page']} 页", "name": docs[by_id[h["chunk_id"]]["document_key"]]["name"]}
                       for h in saved["vector"]]
        raw = store.search_chunks_exact([d["id"] for d in docs.values()], plan.lexical_terms, limit=100)
        l0 = diverse_lexical_hits(raw, 20)
        l1 = raw[:20]
        if hit_ids(l0) != [h["chunk_id"] for h in saved["substring_l0"]]:
            raise RuntimeError(f"P0 substring route drift: {q['id']}")
        bm25_hits = {}
        lexical_query = " ".join(plan.lexical_terms)
        for key, index in indexes.items():
            bm25_hits[key] = [{"chunk_id": row["id"], "document_id": docs[by_id[row["id"]]["document_key"]]["id"],
                               "name": docs[by_id[row["id"]]["document_key"]]["name"],
                               "location": f"第 {by_id[row['id']]['page']} 页", "text": by_id[row["id"]]["text"],
                               "lexical_score": row["score"]}
                              for row in index.search(lexical_query, limit=20)]
        route_hits = {"P1_dense_only": (vector_hits, []), "P2_substring_only": ([], l0),
                      "L1_no_location_dedup": (vector_hits, l1),
                      "B0_existing_tokenizer": (vector_hits, bm25_hits["existing"]),
                      "B0_ngram": (vector_hits, bm25_hits["ngram"])}
        arms = {"P0": saved["P0"], "P5": saved["P0"]}
        for arm_name, (dense, lexical) in route_hits.items():
            arm = complete_pipeline(question, plan, dense, lexical, store, reranker, config)
            arms[arm_name] = pack_arm(arm, score_arm(q, arm, chunks, doc_by_id))
        # P3/P4 use the exact same P0 fused/reranked order; only later modules differ.
        arms["P3_fusion_only"] = {"stages": {"fused": saved["P0"]["stages"]["fused"]},
                                  "scores": {"fused": saved["P0"]["scores"]["fused"]}}
        arms["P4_plus_reranker"] = {"stages": {"fused": saved["P0"]["stages"]["fused"],
                                               "reranked": saved["P0"]["stages"]["reranked"]},
                                      "scores": {"fused": saved["P0"]["scores"]["fused"],
                                                 "reranked": saved["P0"]["scores"]["reranked"]}}
        route_scores = {name: score_layer(q, hits, chunks, doc_by_id) for name, hits in
                        {"dense": vector_hits, "substring_l0": l0, "substring_l1": l1,
                         "bm25_existing": bm25_hits["existing"], "bm25_ngram": bm25_hits["ngram"]}.items()}
        ranks = {name: result["first_full_evidence_rank"] for name, result in route_scores.items()}
        for name, arm in arms.items():
            ranks[name + "_fused"] = arm["scores"]["fused"]["first_full_evidence_rank"]
            for layer in ("reranked", "selected", "expanded", "answer"):
                if layer in arm["scores"]:
                    ranks[name + "_" + layer] = arm["scores"][layer]["first_full_evidence_rank"]
        events = {"fusion": stage_event(ranks["dense"], ranks["P0_fused"], "FUSION"),
                  "rerank": stage_event(ranks["P0_fused"], ranks["P0_reranked"], "RERANK"),
                  "context": stage_event(ranks["P0_selected"], ranks["P0_expanded"], "CONTEXT"),
                  "assessment": stage_event(ranks["P0_expanded"], ranks["P0_answer"], "ASSESSMENT")}
        trace = {"query_id": q["id"], "question": q["question"], "document_key": q["document_key"],
                 "category": category(q["id"]), "query_plan": plan.to_dict(),
                 "routes": {"dense": trace_list(vector_hits), "substring_sql_top100": trace_list(raw),
                            "substring_l0": trace_list(l0), "substring_l1": trace_list(l1),
                            "bm25_existing": trace_list(bm25_hits["existing"]),
                            "bm25_ngram": trace_list(bm25_hits["ngram"])},
                 "route_scores": route_scores, "arms": arms, "ranks": ranks, "events": events,
                 "location_dedup_removed": [hit["chunk_id"] for hit in raw[:20] if hit["chunk_id"] not in hit_ids(l0)]}
        traces.append(trace)
        print(f"ABLATE {q['id']} P0={ranks['P0_answer']} BM25={ranks['B0_ngram_answer']} L1={ranks['L1_no_location_dedup_answer']}", flush=True)
    write_jsonl(OUT / "query-traces.jsonl", traces)
    arms_to_report = ["P0", "P1_dense_only", "P2_substring_only", "P3_fusion_only", "P4_plus_reranker",
                      "P5", "L1_no_location_dedup", "B0_existing_tokenizer", "B0_ngram"]
    metrics = {"by_arm": {arm: {layer: aggregate(traces, arm, layer) for layer in traces[0]["arms"][arm]["scores"]}
                           for arm in arms_to_report},
               "by_query": [{"query_id": row["query_id"], "category": row["category"], "ranks": row["ranks"],
                             "events": row["events"], "assessment": {arm: data.get("assessment") for arm, data in row["arms"].items()
                                                                            if data.get("assessment")}}
                            for row in traces],
               "resource": {"bm25_both_build_s": build_seconds, "bm25_both_peak_python_alloc_bytes": peak_alloc,
                            "bm25_index_bytes": index_sizes,
                            "p0_retrieval_seconds": [r["retrieval_seconds"] for r in p0_rows],
                            "ablation_timing": {arm: [r["arms"][arm].get("timing", {}) for r in traces]
                                                for arm in arms_to_report}}}
    write_json(OUT / "metrics.json", metrics)
    write_json(OUT / "manifest.json", {"dataset_sha256": sha(DATASET),
                                        "b_chunks_sha256": sha(SOURCE / "chunks/B.jsonl"),
                                        "vector_snapshot": str(OUT / "isolated_chroma"),
                                        "source_pdf_sha256": {k: v["hash"] for k,v in docs.items()},
                                        "production_code_sha256": {name: sha(ROOT / f"backend/app/{name}.py") for name in
                                                                    ("engine", "retrieval", "reranker", "evidence", "context", "store", "query_plan", "terms")},
                                        "settings": {key: config[key] for key in CONFIG_FIELDS if key not in ("embedding_url",)},
                                        "bm25": {"k1": 1.2, "b": 0.75, "tokenizers": ["existing_lexical_terms", "NFKC_Han_unigram_bigram_Latin_decimal"],
                                                   "query_input": "same QueryPlan.lexical_terms", "page_dedup": False},
                                        "query_count": len(queries), "excluded_from_means": ["ai-batch-formula"],
                                        "reproduction": "actual Engine.retrieve on isolated Store + frozen B Chroma; actual CUDA reranker; answer assess_evidence replay"})
    print(f"DONE {OUT}", flush=True)


def category(qid: str) -> str:
    if qid in {"ai-q01", "ai-q02"}: return "technical_explanation"
    if qid in {"ai-q03", "ai-q04"}: return "concept_definition"
    if qid in {"ai-q19", "ai-q20", "ai-q21"}: return "technical_comparison"
    if qid in {"policy-awards", "policy-team"}: return "normative_clause"
    if qid in {"policy-gpa", "policy-csp"}: return "precise_number"
    if qid == "policy-table": return "table"
    if qid == "ai-figure": return "figure"
    return "parsing_risk"


if __name__ == "__main__":
    main()
