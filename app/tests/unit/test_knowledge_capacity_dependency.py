"""Fixture-only checks for changed-input dependency storage, not semantic quality."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from app.knowledge import autoschema, business_checkpoint, business_run, source_capacity_repair
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business_scope import block, scope_for


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    text = '기관은 본인이 신청한 경우 접수할 수 있다.'
    other_text = '다른기관은 본인이 신청한 경우 접수할 수 있다.'
    chunks = [autoschema.chunks([block('body', text)], 49152, 8192)[0],
              autoschema.chunks([dict(block('other', other_text), source_version_id='w')], 49152, 8192)[0]]
    alias = dict(source_reference_map=dict(b1=dict(block_id='body')))
    scope = scope_for(alias, text)
    scope['meanings'][0]['participants'] = [
        dict(field='Event', entity_index=None, evidence=[dict(block_id='b1', quote=text)]),
        dict(field='Entity', entity_index=0, evidence=[dict(block_id='b1', quote='기관')])]
    event = dict(Event=text, Entity=['기관'], Scope=scope)
    relation = dict(Head='기관', Relation='before', Tail='신청', Scope=scope_for(alias, text))
    other = dict(Head='다른기관', Relation='접수', Tail='신청',
                 Scope=scope_for(alias, other_text, head='다른기관'))
    control = dict(calls=[], upstream_empty=False, dependency_failure=False)
    class Client:
        def __init__(self, *_): pass
        async def generate(self, request, cancelled=None):
            control['calls'].append(request)
            failed = request.stage == 'event_entity' and other_text not in request.messages[-1]['content']
            if request.stage == 'capacity_repair_event_entity':
                parsed = [] if control['upstream_empty'] else [deepcopy(event)]
            elif request.stage == 'capacity_dependency_event_relation':
                parsed = [deepcopy(relation)]
                failed = control['dependency_failure']
            elif request.stage == 'entity_relation' and other_text in request.messages[-1]['content']:
                parsed = [deepcopy(other)]
            else:
                parsed = dict(definitions=[]) if request.stage == 'direct_definitions' else []
            return dict(request_id=request.request_id, parsed=None if failed else parsed,
                text=json.dumps(parsed), failure_kind='truncated' if failed else None,
                done_reason='length' if failed else 'stop', elapsed_s=.01)
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    service = KnowledgeService(tmp_path/'knowledge.db')
    run = dict(id=uuid4().hex, kind='business', status='running', chunks=chunks,
        blocks=[b for c in chunks for b in c['blocks']], sources={}, input_version_ids=['v','w'],
        claims=[], concepts=[], requirements=[], units=[], repairs=[],
        recipe=dict(version=autoschema.VERSION, generation=dict(provider='ollama'),
            models=dict(draft='draft', review='review'), options=dict(repair=False, conceptualize=False,
                context_tokens=49152, extraction_tokens=8192, review_tokens=8192, concept_tokens=512,
                think=False, timeout=1800, neighbor_mode='plain')),
        model_identity=dict(draft=dict(digest='mock'), review=dict(digest='mock')),
        metrics=dict(llm_calls=0, model_total_s=0))
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], json.dumps(run)))
    for chunk in chunks:
        for role in autoschema.ROLES:
            response = business_run.call(service, run, role, business_run.extraction_messages(run, chunk, role),
                autoschema.extraction_schema(role), reference_map=chunk['source_reference_map'])
            run['units'][-1]['source_chunk_id'] = chunk['id']
            if response is not None:
                business_run.store_extraction(run, chunk, role, response, run['units'][-1])
            business_run.save(service, run)
        business_run.json_call(service, run, 'direct_definitions', business_run.DEFINITION_INSTRUCTION,
            dict(blocks=autoschema.source_packet(chunk['blocks'])), business_run.Definitions)
        run['units'][-1]['source_chunk_id'] = chunk['id']
        business_run.save(service, run)
    run.update(status='partial', graph=autoschema.graph(run['claims'], run['blocks']))
    business_run.save(service, run)
    parent = service.run(run['id'])
    child = service.run(business_checkpoint.prepare(service, parent['id'])['run_id'])
    assert len(business_checkpoint.validate(service, child)) == 8
    child['status'] = 'running'; business_run.save(service, child)
    failed = next(u for u in child['units'] if u['status'] == 'failed')
    plan = [dict(failed_unit_id=failed['id'], origin_run_id=parent['id'], chunk_id=chunks[0]['id'],
                 role='event_entity', strategy='output_cap_only', output_tokens=16384, timeout=1800,
                 refresh_empty_event_relation=True)]
    control['calls'].clear()
    try:
        yield service, child, plan, control, parent
    finally:
        service.shutdown()


def test_changed_input_refreshes_once_without_rewriting_history_or_other_chunk(recovery):
    service, run, plan, control, parent = recovery
    originals = deepcopy(run['units'])
    other = deepcopy(run['claims'])
    source_capacity_repair.repair(service, run, plan)
    assert [r.stage for r in control['calls']] == ['capacity_repair_event_entity', 'capacity_dependency_event_relation']
    old = next(u for u in originals if u['stage'] == 'event_relation')
    new = run['units'][-1]
    assert new['messages'] != old['messages'] and new['schema'] == old['schema']
    assert new['reference_map'] == old['reference_map']
    assert new['request_configuration'] == old['request_configuration']
    assert new['executed_limits'] == old['executed_limits']
    assert new['dependency_refresh_origin']['unit_id'] == old['id']
    assert len(new['materialized_claim_ids']) == 1 and run['units'][:8] == originals
    assert all(c in run['claims'] for c in other) and service.run(parent['id']) == parent
    before = deepcopy(run)
    source_capacity_repair.repair(service, run, plan)
    assert run == before and len(control['calls']) == 2
    with pytest.raises(ValueError, match='새 실행'):
        business_checkpoint.validate(service, run)
    assert len(control['calls']) == 2  # Helper reentry is not whole-execute reentry.


def test_saved_dependency_response_materializes_without_another_generation(recovery, monkeypatch):
    service, run, plan, control, _ = recovery
    store = business_run.store_extraction
    def interrupted(service_run, chunk, role, response, unit):
        if unit['stage'] == 'capacity_dependency_event_relation':
            raise RuntimeError('fixture interruption before storage')
        return store(service_run, chunk, role, response, unit)
    monkeypatch.setattr(business_run, 'store_extraction', interrupted)
    with pytest.raises(RuntimeError):
        source_capacity_repair.repair(service, run, plan)
    run = service.run(run['id'])
    assert 'materialized_claim_ids' not in run['units'][-1]
    monkeypatch.setattr(business_run, 'store_extraction', store)
    source_capacity_repair.repair(service, run, plan)
    assert len(control['calls']) == 2 and len(run['units'][-1]['materialized_claim_ids']) == 1
    before = deepcopy(run)
    source_capacity_repair.repair(service, run, plan)
    assert run == before and len(control['calls']) == 2


@pytest.mark.parametrize('boundary', ['nonempty', 'existing_claim', 'split'])
def test_unsupported_replacement_boundaries_are_rejected_before_generation(recovery, boundary):
    service, run, plan, control, _ = recovery
    if boundary == 'nonempty':
        next(u for u in run['units'] if u['stage'] == 'event_relation')['response']['parsed'] = [dict(Head='old')]
    elif boundary == 'existing_claim':
        run['claims'].append(dict(id='old', role='event_relation', chunk_id=plan[0]['chunk_id']))
    else:
        plan[0]['groups'] = [dict(id='split')]
    with pytest.raises(ValueError, match='not_supported'):
        source_capacity_repair.repair(service, run, plan)
    assert control['calls'] == []


def test_unchanged_empty_upstream_does_not_generate_a_dependency(recovery):
    service, run, plan, control, _ = recovery
    control['upstream_empty'] = True
    source_capacity_repair.repair(service, run, plan)
    source_capacity_repair.repair(service, run, plan)
    assert [r.stage for r in control['calls']] == ['capacity_repair_event_entity']


@pytest.mark.parametrize('boundary', ['nonempty', 'split'])
def test_legacy_upstream_only_plans_keep_their_existing_scope(recovery, boundary):
    service, run, plan, control, _ = recovery
    plan[0].pop('refresh_empty_event_relation')
    original = next(u for u in run['units'] if u['stage'] == 'event_relation')
    if boundary == 'nonempty':
        original['response']['parsed'] = [dict(Head='old')]
    else:
        chunk = run['chunks'][0]
        refs = [dict(block_id=b['id'], span=b.get('span')) for b in chunk['blocks']]
        plan[0]['groups'] = [dict(id='split-view', included_views=refs, target_views=refs)]
    before = deepcopy(original)
    source_capacity_repair.repair(service, run, plan)
    assert [r.stage for r in control['calls']] == ['capacity_repair_event_entity']
    assert original == before and run['units'][-1]['materialized_claim_ids']
    assert not any(u.get('dependency_refresh_origin') for u in run['units'])


def test_failed_dependency_is_preserved_without_an_unchanged_retry(recovery):
    service, run, plan, control, _ = recovery
    control['dependency_failure'] = True
    source_capacity_repair.repair(service, run, plan)
    failed = deepcopy(run['units'][-1])
    assert failed['status'] == 'failed' and failed['materialized_claim_ids'] == []
    source_capacity_repair.repair(service, run, plan)
    assert run['units'][-1] == failed and len(control['calls']) == 2
