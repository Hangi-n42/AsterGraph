from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app.knowledge import autoschema, business_checkpoint, business_run
from app.knowledge.business_models import BusinessRunRequest
from app.knowledge.schemas import RunRequest, SourceRegistration
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business import finish


@pytest.fixture
def completed_source(tmp_path, monkeypatch):
    calls = []
    class Client:
        def __init__(self, *_): pass
        def identities(self, models, required):
            return {k:dict(name=v, digest='mock', context_length=required[k]) for k,v in models.items()}
        async def generate(self, request, cancelled=None):
            calls.append(request.stage)
            parsed = {'definitions': []} if request.stage == 'direct_definitions' else []
            return dict(parsed=parsed, text=json.dumps(parsed),
                failure_kind='truncated' if request.stage == 'entity_relation' else None, elapsed_s=.01)
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    service = KnowledgeService(tmp_path/'knowledge.db')
    vid = service.register('원문.txt', '기관은 신청을 접수한다.'.encode(),
        SourceRegistration(title='원문', publisher='기관', namespace='test'))['source_version_id']
    finish(service, service.start(RunRequest(source_version_ids=[vid]))['run_id'])
    parent = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[vid],
        repair=False, conceptualize=False))['run_id'])
    assert parent['status'] == 'partial'
    calls.clear()
    try:
        yield service, parent, calls
    finally:
        service.shutdown()


def test_product_execute_preserves_failed_outcome_without_native_retry(completed_source):
    service, parent, calls = completed_source
    prepared = business_checkpoint.prepare(service, parent['id'])
    child = service.run(prepared['run_id'])
    assert child['units'] == parent['units'] and child['claims'] == parent['claims']
    assert business_checkpoint.validate(service, child) == {
        (c['id'], role) for c in parent['chunks'] for role in (*autoschema.ROLES, 'direct_definitions')}
    business_run.execute(service, child['id'])
    result = service.run(child['id'])
    assert calls == [] and result['metrics']['llm_calls'] == 0
    assert result['units'] == parent['units'] and result['status'] == 'partial'
    assert service.run(parent['id']) == parent


@pytest.mark.parametrize('field', ['claims', 'units', 'recipe', 'completed_ids'])
def test_checkpoint_rejects_changed_child_before_any_model_call(completed_source, field):
    service, parent, calls = completed_source
    child = service.run(business_checkpoint.prepare(service, parent['id'])['run_id'])
    if field == 'claims': child['claims'].append(dict(id='invented'))
    elif field == 'units': child['units'][0].update(status='succeeded', error=None)
    elif field == 'recipe': child['recipe']['options']['extraction_tokens'] *= 2
    else: child['source_checkpoint']['completed_unit_ids'] = []
    with pytest.raises(ValueError, match='새 실행'):
        business_checkpoint.validate(service, child)
    assert calls == []


def test_checkpoint_rejects_changed_parent_record(completed_source):
    service, parent, calls = completed_source
    child = service.run(business_checkpoint.prepare(service, parent['id'])['run_id'])
    changed = deepcopy(parent); changed['claims'].append(dict(id='changed'))
    with service.repository.connect() as db:
        service.repository.save(db, 'runs', changed)
    with pytest.raises(ValueError, match='새 실행'):
        business_checkpoint.validate(service, child)
    assert calls == []


def test_public_request_has_no_completed_role_skip_field():
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        BusinessRunRequest(source_version_ids=['v'], source_checkpoint={'completed_unit_ids':['arbitrary']})


@pytest.mark.parametrize('cancelled_with_source_id', [False, True])
def test_interrupted_response_is_not_reused_and_only_missing_roles_run(completed_source, cancelled_with_source_id):
    service, parent, calls = completed_source
    interrupted = deepcopy(parent)
    interrupted['id'] = 'interrupted-parent'
    interrupted['status'] = 'failed'
    pending = deepcopy(parent['units'][2])
    pending.update(status='failed', error='interrupted_without_response')
    if cancelled_with_source_id:
        pending.update(error='cancelled', response=dict(failure_kind='cancelled', done=False))
    else:
        pending.pop('source_chunk_id'); pending.pop('response')
    interrupted['units'] = deepcopy(parent['units'][:2]) + [pending]
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (interrupted['id'], json.dumps(interrupted)))
    interrupted = service.run(interrupted['id'])
    child = service.run(business_checkpoint.prepare(service, interrupted['id'])['run_id'])
    assert child['source_checkpoint']['unfinished_units'][0]['id'] == pending['id']
    business_run.execute(service, child['id'], defer_concepts=True)
    result = service.run(child['id'])
    assert result['conceptualization_scope'] == 'deferred_for_capacity_recovery'
    assert calls == ['event_relation', 'direct_definitions']
    assert result['metrics']['llm_calls'] == 2
    assert result['units'][:2] == interrupted['units'][:2]
    assert len(result['units']) == 4 and result['units'][2]['id'] != pending['id']
    assert result['status'] == 'partial' and service.run(interrupted['id']) == interrupted
