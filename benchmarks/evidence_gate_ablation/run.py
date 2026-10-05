"""Run fixed-evidence hard-veto versus advisory generation without index writes."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from urllib.parse import urlparse

from .core import plan_pair

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / 'test-results/evidence-test-frozen-2026-10-03-v1'
BLIND = ROOT / 'test-results/evidence-test-blind-2026-10-03-v1'
OUTPUT = ROOT / 'test-results/evidence-gate-ablation-2026-10-04-v1'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def build_plan() -> tuple[list[dict], dict]:
    freeze_manifest = _read_json(FROZEN / 'test-frozen-v1-manifest.json')
    run_manifest = _read_json(BLIND / 'run-manifest.json')
    dataset_path = FROZEN / 'test-frozen-v1.json'
    blind_path = BLIND / 'blind-results.json'
    if (freeze_manifest['state'] != 'TEST_FROZEN'
            or run_manifest['state'] != 'ONE_TIME_BLIND_RUN_COMPLETE'
            or sha256(dataset_path) != freeze_manifest['dataset_sha256']
            or freeze_manifest['dataset_sha256'] != run_manifest['frozen_dataset_sha256']
            or sha256(blind_path) != run_manifest['files']['blind-results.json']['sha256']):
        raise RuntimeError('Frozen input integrity failed')
    for key, relative in (
        ('E0_code_sha256', 'backend/app/evidence.py'),
        ('E0_query_plan_sha256', 'backend/app/query_plan.py'),
        ('E4_matcher_sha256', 'benchmarks/evidence_matching/matchers.py'),
    ):
        if sha256(ROOT / relative) != freeze_manifest[key]:
            raise RuntimeError(f'Frozen code changed: {key}')
    dataset = _read_json(dataset_path)
    blind = _read_json(blind_path)
    cases = {case['case_id']: case for case in dataset['cases']}
    rows = {row['unit_id']: row for row in blind['rows']}
    units = dataset['evidence_units']
    if len(cases) != 21 or len(units) != 42 or len(rows) != 42 or set(rows) != {unit['unit_id'] for unit in units}:
        raise RuntimeError('Unexpected frozen case/evidence cardinality')
    plan = [route for unit in units for route in plan_pair(cases[unit['case_id']], unit, rows[unit['unit_id']])]
    if len(plan) != 84 or len([x for x in plan if x['mode'] == 'forced_refusal']) != 22:
        raise RuntimeError('Unexpected routing plan cardinality')
    provenance = {
        'frozen_dataset_sha256': freeze_manifest['dataset_sha256'],
        'blind_results_sha256': sha256(blind_path),
        'E0_code_sha256': freeze_manifest['E0_code_sha256'],
        'E0_query_plan_sha256': freeze_manifest['E0_query_plan_sha256'],
        'E4_matcher_sha256': freeze_manifest['E4_matcher_sha256'],
        'core_sha256': sha256(ROOT / 'benchmarks/evidence_gate_ablation/core.py'),
        'runner_sha256': sha256(Path(__file__)),
    }
    return plan, provenance


def _public_model_config(data_dir: Path) -> tuple[dict, dict]:
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.store import DEFAULTS
    db_path = (data_dir / 'knowledge.sqlite3').resolve()
    with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
    config = {**DEFAULTS, **(json.loads(row[0]) if row else {})}
    if not config['allow_external'] or not config['chat_key']:
        raise RuntimeError('Configured answer model/consent unavailable')
    public = {'model': config['chat_model'], 'host': urlparse(config['chat_url']).hostname,
              'allow_external': bool(config['allow_external']), 'max_tokens': 2400}
    return config, public


def prepare(output: Path, data_dir: Path) -> tuple[list[dict], dict]:
    plan, provenance = build_plan()
    _, public_config = _public_model_config(data_dir)
    output.mkdir(parents=True, exist_ok=True)
    plan_path = output / 'run-plan.json'
    content = json.dumps({'schema': 'evidence-gate-ablation-plan-v1',
                          'design': 'fixed_evidence_hard_veto_vs_fallible_advisory',
                          'provenance': provenance, 'model': public_config,
                          'routes': plan}, ensure_ascii=False, indent=2) + '\n'
    if plan_path.exists():
        if plan_path.read_text(encoding='utf-8') != content:
            raise RuntimeError('Existing frozen plan differs; refusing overwrite')
    else:
        plan_path.write_text(content, encoding='utf-8')
    return plan, {'plan_sha256': sha256(plan_path), **provenance, **public_config}


async def _generate(model, config: dict, messages: list[dict]) -> str:
    parts = []
    async for token in model.stream(messages, config):
        parts.append(token)
    answer = ''.join(parts).strip()
    if not answer:
        raise RuntimeError('Answer model returned empty content')
    return answer


def _latest_results(path: Path) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    results = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            record = json.loads(line)
            results[(record['unit_id'], record['variant'])] = record
    return results


def run(output: Path, data_dir: Path) -> None:
    plan, metadata = prepare(output, data_dir)
    config, _ = _public_model_config(data_dir)
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.models import ModelClient
    model = ModelClient(data_dir / 'models')
    response_path = output / 'responses.jsonl'
    existing = _latest_results(response_path)
    total = len(plan)
    for index, route in enumerate(plan, 1):
        key = (route['unit_id'], route['variant'])
        if existing.get(key, {}).get('status') == 'done':
            continue
        started = time.perf_counter()
        try:
            answer = (route['forced_answer'] if route['mode'] == 'forced_refusal'
                      else asyncio.run(_generate(model, config, route['messages'])))
            record = {'unit_id': route['unit_id'], 'variant': route['variant'],
                      'mode': route['mode'], 'E0_label': route['E0_label'],
                      'status': 'done', 'answer': answer,
                      'seconds': round(time.perf_counter() - started, 3)}
        except Exception as exc:
            record = {'unit_id': route['unit_id'], 'variant': route['variant'],
                      'mode': route['mode'], 'E0_label': route['E0_label'],
                      'status': 'error', 'error': f'{type(exc).__name__}: {exc}',
                      'seconds': round(time.perf_counter() - started, 3)}
        with response_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        existing[key] = record
        print(f'{index}/{total} {route["unit_id"]} {route["variant"]}: {record["status"]} {record["seconds"]}s', flush=True)
        if record['status'] != 'done':
            raise RuntimeError(f'Generation failed; partial results saved: {record["error"]}')
    latest = _latest_results(response_path)
    if len(latest) != total or any(row['status'] != 'done' for row in latest.values()):
        raise RuntimeError('Incomplete generation results')
    manifest_path = output / 'generation-manifest.json'
    manifest = {'state': 'GENERATION_COMPLETE', 'schema': 'evidence-gate-ablation-v1',
                **metadata, 'response_sha256': sha256(response_path),
                'routes': total, 'model_calls': sum(x['mode'] == 'model' for x in plan),
                'forced_refusals': sum(x['mode'] == 'forced_refusal' for x in plan)}
    content = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    if manifest_path.exists() and manifest_path.read_text(encoding='utf-8') != content:
        raise RuntimeError('Existing generation manifest differs')
    if not manifest_path.exists():
        manifest_path.write_text(content, encoding='utf-8')
    print(f'COMPLETE {total} routes; {manifest["model_calls"]} model calls; SHA {manifest["response_sha256"]}', flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if args.prepare_only:
        plan, metadata = prepare(args.output, args.data_dir)
        print(f'PREPARED {len(plan)} routes, {sum(x["mode"] == "model" for x in plan)} model calls, SHA {metadata["plan_sha256"]}')
    else:
        run(args.output, args.data_dir)


if __name__ == '__main__':
    main()
