"""Source-role and wire-contract checks. No model semantics are inferred from fixtures."""
from copy import deepcopy
import json

import jsonschema
import pytest

from app.knowledge import autoschema, business_run
from app.knowledge.business_models import BusinessRunRequest
from app.tests.unit.test_knowledge_business_rebuild_natural import natural
from app.tests.unit.test_knowledge_business_rebuild import environment, no_models, run_request


def source(modality='description'):
    if modality == 'description':
        head, tail, text, heading = '세금을 체납중인 기업', '융자제한기업', '① 세금을 체납중인 기업', '바. 융자제한기업'
    else:
        head, tail, heading = '검사 기관', '신청', '검사용 접수 안내'
        text = '검사 기관은 신청을 접수해야 한다.' if modality == 'obligation' else '검사 기관은 신청을 접수할 수 있다.'
    blocks = [dict(id='notice', text='CONTROLLED 코드 검사 자료', context_only=True),
              dict(id='heading', text=heading, context_only=True),
              dict(id='body', text=text, context_only=False),
              dict(id='reference', text='항목별 적용예외는 사업별 융자계획에서 규정', context_only=True)]
    for block in blocks:
        block.update(source_version_id='fixture-v', parse_run_id='fixture-p', locator={})
    chunk = dict(id='fixture-chunk', source_version_id='fixture-v', blocks=blocks,
                 text=autoschema.source_text(blocks),
                 source_reference_map={'b'+str(i+1):dict(block_id=b['id'], span=b.get('span')) for i,b in enumerate(blocks)})
    evidence = [dict(block_id='b3', quote=text)]
    absent = dict(state='absent', text=None)
    scope = dict(evidence=evidence, meanings=[dict(statement_type='instance', relation_kind='other',
        subject=head, action='포함' if modality == 'description' else '접수', object=tail, applies_to='검사 자료', modality=modality,
        **{k:deepcopy(absent) for k in ('conditions', 'exceptions', 'time', 'local_negation', 'references')},
        premises=dict(state='absent', meaning_indices=[]), evidence=evidence, participants=[
            dict(field='Head', entity_index=None, evidence=[dict(block_id='b3', quote=head)]),
            dict(field='Tail', entity_index=None, evidence=[dict(block_id='b2' if modality == 'description' else 'b3', quote=tail)])])])
    return chunk, dict(Head=head, Relation='목록 포함' if modality == 'description' else '접수', Tail=tail), scope


def run(new=True):
    return dict(recipe=dict(version=autoschema.TARGET_CONTEXT_VERSION if new else autoschema.VERSION,
        scope_contract=autoschema.DESCRIPTIVE_SCOPE_CONTRACT if new else autoschema.SCOPE_CONTRACT), claims=[])


def test_target_context_input_preserves_every_packet_alias_and_source_order():
    chunk, _, _ = source()
    original = deepcopy(chunk)
    new = business_run.extraction_request(run(), chunk, 'entity_relation')
    text = new['messages'][-1]['content']
    start = text.index('{"source_order":')
    payload = json.loads(text[start:])
    assert [p['id'] for p in payload['extraction_targets']] == ['b3']
    assert [p['id'] for p in payload['supporting_context']] == ['b1', 'b2', 'b4']
    packets = {p['id']:p for p in [*payload['extraction_targets'], *payload['supporting_context']]}
    assert [packets[i] for i in payload['source_order']] == json.loads(chunk['text'])
    assert new['reference_map'] == chunk['source_reference_map'] and chunk == original
    old = business_run.extraction_request(run(False), chunk, 'entity_relation')
    assert old['messages'] == autoschema.extraction_messages(chunk['text'], 'entity_relation')
    assert old['schema'] == autoschema.extraction_schema('entity_relation')
    assert new['messages'] != old['messages'] and new['schema'] != old['schema']


@pytest.mark.parametrize('role', autoschema.ROLES)
def test_actual_template_passage_contains_only_source_json(role):
    chunk, raw, scope = source()
    current = run()
    candidate = dict(raw=raw, Scope=scope)
    if role == 'event_relation':
        current['claims'] = [dict(chunk_id=chunk['id'], role='event_entity', raw=raw, interpretation=dict(raw=scope))]
    messages = business_run.extraction_request(current, chunk, role)['messages']
    system, stage = messages[0]['content'], messages[1]['content']
    _, passage = stage.rsplit('Here is the passage:', 1)
    payload = json.loads(passage)
    assert stage == autoschema.TRIPLE_INSTRUCTIONS['en'][role] + '\n' + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    assert '위 추출 지시의 작업 범위는 extraction_targets다.' in system
    assert '위 추출 지시의 작업 범위는 extraction_targets다.' not in passage
    assert [p['id'] for p in payload['extraction_targets']] == ['b3']
    assert all(p['text'] in chunk['text'] for p in [*payload['extraction_targets'], *payload['supporting_context']])
    if role == 'event_relation':
        assert payload['unverified_propositions'] == [candidate]
        legacy = business_run.extraction_request(dict(current, recipe=run(False)['recipe']), chunk, role)['messages']
        assert legacy[1]['content'] == autoschema.TRIPLE_INSTRUCTIONS['en'][role] + '\n' + chunk['text'] + '\n같은 원문의 미승인 명제:\n' + json.dumps([candidate], ensure_ascii=False, separators=(',', ':'))
        assert 'unverified_propositions는' not in legacy[0]['content']


@pytest.mark.parametrize('state,indices,valid', [
    ('present', [], False), ('present', [1], True), ('present', [-1], False), ('present', [1, 1], False),
    ('absent', [], True), ('absent', [1], False), ('unresolved', [], True), ('unavailable', [], True),
])
def test_new_wire_premise_constraints_do_not_rewrite_legacy_raw(state, indices, valid):
    chunk, raw, scope = source('permission')
    scope['meanings'][0]['premises'] = dict(state=state, meaning_indices=indices)
    saved = deepcopy(scope)
    schema = business_run.extraction_request(run(), chunk, 'entity_relation')['schema']
    if valid:
        jsonschema.validate([dict(raw, Scope=scope)], schema)
    else:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate([dict(raw, Scope=scope)], schema)
    if state == 'present' and not indices:
        jsonschema.validate([dict(raw, Scope=scope)], autoschema.extraction_schema('entity_relation'))
        old = autoschema.graph_record(chunk, 'entity_relation', raw, 0, scope=scope)
        assert 'invalid premise state' in old['interpretation']['errors']
        assert old['interpretation']['raw'] == saved
    assert scope == saved


@pytest.mark.parametrize('modality', ['description', 'obligation', 'permission'])
def test_new_scope_preserves_descriptive_and_explicit_deontic_values(modality):
    chunk, raw, scope = source(modality)
    saved = deepcopy(scope)
    request = business_run.extraction_request(run(), chunk, 'entity_relation')
    jsonschema.validate([dict(raw, Scope=scope)], request['schema'])
    value = autoschema.graph_record(chunk, 'entity_relation', raw, 0, scope=scope,
                                   scope_contract=autoschema.DESCRIPTIVE_SCOPE_CONTRACT)
    assert value['interpretation']['raw'] == saved
    assert value['interpretation']['meanings'][0]['modality'] == modality
    assert value['review_status'] == 'unreviewed' and value['semantic_status'] == 'unknown'
    assert not value['interpretation']['errors']
    assert autoschema.graph([value])['edges']
    assert autoschema.compact_interpretation(value['interpretation'])['meanings'][0]['modality'] == modality
    if modality == 'description':
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate([dict(raw, Scope=scope)], autoschema.extraction_schema('entity_relation'))
        legacy = autoschema.graph_record(chunk, 'entity_relation', raw, 0, scope=scope)
        assert legacy['interpretation']['errors'] and legacy['interpretation']['contract'] == autoschema.SCOPE_CONTRACT


def test_new_wire_does_not_replace_server_scope_or_target_checks():
    chunk, raw, scope = source()
    scope['evidence'] = [dict(block_id='b4', quote=chunk['blocks'][-1]['text'])]
    value = autoschema.graph_record(chunk, 'entity_relation', raw, 0, scope=scope,
                                   scope_contract=autoschema.DESCRIPTIVE_SCOPE_CONTRACT)
    assert value['interpretation']['target_status'] == 'reference_only'
    assert not autoschema.graph([value])['edges']
    scope['evidence'] = [dict(block_id='b3', quote=chunk['blocks'][2]['text'])]
    for indices in ([0], [9]):
        scope['meanings'][0]['premises'] = dict(state='present', meaning_indices=indices)
        jsonschema.validate([dict(raw, Scope=scope)], business_run.extraction_request(run(), chunk, 'entity_relation')['schema'])
        value = autoschema.graph_record(chunk, 'entity_relation', raw, 0, scope=scope,
                                       scope_contract=autoschema.DESCRIPTIVE_SCOPE_CONTRACT)
        assert 'unresolved interpretation premises' in value['interpretation']['errors']


def test_new_request_contract_is_explicit_and_legacy_is_default():
    assert BusinessRunRequest(source_version_ids=['v']).extraction_contract is None
    assert BusinessRunRequest(source_version_ids=['v'], extraction_contract='target_context_v1').extraction_contract == 'target_context_v1'


def test_repair_and_materialization_dispatch_keep_legacy_scope_and_new_description_separate():
    from app.knowledge import business_review
    from app.knowledge.business_models import Repairs
    from pydantic import ValidationError
    chunk, raw, scope = source()
    original = deepcopy(scope)
    # The normal json_call restores canonical block IDs before patch materialization.
    def restore(value):
        if isinstance(value, dict):
            return {k:chunk['source_reference_map'][v]['block_id'] if k == 'block_id' else restore(v) for k,v in value.items()}
        if isinstance(value, list): return [restore(v) for v in value]
        return value
    canonical = restore(scope)
    patch = dict(meaning_key='fixture', target_id=None, statement='검사 자료의 목록 포함',
        head=raw['Head'], relation=raw['Relation'], tail=raw['Tail'], evidence=canonical['evidence'],
        conditions=[], exceptions=[], period='', references=[], scope=canonical)
    current = run();current['recipe']['review_contract'] = business_review.CONTRACT
    current['blocks'] = chunk['blocks']
    schema = business_run.repair_schema(current)
    validated = schema.model_validate(dict(patches=[patch], unresolved=[])).model_dump()['patches'][0]
    value = business_run.materialize_patch(current, validated, None, 'fixture-repair', chunk['blocks'])
    assert value['interpretation']['contract'] == autoschema.DESCRIPTIVE_SCOPE_CONTRACT
    assert value['interpretation']['raw'] == canonical
    assert value['interpretation']['meanings'][0]['modality'] == 'description'
    assert value['review_status'] == 'unreviewed' and value['semantic_status'] == 'unknown'
    assert business_run.repair_schema(run(False)) is Repairs
    with pytest.raises(ValidationError):
        Repairs.model_validate(dict(patches=[patch], unresolved=[]))
    assert scope == original


def test_product_start_uses_new_contract_and_preserves_two_successful_stages_on_stop(natural, monkeypatch):
    from app.knowledge import business_checkpoint
    from app.tests.unit.test_knowledge_business import finish
    service, _, before, _, _, options, _, _ = natural
    ParentClient = business_run.ModelClient
    stages = []
    class Client(ParentClient):
        async def generate(self, request, cancelled=None):
            stages.append(request.stage)
            output = []
            if request.stage == 'entity_relation':
                text = request.messages[-1]['content']
                payload = json.loads(text[text.index('{"source_order":'):])
                target = payload['extraction_targets'][0]
                quote = target['text'];ref=[dict(block_id=target['id'],quote=quote)]
                absent=dict(state='absent',text=None)
                scope=dict(evidence=ref,meanings=[dict(statement_type='instance',relation_kind='other',subject='기관',
                    action='처리',object='신청',applies_to='코드 검사',modality='description',
                    **{k:deepcopy(absent) for k in ('conditions','exceptions','time','local_negation','references')},
                    premises=dict(state='absent',meaning_indices=[]),evidence=ref,participants=[
                        dict(field=field,entity_index=None,evidence=[dict(block_id=target['id'],quote=value)])
                        for field,value in [('Head','기관'),('Tail','신청')]])])
                output=[dict(Head='기관',Relation='처리',Tail='신청',Scope=scope)]
            return dict(parsed=output,text=json.dumps(output,ensure_ascii=False),done=True,done_reason='stop',
                        failure_kind=None,elapsed_s=0,prompt_eval_count=1,eval_count=1)
    monkeypatch.setattr(business_run,'ModelClient',Client)
    save=business_run.save;stopped=[]
    def stop_after_second_saved_stage(service,run):
        save(service,run)
        if not stopped and run['units'] and run['units'][-1]['stage']=='event_entity' and run['units'][-1].get('source_chunk_id'):
            stopped.append(run['id']);service.cancel(run['id'])
    monkeypatch.setattr(business_run,'save',stop_after_second_saved_stage)
    request=BusinessRunRequest(source_version_ids=[before],extraction_contract='target_context_v1',
        **dict(options,conceptualize=False))
    result=finish(service,service.start_business(request)['run_id'])
    assert result['status']=='cancelled' and stages==['entity_relation','event_entity']
    assert result['recipe']['version']==autoschema.TARGET_CONTEXT_VERSION
    assert result['recipe']['scope_contract']==autoschema.DESCRIPTIVE_SCOPE_CONTRACT
    assert result['claims'][0]['interpretation']['meanings'][0]['modality']=='description'
    assert result['claims'][0]['review_status']=='unreviewed'
    complete,keys=business_checkpoint.completed_prefix(result)
    assert len(complete)==2 and [s for _,s in keys]==stages
    broken=deepcopy(result)
    broken['units'][0]['schema']=autoschema.extraction_schema('entity_relation')
    with pytest.raises(ValueError,match='저장 기록'):
        business_checkpoint.completed_prefix(broken)


@pytest.mark.parametrize('tamper', [None, 'messages', 'schema', 'reference_map'])
def test_new_contract_preserves_other_source_only_with_exact_recorded_request(environment, no_models, tamper):
    from app.knowledge import business_rebuild
    from app.knowledge.schemas import SourceRegistration, RunRequest
    from app.knowledge.service import encode
    from app.tests.unit.test_knowledge_business import finish
    service, change = environment
    template, raw, scope = source('permission')
    html = '<html><body>' + ''.join('<p>' + b['text'] + '</p>' for b in template['blocks']) + '</body></html>'
    version_id = service.register('context.html', html.encode(), SourceRegistration(
        title='검사 자료', publisher='검사', namespace='test', external_id='context'))['source_version_id']
    assert finish(service, service.start(RunRequest(source_version_ids=[version_id]))['run_id'])['status'] == 'succeeded'
    with service.repository.connect() as db:
        version = service.repository.get(db, 'versions', version_id)
        blocks = service.parse_blocks(db, version['latest_parse_run_id'], version_id)
        for block in blocks:
            block['source_id'] = version['source_id']
        views = [dict(b, context_only=n != 2) for n, b in enumerate(blocks)]
        chunk = dict(id='preserved-context', source_version_id=version_id, blocks=views,
            text=autoschema.source_text(views), source_reference_map={
                'b'+str(n+1):dict(block_id=b['id'], span=b.get('span')) for n,b in enumerate(views)})
        parent = service.repository.get(db, 'runs', 'parent')
        parent['recipe'].update(version=autoschema.TARGET_CONTEXT_VERSION, scope_contract=autoschema.DESCRIPTIVE_SCOPE_CONTRACT)
        parent['recipe']['options']['extraction_contract'] = 'target_context_v1'
        claim = autoschema.graph_record(chunk, 'entity_relation', raw, 0, scope=scope,
                                       scope_contract=autoschema.DESCRIPTIVE_SCOPE_CONTRACT)
        assert not claim['interpretation']['errors']
        parent['blocks'].extend(blocks); parent['chunks'].append(chunk); parent['claims'].append(claim)
        parent['input_version_ids'].append(version_id)
        request = business_run.extraction_request(parent, chunk, 'entity_relation')
        assert not any(chunk['text'] in m['content'] for m in request['messages'])
        if tamper == 'messages': request['messages'][-1]['content'] += '\n다른 자료'
        elif tamper: request[tamper] = {}
        parent['units'].append(dict(id='source-unit', source_chunk_id=chunk['id'],
                                   stage='entity_relation', status='succeeded', **request))
        service.repository.save(db, 'runs', parent)
    plan = business_rebuild.plan(service, change)
    request = run_request(plan, extraction_contract='target_context_v1').model_copy(
        update=dict(source_version_ids=[change.after_version_id, version_id]))
    if tamper:
        with pytest.raises(ValueError, match='과거 실제 입력 범위'):
            service.start_business(request)
    else:
        result = finish(service, service.start_business(request)['run_id'])
        assert result['status'] == 'succeeded', result.get('error')
        assert next(c for c in result['claims'] if c['id'] == claim['id']) == claim
        assert result['metrics']['llm_calls'] == 0
        proof = result['source_rebuild']['preserved_extraction_inputs'][0]
        assert proof['stored_request_matches_current_contract'] is True
        assert claim['review_status'] == 'unreviewed' and claim['semantic_status'] == 'unknown'
