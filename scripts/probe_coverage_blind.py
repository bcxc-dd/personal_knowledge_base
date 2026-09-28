"""Offline blind evidence selection probe; not imported by the product."""

import argparse
import asyncio
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

from app.models import ModelClient
from app.store import DEFAULTS
from probe_coverage_upper_bound import build_probe_evidence, generate_probe_answer


def candidate_pool(record, neighboring_rows=()):
    ranked = record['retrieval']['ranked_items'][:20]
    pool = [{**item, 'probe_source': 'ranked_candidate'} for item in ranked]
    seen = {item['chunk_id'] for item in pool}
    for item in record['retrieval']['context_items'][:3]:
        if item['chunk_id'] not in seen:
            pool.append({**item, 'probe_source': 'chapter_context'})
            seen.add(item['chunk_id'])
    for neighbor in neighboring_rows:
        if neighbor['chunk_id'] in seen:
            continue
        ordinal = int(neighbor['chunk_id'].rsplit(':', 1)[-1])
        if any(hit.get('lexical_rank') and hit['lexical_rank'] <= 10
               and hit['document_id'] == neighbor['document_id']
               and hit['location'] == neighbor['location']
               and abs(int(hit['chunk_id'].rsplit(':', 1)[-1]) - ordinal) == 1
               for hit in ranked):
            pool.append({**neighbor, 'probe_source': 'same_page_neighbor'})
            seen.add(neighbor['chunk_id'])
    return pool


def selection_messages(question, input_evidence, candidates):
    def brief(item, limit):
        return {'chunk_id': item['chunk_id'], 'location': item['location'],
                'source': item.get('probe_source', 'current_input'), 'text': item['text'][:limit]}

    payload = {'question': question,
               'current_input': [brief(item, 700) for item in input_evidence],
               'candidates': [brief(item, 650) for item in candidates]}
    return [
        {'role': 'system', 'content': '你是个人知识库的证据筛选器，不要回答用户问题。先把问题拆成独立核心方面，检查当前输入是否有足够正文支持每个方面；仅从给出的候选中选择最多两个可补足缺失事实的片段。区分定义、原因、成立条件、当前仍需做的计算；章节总结要覆盖章节正文的重要结构与章末结论。不要把词语相似当成事实支持，也不要凭常识补全。若当前输入已经足够，返回空数组。只返回一个 JSON 对象，格式为 {"add_chunk_ids":["完整chunk_id"]}，不要 Markdown。'},
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
    ]


def parse_selection(response, candidates):
    data = json.loads(response.strip())
    ids = data.get('add_chunk_ids')
    if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
        raise ValueError('选择器未返回片段 ID 列表。')
    if len(ids) > 2 or len(set(ids)) != len(ids):
        raise ValueError('最多只能选择两个不同片段。')
    available = {item['chunk_id'] for item in candidates}
    if not set(ids) <= available:
        raise ValueError('选择器返回了候选之外的片段。')
    return ids


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='无金标准的离线证据盲选实验；不改变产品问答。')
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
    cases = {record['id']: record for record in baseline['results']}
    if len(cases) != 25 or baseline.get('document_name') != 'AI-Infra-Book.pdf':
        raise ValueError('需要完整 25 题的 AI Infra v2 基线报告。')
    db_uri = (args.data_dir / 'knowledge.sqlite3').resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(db_uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        config_rows = db.execute('SELECT value FROM settings WHERE id=1').fetchall()
        document_rows = db.execute('SELECT hash FROM documents WHERE id=? AND deleted=0',
                                   (baseline['document_id'],)).fetchall()
        if len(document_rows) != 1 or document_rows[0]['hash'] != baseline['document_sha256']:
            raise ValueError('当前资料与基线报告不一致。')
        records = db.execute('SELECT id, document_id, ordinal, text, location FROM chunks WHERE document_id=?',
                             (baseline['document_id'],)).fetchall()
    config = {**DEFAULTS, **(json.loads(config_rows[0]['value']) if config_rows else {})}
    if not config['chat_key'] or not config['allow_external']:
        raise ValueError('回答服务尚未配置或未允许发送检索片段。')
    rows_by_ordinal = {row['ordinal']: dict(row) for row in records}
    model = ModelClient(args.data_dir / 'models')
    targets = ('q05', 'q15', 'q04', 'q18', 'q23', 'q24', 'q25')
    output = {'schema': 'coverage-blind-probe-v1', 'baseline_report': str(args.baseline),
              'document_sha256': baseline['document_sha256'],
              'method': 'model_selects_up_to_two_from_bounded_candidates_no_gold_or_page_hints',
              'results': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for case_id in targets:
        record = cases[case_id]
        ranked = record['retrieval']['ranked_items'][:20]
        lexical_ordinals = [int(item['chunk_id'].rsplit(':', 1)[-1]) for item in ranked
                            if item.get('lexical_rank') and item['lexical_rank'] <= 10]
        neighbors = []
        for ordinal in lexical_ordinals:
            for adjacent in (ordinal - 1, ordinal + 1):
                row = rows_by_ordinal.get(adjacent)
                if row is not None:
                    neighbors.append({**row, 'chunk_id': row['id'], 'name': baseline['document_name']})
        pool = candidate_pool(record, neighbors)
        messages = selection_messages(record['question'], record['answer']['input_evidence'], pool)
        started = time.perf_counter()
        response = ''
        try:
            async def collect():
                value = ''
                async for token in model.stream(messages, config):
                    value += token
                return value

            response = asyncio.run(collect())
            chosen = parse_selection(response, pool)
            selection = {'status': 'done', 'chunk_ids': chosen}
        except Exception as exc:
            selection = {'status': 'error', 'chunk_ids': [], 'error': f'{type(exc).__name__}: {exc}'}
        result = {'id': case_id, 'question': record['question'], 'pool_size': len(pool),
                  'selector_prompt_chars': len(messages[1]['content']),
                  'selection_seconds': round(time.perf_counter() - started, 2),
                  'selection_raw': response, 'selection': selection}
        if selection['status'] == 'done' and case_id in {'q05', 'q15'}:
            selected_ordinals = [int(chunk_id.rsplit(':', 1)[-1]) for chunk_id in selection['chunk_ids']]
            adjacent_rows = [item for item in pool if item.get('probe_source') == 'same_page_neighbor']
            evidence = build_probe_evidence(record, selected_ordinals, adjacent_rows=adjacent_rows)
            result['input_ids'] = [item['chunk_id'] for item in evidence]
            answer_started = time.perf_counter()
            try:
                result['answer'] = asyncio.run(generate_probe_answer(record['question'], evidence, model, config))
                result['answer_status'] = 'done'
            except Exception as exc:
                result['answer_status'] = 'error'
                result['answer_error'] = f'{type(exc).__name__}: {exc}'
            result['answer_seconds'] = round(time.perf_counter() - answer_started, 2)
        output['results'].append(result)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'{case_id}: {selection["status"]} selected={selection["chunk_ids"]} in {result["selection_seconds"]}s', flush=True)
    print(f'盲选记录：{args.output}')
