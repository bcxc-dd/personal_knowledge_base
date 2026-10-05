"""One-time E0/E4 blind comparison on an already human-frozen TEST set.

No retrieval, chunking, index, reranker, or matcher rules are changed here.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[2]
FROZEN=ROOT/'test-results/evidence-test-frozen-2026-10-03-v1'
OUTPUT=ROOT/'test-results/evidence-test-blind-2026-10-03-v1'
CLASSES=('FULL','PARTIAL','NONE')
LABEL={'SUPPORTED':'FULL','PARTIAL':'PARTIAL','NOT_SUPPORTED':'NONE'}
STRUCTURED_FIELDS=('numeric_value','operator','scope','answer_polarity','relation',
                   'table_row','table_column','table_cell','comparison_pair','derived_difference')


def sha256(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classification(rows:list[dict])->dict:
    pairs=[(r['gold'],r['predicted']) for r in rows]
    confusion={g:{p:sum(a==g and b==p for a,b in pairs) for p in CLASSES} for g in CLASSES}
    by_class={}
    for label in CLASSES:
        tp=confusion[label][label]
        gold_n=sum(a==label for a,_ in pairs)
        pred_n=sum(b==label for _,b in pairs)
        precision=tp/pred_n if pred_n else 0.0
        recall=tp/gold_n if gold_n else 0.0
        by_class[label]={'n':gold_n,'correct':tp,'precision':precision,'recall':recall,
                         'f1':2*precision*recall/(precision+recall) if precision+recall else 0.0}
    n=len(rows)
    return {'n':n,'accuracy':sum(a==b for a,b in pairs)/n if n else 0.0,
            'macro_f1':sum(by_class[x]['f1'] for x in CLASSES)/len(CLASSES),
            'by_class':by_class,'confusion':confusion,
            'false_acceptance':{
                'NONE_TO_FULL':confusion['NONE']['FULL'],
                'NONE_TO_PARTIAL':confusion['NONE']['PARTIAL'],
                'PARTIAL_TO_FULL':confusion['PARTIAL']['FULL']},
            'false_rejection':{
                'FULL_TO_NONE':confusion['FULL']['NONE'],
                'FULL_TO_PARTIAL':confusion['FULL']['PARTIAL'],
                'PARTIAL_TO_NONE':confusion['PARTIAL']['NONE']}}


def observable_structured(case:dict, decision:dict)->dict:
    """Only parse explicit matcher output; never infer values from the gold or text."""
    output=' | '.join([*decision.get('matched',[]),*decision.get('constraints',[])])
    observed={key:'NOT_OBSERVABLE' for key in STRUCTURED_FIELDS}
    gold=case.get('structured_gold') or {}
    cells=gold.get('cells') or []
    value_matches=re.findall(r'\bvalue\s*=\s*(-?\d+(?:\.\d+)?)\b',output,re.I)
    if len(cells)==1 and len(value_matches)==1 and isinstance(cells[0]['value'],(int,float)):
        observed['numeric_value']={'observed':float(value_matches[0]),
                                   'expected':cells[0]['value'],
                                   'correct':float(value_matches[0])==cells[0]['value']}
    if len(cells)==1:
        row,column=cells[0]['row'],cells[0]['column']
        row_match=re.search(r'\brow\s*=\s*([^|]+)',output,re.I)
        col_match=re.search(r'\bcolumn\s*=\s*([^|]+)',output,re.I)
        if row_match:
            actual=row_match.group(1).strip()
            observed['table_row']={'observed':actual,'expected':row,'correct':actual==row}
        if col_match:
            actual=col_match.group(1).strip()
            observed['table_column']={'observed':actual,'expected':column,'correct':actual==column}
        if all(isinstance(observed[k],dict) for k in ('numeric_value','table_row','table_column')):
            observed['table_cell']={'correct':all(observed[k]['correct'] for k in ('numeric_value','table_row','table_column'))}
    op=re.search(r'\boperator\s*=\s*(>=|<=|>|<|=)',output,re.I)
    required=[f for f in case['expected_facts'] if 'operator' in f]
    if op and len(required)==1:
        observed['operator']={'observed':op.group(1),'expected':required[0]['operator'],
                              'correct':op.group(1)==required[0]['operator']}
    scope=re.search(r'\bscope\s*=\s*([^|]+)',output,re.I)
    scopes=[f['scope'] for f in case['expected_facts'] if 'scope' in f]
    if scope and len(set(scopes))==1:
        actual=scope.group(1).strip()
        observed['scope']={'observed':actual,'expected':scopes[0],'correct':actual==scopes[0]}
    polarity=re.search(r'\banswer\s*=\s*(YES|NO)\b',output,re.I)
    if polarity and case.get('polarity_gold'):
        actual=polarity.group(1).upper()
        target=case['polarity_gold']['expected_polarity']
        observed['answer_polarity']={'observed':actual,'expected':target,'correct':actual==target}
    difference=re.search(r'\bdifference\s*=\s*(-?\d+(?:\.\d+)?)\b',output,re.I)
    comparison=gold.get('comparison') or {}
    if difference and comparison.get('derived_difference') is not None:
        actual=float(difference.group(1))
        target=comparison['derived_difference']
        observed['derived_difference']={'observed':actual,'expected':target,'correct':actual==target}
    return observed


def structured_metrics(rows:list[dict], variant:str)->dict:
    result={}
    for field in STRUCTURED_FIELDS:
        checks=[r['structured'][variant][field] for r in rows
                if isinstance(r['structured'][variant][field],dict)
                and 'correct' in r['structured'][variant][field]]
        result[field]=({'n_observable':len(checks),'correct':sum(x['correct'] for x in checks),
                        'accuracy':sum(x['correct'] for x in checks)/len(checks)}
                       if checks else 'NOT_OBSERVABLE')
    return result


def _verify_frozen(frozen_dir:Path)->tuple[dict,dict]:
    dataset_path=frozen_dir/'test-frozen-v1.json'
    manifest_path=frozen_dir/'test-frozen-v1-manifest.json'
    if not dataset_path.exists() or not manifest_path.exists():
        raise FileNotFoundError('Human-signed TEST_FROZEN v1 and manifest are required')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    dataset=json.loads(dataset_path.read_text(encoding='utf-8'))
    if manifest['state']!='TEST_FROZEN' or dataset['state']!='TEST_FROZEN' or \
       sha256(dataset_path)!=manifest['dataset_sha256']:
        raise RuntimeError('Frozen TEST integrity check failed')
    for field,path in (
        ('E0_code_sha256',ROOT/'backend/app/evidence.py'),
        ('E0_query_plan_sha256',ROOT/'backend/app/query_plan.py'),
        ('E4_matcher_sha256',ROOT/'benchmarks/evidence_matching/matchers.py')):
        if sha256(path)!=manifest[field]:
            raise RuntimeError(f'Frozen matcher/input code changed: {field}')
    if any(c['human_review_state'] not in {'CONFIRMED','CORRECTED','EXCLUDED'} or
           c['parser_status_provisional'] for c in dataset['cases']):
        raise RuntimeError('Pending human review found in frozen TEST')
    return dataset,manifest


def _failure_hint(case:dict,unit:dict)->str:
    cid=case['case_id']
    if cid=='P04': return 'MULTI_FACT_COVERAGE'
    if cid=='P05': return 'ORDERED_RULE'
    if cid=='P06': return 'CONDITION_BOUNDARY'
    if cid in {'P03'}: return 'NEGATION_SCOPE'
    if cid in {'A05','F01','F02','F03','F04','F05','T04'}: return 'TABLE_MAPPING'
    if cid in {'P01','P02'}: return 'WRONG_SCOPE'
    if unit['pair_type']=='hard_negative' and unit['answerability']=='PARTIAL':
        return 'PARTIAL_SUPPORT'
    return 'OTHER'


def _score(rows:list[dict])->dict:
    metrics={}
    for variant in ('E0','E4'):
        all_adapted=[{**r,'predicted':r[variant]['predicted_answerability']} for r in rows]
        adapted=[r for r in all_adapted if r['metric_group']=='MAIN_SINGLE_CHUNK']
        diagnostic=[r for r in all_adapted if r['metric_group']=='MULTI_CHUNK_DIAGNOSTIC']
        by_doc=defaultdict(list)
        by_type=defaultdict(list)
        by_pair=defaultdict(list)
        for r in adapted:
            by_doc[r['document_slug']].append(r)
            by_type[r['query_type']].append(r)
            by_pair[r['pair_type']].append(r)
        metrics[variant]={
            'overall':classification(adapted),
            'all_pairs_including_diagnostic':classification(all_adapted),
            'multi_chunk_diagnostic':classification(diagnostic),
            'by_document':{k:classification(v) for k,v in sorted(by_doc.items())},
            'by_query_type':{k:classification(v) for k,v in sorted(by_type.items())},
            'by_pair_type':{k:classification(v) for k,v in sorted(by_pair.items())},
            'structured_correctness':structured_metrics(adapted,variant),
        }
    return metrics


def _report(rows:list[dict],metrics:dict,manifest:dict)->str:
    lines=['# TEST_FROZEN v1 · E0 vs E4 独立盲测', '',
           '> 已冻结新中文文档 gold 后，一次性运行。这里只评给定证据的判定；未改变检索、切分或重排，也未测最终生成答案。', '',
           f"- TEST SHA-256：`{manifest['dataset_sha256']}`",
           f"- 文档 {manifest['number_of_documents']} 份，query {manifest['number_of_queries']} 道，正例 {manifest['number_of_positive_pairs']}、真实负例 {manifest['number_of_hard_negative_pairs']}。",
           f"- 主指标为 {manifest['main_query_count']} 道单 chunk 题；{manifest['multi_chunk_diagnostic_query_count']} 道跨 chunk 题单列诊断。", '',
           '| 实现 | n | accuracy | macro F1 | FULL precision/recall | PARTIAL precision/recall | NONE precision/recall |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for variant in ('E0','E4'):
        m=metrics[variant]['overall']
        def pr(label):
            x=m['by_class'][label]
            return f"{x['precision']:.3f}/{x['recall']:.3f} (n={x['n']})"
        lines.append(f"| {variant} | {m['n']} | {m['accuracy']:.3f} | {m['macro_f1']:.3f} | {pr('FULL')} | {pr('PARTIAL')} | {pr('NONE')} |")
    lines += ['', '## 跨 chunk 诊断（不计主指标）', '',
              'F03 的正例为 `tables:4 + tables:5` 合并提供的 evidence unit；本适配器把原 chunk 文本按顺序拼接后交给同一判定接口，不能等同于生产检索已实现跨 chunk 聚合。', '',
              '| 实现 | 诊断 pair n | 分类正确 |', '|---|---:|---:|']
    for variant in ('E0','E4'):
        m=metrics[variant]['multi_chunk_diagnostic']
        lines.append(f"| {variant} | {m['n']} | {sum(m['confusion'][c][c] for c in CLASSES)}/{m['n']} |")
    for grouping,title in [('by_document','按文档'),('by_query_type','按题型'),('by_pair_type','按证据 pair')]:
        lines += ['',f'## {title}','', '| 组 | E0 n/accuracy | E4 n/accuracy |', '|---|---:|---:|']
        for key in metrics['E0'][grouping]:
            a=metrics['E0'][grouping][key]; b=metrics['E4'][grouping][key]
            lines.append(f"| {key} | {a['n']}/{a['accuracy']:.3f} | {b['n']}/{b['accuracy']:.3f} |")
    lines += ['', '## 误放行与误拒', '', '| 类别 | E0 | E4 |', '|---|---:|---:|']
    for category in ('false_acceptance','false_rejection'):
        for key in metrics['E0']['overall'][category]:
            lines.append(f"| {key} | {metrics['E0']['overall'][category][key]} | {metrics['E4']['overall'][category][key]} |")
    lines += ['', '## 结构化正确性', '',
              '只统计 matcher 明确输出的字段；未显式输出时记 `NOT_OBSERVABLE`，不从 gold 或证据原文反填。', '',
              '| 字段 | E0 | E4 |', '|---|---|---|']
    for field in STRUCTURED_FIELDS:
        def show(v):
            x=metrics[v]['structured_correctness'][field]
            return f"{x['correct']}/{x['n_observable']} ({x['accuracy']:.3f})" if isinstance(x,dict) else x
        lines.append(f'| {field} | {show("E0")} | {show("E4")} |')
    lines += ['', '## 逐 pair 结果', '',
              '| case | 文档 | 指标组 | pair | gold | E0 | E4 | 暂拟失败类 |',
              '|---|---|---|---|---|---|---|---|']
    for r in rows:
        lines.append(f"| {r['case_id']} | {r['document_slug']} | {r['metric_group']} | {r['pair_type']} | {r['gold']} | {r['E0']['predicted_answerability']} | {r['E4']['predicted_answerability']} | {r['failure_hint'] if r['E0']['predicted_answerability']!=r['gold'] or r['E4']['predicted_answerability']!=r['gold'] else '—'} |")
    lines += ['', '逐题原始判定、显式可观察字段和 evidence unit 见 `blind-results.json`；错误归因需在首次运行后人工审阅 `failure-analysis-draft.json`，不得据此修改 frozen gold 或 E4。']
    return '\n'.join(lines)+'\n'


def run_blind(frozen_dir:Path=FROZEN,output_dir:Path=OUTPUT)->dict:
    if output_dir.exists():
        raise FileExistsError(output_dir)
    dataset,manifest=_verify_frozen(frozen_dir)
    sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
    from benchmarks.evidence_matching import matchers
    cases={c['case_id']:c for c in dataset['cases'] if c['split']=='TEST_FROZEN'}
    rows=[]
    for unit in dataset['evidence_units']:
        case=cases[unit['case_id']]
        adapted={'case_id':unit['unit_id'],'query':case['query'],
                 'evidence_text':unit['evidence_text'],
                 'evidence_metadata':unit['evidence_metadata']}
        citation={'chunk_id':unit['unit_id'],'document_id':case['document_id'],
                  'name':case['source_title'],'text':unit['evidence_text']}
        with patch.object(matchers,'citation',lambda _case,source=citation:source):
            e0=matchers.evaluate(adapted,'E0')
            e4=matchers.evaluate(adapted,'E4')
        row={'unit_id':unit['unit_id'],'case_id':case['case_id'],
             'document_slug':case['document_slug'],'query_type':case['query_type'],
             'metric_group':case['metric_group'],
             'query':case['query'],'pair_type':unit['pair_type'],
             'chunk_ids':unit['chunk_ids'],'gold':unit['answerability'],
             'gold_expected_facts':case['expected_facts'] if unit['pair_type']=='positive' else [],
             'E0':{**e0,'predicted_answerability':LABEL[e0['predicted_label']]},
             'E4':{**e4,'predicted_answerability':LABEL[e4['predicted_label']]},
             'structured':{'E0':observable_structured(case,e0),
                           'E4':observable_structured(case,e4)},
             'failure_hint':_failure_hint(case,unit)}
        row['structured_fact_error']={variant:(row[variant]['predicted_answerability']=='FULL' and
                                               any(isinstance(x,dict) and x.get('correct') is False
                                                   for x in row['structured'][variant].values()))
                                      for variant in ('E0','E4')}
        rows.append(row)
    if len(rows)!=manifest['number_of_positive_pairs']+manifest['number_of_hard_negative_pairs']:
        raise RuntimeError('Frozen pair count disagrees with run')
    # Ensure the comparison itself did not mutate either implementation.
    _verify_frozen(frozen_dir)
    metrics=_score(rows)
    failures=[{'unit_id':r['unit_id'],'case_id':r['case_id'],'document_slug':r['document_slug'],
               'pair_type':r['pair_type'],'metric_group':r['metric_group'],'gold':r['gold'],
               'E0':r['E0']['predicted_answerability'],'E4':r['E4']['predicted_answerability'],
               'suggested_category':r['failure_hint'],'human_failure_review':'PENDING'}
              for r in rows if any(r[v]['predicted_answerability']!=r['gold'] or r['structured_fact_error'][v]
                                   for v in ('E0','E4'))]
    output_dir.mkdir(parents=True)
    payloads={'blind-results.json':{'schema':'evidence-blind-results-v1','rows':rows},
              'metrics.json':metrics,'failure-analysis-draft.json':{'failures':failures}}
    for name,payload in payloads.items():
        with (output_dir/name).open('x',encoding='utf-8') as f:
            json.dump(payload,f,ensure_ascii=False,indent=2)
    (output_dir/'report.md').write_text(_report(rows,metrics,manifest),encoding='utf-8')
    result={'state':'ONE_TIME_BLIND_RUN_COMPLETE','frozen_dataset_sha256':manifest['dataset_sha256'],
            'E0_code_sha256':manifest['E0_code_sha256'],'E4_matcher_sha256':manifest['E4_matcher_sha256'],
            'runner_sha256':sha256(Path(__file__)),
            'files':{name:{'sha256':sha256(output_dir/name),'bytes':(output_dir/name).stat().st_size}
                     for name in [*payloads,'report.md']}}
    with (output_dir/'run-manifest.json').open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    return result


if __name__=='__main__':
    print(json.dumps(run_blind(),ensure_ascii=False,indent=2))
