from app.evidence import assess_evidence


def test_lexical_only_prefill_decode_body_supports_both_parts():
    result = assess_evidence('预填充和解码分别做什么？', [{
        'chunk_id': 'page-14',
        'retrieval_sources': ['lexical'],
        'vector_similarity': None,
        'text': '模型先处理输入，这一阶段称为预填充；随后逐步生成新 token，这一阶段称为解码。',
    }])

    assert result.status == 'supported'
    assert result.evidence_chunk_ids == ('page-14',)


def test_generic_gpu_evidence_does_not_support_precise_cluster_count():
    result = assess_evidence('书中给出了某特定公司内部 GPU 集群的精确数量吗？', [{
        'chunk_id': 'gpu',
        'retrieval_sources': ['vector'],
        'vector_similarity': 0.8,
        'text': 'GPU 是人工智能训练常用的加速硬件。',
    }])

    assert result.status == 'insufficient'


def test_contents_hit_is_not_usable_definition_evidence():
    result = assess_evidence('什么是 AI Infra？', [{
        'chunk_id': 'contents',
        'retrieval_sources': ['lexical'],
        'text': '目录：第 1 章 AI Infra',
    }])

    assert result.status == 'insufficient'
