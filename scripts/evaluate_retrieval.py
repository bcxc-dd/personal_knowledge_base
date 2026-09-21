import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.engine import Engine
from app.evaluation import evaluate_case, load_suite, summarize
from app.models import fingerprint


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='运行 AI-Infra 检索评测。')
    parser.add_argument('--suite', type=Path, default=ROOT / 'docs' / 'evaluations' / 'ai-infra-retrieval-v1.json')
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('RAG_DATA_DIR', 'data')))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--with-answer', action='store_true', help='调用当前回答服务并保存待人工评分的回答。')
    return parser.parse_args(argv)


def open_engine(data_dir):
    return Engine(data_dir)


def _document(engine, suite):
    documents = [doc for doc in engine.store.documents() if doc['name'] == suite.document_name]
    if len(documents) != 1:
        raise ValueError(f'需要恰好一份 {suite.document_name}，当前找到 {len(documents)} 份。')
    doc = documents[0]
    if doc['hash'] != suite.document_sha256:
        raise ValueError(f'PDF SHA-256 不一致：预期 {suite.document_sha256}，实际 {doc["hash"]}。')
    if doc['status'] != 'ready':
        raise ValueError(f'PDF 尚未就绪，当前状态为 {doc["status"]}。')
    if doc['fingerprint'] != fingerprint(engine.store.settings()):
        raise ValueError('PDF 向量索引与当前向量配置不匹配，请先重建索引。')
    return doc


async def _answer(engine, case, document):
    done = None
    async for event in engine.answer(case.question, document['kb_id'], [document['id']], None):
        if event['event'] == 'done':
            done = event['data']
    if done is None:
        return {'content': '', 'citations': [], 'warning': '回答未完成。'}
    return {'content': done['content'], 'citations': done['citations'], 'warning': done['warning']}


def main(argv=None):
    args = parse_args(argv)
    try:
        suite = load_suite(args.suite)
        engine = open_engine(args.data_dir)
        document = _document(engine, suite)
        indexed_chunks = engine.store.chunks(document['id'])
        results = []
        for case in suite.cases:
            retrieved = engine.retrieve(case.question, document['kb_id'], [document['id']])
            result = evaluate_case(case, list(retrieved), retrieved.diagnostics.get('items', []), indexed_chunks)
            result['retrieval_diagnostics'] = retrieved.diagnostics
            if args.with_answer:
                answer = asyncio.run(_answer(engine, case, document))
                result['answer_review'] = {**answer, 'clarity_score': None, 'citation_fit_score': None, 'review_notes': ''}
            results.append(result)
        output = args.output or Path('test-results') / f'ai-infra-retrieval-{datetime.now():%Y%m%d-%H%M%S}.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({
            'suite_version': suite.version, 'document_name': suite.document_name,
            'document_id': document['id'], 'document_sha256': document['hash'],
            'created_at': datetime.now().astimezone().isoformat(), 'summary': summarize(results), 'results': results,
        }, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'评测完成：{output}')
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'评测无法运行：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
