"""Deterministic Chinese BM25 and unweighted RRF for an isolated benchmark."""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import re
import unicodedata


def chinese_terms(text: str) -> list[str]:
    """Han unigrams/bigrams plus whole Latin identifiers and decimal numbers."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    terms = []
    for match in re.finditer(r"[\u4e00-\u9fff]+|[a-z][a-z0-9_]*|\d+(?:\.\d+)?", normalized):
        value = match.group()
        if "\u4e00" <= value[0] <= "\u9fff":
            terms.extend(value)
            terms.extend(value[i:i + 2] for i in range(len(value) - 1))
        else:
            terms.append(value)
    return terms


class BM25Index:
    def __init__(self, rows: list[dict], k1: float = 1.2, b: float = 0.75):
        if not rows or k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("invalid BM25 corpus or parameters")
        self.k1 = k1
        self.b = b
        self.doc_ids = [row["id"] for row in rows]
        self.doc_lengths = []
        self.postings = defaultdict(list)
        for index, row in enumerate(rows):
            counts = Counter(chinese_terms(row["text"]))
            self.doc_lengths.append(sum(counts.values()))
            for term, frequency in counts.items():
                self.postings[term].append((index, frequency))
        self.avgdl = sum(self.doc_lengths) / len(rows)
        self.idf = {term: math.log(1 + (len(rows) - len(hits) + 0.5) / (len(hits) + 0.5))
                    for term, hits in self.postings.items()}

    def search(self, query: str, limit: int = 50) -> list[dict]:
        if limit < 1:
            return []
        scores = defaultdict(float)
        for term in set(chinese_terms(query)):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for index, frequency in self.postings[term]:
                length = self.doc_lengths[index]
                denominator = frequency + self.k1 * (1 - self.b + self.b * length / self.avgdl)
                scores[index] += idf * frequency * (self.k1 + 1) / denominator
        ranked = sorted(scores, key=lambda i: (-scores[i], i))[:limit]
        return [{"id": self.doc_ids[i], "score": scores[i]} for i in ranked]

    def serializable(self) -> dict:
        return {"k1": self.k1, "b": self.b, "doc_ids": self.doc_ids, "doc_lengths": self.doc_lengths,
                "avgdl": self.avgdl, "postings": dict(self.postings)}


def rrf_rank(dense_ids: list[str], lexical_ids: list[str], top_n: int = 50, limit: int = 50,
             k: int = 60) -> list[str]:
    if top_n < 1 or limit < 1 or k < 1:
        raise ValueError("invalid RRF settings")
    dense = {cid: i for i, cid in enumerate(dense_ids[:top_n], 1)}
    lexical = {cid: i for i, cid in enumerate(lexical_ids[:top_n], 1)}
    candidates = dense.keys() | lexical.keys()

    def order(cid):
        dr, lr = dense.get(cid), lexical.get(cid)
        score = (1 / (k + dr) if dr else 0) + (1 / (k + lr) if lr else 0)
        return (-score, min(dr or 10**9, lr or 10**9), dr or 10**9, lr or 10**9, cid)

    return sorted(candidates, key=order)[:limit]
