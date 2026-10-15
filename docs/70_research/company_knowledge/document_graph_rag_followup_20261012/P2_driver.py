"""Native-position-only QA comparison through the existing product entry point."""
import argparse
import asyncio
from copy import deepcopy
from dataclasses import asdict
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from app.knowledge import business_run, business_use, graph_retrieval as gr
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService, utcnow
from app.generation.model_client import ModelClient

ROOT = Path('/Users/hyeongi/.codex/worktrees/document-graph-rag-comparison/Civil-Complaints-System')
BASE = ROOT / 'data/knowledge/evaluations/document_graph_rag_20261012/presentation_20261012'
OUT = ROOT / 'data/knowledge/evaluations/document_graph_rag_followup_20261012/P2_native_locations_v1'
CASES = [f'{q}_{a}' for q in ['SUP02', 'SUP01', 'SUP03'] for a in ['C', 'B']]
TARGET_DIGEST = '25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e'

def read(path):
    return json.loads(Path(path).read_text())

def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def normalized(request):
    result = asdict(request)
    result.pop('request_id')
    return result

class Captured(Exception):
    pass

args = argparse.ArgumentParser()
args.add_argument('mode', choices=['prepare', 'execute'])
args.add_argument('cases', nargs='*')
args = args.parse_args()
assert set(args.cases) <= set(CASES)
build = read(BASE / 'source_build_manifest.json')
execution = read(BASE / 'qa/execution_manifest.json')
source_database = Path(build['database'])
assert source_database != OUT / 'knowledge.db'
OUT.mkdir(parents=True, exist_ok=True)
original_retrieve, original_select = gr.retrieve, gr.select_passages
baseline = None
captured = None

def reused_retrieval(service, run, snapshot, request):
    assert request.model_dump() == baseline['request']
    assert snapshot['id'] == 'run:' + execution['source_run_id']
    run['graph_retrieval'] = deepcopy(baseline['run']['graph_retrieval'])
    run['passage_index'] = deepcopy(baseline['run']['passage_index'])
    run['retrieval_reuse'] = dict(baseline_run_id=baseline['run']['id'], kind='unchanged_saved_ranking_and_selection',
        source_run_sha256=execution['source_run_sha256'], new_search_or_relation_selection_calls=0)
    return deepcopy(baseline['run']['retrieval'])

def reused_selection(candidates, ranked, blocks, options, limit):
    assert limit == baseline['request']['limit'] == 12
    assert ranked == baseline['run']['retrieval']
    assert {c['id'] for c in candidates} == set(baseline['run']['passage_index']['texts'])
    return deepcopy(ranked), deepcopy(baseline['run']['passage_selection'])

class CaptureClient:
    def __init__(self, config):
        assert config == baseline['run']['recipe']['generation']

    async def generate(self, request, cancelled=None):
        global captured
        captured = normalized(request)
        raise Captured()

class GuardedClient(ModelClient):
    async def generate(self, request, cancelled=None):
        assert normalized(request) == frozen['cases'][current]['request']
        assert request.stage == 'business_qa' and request.model == 'qwen3.8:27b-q4_K_M'
        assert request.max_tokens == 4096 and request.context_tokens == 49152
        return await super().generate(request, cancelled)

gr.retrieve, gr.select_passages = reused_retrieval, reused_selection

if args.mode == 'prepare':
    assert not (OUT / 'input_contract.json').exists(), 'Existing frozen contract must not be overwritten'
    with sqlite3.connect(source_database.as_uri() + '?mode=ro', uri=True) as src:
        source = json.loads(src.execute('SELECT payload FROM runs WHERE id=?', (execution['source_run_id'],)).fetchone()[0])
        assert digest(source) == execution['source_run_sha256']
        with sqlite3.connect(OUT / 'knowledge.db') as dst:
            src.backup(dst)
    service = KnowledgeService(OUT / 'knowledge.db')
    business_run.ModelClient = CaptureClient
    contract = dict(version='reader-native-locations-only-v1', created_at=utcnow(), cases={},
        source_run_id=execution['source_run_id'], source_run_sha256=execution['source_run_sha256'],
        original_database_sha256=sha(source_database), model_digest=TARGET_DIGEST,
        product_code={str(p.relative_to(ROOT)): sha(p) for p in [ROOT/'app/knowledge/graph_retrieval.py',
            ROOT/'app/knowledge/business_use.py', ROOT/'app/knowledge/business_run.py', ROOT/'app/generation/model_client.py']},
        driver_sha256=sha(__file__), tests='25 passed in 7.55s', new_model_calls_before_freeze=0,
        approved_target_cases=['SUP02_C', 'SUP02_B'], controls_conditional_on_improvement=['SUP01_C','SUP01_B','SUP03_C','SUP03_B'])
    for current in CASES:
        captured = None
        baseline = read(BASE / 'qa/presentation_exploratory' / (current + '.json'))
        old_unit = next(u for u in baseline['run']['units'] if u['stage'] == 'business_qa')
        request = BusinessQuery.model_validate(baseline['request'])
        started = time.monotonic()
        try:
            result = business_use.query(service, request, context_mode=baseline['run']['context_mode'])
            raise AssertionError('Reader capacity failed before input capture: ' + str(result))
        except Captured:
            pass
        assert captured is not None
        assert captured['messages'][0] == old_unit['messages'][0]
        assert captured['schema'] == old_unit['schema']
        old_payload = json.loads(old_unit['messages'][1]['content'])
        new_payload = json.loads(captured['messages'][1]['content'])
        stripped = deepcopy(new_payload)
        for field in ['context', 'source_context']:
            assert len(stripped[field]) == len(old_payload[field])
            for row, old in zip(stripped[field], old_payload[field]):
                for key in ['block_order', 'element_path']:
                    row.get('locator', {}).pop(key, None)
                if not row.get('locator') and 'locator' not in old:
                    row.pop('locator', None)
        assert stripped == old_payload, 'Non-location payload change'
        assert captured['temperature'] == 0 and captured['think'] is False and captured['timeout'] == 1800
        assert captured['max_tokens'] == 4096 and captured['context_tokens'] == 49152
        with service.repository.connect() as db:
            runs = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM runs')]
        run = next(r for r in reversed(runs) if r.get('query') == request.model_dump() and r['units'] and r['units'][-1]['status'] == 'running')
        run.update(status='failed', finished_at=utcnow(), error='preflight_capture_no_model_call')
        run['units'][-1].update(status='failed', error='preflight_capture_no_model_call')
        business_run.save(service, run)
        contract['cases'][current] = dict(request=captured, request_sha256=digest(captured), baseline_file_sha256=sha(BASE/'qa/presentation_exploratory'/(current+'.json')),
            baseline_run_id=baseline['run']['id'], baseline_input_sha256=digest(old_unit['messages']),
            source_context_budget=run['source_context_budget'], selected_ids_unchanged=run['provided_ids'] if 'provided_ids' in run else [h['block_id'] for h in baseline['run']['retrieval']],
            payload_only_locator_changes=True, prepare_elapsed_s=time.monotonic()-started)
        print(current, 'frozen', digest(captured), 'source_budget', run['source_context_budget'], flush=True)
    service.executor.shutdown(wait=True)
    write(OUT/'input_contract.json', contract)
    print('CONTRACT', sha(OUT/'input_contract.json'), flush=True)
else:
    frozen = read(OUT / 'input_contract.json')
    assert sha(__file__) == frozen['driver_sha256']
    assert sha(source_database) == frozen['original_database_sha256']
    for name, expected in frozen['product_code'].items():
        assert sha(ROOT/name) == expected
    lock = Path(build['inference_lock']).open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    identity = ModelClient(baseline['run']['recipe']['generation'] if baseline else
        read(BASE/'qa/presentation_exploratory/SUP02_C.json')['run']['recipe']['generation']).identities(
            {'review': 'qwen3.8:27b-q4_K_M'}, {'review': 49152})
    assert identity['review']['digest'] == frozen['model_digest']
    service = KnowledgeService(OUT / 'knowledge.db')
    business_run.ModelClient = GuardedClient
    for current in args.cases:
        target = OUT / (current + '.json')
        assert not target.exists(), 'No unchanged retry or overwrite'
        baseline = read(BASE / 'qa/presentation_exploratory' / (current + '.json'))
        assert sha(BASE/'qa/presentation_exploratory'/(current+'.json')) == frozen['cases'][current]['baseline_file_sha256']
        request = BusinessQuery.model_validate(baseline['request'])
        started = time.monotonic()
        result = business_use.query(service, request, context_mode=baseline['run']['context_mode'])
        run = service.run(result['run_id'])
        write(target, dict(case=current, result=result, run=run, elapsed_s=time.monotonic()-started,
            frozen_contract_sha256=sha(OUT/'input_contract.json'), baseline_run_id=baseline['run']['id'],
            scope='same saved context, native locator information only; no new search/edge filter'))
        print(current, 'saved', result['status'], run['id'], flush=True)
    service.executor.shutdown(wait=True)
    fcntl.flock(lock, fcntl.LOCK_UN)
