"""Freeze a TEST set only after explicit case-by-case human signoff.

This module does not import or call E0/E4. A pending template cannot freeze.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_DIR = ROOT / 'test-results/test-frozen-intake-2026-10-03/test-candidate-review-v5'
OUTPUT_DIR = ROOT / 'test-results/evidence-test-frozen-2026-10-03-v1'
CHECK_FIELDS = (
    'query', 'pdf_page', 'parser_page_text', 'production_chunk',
    'required_facts', 'expected_facts', 'positive_evidence',
    'hard_negative', 'answerability', 'parser_status', 'expected_answer',
)
ALLOWED_CORRECTIONS = {
    'query', 'query_type', 'pdf_page', 'required_facts', 'expected_facts',
    'expected_answer', 'positive_evidence_ids', 'hard_negative_evidence_ids',
    'answerability', 'relation_status', 'risk_flags', 'structured_gold',
    'polarity_gold', 'aggregation_category', 'metric_group',
    'parser_validation', 'review_notes',
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_inputs(candidate_dir: Path) -> tuple[dict, dict, dict]:
    manifest = json.loads((candidate_dir/'review-manifest.json').read_text(encoding='utf-8'))
    for name, spec in manifest['files'].items():
        if sha256(candidate_dir/name) != spec['sha256']:
            raise RuntimeError(f'Candidate review file changed: {name}')
    review = json.loads((candidate_dir/'test-candidate-review.json').read_text(encoding='utf-8'))
    evidence = json.loads((candidate_dir/'case-evidence.json').read_text(encoding='utf-8'))
    return manifest, review, evidence


def signoff_template(candidate_dir: Path = CANDIDATE_DIR) -> dict:
    _, review, evidence = _load_inputs(candidate_dir)
    negatives = {}
    for pair in evidence['hard_negative_pairs']:
        negatives.setdefault(pair['case_id'], {})[pair['chunk_id']] = pair['answerability']
    return {
        'schema':'evidence-test-human-signoff-v1',
        'candidate_review_sha256':sha256(candidate_dir/'test-candidate-review.json'),
        'candidate_evidence_sha256':sha256(candidate_dir/'case-evidence.json'),
        'state':'UNSIGNED_TEMPLATE',
        'human_signoff_source':None,
        'decisions':[
            {'case_id':case['case_id'], 'decision':None, 'reviewer':None,
             'reviewed_at':None, 'review_notes':None, 'parser_status':None,
             'checks':{key:None for key in CHECK_FIELDS},
             'proposed_hard_negative_labels':negatives.get(case['case_id'], {}),
             'hard_negative_labels':None, 'corrections':{}, 'exclusion_reason':None}
            for case in review['cases']
        ],
    }


def _validate_signoff(signoff: dict, review: dict, evidence: dict) -> dict:
    cases={case['case_id']:case for case in review['cases']}
    decisions=signoff.get('decisions') or []
    if len(decisions)!=len(cases) or {d.get('case_id') for d in decisions}!=set(cases):
        raise ValueError('Human signoff missing: exactly one decision per candidate case is required')
    if len({d['case_id'] for d in decisions})!=len(decisions):
        raise ValueError('Duplicate human decisions')
    negatives={}
    for pair in evidence['hard_negative_pairs']:
        negatives.setdefault(pair['case_id'],set()).add(pair['chunk_id'])
    return {d['case_id']:d for d in decisions}


def _approved_case(case: dict, decision: dict, evidence: dict) -> dict:
    cid=case['case_id']
    if decision.get('decision') not in {'CONFIRMED','CORRECTED','EXCLUDED'}:
        raise ValueError(f'Human signoff missing: {cid} decision')
    if not decision.get('reviewer') or not decision.get('reviewed_at') or not decision.get('review_notes'):
        raise ValueError(f'Human signoff missing: {cid} provenance/notes')
    try:
        datetime.fromisoformat(decision['reviewed_at'].replace('Z','+00:00'))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid review timestamp: {cid}') from exc
    if decision.get('checks') != {key:True for key in CHECK_FIELDS}:
        raise ValueError(f'Human signoff missing: {cid} checklist')
    if decision.get('parser_status') not in {'PASS','FAIL','AMBIGUOUS'}:
        raise ValueError(f'Human signoff missing: {cid} parser status')
    corrections=decision.get('corrections') or {}
    if set(corrections)-ALLOWED_CORRECTIONS:
        raise ValueError(f'Unrecognized corrections: {cid}')
    if decision['decision']=='CORRECTED' and not corrections:
        raise ValueError(f'CORRECTED without corrections: {cid}')
    if decision['parser_status']!='PASS' and decision['decision']!='EXCLUDED':
        raise ValueError(f'Parser failure/ambiguity must be excluded: {cid}')
    if decision['decision']=='EXCLUDED' and not decision.get('exclusion_reason'):
        raise ValueError(f'Excluded case needs a reason: {cid}')
    row=copy.deepcopy(case)
    row.update(copy.deepcopy(corrections))
    if row['document_id']!=case['document_id'] or row['document_sha256']!=case['document_sha256']:
        raise ValueError(f'Document identity changed: {cid}')
    if len(row['positive_evidence_ids'])==1 and \
       set(row['positive_evidence_ids']) & set(row['hard_negative_evidence_ids']):
        raise ValueError(f'Positive and negative evidence overlap: {cid}')
    for chunk_id in row['positive_evidence_ids']+row['hard_negative_evidence_ids']:
        if chunk_id not in evidence['chunks']:
            raise ValueError(f'Unknown chunk: {cid}/{chunk_id}')
        if evidence['chunks'][chunk_id]['document_id']!=row['document_id']:
            raise ValueError(f'Cross-document evidence: {cid}/{chunk_id}')
    labels=decision.get('hard_negative_labels')
    if not isinstance(labels,dict) or set(labels)!=set(row['hard_negative_evidence_ids']):
        raise ValueError(f'Human signoff missing: {cid} hard-negative labels')
    if any(label not in {'NONE','PARTIAL'} for label in labels.values()):
        raise ValueError(f'Invalid hard-negative label: {cid}')
    if decision['decision']!='EXCLUDED':
        if row['answerability']!='FULL':
            raise ValueError(f'Positive pair must be FULL: {cid}')
        required={f['fact_id'] for f in row['required_facts']}
        expected={f['fact_id'] for f in row['expected_facts']}
        if not required or len(required)!=len(row['required_facts']) or expected!=required:
            raise ValueError(f'Incomplete positive fact gold: {cid}')
        if row['query_type']=='YES_NO' and not row.get('polarity_gold'):
            raise ValueError(f'Missing polarity gold: {cid}')
        if cid in {'A05','F01','F02','F03','F04','F05','T04'} and not row.get('structured_gold'):
            raise ValueError(f'Missing structured table gold: {cid}')
    group=row.get('metric_group') or 'MAIN_SINGLE_CHUNK'
    if group not in {'MAIN_SINGLE_CHUNK','MULTI_CHUNK_DIAGNOSTIC'}:
        raise ValueError(f'Invalid metric group: {cid}')
    if group=='MAIN_SINGLE_CHUNK' and len(row['positive_evidence_ids'])!=1 and decision['decision']!='EXCLUDED':
        raise ValueError(f'Multi-chunk positive in single-chunk main metric: {cid}')
    if group=='MULTI_CHUNK_DIAGNOSTIC' and len(row['positive_evidence_ids'])<2 and decision['decision']!='EXCLUDED':
        raise ValueError(f'Diagnostic case lacks multiple chunks: {cid}')
    row['metric_group']=group
    row['human_review_state']=decision['decision']
    row['human_reviewer']=decision['reviewer']
    row['human_reviewed_at']=decision['reviewed_at']
    row['human_review_notes']=decision['review_notes']
    row['parser_status']=decision['parser_status']
    row['parser_status_provisional']=False
    row['hard_negative_gold']=labels
    row['split']='TEST_FROZEN' if decision['decision']!='EXCLUDED' else 'TEST_EXCLUDED'
    row['failure_type']='PARSING_FAILURE' if decision['parser_status']=='FAIL' else None
    row['exclusion_reason']=decision.get('exclusion_reason')
    return row


def _units(rows: list[dict], evidence: dict) -> list[dict]:
    units=[]
    for row in rows:
        if row['split']!='TEST_FROZEN':
            continue
        cid=row['case_id']
        groups=[('positive',row['positive_evidence_ids'],row['answerability'])]
        groups += [('hard_negative', [chunk_id], label)
                   for chunk_id,label in row['hard_negative_gold'].items()]
        for kind,ids,label in groups:
            units.append({
                'unit_id':f'{cid}:{kind}:'+','.join(ids), 'case_id':cid,
                'pair_type':kind,'chunk_ids':ids,
                'evidence_text':'\n\n'.join(evidence['chunks'][i]['text'] for i in ids),
                'evidence_metadata':[{'chunk_id':i,'document_key':row['document_slug'],
                                      'page':evidence['chunks'][i]['page']}
                                     for i in ids],
                'answerability':label,
            })
    return units


def final_review_sheet(rows: list[dict]) -> str:
    lines=['# TEST_FROZEN v1 最终逐题签核表','',
           '> 本表由冻结 JSON 的最终字段生成；正例和负例以同一个冻结版本为准。', '',
           '| case | 文档 | parser | 人审 | 指标组 | positive=gold | hard negative=gold |',
           '|---|---|---|---|---|---|---|']
    for row in rows:
        positive=', '.join(row['positive_evidence_ids'])+'='+row['answerability']
        negative=', '.join(f'{cid}={label}' for cid,label in row['hard_negative_gold'].items())
        lines.append(f"| {row['case_id']} | {row['document_slug']} | {row['parser_status']} | {row['human_review_state']} | {row['metric_group']} | {positive} | {negative} |")
    for row in rows:
        lines += ['',f"## {row['case_id']} · {row['source_title']}",'',
                  f"- Query：{row['query']}",
                  f"- PDF 页：{row['pdf_page']}；parser：`{row['parser_status']}`；复核：`{row['human_review_state']}`。",
                  f"- 指标组：`{row['metric_group']}`；positive：`{', '.join(row['positive_evidence_ids'])}` = `{row['answerability']}`。",
                  f"- Hard negative：{', '.join(f'`{cid}` = `{label}`' for cid,label in row['hard_negative_gold'].items())}。",
                  f"- Answer：{row['expected_answer']}",
                  f"- 修订记录：{row['human_review_notes']}",
                  f"- parser 判据：{row['parser_validation']['basis']}",
                  '', '```json',
                  json.dumps({'required_facts':row['required_facts'],
                              'expected_facts':row['expected_facts'],
                              'structured_gold':row['structured_gold'],
                              'polarity_gold':row['polarity_gold']},ensure_ascii=False,indent=2),
                  '```']
    return '\n'.join(lines)+'\n'


def freeze_test(signoff_path: Path, output_dir: Path = OUTPUT_DIR,
                candidate_dir: Path = CANDIDATE_DIR) -> dict:
    if output_dir.exists():
        raise FileExistsError(output_dir)
    candidate_manifest,review,evidence=_load_inputs(candidate_dir)
    signoff=json.loads(signoff_path.read_text(encoding='utf-8'))
    if signoff.get('state')!='HUMAN_SIGNED' or not signoff.get('human_signoff_source'):
        raise ValueError('Human signoff missing: signed state and source required')
    if signoff.get('candidate_review_sha256')!=sha256(candidate_dir/'test-candidate-review.json') or \
       signoff.get('candidate_evidence_sha256')!=sha256(candidate_dir/'case-evidence.json'):
        raise ValueError('Signoff references a different candidate revision')
    decisions=_validate_signoff(signoff,review,evidence)
    rows=[_approved_case(case,decisions[case['case_id']],evidence)
          for case in review['cases']]
    units=_units(rows,evidence)
    frozen=[r for r in rows if r['split']=='TEST_FROZEN']
    if not frozen:
        raise ValueError('No eligible TEST cases after signoff')
    now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    payload={'schema':'evidence-test-frozen-v1','schema_version':'1.0',
             'state':'TEST_FROZEN','freeze_timestamp_utc':now,
             'human_signoff_sha256':sha256(signoff_path),
             'candidate_review_sha256':sha256(candidate_dir/'test-candidate-review.json'),
             'cases':rows,'evidence_units':units}
    output_dir.mkdir(parents=True)
    dataset_path=output_dir/'test-frozen-v1.json'
    with dataset_path.open('x',encoding='utf-8') as f:
        json.dump(payload,f,ensure_ascii=False,indent=2)
    sheet_path=output_dir/'final-review-sheet.md'
    with sheet_path.open('x',encoding='utf-8') as f:
        f.write(final_review_sheet(rows))
    try:
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    except (OSError,subprocess.CalledProcessError):
        commit=None
    manifest={
        'state':'TEST_FROZEN','schema_version':'1.0','freeze_timestamp_utc':now,
        'dataset_sha256':sha256(dataset_path),'dataset_bytes':dataset_path.stat().st_size,
        'final_review_sheet_sha256':sha256(sheet_path),
        'candidate_review_sha256':payload['candidate_review_sha256'],
        'candidate_evidence_sha256':sha256(candidate_dir/'case-evidence.json'),
        'human_signoff_sha256':payload['human_signoff_sha256'],
        'chunk_corpus_sha256':candidate_manifest['chunk_corpus_sha256'],
        'document_sha256':candidate_manifest['document_sha256'],
        'number_of_documents':len({r['document_id'] for r in frozen}),
        'number_of_queries':len(frozen),
        'main_query_count':sum(r['metric_group']=='MAIN_SINGLE_CHUNK' for r in frozen),
        'multi_chunk_diagnostic_query_count':sum(r['metric_group']=='MULTI_CHUNK_DIAGNOSTIC' for r in frozen),
        'number_of_positive_pairs':sum(u['pair_type']=='positive' for u in units),
        'number_of_hard_negative_pairs':sum(u['pair_type']=='hard_negative' for u in units),
        'parser_pass_count':sum(r['parser_status']=='PASS' for r in rows),
        'parser_failure_count':sum(r['parser_status']=='FAIL' for r in rows),
        'parser_ambiguous_count':sum(r['parser_status']=='AMBIGUOUS' for r in rows),
        'excluded_count':sum(r['split']=='TEST_EXCLUDED' for r in rows),
        'git_head':commit,
        'E0_code_sha256':sha256(ROOT/'backend/app/evidence.py'),
        'E0_query_plan_sha256':sha256(ROOT/'backend/app/query_plan.py'),
        'E4_matcher_sha256':sha256(ROOT/'benchmarks/evidence_matching/matchers.py'),
        'freeze_code_sha256':sha256(Path(__file__)),
    }
    with (output_dir/'test-frozen-v1-manifest.json').open('x',encoding='utf-8') as f:
        json.dump(manifest,f,ensure_ascii=False,indent=2)
    return manifest


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('signed_decisions',type=Path)
    args=parser.parse_args()
    print(json.dumps(freeze_test(args.signed_decisions),ensure_ascii=False,indent=2))
