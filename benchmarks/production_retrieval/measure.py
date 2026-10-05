"""Measure isolated SQL/BM25 route overhead without touching production data."""
from __future__ import annotations

import json
import ctypes
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.query_plan import build_query_plan
from app.store import Store
from benchmarks.hybrid_retrieval.core import chinese_terms
from benchmarks.production_retrieval.core import BM25Index, existing_lexical_tokens
from benchmarks.production_retrieval.run import DATASET, OUT, SOURCE, read_jsonl, write_json


def summary(seconds):
    ordered = sorted(seconds)
    return {"count": len(seconds), "mean_ms": statistics.mean(seconds) * 1000,
            "median_ms": statistics.median(seconds) * 1000,
            "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * .95))] * 1000,
            "max_ms": max(seconds) * 1000}


def rss_bytes():
    try:
        import psutil
        return psutil.Process().memory_info().rss
    except ImportError:
        if sys.platform != "win32":
            return None
        class MemoryCounters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_uint32), ("page_fault_count", ctypes.c_uint32),
                        *[(name, ctypes.c_size_t) for name in
                          ("peak_working_set", "working_set", "peak_paged_pool", "paged_pool",
                           "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile")]]
        counters = MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        handle = kernel.GetCurrentProcess()
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return counters.working_set


def main():
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    source = read_jsonl(SOURCE / "chunks/B.jsonl")
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    docs = manifest["corpus"]
    chunks = [{**c, "id": f"{docs[c['document_key']]['document_id']}:{c['ordinal']}"} for c in source]
    store = Store(OUT / "isolated_store")
    doc_ids = [docs[key]["document_id"] for key in ("ai_infra", "promotion")]
    rss_before = rss_bytes()
    built = {}
    indexes = {}
    for name, tokenize in (("existing", existing_lexical_tokens), ("ngram", chinese_terms)):
        started = time.perf_counter()
        indexes[name] = BM25Index(chunks, tokenize)
        built[name] = {"seconds": time.perf_counter() - started,
                       "rss_after_bytes": rss_bytes()}
    timings = {key: [] for key in ("substring_sql", "bm25_existing", "bm25_ngram")}
    for _ in range(5):
        for query in dataset["queries"]:
            terms = build_query_plan(query["question"]).lexical_terms
            lexical_query = " ".join(terms)
            started = time.perf_counter()
            store.search_chunks_exact(doc_ids, terms, limit=100)
            timings["substring_sql"].append(time.perf_counter() - started)
            for name in ("existing", "ngram"):
                started = time.perf_counter()
                indexes[name].search(lexical_query, limit=20)
                timings["bm25_" + name].append(time.perf_counter() - started)
    write_json(OUT / "resource-audit.json", {"repeats": 5, "queries": len(dataset["queries"]),
                                              "process_rss_before_bytes": rss_before,
                                              "build": built,
                                              "latency": {key: summary(value) for key, value in timings.items()},
                                              "caveat": "Warm isolated route calls; no vector query, reranker, concurrency or API/LLM time."})
    print(json.dumps({key: summary(value) for key, value in timings.items()}, indent=2))


if __name__ == "__main__":
    main()
