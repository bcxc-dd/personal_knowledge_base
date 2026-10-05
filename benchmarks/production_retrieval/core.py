"""Read-only helpers for the Chinese production retrieval ablation."""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import re

from app.terms import lexical_terms
from benchmarks.structure_chunking.core import score_query


def existing_lexical_tokens(text: str) -> list[str]:
    """The project's current term extractor, applied symmetrically to text/query."""
    return [term.casefold() for term in lexical_terms(text)]


def source_page(location: str | None) -> int | None:
    match = re.fullmatch(r"第\s*(\d+)\s*页", str(location or ""))
    return int(match.group(1)) if match else None


def score_layer(query: dict, hits: list[dict], corpus: list[dict], document_by_id: dict[str, str]) -> dict:
    """Use the frozen fact/page scorer at one pipeline layer."""
    ranked = [{"document_key": document_by_id.get(hit.get("document_id"), hit.get("document_key")),
               "page": source_page(hit.get("location")) if "location" in hit else hit.get("page"),
               "text": hit["text"]} for hit in hits]
    by_doc = defaultdict(list)
    for row in corpus:
        by_doc[row["document_key"]].append(row["text"])
    source = {key: "\n".join(texts) for key, texts in by_doc.items()}
    return score_query(query, corpus, ranked, source)


def stage_event(before: int | None, after: int | None, stage: str) -> str | None:
    if stage == "ASSESSMENT" and before is not None and after is None:
        return "EVIDENCE_FILTER_DROP"
    if stage == "CONTEXT" and before is None and after is not None:
        return "CONTEXT_RESCUE"
    if (before is None or before > 5) and after is not None and after <= 5:
        return f"{stage}_RESCUE"
    if before is not None and before <= 5 and (after is None or after > 5):
        return f"{stage}_DEGRADE"
    return None


class BM25Index:
    """Same BM25 formula for either explicitly chosen Chinese tokenizer."""

    def __init__(self, rows: list[dict], tokenize, k1: float = 1.2, b: float = 0.75):
        if not rows:
            raise ValueError("empty corpus")
        self.k1, self.b, self.tokenize = k1, b, tokenize
        self.ids = [row["id"] for row in rows]
        self.lengths = []
        self.postings = defaultdict(list)
        for i, row in enumerate(rows):
            counts = Counter(tokenize(row["text"]))
            self.lengths.append(sum(counts.values()))
            for term, tf in counts.items():
                self.postings[term].append((i, tf))
        self.avgdl = sum(self.lengths) / len(rows) or 1
        self.idf = {term: math.log(1 + (len(rows) - len(hits) + 0.5) / (len(hits) + 0.5))
                    for term, hits in self.postings.items()}

    def search(self, text: str, limit: int = 20) -> list[dict]:
        scores = defaultdict(float)
        for term in set(self.tokenize(text)):
            if term not in self.idf:
                continue
            for i, tf in self.postings[term]:
                denom = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avgdl)
                scores[i] += self.idf[term] * tf * (self.k1 + 1) / denom
        order = sorted(scores, key=lambda i: (-scores[i], i))[:limit]
        return [{"id": self.ids[i], "score": scores[i]} for i in order]

    def serializable(self) -> dict:
        return {"k1": self.k1, "b": self.b, "ids": self.ids, "lengths": self.lengths,
                "avgdl": self.avgdl, "postings": dict(self.postings)}
