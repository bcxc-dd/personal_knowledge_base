"""Known failing user questions, with relevant evidence supplied directly."""

import json
from pathlib import Path

import pytest

from app.evidence import assess_evidence


CASES = json.loads(
    (Path(__file__).resolve().parents[2] / 'docs/evaluations/2026-09-26-promotion-regression.json').read_text(encoding='utf-8')
)['cases']


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_promotion_question_accepts_relevant_evidence(case):
    citations = [
        {'chunk_id': f"{case['id']}:{i}", 'location': f"第 {excerpt['page']} 页", 'text': excerpt['text']}
        for i, excerpt in enumerate(case['controlled_excerpts'], 1)
    ]
    assessment = assess_evidence(case['question'], citations)
    assert assessment.status == 'supported'
    assert assessment.evidence_chunk_ids == tuple(citation['chunk_id'] for citation in citations)
