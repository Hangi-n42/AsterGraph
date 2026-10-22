"""Synthetic identical-scope reuse; no real approval or model execution."""
from copy import deepcopy
from hashlib import sha256
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.knowledge import business_use, source_list_service as operation
from app.knowledge.availability import _write_status
from app.knowledge.business_models import BusinessQuery
from app.tests.unit.test_knowledge_source_list_service import case
from app.tests.unit.test_knowledge_source_timing_consumer import bound


def store(db, table, value):
    db.execute(f'INSERT INTO {table}(id,payload) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
               (value['id'], json.dumps(value)))


@pytest.fixture
def copied(bound, monkeypatch):
    service, origin, payload, prior = bound
    instruction = 'fixture condition producer contract'
    monkeypatch.setattr(operation, 'CONDITION_INSTRUCTION_SHA256', sha256(instruction.encode()).hexdigest())
    requirement = dict(id='r', revision=1, status='ready', question='검사 기준', criterion='원문 보존')
    origin['requirements'] = [deepcopy(requirement)]
    origin['claims'][0].update(statement='원래 본문', conditions=['원래 조건'], review_status='accepted')
    with service.repository.connect() as db:
        a = service.repository.get(db, 'runs', 'conditions')
        b = service.repository.get(db, 'runs', 'timing')['units'][0]
        a['answer_contract'] = 'source-list-conditions-v1'
        unit = a['units'][0]
        unit['messages'].insert(0, dict(role='system', content=instruction))
        for key in ('requested_limits', 'executed_limits', 'request_configuration'):
            unit[key] = deepcopy(b[key])
        unit['response'].update(provider='fixture', model='fixture', stage='source_list_conditions', done=True, done_reason='stop',
            raw_response=dict(message=dict(content=unit['response']['text'])))
        service.repository.save(db, 'runs', a)
        run = service.repository.get(db, 'runs', 'origin')
        run['changeset_id'] = 'fixture_change'
        service.repository.save(db, 'runs', run)
        store(db, 'changesets', dict(id='fixture_change', run_id='origin', revision=2))
        store(db, 'requirements', requirement)
        for block in origin['blocks']:
            block['evidence_id'] = 'evidence:' + block['id']
            store(db, 'evidence', dict(id=block['evidence_id'], block_id=block['id']))
            db.execute('UPDATE blocks SET payload=? WHERE id=?', (json.dumps(block), block['id']))
        store(db, 'snapshots', origin)
        current = deepcopy(origin)
        current.update(id='FIXTURE_ONLY_new', actor='FIXTURE_ONLY', reason='검사 전용 · 실제 승인 아님')
        store(db, 'snapshots', current)
    payload.update(snapshot_id=current['id'])
    payload['list_comparison']['reuse_from_snapshot_id'] = origin['id']
    return service, origin, current, payload


def assembled(copied):
    service, _, current, payload = copied
    with service.repository.connect() as db:
        return operation.assemble(service, db, BusinessQuery.model_validate(payload), current)


def test_new_scope_keeps_original_answer_producers_and_actual_origin_object(copied, monkeypatch):
    service, origin, current, payload = copied
    original_request = deepcopy(payload)
    original_request['snapshot_id'] = origin['id']
    original_request['list_comparison'].pop('reuse_from_snapshot_id')
    with service.repository.connect() as db:
        original = operation.assemble(service, db, BusinessQuery.model_validate(original_request), origin)
        before = list(db.execute('SELECT id,payload FROM runs'))
    original_conditions = operation.stored_conditions
    def inspect_origin(svc, db, sources, selected, *args):
        assert selected == svc.repository.get(db, 'snapshots', origin['id'])
        assert selected['id'] != current['id']
        return original_conditions(svc, db, sources, selected, *args)
    monkeypatch.setattr(operation, 'stored_conditions', inspect_origin)
    actual = assembled(copied)
    receipt = actual.pop('stored_scope_reuse')
    assert actual == original
    assert receipt['producer_snapshot_id'] == origin['id'] and receipt['consumer_snapshot_id'] == current['id']
    assert receipt['producer_snapshot_sha256'] != receipt['consumer_snapshot_sha256']
    assert receipt['producers'][0]['run_id'] == 'conditions'
    assert receipt['producers'][1]['run_id'] == 'timing'
    assert receipt['semantic_approval'] is False
    with service.repository.connect() as db:
        assert list(db.execute('SELECT id,payload FROM runs')) == before
        assert service.repository.get(db, 'snapshots', current['id']) == current


def test_api_saves_new_consumer_id_and_receipt_without_rewriting_producers(copied, monkeypatch):
    from app.api.routers import knowledge as api
    from app.knowledge import autoschema
    service, origin, current, payload = copied
    monkeypatch.setattr(api.settings, 'KNOWLEDGE_ENABLED', True)
    monkeypatch.setattr(autoschema, 'graph', lambda *a: dict(nodes=[], edges=[]))
    app = FastAPI(); app.include_router(api.router, prefix='/api/v1')
    app.dependency_overrides[api.get_knowledge_service] = lambda: service
    monkeypatch.setattr(business_use, 'change_view', lambda *a: dict(eligible_ids=[], eligibility_blocks={}, explicit_review_options=[]))
    client = TestClient(app)
    response = client.post('/api/v1/knowledge/business/search', json=payload)
    assert response.status_code == 200, response.text
    result = response.json()['data']
    saved = client.get('/api/v1/knowledge/runs/' + result['run_id']).json()['data']
    detail = client.get('/api/v1/knowledge/workbench/answers', params=dict(kind='source_graph', scope_id=current['id'], answer_id=saved['id'])).json()['data']['detail']
    assert result['snapshot_id'] == saved['snapshot_id'] == saved['query']['snapshot_id'] == detail['snapshot_id'] == current['id']
    assert result['answer'] == saved['answer'] == detail['answer']
    assert saved['execution_boundary']['stored_scope_reuse']['producer_snapshot_id'] == origin['id']
    assert saved['condition_consumer']['original_validation']['record_integrity'] == 'invalid'
    assert saved['condition_consumer']['original_status'] == 'partial'
    assert saved['timing_consumer']['semantic_status'] == 'unverified'
    assert not saved['condition_consumer']['human_approval']
    assert saved['status'] == 'succeeded' and saved['answer_status'] == 'partial'
    assert saved['units'] == [] and saved['metrics']['llm_calls'] == 0


@pytest.mark.parametrize('origin_id', [None, 'missing', 'FIXTURE_ONLY_new', 'unrelated'])
def test_missing_or_forged_origin_cannot_bypass_same_snapshot_contract(copied, origin_id):
    service, origin, _, payload = copied
    if origin_id == 'unrelated':
        with service.repository.connect() as db:
            store(db, 'snapshots', dict(origin, id=origin_id))
    payload['list_comparison']['reuse_from_snapshot_id'] = origin_id
    with pytest.raises((ValueError, KeyError)):
        assembled(copied)


@pytest.mark.parametrize('fault', ['body','condition','address','version','product','duplicate_claim','duplicate_block',
                                 'review','usage','date','method_tail','list_quantity','source_run'])
def test_any_scope_input_change_is_rejected_without_partial_equivalence(copied, fault):
    service, _, current, payload = copied
    if fault == 'body': current['claims'][0]['statement'] = '다른 본문'
    elif fault == 'condition': current['claims'][0]['conditions'] = ['다른 조건']
    elif fault == 'address': current['blocks'][0]['locator']['start_char'] = 999
    elif fault == 'version': current['source_versions']['v1']['sha256'] = 'different'
    elif fault == 'product': current['claims'] = [c for c in current['claims'] if c['id'] != payload['list_comparison']['products'][0]['storage_claim_id']]
    elif fault == 'duplicate_claim': current['claims'].append(deepcopy(current['claims'][0]))
    elif fault == 'duplicate_block': current['blocks'].append(deepcopy(current['blocks'][0]))
    elif fault == 'review': current['claims'][0]['review_status'] = 'unreviewed'
    elif fault == 'usage': current['public_scope_usage'] = 'expanded'
    elif fault == 'date': current['source_versions']['v1']['dates'] = ['different']
    elif fault == 'method_tail': next(b for b in current['blocks'] if b['id'] == 'method')['text'] += '다른 후속 조건'
    elif fault == 'list_quantity': current['blocks'][0]['text'] = current['blocks'][0]['text'].replace('1g', '9g')
    else: current['run_id'] = 'different'
    with service.repository.connect() as db:
        store(db, 'snapshots', current)
    with pytest.raises(ValueError, match='전체 입력'):
        assembled(copied)


@pytest.mark.parametrize('fault', ['source_restriction','evidence_restriction','origin_invalidation','current_invalidation','revision','criterion'])
def test_current_restrictions_invalidations_and_criteria_block_reuse(copied, fault):
    service, origin, current, _ = copied
    with service.repository.connect() as db:
        if fault.endswith('restriction'):
            target = ('source_version', 'v1') if fault.startswith('source') else ('evidence', current['blocks'][0]['evidence_id'])
            _write_status(db, [target], 'blocked', 'FIXTURE_ONLY', '검사 전용')
        elif fault.endswith('invalidation'):
            store(db, 'snapshot_events', dict(id='invalid', event='business_correction',
                snapshot_id=origin['id'] if fault.startswith('origin') else current['id']))
        else:
            row = service.repository.get(db, 'requirements', 'r')
            row['revision' if fault == 'revision' else 'criterion'] = 2 if fault == 'revision' else '다른 기준'
            store(db, 'requirements', row)
    with pytest.raises(ValueError):
        assembled(copied)


@pytest.mark.parametrize('fault', ['instruction','raw','query_snapshot','limits'])
def test_original_producer_contract_is_checked_without_rewriting_it(copied, fault):
    service, _, _, _ = copied
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', 'conditions')
        if fault == 'instruction': run['units'][0]['messages'][0]['content'] = 'other'
        elif fault == 'raw': run['units'][0]['response']['raw_response']['message']['content'] = '{}'
        elif fault == 'query_snapshot': run['query']['snapshot_id'] = 'forged'
        else: run['units'][0]['executed_limits']['max_tokens'] += 1
        service.repository.save(db, 'runs', run)
    with pytest.raises(ValueError):
        assembled(copied)


@pytest.mark.parametrize('fault', ['requirement_revision','criterion','changeset_revision','status_revision','producer','snapshot'])
def test_save_rechecks_input_producers_and_current_revision(copied, monkeypatch, fault):
    service, _, current, payload = copied
    real_assemble = operation.assemble
    def changed_after_assembly(*args):
        result = real_assemble(*args)
        with service.repository.connect() as db:
            if fault in {'requirement_revision','criterion'}:
                row = service.repository.get(db, 'requirements', 'r')
                row['revision' if fault == 'requirement_revision' else 'criterion'] = 2 if fault == 'requirement_revision' else '다른 기준'
                store(db, 'requirements', row)
            elif fault == 'changeset_revision':
                row = service.repository.get(db, 'changesets', 'fixture_change'); row['revision'] += 1
                store(db, 'changesets', row)
            elif fault == 'status_revision': db.execute('UPDATE knowledge_state SET status_revision=status_revision+1')
            elif fault == 'producer':
                row = service.repository.get(db, 'runs', 'conditions'); row['units'][0]['messages'][0]['content'] = 'other'
                service.repository.save(db, 'runs', row)
            else:
                row = service.repository.get(db, 'snapshots', current['id']); row['claims'][0]['statement'] = 'changed'
                store(db, 'snapshots', row)
        return result
    monkeypatch.setattr(operation, 'assemble', changed_after_assembly)
    result = business_use.query(service, BusinessQuery.model_validate(payload))
    assert result['status'] == 'needs_review' and result['answer'] is None
    assert result['execution_boundary']['stored_scope_reuse_conflict'] is True
    with service.repository.connect() as db:
        assert not service.repository.has_active_runs(db)
