"""Portable regression checks for bounded repair storage and explicit source context."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from app.knowledge import autoschema, business_concepts, business_run, source_capacity_repair
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business_scope import block, scope_for


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    chunk = autoschema.chunks([block('body', '기관은 본인이 신청한 경우 접수할 수 있다.')], 49152, 8192)[0]
    parsed = [dict(Head='기관', Relation='접수', Tail='신청', Scope=scope_for(chunk, chunk['blocks'][0]['text']))]
    control = dict(kind='truncated', calls=[])
    service = KnowledgeService(tmp_path / 'knowledge.db')
    run = dict(id=uuid4().hex, status='running', kind='business', chunks=[chunk], claims=[], units=[],
        recipe=dict(concept_work_contract='exact-original-concept-work-v1',version=autoschema.VERSION, generation=dict(provider='ollama'), models=dict(draft='draft', review='review'),
                    options=dict(context_tokens=49152, extraction_tokens=8192, review_tokens=4096, concept_tokens=512, think=False, timeout=1800, neighbor_mode='plain')),
        model_identity=dict(draft=dict(digest='a'*64), review=dict(digest='a'*64)), metrics=dict(llm_calls=0, model_total_s=0))
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], json.dumps(run)))
    class Client:
        def __init__(self, *_): pass
        def execution_identity(self,model,temperature,**limits):
            return dict(engine='ollama',engine_version='fixture-only',model_digest='a'*64,
                precision=dict(weights='fixture'),sampling=dict(contract='ollama-request-and-model-defaults-v1',
                    request_options=dict(temperature=temperature,num_predict=limits['max_tokens'],num_ctx=limits['context_tokens']),
                    think=limits['think'],model_parameters='fixture defaults',model_configuration_sha256='b'*64))
        async def generate(self, request, cancelled=None):
            control['calls'].append(request)
            if request.stage.startswith('capacity_repair_'):
                with service.repository.connect() as db:
                    unit = service.repository.get(db, 'runs', run['id'])['units'][-1]
                assert unit['source_chunk_id'] == chunk['id'] and unit['repair_view_id'] in run['capacity_repair_views']
                assert unit['capacity_repair_origin']['unit_id'] == original['id']
            if control['kind'] == 'pending': raise RuntimeError('fixture interruption')
            failed = control['kind'] != 'success'
            return dict(request_id=request.request_id, parsed=None if failed else deepcopy(parsed),
                        text=json.dumps(['접수']) if request.stage.startswith('concept_') else json.dumps(parsed),
                        failure_kind=control['kind'] if failed else None,
                        done=not failed, done_reason='length' if failed else 'stop', elapsed_s=0)
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    business_run.call(service, run, 'entity_relation', business_run.extraction_messages(run, chunk, 'entity_relation'),
                      autoschema.extraction_schema('entity_relation'), reference_map=chunk['source_reference_map'])
    original = run['units'][0]
    original['source_chunk_id'] = chunk['id']
    business_run.save(service, run)
    run['metrics'] = dict(llm_calls=0, model_total_s=0)
    control['calls'].clear(); control['kind'] = 'success'
    plan = [dict(failed_unit_id=original['id'], origin_run_id='fixture-source', chunk_id=chunk['id'], role='entity_relation',
                 strategy='same_input', output_tokens=16384, timeout=1800)]
    try:
        yield service, run, plan, control, deepcopy(original)
    finally:
        service.shutdown()


def reload_run(service, run):
    with service.repository.connect() as db:
        return service.repository.get(db, 'runs', run['id'])


def test_completed_repair_is_not_generated_or_materialized_twice(recovery):
    service, run, plan, control, original = recovery
    source_capacity_repair.repair(service, run, plan)
    before = deepcopy(run)
    source_capacity_repair.repair(service, run, plan)
    assert run == before and len(control['calls']) == 1 and len(run['claims']) == 1
    assert run['units'][0] == original
    with pytest.raises(AssertionError):
        run['claims'].clear()
        source_capacity_repair.repair(service, run, plan)
    assert len(control['calls']) == 1


def test_saved_response_materializes_once_after_storage_interruption(recovery, monkeypatch):
    service, run, plan, control, _ = recovery
    real_store = business_run.store_extraction
    monkeypatch.setattr(business_run, 'store_extraction', lambda *a: (_ for _ in ()).throw(RuntimeError('fixture before storage')))
    with pytest.raises(RuntimeError): source_capacity_repair.repair(service, run, plan)
    run = reload_run(service, run)
    assert not run['claims'] and 'materialized_claim_ids' not in run['units'][-1]
    monkeypatch.setattr(business_run, 'store_extraction', real_store)
    source_capacity_repair.repair(service, run, plan)
    source_capacity_repair.repair(service, run, plan)
    assert len(control['calls']) == 1 and len(run['units']) == 2 and len(run['claims']) == 1


def test_split_view_is_resolved_by_graph_and_concept_source_lookup(recovery):
    service, run, plan, _, _ = recovery
    chunk = run['chunks'][0]
    refs = [dict(block_id=b['id'], span=b.get('span')) for b in chunk['blocks']]
    plan[0]['groups'] = [dict(id='split-view', included_views=refs, target_views=refs)]
    source_capacity_repair.repair(service, run, plan)
    assert run['claims'][0]['chunk_id'] == 'split-view'
    run['graph'] = autoschema.graph(run['claims'])
    assert run['graph']['edges'] and 'split-view' in business_run.source_chunks(run)
    planned = business_concepts.prepare(run, autoschema.concept_targets(run['graph']), 'plain')
    assert planned and all('split-view' in p['selection']['mandatory_chunk_ids'] for p in planned)


def test_all_concept_kinds_continue_from_stored_claims_with_exact_input_reuse(recovery):
    service, run, plan, control, _ = recovery
    source_capacity_repair.repair(service, run, plan)
    chunk = run['chunks'][0]; text = chunk['blocks'][0]['text']; scope = scope_for(chunk, text)
    meaning = scope['meanings'][0]
    meaning['participants'] = [dict(field='Event', entity_index=None, evidence=scope['evidence']),
        dict(field='Entity', entity_index=0, evidence=[dict(block_id='b1', quote='기관')]),
        dict(field='Entity', entity_index=1, evidence=[dict(block_id='b1', quote='신청')])]
    run['claims'].append(autoschema.graph_record(chunk, 'event_entity', dict(Event=text, Entity=['기관', '신청']), 0, scope=scope))
    run['graph'] = autoschema.graph(run['claims']); run['concepts'] = []
    targets = autoschema.concept_targets(run['graph']); ids = {c['id'] for c in run['claims']}
    control['calls'].clear()
    business_concepts.refresh_changed(service, run, ids)
    assert {c['target']['kind'] for c in run['concepts']} == {'entity', 'event', 'relation'}
    assert len(run['concepts']) == len(targets) and all(r.stage.startswith('concept_') for r in control['calls'])
    concept_units = deepcopy([u for u in run['units'] if u['stage'].startswith('concept_')])
    business_concepts.refresh_changed(service, run, ids)
    assert len(control['calls']) == len(targets)
    child = deepcopy(run); child.update(id=uuid4().hex, parent_run_id=run['id'], units=[], concepts=[],
        parent_recipe=deepcopy(run['recipe']), parent_model_identity=deepcopy(run['model_identity']),
        reusable_units=concept_units, source_checkpoint=dict(fixture_only=True), metrics=dict(llm_calls=0, model_total_s=0))
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (child['id'], json.dumps(child)))
    control['calls'].clear()
    business_concepts.refresh_changed(service, child, ids)
    assert control['calls'] == [] and child['metrics']['llm_calls'] == 0
    assert child['metrics']['reused_responses'] == len(targets)
    old = concept_units[0]; changed = deepcopy(old['messages']); changed[-1]['content'] += '\n변경된 입력'
    business_run.call(service, child, old['stage'], changed, max_tokens=512)
    assert len(control['calls']) == 1


@pytest.mark.parametrize('interruption', ['pending', 'cancelled'])
def test_unfinished_request_gets_new_record_and_preserves_previous(recovery, interruption):
    service, run, plan, control, original = recovery
    control['kind'] = interruption
    if interruption == 'pending':
        with pytest.raises(RuntimeError): source_capacity_repair.repair(service, run, plan)
    else:
        source_capacity_repair.repair(service, run, plan)
    run = reload_run(service, run); unfinished = deepcopy(run['units'][-1])
    control['kind'] = 'success'
    source_capacity_repair.repair(service, run, plan)
    source_capacity_repair.repair(service, run, plan)
    assert len(control['calls']) == 2 and len(run['units']) == 3 and len(run['claims']) == 1
    assert run['units'][0] == original and run['units'][1] == unfinished


def test_same_failed_settings_are_not_repeated_and_changed_settings_are_separate(recovery):
    service, run, plan, control, _ = recovery
    control['kind'] = 'truncated'
    source_capacity_repair.repair(service, run, plan); failed = deepcopy(run['units'][-1])
    source_capacity_repair.repair(service, run, plan)
    assert len(control['calls']) == 1 and not run['claims']
    changed = deepcopy(plan); changed[0].update(output_tokens=24576, timeout=2400); control['kind'] = 'success'
    source_capacity_repair.repair(service, run, changed)
    assert len(control['calls']) == 2 and run['units'][1] == failed and len(run['claims']) == 1
    assert control['calls'][-1].max_tokens == 24576 and control['calls'][-1].timeout == 2400


def test_preflight_is_recorded_once_without_model_invocation(recovery):
    service, run, plan, control, _ = recovery
    plan[0]['output_tokens'] = 50000
    source_capacity_repair.repair(service, run, plan); source_capacity_repair.repair(service, run, plan)
    assert not control['calls'] and len(run['units']) == 2 and run['units'][-1]['error'] == 'input_capacity'


def test_explicit_context_keeps_common_and_owned_sources_without_global_loss():
    blocks = [dict(block('header', '표 제목'), context_only=True),
              dict(block('context1', '첫 행 문맥', row=1), context_only=True),
              dict(block('one', '첫 행 대상', row=1), context_only=False),
              dict(block('two', '둘째 행 대상', row=2), context_only=False),
              dict(block('context2', '둘째 행 문맥', row=2), context_only=True)]
    chunk = dict(id='table', blocks=blocks, source_version_id='v')
    refs = lambda ids: [dict(block_id=i, span=None) for i in ids]
    groups = [dict(id='one-view', included_views=refs(['header', 'context1', 'one']), target_views=refs(['one'])),
              dict(id='two-view', included_views=refs(['header', 'two', 'context2']), target_views=refs(['two']))]
    result = source_capacity_repair.views(chunk, groups, refs(['header']))
    assert [{b['id'] for b in v['blocks']} for v in result] == [{'header', 'context1', 'one'}, {'header', 'two', 'context2'}]
    assert [b for v in result for b in v['blocks'] if not b['context_only']] == blocks[2:4]
    bad = deepcopy(groups); bad[0]['included_views'] = refs(['context1', 'one'])
    with pytest.raises(AssertionError): source_capacity_repair.views(chunk, bad, refs(['header']))
    bad = deepcopy(groups); bad[1]['included_views'] = refs(['header', 'two'])
    with pytest.raises(AssertionError): source_capacity_repair.views(chunk, bad, refs(['header']))
    with pytest.raises(AssertionError): source_capacity_repair.views(chunk, groups)
