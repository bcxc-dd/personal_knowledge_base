"""Record the user's explicit 17-confirm/4-correct TEST review verbatim by case.

No matcher is imported or run. This only fills a signed review record.
"""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.evidence_annotation_v2.freeze_test_dataset import (
    CHECK_FIELDS, CANDIDATE_DIR, ROOT, sha256, signoff_template,
)


OUTPUT=ROOT/'test-results/test-frozen-intake-2026-10-03/human-signoff-v5.json'
CORRECTED={'T03','A04','F03','F04'}
REVIEW_SOURCE='direct human reply to request_user_input_async call_J51qNkIBxx6aBmeGr3zp8FBj on 2026-10-03'


def build_signed_decisions(recorded_at:str)->dict:
    signed=signoff_template()
    candidate=json.loads((CANDIDATE_DIR/'test-candidate-review.json').read_text(encoding='utf-8'))
    cases={case['case_id']:case for case in candidate['cases']}
    if set(cases)!={d['case_id'] for d in signed['decisions']} or len(cases)!=21:
        raise ValueError('Candidate case set changed')
    signed['state']='HUMAN_SIGNED'
    signed['human_signoff_source']=REVIEW_SOURCE
    signed['human_signoff_summary']='17 CONFIRMED, 4 CORRECTED (T03,A04,F03,F04), 0 EXCLUDED; P04 single-chunk COMPOUND confirmed.'
    for decision in signed['decisions']:
        cid=decision['case_id']
        decision['decision']='CORRECTED' if cid in CORRECTED else 'CONFIRMED'
        decision['reviewer']='human_user'
        decision['reviewed_at']=recorded_at
        decision['parser_status']='PASS'
        decision['checks']={key:True for key in CHECK_FIELDS}
        decision['hard_negative_labels']=decision['proposed_hard_negative_labels']
        decision['review_notes']='用户逐题确认 v5 的 query、PDF/parser、事实、正负证据、标签与答案。'
        if cid=='T03':
            parser_validation={**cases[cid]['parser_validation'],
                               'checked_chunks':['technical:35','technical:36'],
                               'basis':'PDF第13页及production chunk核对：technical:35单独完整覆盖生成/存储/销毁安全与方便获取/使用；36只是连续上下文。'}
            decision['corrections']={'positive_evidence_ids':['technical:35'],
                                     'parser_validation':parser_validation,
                                     'review_notes':'technical:35 单独 FULL；36 非必需正例。'}
            decision['review_notes']='用户修订：technical:35 单独 FULL；technical:34 仍为 NONE；parser PASS。'
        elif cid=='A04':
            parser_validation={**cases[cid]['parser_validation'],
                               'checked_chunks':['paper:44','paper:45'],
                               'basis':'PDF第8页及production chunk核对：paper:44已含消融设置、有无增强对比、结果方向和作者结论；45用于A05数值。'}
            decision['corrections']={'positive_evidence_ids':['paper:44'],
                                     'parser_validation':parser_validation,
                                     'review_notes':'paper:44 单独 FULL；paper:45 非必需正例。'}
            decision['review_notes']='用户修订：paper:44 单独 FULL；paper:40 仍为 NONE；parser PASS。'
        elif cid=='F03':
            parser_validation={**cases[cid]['parser_validation'],
                               'checked_chunks':['tables:4','tables:5'],
                               'basis':'PDF第3页类别跨行：tables:4提供全日制专业学位硕士类别，tables:5含99000 MBA行及非全日制114000 MBA行；需两chunk合并确认前者范围。'}
            decision['corrections']={
                'positive_evidence_ids':['tables:4','tables:5'],
                'hard_negative_evidence_ids':['tables:5'],
                'metric_group':'MULTI_CHUNK_DIAGNOSTIC',
                'aggregation_category':'MULTI_CHUNK_DIAGNOSTIC',
                'parser_validation':parser_validation,
                'review_notes':'真实跨chunk证据边界：4+5 FULL；5 单独 PARTIAL。parser PASS，非解析失败。',
            }
            decision['hard_negative_labels']={'tables:5':'PARTIAL'}
            decision['review_notes']='用户修订：tables:4+5 FULL、tables:5 PARTIAL；单列跨chunk诊断；parser PASS。'
        elif cid=='F04':
            parser_validation={**cases[cid]['parser_validation'],
                               'checked_chunks':['tables:5','tables:6'],
                               'basis':'PDF第3页与两chunk均核对；tables:5本身已按顺序含全日制学术型博士类别、系统科学、9000元/学年，tables:6为重复支持。'}
            decision['corrections']={'positive_evidence_ids':['tables:5'],
                                     'parser_validation':parser_validation,
                                     'review_notes':'tables:5 单独 FULL；tables:6 非必需正例，tables:4 NONE。'}
            decision['review_notes']='用户修订：tables:5 单独 FULL；tables:4 NONE；parser PASS。'
    return signed


def write_signed_decisions(recorded_at:str,output:Path=OUTPUT)->dict:
    if output.exists():
        raise FileExistsError(output)
    signed=build_signed_decisions(recorded_at)
    with output.open('x',encoding='utf-8') as f:
        json.dump(signed,f,ensure_ascii=False,indent=2)
    return {'path':str(output),'sha256':sha256(output),'confirmed':17,'corrected':4,'excluded':0}


if __name__=='__main__':
    print(json.dumps(write_signed_decisions('2026-10-03T12:21:18Z'),ensure_ascii=False,indent=2))
