RRF_K = 60


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
