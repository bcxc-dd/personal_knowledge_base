"""Reproduce analyst-reviewed answer outcomes from immutable generation outputs."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from .run import FROZEN, OUTPUT, sha256

SUCCESS = {'FULL_CORRECT', 'PARTIAL_BOUNDED', 'NONE_ABSTAIN'}
GROUPS = ('MAIN_SINGLE_CHUNK', 'MULTI_CHUNK_DIAGNOSTIC')
VARIANTS = ('hard_veto', 'advisory')


def summarize(records: list[dict], case_groups: dict[str, str]) -> dict:
    buckets = {group: {variant: [] for variant in VARIANTS} for group in GROUPS}
    for row in records:
        case_id = row['unit_id'].split(':', 1)[0]
        if case_id not in case_groups:
            raise ValueError(f'unknown case: {case_id}')
        group = case_groups[case_id]
        if group not in buckets or row['variant'] not in VARIANTS:
            raise ValueError('unknown group or variant')
        if row['success'] != (row['verdict'] in SUCCESS):
            raise ValueError('review success/verdict mismatch')
        buckets[group][row['variant']].append(row)
    result = {}
    for group in GROUPS:
        result[group] = {}
        for variant in VARIANTS:
            items = buckets[group][variant]
            by_gold = {}
            for gold in ('FULL', 'PARTIAL', 'NONE'):
                selected = [row for row in items if row['gold'] == gold]
                by_gold[gold] = {'n': len(selected), 'success': sum(row['success'] for row in selected)}
            count = Counter(row['verdict'] for row in items)
            result[group][variant] = {
                'n': len(items), 'success': sum(row['success'] for row in items),
                'success_rate': sum(row['success'] for row in items) / len(items) if items else None,
                'by_gold': by_gold, 'by_verdict': dict(sorted(count.items())),
                'medium_confidence': sum(row['confidence'] == 'MEDIUM' for row in items),
                'false_refusal': count['FALSE_REFUSAL'],
                'over_refusal': count['OVER_REFUSAL'],
                'wrong_fact': count['WRONG_FACT'],
                'unsupported_side_claim': count['UNSUPPORTED_SIDE_CLAIM'],
            }
    return result


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def build(output: Path = OUTPUT) -> tuple[dict, str]:
    dataset_path = FROZEN / 'test-frozen-v1.json'
    dataset = _read(dataset_path)
    plan_path = output / 'run-plan.json'
    plan = _read(plan_path)
    manifest = _read(output / 'generation-manifest.json')
    annotations = _read(output / 'review-annotations.json')
    response_path = output / 'responses.jsonl'
    responses = [json.loads(line) for line in response_path.read_text(encoding='utf-8').splitlines() if line]
    if (sha256(dataset_path) != manifest['frozen_dataset_sha256']
            or sha256(plan_path) != manifest['plan_sha256']
            or sha256(response_path) != manifest['response_sha256']
            or annotations['frozen_dataset_sha256'] != manifest['frozen_dataset_sha256']
            or annotations['responses_sha256'] != manifest['response_sha256']):
        raise RuntimeError('Scoring input hash mismatch')
    route_keys = {(r['unit_id'], r['variant']) for r in plan['routes']}
    response_keys = {(r['unit_id'], r['variant']) for r in responses}
    review_keys = {(r['unit_id'], r['variant']) for r in annotations['records']}
    if len(route_keys) != 84 or len(responses) != 84 or len(response_keys) != 84 or \
            len(annotations['records']) != 84 or route_keys != response_keys or route_keys != review_keys:
        raise RuntimeError('Missing or duplicate route/review')
    unit_gold = {u['unit_id']: u['answerability'] for u in dataset['evidence_units']}
    case_groups = {c['case_id']: c['metric_group'] for c in dataset['cases']}
    for r in annotations['records']:
        if unit_gold[r['unit_id']] != r['gold']:
            raise RuntimeError('Gold was changed in review')
    summary = summarize(annotations['records'], case_groups)
    review_by_key = {(r['unit_id'], r['variant']): r for r in annotations['records']}
    routes_by_key = {(r['unit_id'], r['variant']): r for r in plan['routes']}
    latency = {}
    for variant in VARIANTS:
        subset = [r for r in responses if r['variant'] == variant]
        calls = [r for r in subset if r['mode'] == 'model']
        latency[variant] = {
            'routes': len(subset), 'model_calls': len(calls),
            'forced_refusals': len(subset) - len(calls),
            'sum_model_seconds': round(sum(r['seconds'] for r in calls), 3),
            'mean_model_seconds': round(sum(r['seconds'] for r in calls) / len(calls), 3),
        }
    invalid_citation_ids = []
    import re
    for r in responses:
        for match in re.findall(r'\[(\d+)\]', r['answer']):
            if match != '1':
                invalid_citation_ids.append([r['unit_id'], r['variant'], match])
    metrics = {'schema': 'evidence-gate-ablation-metrics-v1',
               'review_status': annotations['status'],
               'frozen_dataset_sha256': manifest['frozen_dataset_sha256'],
               'responses_sha256': manifest['response_sha256'],
               'review_sha256': sha256(output / 'review-annotations.json'),
               'summary': summary, 'latency': latency,
               'invalid_citation_ids': invalid_citation_ids}
    lines = ['# Evidence hard-veto vs advisory · 固定证据生成对照', '',
             '> 诊断性结果：复用已看过的中文 TEST_FROZEN v1；42 个证据 unit、84 条回答路径。不是新的独立 TEST，也不是生产迁移验收。', '',
             f'- 冻结题集 SHA-256：`{manifest["frozen_dataset_sha256"]}`',
             f'- 回答输出 SHA-256：`{manifest["response_sha256"]}`',
             f'- 模型：`{manifest["model"]}`（{manifest["host"]}）；两组只见 query 和同一证据片段，advisory 组另收到可错的 E0 状态提示；均不见 gold。',
             '- `hard_veto` 沿用 E0 的直接拒答／部分提示／模型路由；`advisory` 把判定标为可能误判，由模型根据同一原文决定答、部分答或拒答。',
             '- 使用同一来源文本和基础系统提示；为避免 excerpt 再次裁剪已签核事实，两组均使用完整 evidence unit。这是生产路由的隔离近似，并非真实端到端服务复测。', '',
             '## 严格答案结果', '',
             '| 集合 | 路由 | 严格成功 | FULL | PARTIAL | NONE |',
             '|---|---|---:|---:|---:|---:|']
    for group in GROUPS:
        for variant in VARIANTS:
            s = summary[group][variant]
            cell = lambda gold: f'{s["by_gold"][gold]["success"]}/{s["by_gold"][gold]["n"]}'
            lines.append(f'| {group} | {variant} | {s["success"]}/{s["n"]} | {cell("FULL")} | {cell("PARTIAL")} | {cell("NONE")} |')
    main_hard = summary['MAIN_SINGLE_CHUNK']['hard_veto']
    main_advisory = summary['MAIN_SINGLE_CHUNK']['advisory']
    lines += ['',
              f'主集硬门槛的失败包括完整证据误拒 {main_hard["false_refusal"]}、部分证据全拒 {main_hard["over_refusal"]}、错误事实 {main_hard["wrong_fact"]}、带错范围的附带断言 {main_hard["unsupported_side_claim"]}。',
              '在 17 个 NONE 负例中，两组均未直接给出目标答案；硬门槛版本另有 P01 的错范围附带断言。',
              'A04 正例与 A05 部分负例的 advisory 评价为中等把握；若两项都按失败计，advisory 主集仍为 38/40。若宽松地把 P01 硬门槛的最终拒答视作成功，hard_veto 为 27/40。', '',
              '## 成本与引用', '',
              '| 路由 | 模型调用 | 规则直接拒答 | 模型调用耗时合计 | 每次模型调用均值 |',
              '|---|---:|---:|---:|---:|']
    for variant in VARIANTS:
        x = latency[variant]
        lines.append(f'| {variant} | {x["model_calls"]} | {x["forced_refusals"]} | {x["sum_model_seconds"]:.3f}s | {x["mean_model_seconds"]:.3f}s |')
    lines += ['', f'引用编号越界：{len(invalid_citation_ids)}。引用编号合法不等于引用事实正确；P01 与 F03 的事实错误已在严格答案评审中计入。当前流式客户端未记录服务端 token usage，不能从耗时推出准确成本。', '',
              '## 逐证据 unit 结果', '',
              '| unit | gold | E0 路由标签 | hard_veto 回答 | advisory 回答 |',
              '|---|---|---|---|---|']
    for unit in dataset['evidence_units']:
        key = unit['unit_id']
        hard = review_by_key[key, 'hard_veto']
        advisory = review_by_key[key, 'advisory']
        label = routes_by_key[key, 'hard_veto']['E0_label']
        lines.append(f'| `{key}` | {unit["answerability"]} | {label} | {hard["verdict"]} | {advisory["verdict"]} |')
    lines += ['', '所有原始回答和耗时在 `responses.jsonl`；逐条评分理由与把握在 `review-annotations.json`。', '',
              '## 解释与决策', '',
              '- E4 在独立 matcher TEST 中相对 E0 没有增量，应结束该规则优化方向。这里评估的是 **生产 E0 式硬否决策略**，不是把 E4 接入生产。',
              '- 在这次固定证据生成中，硬否决没有表现出额外的目标答案防错收益：其误放行的 NONE 负例多数仍被模型自行拒答；它却阻断了 10 个完整证据正例。P06 的自相矛盾与 F03 的表格错值说明“判定放行”也不保证答案正确。',
              '- 因此支持继续研究“取消启发式判定的一票否决权”；**不凭本次诊断直接删除生产模块**。这里每题仅一个预选 evidence unit，advisory 提示包含可错的 E0 状态，每条模型路径只采样一次且评分由 agent 完成；真实混合检索上下文、无证据输入、用户体验和模型重复性尚未验证。',
              '- 若要改生产，先在新独立中文资料中同时考察可回答题、真正无依据题、混合多片段和缺省来源，人工复核答案与引用，并记录回答成本。已看过的 TEST_FROZEN v1 不得再充当独立迁移指标。']
    return metrics, '\n'.join(lines) + '\n'


def main() -> None:
    metrics, report = build()
    metrics_path = OUTPUT / 'metrics.json'
    report_path = OUTPUT / 'report.md'
    if metrics_path.exists() or report_path.exists():
        raise FileExistsError('Scored artifacts already exist')
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report_path.write_text(report, encoding='utf-8')
    manifest = {'state': 'DIAGNOSTIC_REVIEW_COMPLETE',
                'generation_manifest_sha256': sha256(OUTPUT / 'generation-manifest.json'),
                'review_annotations_sha256': sha256(OUTPUT / 'review-annotations.json'),
                'metrics_sha256': sha256(metrics_path), 'report_sha256': sha256(report_path)}
    (OUTPUT / 'score-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'MAIN hard={metrics["summary"]["MAIN_SINGLE_CHUNK"]["hard_veto"]["success"]}/40 '
          f'advisory={metrics["summary"]["MAIN_SINGLE_CHUNK"]["advisory"]["success"]}/40')


if __name__ == '__main__':
    main()
