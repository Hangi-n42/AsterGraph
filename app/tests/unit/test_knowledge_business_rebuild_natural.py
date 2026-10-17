"""Native models are replaced by deterministic fixtures; product storage/execute remain real."""
from copy import deepcopy
import json

import pytest

from app.knowledge import autoschema, business_run, business_rebuild, business_rebuild_html, business_concepts
from app.knowledge.business_models import BusinessRunRequest, SourceRebuildPlanRequest
from app.knowledge.schemas import SourceRegistration, RunRequest
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business import finish


@pytest.fixture
def natural(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path/'knowledge.db')
    calls, controls = [], dict(bad_definition=False)
    class Stub:
        def __init__(self, *a, **k): pass
        def identities(self, models, required_context):
            return {r: dict(name=m, digest='a'*64, context_length=49152) for r, m in models.items()}
        def execution_identity(self, model, temperature, **limits):
            return dict(engine='ollama', engine_version='fixture', model_digest='a'*64,
                precision=dict(weights='fixture'), sampling=dict(contract='ollama-request-and-model-defaults-v1',
                    request_options=dict(temperature=temperature, num_predict=limits['max_tokens'], num_ctx=limits['context_tokens']),
                    think=limits['think'], model_parameters='fixture', model_configuration_sha256='b'*64))
        async def generate(self, request, cancelled=None):
            calls.append(request.stage)
            output = []
            text = request.messages[-1]['content']
            if request.stage == 'entity_relation':
                start = text.index('[{"id":"b1"')
                blocks, _ = json.JSONDecoder().raw_decode(text[start:])
                target = next(b for b in blocks if not b.get('context_only'))
                quote = target['text']; ref = [dict(block_id=target['id'], quote=quote)]
                head, tail = ('기관', '신청') if '신청' in quote else ('관청', '허가')
                absent = dict(state='absent', text=None)
                scope = dict(evidence=ref, meanings=[dict(statement_type='rule', relation_kind='authority',
                    subject=head, action='처리', object=tail, applies_to='발췌', modality='permission',
                    **{k:deepcopy(absent) for k in ('conditions', 'exceptions', 'time', 'local_negation', 'references')},
                    premises=dict(state='absent', meaning_indices=[]), evidence=ref, participants=[
                        dict(field=field, entity_index=None, evidence=[dict(block_id=target['id'], quote=value)])
                        for field, value in [('Head', head), ('Tail', tail)]])])
                output = [dict(Head=head, Relation='처리', Tail=tail, Scope=scope)]
            elif request.stage == 'direct_definitions':
                output = dict(definitions=[])
                blocks = json.loads(text)['blocks']
                target = next(b for b in blocks if not b.get('context_only'))
                if '신청' in target['text']:
                    output['definitions'] = [dict(term='기관', definition='정의 검사',
                        evidence=[dict(block_id=target['id'], quote=target['text'])])]
                if controls['bad_definition']:
                    controls['bad_definition'] = False
                    blocks = json.loads(text)['blocks']
                    target = next(b for b in blocks if not b.get('context_only'))
                    output['definitions'] = [dict(term='기관', definition='정의 검사', evidence=[dict(block_id=target['id'], quote=q)])
                                             for q in (target['text'], '원문에 없는 정의 인용')]
            return dict(parsed=output, text='검사 유형' if request.stage.startswith('concept_') else json.dumps(output),
                failure_kind=None, done=True, done_reason='stop', elapsed_s=0, prompt_eval_count=1, eval_count=1)
    monkeypatch.setattr(business_run, 'ModelClient', Stub)
    def register(body):
        version = service.register('controlled.html', ('<html><body><main id="root">'+body+'</main></body></html>').encode(),
            SourceRegistration(title='CONTROLLED 검증 자료', publisher='검사', namespace='test', external_id='same',
                               selected_scope=dict(selector='#root')))['source_version_id']
        assert finish(service, service.start(RunRequest(source_version_ids=[version]))['run_id'])['status'] == 'succeeded'
        return version
    before = register('<h2>공통 상위 조건</h2><section id="one"><p>기관은 신청을 처리한다.</p></section>'
                      '<section id="two"><ul><li><p>관청은 허가를 처리한다.</p></li></ul></section>')
    after = register('<h2>공통 상위 조건</h2><section id="one"><p>기관은 신청을 처리한다.</p></section>'
                     '<section id="two"><ul><li><p>관청은 허가를 처리한다.</p><p>단, 새 예외가 적용된다.</p></li></ul></section>')
    options = dict(source_unit_policy=business_rebuild_html.POLICY, repair=False, model='fixture', review_model='fixture')
    parent = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[before], **options))['run_id'])
    assert parent['status'] == 'succeeded', parent.get('error')
    with service.repository.connect() as db:
        parent = service.repository.get(db, 'runs', parent['id'])
    try:
        yield service, register, before, after, parent, options, calls, controls
    finally:
        service.shutdown()


def build_plan(env, after=None):
    service, _, before, version, parent, *_ = env
    return business_rebuild.plan(service, SourceRebuildPlanRequest(parent_run_id=parent['id'],
        before_version_id=before, after_version_id=after or version))


def test_new_child_exception_rebuilds_parent_unit_and_rebinds_unchanged_unit_with_separate_concept_proof(natural):
    service, _, before, after, parent, options, calls, _ = natural
    original = deepcopy(parent)
    plan = build_plan(natural)
    assert {u['unit_key']:u['action'] for u in plan['source_units']} == {'one':'rebind_source', 'two':'rebuild_source'}
    calls.clear()
    result = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[after],
        source_rebuild_plan_id=plan['id'], **options))['run_id'])
    assert result['status'] == 'succeeded', result.get('error')
    assert calls.count('entity_relation') == calls.count('direct_definitions') == 1
    assert len(result['source_rebuild']['source_claim_bindings']) == 2
    assert len(result['source_concept_bindings']) == 3
    assert sum(stage.startswith('concept_') for stage in calls) == 3
    assert len(result['claims']) == 3 and len({c['id'] for c in result['claims']}) == 3
    definition = next(c for c in result['claims'] if c['role'] == 'direct_definition')
    assert business_run.exact_evidence(definition['evidence'], result['blocks']) == definition['evidence']
    assert all(c['source_version_ids'] == [after] and c['review_status'] == 'unreviewed' for c in result['claims'])
    old_control = next(c for c in parent['claims'] if c['role'] == 'entity_relation' and c['raw']['Head'] == '기관')
    new_control = next(c for c in result['claims'] if c['role'] == 'entity_relation' and c['raw']['Head'] == '기관')
    assert new_control['interpretation']['raw'] == old_control['interpretation']['raw']
    assert all(e['source_version_id'] == after for e in new_control['interpretation']['evidence'])
    assert all(c['source_result_binding']['approval_inherited'] is False for c in result['concepts'] if c.get('source_result_binding'))
    assert all(not u.get('reused_from') for u in result['units'])
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', parent['id']) == original
    from app.knowledge.business_rebuild_concepts import bind_unchanged
    planned = business_concepts.prepare(result, autoschema.concept_targets(result['graph']), 'plain', service=service)
    assert len(bind_unchanged(service, result, planned)) == 3
    assert len(result['source_concept_bindings']) == 3
    with service.repository.connect() as db:
        event = business_rebuild.snapshot_invalidations(db, dict(id='old', source_versions={before:{}}, claims=parent['claims']))
    assert event[0]['reason'] == 'new_source_change_not_applied_to_this_snapshot'
    assert len(event[0]['claim_ids']) == 1


def test_new_global_note_reprocesses_all_units_even_without_old_evidence_link(natural):
    service, register, _, _, _, _, _, _ = natural
    changed = register('<h2>공통 상위 조건</h2><section id="one"><p>기관은 신청을 처리한다.</p></section>'
        '<section id="two"><ul><li><p>관청은 허가를 처리한다.</p></li></ul></section><p>귀속이 불명확한 새 예외</p>')
    plan = build_plan(natural, changed)
    assert [u['action'] for u in plan['source_units']] == ['rebuild_source', 'rebuild_source']


def test_explicit_scope_error_is_unresolved_and_unchanged_failed_input_is_not_regenerated(natural):
    service, _, _, after, parent, options, calls, _ = natural
    claim = next(c for c in parent['claims'] if c['role'] == 'entity_relation' and c['raw']['Head'] == '기관')
    chunk = next(c for c in parent['chunks'] if c['id'] == claim['chunk_id'])
    unit = next(u for u in parent['units'] if u.get('source_chunk_id') == chunk['id'] and u['stage'] == 'entity_relation')
    row = unit['response']['parsed'][0]
    row['Scope']['meanings'][0]['premises'] = dict(state='present', meaning_indices=[])
    unit['response']['text'] = json.dumps(unit['response']['parsed'], ensure_ascii=False)
    bad = autoschema.graph_record(chunk, 'entity_relation', claim['raw'], 0, scope=row['Scope'], scope_required=True)
    assert bad['interpretation']['errors'] == ['invalid premise state'] and not bad.get('extraction_error')
    parent['claims'] = [bad if c['id'] == claim['id'] else c for c in parent['claims']]
    parent['graph'] = autoschema.graph(parent['claims'])
    with service.repository.connect() as db:
        service.repository.save(db, 'runs', parent)
    plan = build_plan(natural)
    unit_plan = next(u for u in plan['source_units'] if u['unit_key'] == 'one')
    assert unit_plan['action'] == 'unresolved_source' and unit_plan['prior_input_errors'][0]['scope_errors']
    calls.clear()
    result = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[after],
        source_rebuild_plan_id=plan['id'], **dict(options, conceptualize=False)))['run_id'])
    assert result['status'] == 'partial' and result['extraction_complete'] is False
    assert calls == [*autoschema.ROLES, 'direct_definitions']
    assert result['source_rebuild']['unresolved_source_units'] == [unit_plan]
    assert not result['source_rebuild']['source_claim_bindings']
    assert not any(c['raw'].get('Head') == '기관' for c in result['claims'])
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', parent['id']) == parent


def test_new_unlinked_source_requirement_is_discovered_as_pending_in_public_old_snapshot_query(natural):
    from app.knowledge import business_store, business_use
    from app.knowledge.business_models import RequirementInput, BusinessQuery
    from app.knowledge.service import encode, KnowledgeConflict
    service, _, before, _, parent, _, calls, _ = natural
    source_id = parent['sources'][before]['source_id']
    requirements = []
    for identifier, source_ids in [('unlinked-same-source', [source_id]), ('unspecified-scope', [])]:
        requirements.append(business_store.put_requirement(service, RequirementInput(id=identifier,
            question_ids=[identifier], question='제공 원문의 적용 범위를 확인한다.', target='제공 원문',
            situation='원문 갱신', period='제공 버전', criterion='원문에 근거한 적용 범위만 설명한다.', source_ids=source_ids)))
    plan = build_plan(natural)
    assert plan['request']['requirement_ids'] == []
    discovery = plan['requirement_discovery']
    assert set(discovery['candidate_ids']) == {r['id'] for r in requirements}
    assert set(discovery['unselected_review_ids']) == set(discovery['candidate_ids'])
    assert discovery['direct_dependency_ids'] == [] and not discovery['automatic_meaning_impact']
    assert all(d['status'] == 'unassessed' for d in discovery['stored_dependencies'])
    snapshot = dict(id='old-reviewed-view', kind='source_graph', run_id=parent['id'], source_versions=parent['sources'],
        blocks=parent['blocks'], claims=deepcopy(parent['claims']), concepts=parent['concepts'], requirements=requirements,
        assessments={})
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)', (snapshot['id'], encode(snapshot)))
    count = len(calls)
    result = business_use.query(service, BusinessQuery(question=requirements[0]['question'],
        snapshot_id=snapshot['id'], requirement_ids=[requirements[0]['id']]))
    assert result['status'] == 'needs_review' and result['answer'] is None and len(calls) == count
    assert result['invalidations'][0]['reason'] == 'new_source_change_not_applied_to_this_snapshot'
    with service.repository.connect() as db:
        assert service.repository.get(db, 'snapshots', snapshot['id']) == snapshot
        changed = service.repository.get(db, 'requirements', requirements[0]['id'])
        changed['revision'] += 1
        service.repository.save(db, 'requirements', changed)
        with pytest.raises(KnowledgeConflict, match='요구'):
            business_rebuild.validate(service, db, plan)


@pytest.mark.parametrize('difference', ['neighbor_mode', 'concept_tokens'])
def test_concept_input_policy_change_creates_new_work_instead_of_source_rebinding(natural, difference):
    service, _, _, after, _, options, calls, _ = natural
    plan = build_plan(natural)
    updated = dict(options, **{difference:'structured' if difference == 'neighbor_mode' else 1024})
    calls.clear()
    result = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[after],
        source_rebuild_plan_id=plan['id'], **updated))['run_id'])
    assert result['status'] == 'succeeded', result.get('error')
    assert result.get('source_concept_bindings', []) == []
    assert sum(stage.startswith('concept_') for stage in calls) == 6


@pytest.mark.parametrize('changed_policy', [False, True])
def test_json_update_reuses_exact_completed_concept_work_of_unchanged_html_source(natural, changed_policy):
    from app.knowledge.service import encode
    service, _, html, _, parent, options, calls, _ = natural
    versions = [service.register('rows.json', json.dumps([dict(id=1, value=value)]).encode(),
        SourceRegistration(title='JSON 행', publisher='검사', namespace='rows', external_id='same'))['source_version_id']
        for value in (10, 11)]
    assert finish(service, service.start(RunRequest(source_version_ids=versions))['run_id'])['status'] == 'succeeded'
    with service.repository.connect() as db:
        version = service.repository.get(db, 'versions', versions[0])
        blocks = service.parse_blocks(db, version['latest_parse_run_id'], version['id'])
        for block in blocks:
            block['source_id'] = version['source_id']
        chunks = autoschema.chunks(blocks, 49152, 4096, 1000)
        parent['input_version_ids'].append(versions[0])
        parent['sources'][versions[0]] = dict(source_id=version['source_id'], title='JSON 행',
            filename=version['filename'], sha256=version['sha256'], dates=version['dates'])
        parent['blocks'].extend(blocks); parent['chunks'].extend(chunks)
        parent['claims'].extend(business_run.direct_tabular_row(c, b, n) for c in chunks for n, b in enumerate(c['blocks']))
        parent['graph'] = autoschema.graph(parent['claims'])
        service.repository.save(db, 'runs', parent)
    plan = business_rebuild.plan(service, SourceRebuildPlanRequest(parent_run_id=parent['id'],
        before_version_id=versions[0], after_version_id=versions[1], key_fields=['id']))
    calls.clear()
    settings = dict(options, source_unit_policy='whole', neighbor_mode='structured' if changed_policy else 'plain')
    result = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[html, versions[1]],
        source_rebuild_plan_id=plan['id'], **settings))['run_id'])
    assert result['status'] == 'succeeded', result.get('error')
    assert len(result['concepts']) == 6
    assert sum(stage.startswith('concept_') for stage in calls) == (6 if changed_policy else 0)
    if not changed_policy:
        assert result['metrics']['reused_responses'] == 6
        assert all(u['reused_from']['run_id'] == parent['id'] for u in result['units'] if u['stage'].startswith('concept_'))
        assert {c['work_id'] for c in result['concepts']} == {c['work_id'] for c in parent['concepts']}
    assert not result.get('source_concept_bindings')


@pytest.mark.parametrize('remove', [False, True])
def test_unique_section_movement_and_deletion_keep_new_addresses_without_old_concept_targets(natural, remove):
    service, register, before, _, parent, options, calls, _ = natural
    second = '' if remove else '<section id="two"><ul><li><p>관청은 허가를 처리한다.</p></li></ul></section>'
    after = register('<h2>공통 상위 조건</h2>'+second+'<section id="one"><p>기관은 신청을 처리한다.</p></section>')
    plan = build_plan(natural, after)
    assert [u['action'] for u in plan['source_units']] == ['rebind_source', 'remove_source' if remove else 'rebind_source']
    calls.clear()
    result = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[after],
        source_rebuild_plan_id=plan['id'], **options))['run_id'])
    assert result['status'] == 'succeeded', result.get('error')
    assert calls == []
    assert len(result['claims']) == (2 if remove else 3)
    assert len(result['source_concept_bindings']) == (3 if remove else 6)
    assert all(c['source_version_ids'] == [after] for c in result['claims'])
    current = {t['id'] for t in autoschema.concept_targets(result['graph'])}
    assert {c['target']['id'] for c in result['concepts']} == current
    assert not current.intersection(c['target']['id'] for c in parent['concepts'])
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', parent['id']) == parent
        assert business_rebuild.snapshot_invalidations(db, dict(id='after', source_versions={after:{}}, claims=result['claims'])) == []


def test_definition_failure_is_atomic_and_actual_execute_resume_only_retries_failed_stage(natural):
    service, _, _, after, _, options, calls, controls = natural
    plan = build_plan(natural)
    controls['bad_definition'] = True
    request = BusinessRunRequest(source_version_ids=[after], source_rebuild_plan_id=plan['id'], **options)
    failed = finish(service, service.start_business(request)['run_id'])
    assert failed['status'] == 'failed' and len([c for c in failed['claims'] if c['role'] == 'direct_definition']) == 1
    assert failed['units'][-1]['stage'] == 'direct_definitions' and failed['units'][-1]['status'] == 'failed'
    calls.clear()
    resumed = finish(service, service.start_business(request.model_copy(update={'resume_run_id':failed['id']}))['run_id'])
    assert resumed['status'] == 'succeeded', resumed.get('error')
    assert all(stage not in autoschema.ROLES for stage in calls)
    assert calls.count('direct_definitions') == 1
    assert len(resumed['claims']) == len({c['id'] for c in resumed['claims']}) == 3
    assert resumed['source_rebuild']['prior_failures'][0]['unit_ids'] == [failed['units'][-1]['id']]


def test_actual_cancel_after_saved_success_resumes_only_unfinished_extraction(natural, monkeypatch):
    service, _, _, after, _, options, calls, _ = natural
    plan = build_plan(natural)
    save = business_run.save
    stopped = []
    def cancel_after_first_checkpoint(service, run):
        save(service, run)
        completed = run.get('source_rebuild', {}).get('completed_extraction', [])
        if not stopped and any(c['stage'] == 'entity_relation' for c in completed):
            stopped.append(run['id'])
            assert service.cancel(run['id'])['status'] == 'cancel_requested'
    monkeypatch.setattr(business_run, 'save', cancel_after_first_checkpoint)
    request = BusinessRunRequest(source_version_ids=[after], source_rebuild_plan_id=plan['id'],
        **dict(options, conceptualize=False))
    calls.clear()
    cancelled = finish(service, service.start_business(request)['run_id'])
    assert cancelled['status'] == 'cancelled' and stopped == [cancelled['id']]
    assert calls == ['entity_relation']
    assert len(cancelled['source_rebuild']['completed_extraction']) == 1
    first = next(u for u in cancelled['units'] if u['stage'] == 'entity_relation')
    calls.clear()
    resumed = finish(service, service.start_business(request.model_copy(update={'resume_run_id':cancelled['id']}))['run_id'])
    assert resumed['status'] == 'succeeded', resumed.get('error')
    assert calls == ['event_entity', 'event_relation', 'direct_definitions']
    assert [u for u in resumed['units'] if u['stage'] == 'entity_relation'] == [first]
    assert len(resumed['claims']) == len({c['id'] for c in resumed['claims']}) == 3
    assert len(resumed['source_rebuild']['completed_extraction']) == 4
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', cancelled['id'])['status'] == 'cancelled'
