import pytest

from app.retrieval import fuse_candidates


def hit(chunk_id, **extra):
    return {
        'chunk_id': chunk_id,
        'document_id': 'doc',
        'name': 'book.pdf',
        'location': '第 14 页',
        'text': '正文',
        **extra,
    }


def test_fuses_both_routes_and_keeps_lexical_only_vector_fields_null():
    items = fuse_candidates(
        [hit('both', distance=0.1), hit('vector', distance=0.2)],
        [hit('both', lexical_score=3), hit('lexical', lexical_score=2)],
    )

    both = next(item for item in items if item['chunk_id'] == 'both')
    lexical = next(item for item in items if item['chunk_id'] == 'lexical')

    assert both['retrieval_sources'] == ['lexical', 'vector']
    assert (both['vector_rank'], both['lexical_rank']) == (1, 1)
    assert both['fused_score'] == pytest.approx(2 / 61)
    assert lexical['vector_rank'] is None
    assert lexical['vector_similarity'] is None
    assert lexical['fused_score'] == pytest.approx(1 / 62)


def test_keeps_vector_only_lexical_fields_null():
    items = fuse_candidates(
        [hit('z-vector', distance=0.1), hit('a-vector', distance=0.2)],
        [],
    )

    assert all(item['lexical_rank'] is None for item in items)
    assert all(item['lexical_score'] is None for item in items)
    assert [item['fused_rank'] for item in items] == [1, 2]


def test_breaks_equal_route_scores_by_chunk_id():
    items = fuse_candidates(
        [hit('z-vector', distance=0.1)],
        [hit('a-lexical', lexical_score=1)],
    )

    assert [item['chunk_id'] for item in items] == ['a-lexical', 'z-vector']
