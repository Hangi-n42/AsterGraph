"""Literal address checks do not certify a proposed participant's semantic role."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest

from app.knowledge import autoschema, business_run, business_review, business_participants as participants
from app.knowledge import business_participant_resume as resume
from app.knowledge.business_checkpoint import digest
from app.tests.unit.test_knowledge_business_missing_recovery import fixture, native_contract
from app.tests.unit.test_knowledge_business_local_review import local_run


def proposal(run):
    return dict(meaning_key='part', target_id=None, role='event_entity', raw=dict(
        Event=run['blocks'][0]['text'], Entity=['신청 기관']), evidence=[dict(block_id='body', quote=run['blocks'][0]['text'])],
        conditions=[], exceptions=[], period='', references=[], conversion_reason='', reuse_claim_ids=[], scope=None)


def selected(monkeypatch):
    run = local_run(); patch = proposal(run)
    def answer(_s, current, stage, instruction, context, schema):
        assert stage == 'source_literal_participants'
        assert context['proposals'][0]['unverified_proposal'] == patch
        current['units'].append(dict(id='selection'))
        return dict(choices=[dict(proposal_index=0, entity_index=0, evidence_index=0,
            literal='신청', reason='접수의 영향을 받는 대상으로 변경')], unresolved=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    output = participants.select(None, run, dict(patches=[patch], unresolved=[]), run['blocks'], {'part'})
    value = business_run.materialize_patch(run, output['patches'][0], None, 'repair', run['blocks'], origin='model_statement_recovery')
    return run, value, patch


def test_object_participation_keeps_fixed_event_and_unverified_original(monkeypatch):
    run, value, original = selected(monkeypatch)
    assert value['raw'] == dict(Event=original['raw']['Event'], Entity=['신청'])
    assert value['literal_grounding']['unverified_proposal'] == original
    assert value['semantic_status'] == 'unknown' and value['review_status'] == 'unreviewed'
    assert 'interpretation' not in value
    before = autoschema.graph(run['claims'])
    graph = autoschema.graph([*run['claims'], value], run['blocks'])
    assert all(n in graph['nodes'] for n in before['nodes']) and all(e in graph['edges'] for e in before['edges'])
    edge = next(e for e in graph['edges'] if e['claim_id'] == value['id'])
    node = next(n for n in graph['nodes'] if n['id'] == edge['tail'])
    assert edge['relation'] == 'participation' and node['literal_evidence']['quote'] == '신청'
    assert node['identity_scope'] == 'source_version+parse+exact_literal_span+kind'
    instruction, context, _ = business_review.candidate_request(run, [value])
    assert context['claims'][0]['literal_grounding'] == value['literal_grounding']
    assert '행위자만 뜻하지 않는다' in instruction


@pytest.mark.parametrize('change', ['event','statement','conditions','period','source','parse','span','evidence','context','versions','negative_evidence','negative_entity','duplicate','missing','false_literal'])
def test_stored_contract_mutations_fail_in_graph_and_own_source(monkeypatch, change):
    run, value, _ = selected(monkeypatch)
    if change == 'event': value['raw']['Event'] += ' 변경'
    elif change == 'statement': value['statement'] += ' 변경'
    elif change in {'conditions','period'}: value[change] = ['다름'] if change == 'conditions' else '다름'
    elif change in {'source','parse','span'}:
        key = {'source':'source_version_id','parse':'parse_run_id','span':'start_char'}[change]
        value['edit_participants'][0][key] = 999 if change == 'span' else 'other'
    elif change == 'evidence': value['evidence'][0]['quote'] = '기관'
    elif change == 'context': value['evidence_context'][0]['quote'] = '기관'
    elif change == 'versions': value['source_version_ids'] = ['other']
    elif change == 'negative_evidence': value['literal_grounding']['choices'][0]['evidence_index'] = -1
    elif change == 'negative_entity': value['literal_grounding']['choices'][0]['entity_index'] = -1
    elif change == 'duplicate': value['literal_grounding']['choices'] *= 2
    elif change == 'missing': value['literal_grounding']['choices'] = []
    elif change == 'false_literal': value['raw']['Entity'] = ['없는 대상']
    with pytest.raises(ValueError): autoschema.graph([value], run['blocks'])
    with pytest.raises(ValueError): business_review.candidate_request(run, [value])


@pytest.mark.parametrize('field,value', [('superseded_by',['replacement']),('interpretation',dict(target_status='reference_only'))])
def test_inactive_stale_contract_does_not_break_active_graph(monkeypatch, field, value):
    run, claim, _ = selected(monkeypatch); claim['raw']['Event'] = 'stale'; claim[field] = value
    actual = autoschema.graph([*run['claims'], claim], run['blocks']); baseline = autoschema.graph(run['claims'])
    assert actual['nodes'] == baseline['nodes'] and actual['edges'] == baseline['edges']


@pytest.mark.parametrize('origin', ['user','model_event_field_edit'])
def test_existing_event_edit_invalidates_prior_selection_contract(monkeypatch, origin):
    run, old, patch = selected(monkeypatch)
    patch.update(target_id=old['id'], raw=dict(Event='기관은 신청을 처리한다.', Entity=['신청']))
    after = business_run.materialize_patch(run, patch, old, 'edit', run['blocks'], origin=origin)
    assert 'literal_grounding' not in after and old.get('literal_grounding')
    assert after['literal_grounding_history'][-1]['invalidated_by'] == 'edit'
    assert autoschema.graph([after], run['blocks'])['edges']


def test_same_literal_in_another_source_is_not_merged(monkeypatch):
    run, first, _ = selected(monkeypatch)
    second = deepcopy(first); second['id'] = 'other'
    block = dict(run['blocks'][0], id='other-body', source_version_id='other-v', parse_run_id='other-p')
    marker = second['literal_grounding']
    marker['unverified_proposal']['evidence'][0]['block_id'] = block['id']
    marker['proposal_sha256'] = digest(marker['unverified_proposal'])
    for ref in [*second['evidence'],*second['evidence_context'],*second['edit_participants'],*marker['original_evidence']]:
        ref.update(block_id=block['id'],source_version_id=block['source_version_id'],parse_run_id=block['parse_run_id'])
    second['source_version_ids'] = ['other-v']
    graph = autoschema.graph([first, second], [*run['blocks'],block])
    assert len({e['tail'] for e in graph['edges']}) == 2


def test_out_of_scope_patch_does_not_start_selection(monkeypatch):
    run = local_run()
    monkeypatch.setattr(business_run, 'json_call', lambda *a:pytest.fail('unexpected native selection'))
    output = dict(patches=[proposal(run)], unresolved=[])
    assert participants.select(None,run,output,run['blocks'],{'other'}) == output


@pytest.mark.parametrize('literal', ['없는 대상', '기관'])
def test_missing_or_ambiguous_literal_cannot_use_first_hit(literal):
    run = local_run(); run['blocks'][0]['text'] = '기관과 기관은 신청을 접수한다.'
    refs = business_run.exact_evidence([dict(block_id='body',quote=run['blocks'][0]['text'])],run['blocks'])
    with pytest.raises(ValueError): participants.address(literal,refs,0,run['blocks'])


def test_ambiguous_original_quote_does_not_start_selection(monkeypatch):
    run = local_run(); patch = proposal(run)
    run['blocks'][0]['text'] *= 2
    monkeypatch.setattr(business_run,'json_call',lambda *a:pytest.fail('ambiguous original quote'))
    output = dict(patches=[patch],unresolved=[])
    assert participants.select(None,run,output,run['blocks'],{'part'}) == output


def stored_failure(monkeypatch):
    run, req, source = fixture(monkeypatch)
    native_contract(monkeypatch,run,status='missing',location=False)
    assessment = business_run.assess(None,run,req,source=source,focus_meaning_keys=['part'])
    for unit in run['units']:
        unit['stage'] = 'requirement_representation'
    run['assessments'] = [assessment]
    run.update(kind='business',status='partial',finished_at='done',model_identity={}, input_version_ids=['v'],sources={},answer_items=[])
    run['recipe'].update(models=dict(draft='draft',review='review'),generation={})
    patch = proposal(run)
    def answer(_s,current,stage,instruction,context,schema):
        if stage == 'source_literal_participants':
            current['units'].append(dict(id='selection',stage=stage))
            return dict(choices=[],unresolved=[0])
        request = business_run.json_request(current,stage,instruction,context,schema)
        output = schema.model_validate(dict(patches=[patch],unresolved=[])).model_dump()
        from app.knowledge.discovery_analysis import remap
        limits = dict(max_tokens=run['recipe']['options']['review_tokens'],context_tokens=run['recipe']['options']['context_tokens'],think=False)
        current['units'].append(dict(id='original',stage=stage,status='succeeded',error=None,**{k:request[k] for k in ('messages','schema','reference_map')},
            request_configuration=dict(model='review',generation={},identity={},temperature=0,timeout=run['recipe']['options']['timeout']),
            requested_limits=limits,executed_limits=deepcopy(limits),response=dict(parsed=remap(output,request['reference_map'] or {}))))
        return output
    monkeypatch.setattr(business_run,'json_call',answer)
    assert not business_run.repair(None,run,req,assessment)
    service = SimpleNamespace(repository=SimpleNamespace(connect=lambda:nullcontext(None),get=lambda *a:dict(req,status='active')))
    monkeypatch.setattr(resume.business_use,'restricted_sources',lambda *a:False)
    return service,run


def test_general_recovery_and_resume_use_same_failed_native_proposal(monkeypatch):
    service,run = stored_failure(monkeypatch)
    before = deepcopy(run['claims']); receipt = run['repairs'][-1]
    plan = resume.plan(service,run,receipt['id'])
    assert len(plan['proposals']['patches']) == 1 and plan['original_unit_id'] == 'original'
    assert run['claims'] == before


@pytest.mark.parametrize('field', ['messages','schema','reference_map','request_configuration','executed_limits','response'])
def test_resume_rejects_changed_native_request_or_response(monkeypatch,field):
    service,run = stored_failure(monkeypatch)
    unit = next(u for u in run['units'] if u.get('id') == 'original')
    if field == 'messages': unit[field][0]['content'] += ' altered'
    elif field == 'response': unit[field]['parsed']['patches'][0]['raw']['Event'] = 'altered'
    else: unit[field]['altered'] = True
    with pytest.raises(ValueError): resume.plan(service,run,run['repairs'][-1]['id'])


def test_mixed_semantic_edit_replay_is_read_only_and_explicitly_unsupported(monkeypatch):
    from app.tests.unit.test_knowledge_business_event_repair import event_case
    run, assessment, _ = event_case(); cid = run['claims'][0]['id']
    assessment['actions'][0].update(error_fields={cid:['raw.Event']}, error_evidence=[dict(block_id='body',quote='기관')])
    monkeypatch.setattr(business_run,'event_meaning_edit',lambda *a:pytest.fail('replay made a model call'))
    with pytest.raises(ValueError,match='혼합'):
        business_run.repair(None,run,run['requirements'][0],assessment,replay_unit={})


@pytest.mark.parametrize('status',['queued','running','partial','failed','cancelled'])
def test_repeated_start_returns_same_child_without_new_plan_or_calls(monkeypatch,status):
    parent = dict(id='parent'); receipt = dict(repair_id='repair',parent_sha256=digest(parent))
    child = dict(id='child',parent_run_id='parent',status=status,participant_resumption=receipt)
    db = SimpleNamespace(execute=lambda *a:[dict(payload=json.dumps(child))])
    repository = SimpleNamespace(connect=lambda:nullcontext(db),get=lambda *a:parent,
        has_active_runs=lambda *a:pytest.fail('matching child should be returned first'))
    service = SimpleNamespace(lock=nullcontext(),repository=repository,closed=False)
    monkeypatch.setattr(resume,'plan',lambda *a:pytest.fail('duplicate selection plan'))
    assert resume.start(service,'parent','repair') == dict(run_id='child',status=status,participant_resumption=receipt,reused=True)
