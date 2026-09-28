import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.engine import Engine, normalize_question
from app.evaluation import evaluate_case, load_suite, summarize
from app.evaluation_v2 import build_case_record, load_calibrated_suite, summarize_run
from app.evidence import assess_evidence
from app.models import ModelClient, fingerprint
from app.reranker import Reranker


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='运行 AI-Infra 检索评测。')
    parser.add_argument('--suite', type=Path, default=ROOT / 'docs' / 'evaluations' / 'ai-infra-answerability-v2.json')
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


def snapshot_engine(data_dir, target):
    """Run evaluation against a consistent DB and index copy, leaving user history alone."""
    source_db = data_dir / 'knowledge.sqlite3'
    if not source_db.is_file() or not (data_dir / 'chroma').is_dir():
        raise ValueError('评测数据目录缺少 SQLite 或 Chroma 索引。')
    target.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_db) as source, sqlite3.connect(target / 'knowledge.sqlite3') as copy:
        source.backup(copy)
    shutil.copytree(data_dir / 'chroma', target / 'chroma')
    engine = Engine(target)
    engine.models = ModelClient(data_dir / 'models')
    engine.reranker = Reranker(data_dir / 'models')
    return engine


def close_evaluation_engine(engine):
    engine.close()
    # Chroma keeps Windows index files open after a query. Stop its system
    # before TemporaryDirectory removes the isolated snapshot.
    engine.vectors.client._system.stop()


async def run_calibrated_case(engine, case, document, with_answer):
    if with_answer:
        sources, done, error = {}, None, None
        async for event in engine.answer(case['question'], document['kb_id'], [document['id']], None):
            if event['event'] == 'sources':
                sources = event['data']
            elif event['event'] == 'done':
                done = event['data']
            elif event['event'] == 'error':
                error = event['data'].get('message', '回答失败')
        if done is None and error is None:
            error = '回答流未完成。'
        return build_case_record(case, sources, done=done, error=error)
    question = normalize_question(case['question'])
    retrieved = engine.retrieve(question, document['kb_id'], [document['id']])
    citations = [{**hit, 'id': i + 1} for i, hit in enumerate(retrieved)]
    assessment = assess_evidence(question, citations).to_dict()
    sources = {'citations': [hit for hit in citations if hit['chunk_id'] in assessment['evidence_chunk_ids']],
               'retrieval_diagnostics': retrieved.diagnostics, 'evidence_assessment': assessment}
    return build_case_record(case, sources)


def run_fixtures(suite):
    questions = {case['id']: case['question'] for case in suite.cases}
    results = []
    for fixture in suite.fixtures:
        hits = [{'chunk_id': f"{fixture['id']}:{i}", 'text': excerpt['text'],
                 'location': f"第 {excerpt['page']} 页"}
                for i, excerpt in enumerate(fixture['excerpts'], 1)]
        result = assess_evidence(normalize_question(questions[fixture['case_id']]), hits).to_dict()
        results.append({'id': fixture['id'], 'case_id': fixture['case_id'],
                        'expected_status': fixture['expected_status'], 'actual_assessment': result,
                        'status_match': fixture['expected_status'] == result['status']})
    return results


def _code_revision():
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def run_calibrated(args):
    suite = load_calibrated_suite(args.suite)
    output = args.output or Path('test-results') / f'ai-infra-evaluation-v2-{datetime.now():%Y%m%d-%H%M%S}.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    data_dir = args.data_dir.resolve()
    with tempfile.TemporaryDirectory(prefix='rag-eval-') as temporary:
        engine = snapshot_engine(data_dir, Path(temporary))
        try:
            document = _document(engine, suite)
            config = engine.store.settings(public=True)
            report = {
                'schema': 'ai-infra-runtime-report-v2', 'suite_version': suite.version,
                'suite_sha256': hashlib.sha256(args.suite.read_bytes()).hexdigest(),
                'document_name': suite.document_name, 'document_sha256': suite.document_sha256,
                'document_id': document['id'], 'code_revision': _code_revision(),
                'created_at': datetime.now().astimezone().isoformat(),
                'data_source': str(data_dir), 'execution': 'isolated_data_snapshot',
                'with_answer': args.with_answer,
                'config': {key: value for key, value in config.items() if key not in {'chat_key_set', 'embedding_key_set'}},
                'results': [], 'assessment_fixtures': [],
            }
            for case in suite.cases:
                try:
                    record = asyncio.run(run_calibrated_case(engine, case, document, args.with_answer))
                except Exception as exc:
                    record = build_case_record(case, {}, error=f'{type(exc).__name__}: {exc}')
                report['results'].append(record)
                report['summary'] = summarize_run(report['results'])
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f"{case['id']}: {record['assessment'].get('status', 'missing')} / {record['answer']['status']}", flush=True)
            report['assessment_fixtures'] = run_fixtures(suite)
            report['completed_at'] = datetime.now().astimezone().isoformat()
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'评测记录：{output}')
            return 0
        finally:
            close_evaluation_engine(engine)


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
        if json.loads(args.suite.read_text(encoding='utf-8')).get('schema') == 'ai-infra-gold-rubric':
            return run_calibrated(args)
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
