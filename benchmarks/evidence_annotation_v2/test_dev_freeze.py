import copy
import json

import pytest

from benchmarks.evidence_annotation_v2.dev_freeze import amend_cases, freeze_dev, sha256


def test_explicit_human_decisions_apply_only_to_nine_cases():
    source = json.load(open('test-results/evidence-matching-v2-2026-10-03/dataset-v2.json', encoding='utf-8'))
    untouched = copy.deepcopy(source)
    frozen = amend_cases(source)
    rows = {row['case_id']: row for row in frozen['cases']}
    assert source == untouched
    assert len(rows) == 36
    assert sum(row['human_review_state'] == 'RELABELLED' for row in rows.values()) == 9
    assert sum(row['human_review_state'] == 'CONFIRMED' for row in rows.values()) == 27
    for case_id in ('gpa-real', 'gpa-newline', 'gpa-ranking-negative',
                    'gpa-other-metric', 'gpa-exception-scope', 'gpa-synthetic-positive'):
        assert rows[case_id]['required_facts'][0]['target']['scope'] == '推免推荐条件'
    assert rows['csp-no-output']['query'] == 'CSP考试成绩达到300分时，g_i的具体取值是多少？'
    assert rows['csp-no-output']['query_plan_v1'] is None
    assert rows['gqa-mqa-swapped']['expected_answer'] == '按该片段，GQA所有Q头共用一组KV，MQA按组共享不同KV。'
    assert rows['negated-definition']['evidence_text'] == (
        'AI Infra并不是支撑AI训练和推理的基础设施。\n'
        '该片段同时声称，AI Infra的主要组成包括计算设备、存储与互联，以及组织这些资源的软件。'
    )
    for row in frozen['cases']:
        assert row['split'] == 'DEV'
        assert row['review_date'] == '2026-10-03'
        assert row['review_notes']


def test_freeze_is_immutable_and_hash_verified(tmp_path):
    source = tmp_path / 'draft.json'
    original = open('test-results/evidence-matching-v2-2026-10-03/dataset-v2.json', encoding='utf-8').read()
    source.write_text(original, encoding='utf-8')
    before = sha256(source)
    output = tmp_path / 'frozen.json'
    manifest_path = tmp_path / 'manifest.json'
    manifest = freeze_dev(source, output, manifest_path)
    assert sha256(source) == before
    assert manifest['dataset_sha256'] == sha256(output)
    assert manifest['source_dataset_sha256'] == before
    assert manifest['case_count'] == 36
    assert manifest['test_frozen_count'] == 0
    with pytest.raises(FileExistsError):
        freeze_dev(source, output, manifest_path)
