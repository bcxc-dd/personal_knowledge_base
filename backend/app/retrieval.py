RRF_K = 60


def merge_vector_query_hits(query_results, limit, rrf_k=RRF_K):
    """Combine original and one rewritten vector query before route fusion."""
    if len(query_results) == 1:
        return query_results[0]
    merged = {}
    for query_index, hits in enumerate(query_results):
        for rank, hit in enumerate(hits, 1):
            key = hit['chunk_id']
            item = merged.setdefault(key, {**hit, 'vector_query_indices': [], 'vector_query_score': 0.0})
            item['vector_query_indices'].append(query_index)
            item['vector_query_score'] += 1 / (rrf_k + rank)
    return sorted(merged.values(), key=lambda item: (-item['vector_query_score'],
                                                    0 if 0 in item['vector_query_indices'] else 1,
                                                    item['chunk_id']))[:limit]


def fuse_candidates(vector_hits, lexical_hits, rrf_k=RRF_K):
    """Merge independent retrieval routes and rank their union with RRF."""
    merged = {}
    for source, hits in (('vector', vector_hits), ('lexical', lexical_hits)):
        for rank, raw in enumerate(hits, 1):
            item = merged.setdefault(raw['chunk_id'], {
                **raw,
                'vector_rank': None,
                'vector_similarity': None,
                'lexical_rank': None,
                'lexical_score': None,
                'retrieval_sources': [],
            })
            item['retrieval_sources'].append(source)
            if source == 'vector':
                item['vector_rank'] = rank
                item['vector_similarity'] = 1 - raw['distance']
            else:
                item['lexical_rank'] = rank
                item['lexical_score'] = raw['lexical_score']

    for item in merged.values():
        item['retrieval_sources'] = sorted(set(item['retrieval_sources']))
        item['fused_score'] = sum(
            1 / (rrf_k + rank)
            for rank in (item['vector_rank'], item['lexical_rank'])
            if rank is not None
        )

    items = sorted(merged.values(), key=lambda item: (-item['fused_score'], item['chunk_id']))
    for rank, item in enumerate(items, 1):
        item['fused_rank'] = rank
    return items
