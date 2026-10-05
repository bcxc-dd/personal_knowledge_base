"""Pure scoring and page-diversity helpers for the isolated benchmark."""
from __future__ import annotations

from collections import Counter

from benchmarks.structure_chunking.core import _norm


def limit_by_location(hits: list[dict], per_location: int, limit: int) -> list[dict]:
    """Preserve production SQL order while varying only each location's cap."""
    if per_location < 1 or limit < 1:
        raise ValueError("caps must be positive")
    chosen, counts, ids = [], Counter(), set()
    for hit in hits:
        cid = hit["chunk_id"]
        location = hit.get("location")
        if cid in ids or counts[location] >= per_location:
            continue
        chosen.append(hit)
        ids.add(cid)
        counts[location] += 1
        if len(chosen) >= limit:
            break
    return chosen


def gold_coverage(query: dict, hits: list[dict]) -> dict:
    """Count manually specified facts found in the correct document and page."""
    found, bearing = set(), 0
    for hit in hits:
        matching = [fact["id"] for fact in query["facts"]
                    if hit.get("document_key") == query["document_key"]
                    and (not fact.get("source_pages") or hit.get("page") in fact["source_pages"])
                    and all(_norm(term) in _norm(hit.get("text", "")) for term in fact["all_terms"])]
        if matching:
            bearing += 1
            found.update(matching)
    return {"found": sorted(found), "fraction": len(found) / len(query["facts"]),
            "fact_bearing_hits": bearing, "hit_precision": bearing / len(hits) if hits else 0.0}


def filter_effect(query: dict, before: list[dict], after: list[dict]) -> str:
    prior, later = gold_coverage(query, before), gold_coverage(query, after)
    if prior["fraction"] == 1 and later["fraction"] < 1:
        return "FILTER_DROP"
    if (prior["fraction"] == later["fraction"] == 1
            and later["hit_precision"] > prior["hit_precision"]):
        return "FILTER_RESCUE"
    return "FILTER_NEUTRAL"


def classify_failure(parsed: bool, raw_lexical: int | None, dedup_lexical: int | None,
                     fused: int | None, reranked: int | None, selected: int | None,
                     expanded: int | None, final: int | None) -> str:
    if not parsed:
        return "PARSING_FAILURE"
    if final is not None:
        return "SUCCESS" if final <= 5 else "RANKING_FAILURE"
    if selected is not None and expanded is not None:
        return "EVIDENCE_FILTER_DROP"
    if fused is not None and fused <= 5 and reranked is not None and reranked > 5 and selected is None:
        return "RANKING_FAILURE"
    if reranked is not None and selected is None:
        return "SELECTION_CUTOFF"
    if fused is not None and reranked is None:
        return "RANKING_FAILURE"
    if raw_lexical is not None and dedup_lexical is None and fused is None:
        return "LOCATION_DEDUP_DROP"
    return "RETRIEVAL_FAILURE"


def diversity(hits: list[dict]) -> dict:
    counts = Counter(hit.get("location") for hit in hits)
    repeated = sum(count - 1 for count in counts.values())
    shingles = []
    for hit in hits:
        value = _norm(str(hit.get("text", "")))
        shingles.append({value[i:i + 3] for i in range(max(0, len(value) - 2))})
    near_duplicates = sum(
        bool(shingles[i] or shingles[j])
        and len(shingles[i] & shingles[j]) / len(shingles[i] | shingles[j]) >= 0.8
        for i, left in enumerate(hits) for j, right in enumerate(hits[i + 1:], i + 1)
        if left.get("location") == right.get("location")
    )
    return {"candidate_count": len(hits), "unique_pages": len(counts),
            "same_page_chunk_ratio": repeated / len(hits) if hits else 0.0,
            "max_chunks_per_page": max(counts.values(), default=0),
            "same_page_near_duplicate_pairs": near_duplicates}
