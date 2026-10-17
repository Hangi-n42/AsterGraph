"""Capture final source-reader inputs and compare frozen P4 requests; no models."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from app.knowledge import business_run, business_use, graph_retrieval as gr
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService, utcnow

ROOT = Path('/Users/hyeongi/.codex/worktrees/document-graph-rag-comparison/Civil-Complaints-System')
DATA = ROOT / 'data/knowledge/evaluations/document_graph_rag_continuation_v1'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
digest = lambda v: hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
rows = []
current = captured = baseline = None

class Captured(Exception):
    pass

class CaptureClient:
    def __init__(self, config):
        assert config == baseline['run']['recipe']['generation']

    async def generate(self, request, cancelled=None):
        global captured
        captured = asdict(request)
        captured.pop('request_id')
        assert request.stage == 'business_qa'
        raise Captured()

def ranking(service, run, snapshot, request):
    run['graph_retrieval'] = deepcopy(baseline['run']['graph_retrieval'])
    run['passage_index'] = deepcopy(baseline['run']['passage_index'])
    return [dict(block_id=h['id'], file_id=h['evidence']['source_version_id'], score=h['score'])
            for h in baseline['run']['graph_retrieval']['ranked_passages']]

gr.retrieve = ranking
gr.select_passages = lambda *_: (deepcopy(baseline['run']['retrieval']), deepcopy(baseline['run']['passage_selection']))
business_run.ModelClient = CaptureClient
build = read(ROOT / 'data/knowledge/evaluations/document_graph_rag_20261012/presentation_20261012/source_build_manifest.json')
original_sha = sha(Path(build['database']))
with TemporaryDirectory(prefix='rag-final-input-replay-', dir='/private/tmp') as temp:
    with sqlite3.connect(Path(build['database']).as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(Path(temp) / 'knowledge.db') as copy:
            source.backup(copy)
    service = KnowledgeService(Path(temp) / 'knowledge.db')
    try:
        for scope in ['P4', 'P4_current_baseline', 'P4_gap_B']:
            contract = read(DATA / scope / 'input_contract.json')
            for current, frozen in contract['cases'].items():
                baseline = read(Path(frozen['baseline_file']))
                request = BusinessQuery.model_validate(baseline.get('request', baseline['run']['query']))
                request.source_context_format = 'separate' if scope == 'P4_current_baseline' else 'native_bundle'
                captured = None
                try:
                    business_use.query(service, request, context_mode=baseline['run']['context_mode'])
                except Captured:
                    pass
                with service.repository.connect() as db:
                    runs = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM runs ORDER BY rowid DESC')]
                run = next(row for row in runs if row.get('query') == request.model_dump())
                assert run['status'] == 'running' and not run['units'][-1].get('response')
                run.update(status='failed', finished_at=utcnow(), error='input_capture_no_model_call')
                run['units'][-1].update(status='failed', error='input_capture_no_model_call')
                business_run.save(service, run)
                assert captured == frozen['qa_request'], (scope, current, 'Final input changed')
                rows.append(dict(scope=scope, case=current, request_sha256=digest(captured),
                                 identical_to_frozen=True, actual_model_calls=0))
    finally:
        service.shutdown()
assert len(rows) == 8 and sha(Path(build['database'])) == original_sha
report = dict(version='final-product-frozen-input-replay-v1', model_calls=0,
    cases=rows, original_DB_sha256=original_sha, source_DB_unchanged=True,
    final_product_sha256={str(p.relative_to(ROOT)): sha(p) for p in [
        ROOT / 'app/knowledge/business_models.py', ROOT / 'app/knowledge/business_use.py',
        ROOT / 'app/knowledge/graph_retrieval.py']})
path = Path('/private/tmp/rag-continuation-diagnostic/final_input_replay.json')
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False))
