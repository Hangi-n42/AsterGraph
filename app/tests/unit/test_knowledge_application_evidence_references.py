"""Application evidence wire references preserve full stored data and item ownership."""
from copy import deepcopy
import json

import pytest

from app.knowledge import business_run
from app.knowledge.business_models import ContributionReviewCheck
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_business_local_review import local_run


def case():
    run=local_run()
    refs=business_run.exact_evidence([dict(block_id='body',quote=run['blocks'][0]['text'])],run['blocks'])
    refs[0].update(precision='chunk',context_only=False)
    applications=[dict(item_id='answer',required_for_requirement=True,required_content='접수',
        requirement_link=dict(reason='원래 필요 이유'),evidence=deepcopy(refs)),
        dict(item_id='reference',required_for_requirement=False,required_content=None,evidence=deepcopy(refs)),
        dict(item_id='pending',required_for_requirement=None,required_content=None,evidence=[]),
        dict(item_id='legacy',required_for_requirement=None,evidence=None)]
    context=dict(source=dict(meanings=[dict(key='m',statement='원문 그대로',conditions=['조건'],exceptions=['예외'],
        period='',premise_keys=None,evidence=deepcopy(refs),requirement_applications=applications)]),
        required_content_targets=[dict(meaning_key='m',scope_id='scope',content='접수',
            evidence=deepcopy(refs+refs),applications=deepcopy(applications[:1]))],
        claims=deepcopy(run['claims']),blocks=deepcopy(run['blocks']),
        whole_candidate_judgments=[dict(id='original',status='unknown')],repair_context=[],requirement=dict(question='원래 질문'))
    return run,context


def decode(request):
    reverse={v:k for k,v in (request['reference_map'] or {}).items()}
    context=business_run.remap_expression_keys(remap(json.loads(request['messages'][1]['content']),reverse),reverse)
    return business_run.restore_application_evidence(context,request['evidence_reference_map'],request['application_evidence_bindings'])


def test_product_request_restores_every_value_and_keeps_other_fields_schema_and_criteria(monkeypatch):
    run,context=case();before=deepcopy(context)
    request=business_run.json_request(run,'requirement_representation','판정 지시 고정',context,ContributionReviewCheck)
    with monkeypatch.context() as m:
        m.setattr(business_run,'reference_application_evidence',lambda *a:None)
        original=business_run.json_request(run,'requirement_representation','판정 지시 고정',context,ContributionReviewCheck)
    raw=json.loads(original['messages'][1]['content'])
    reverse={v:k for k,v in (original['reference_map'] or {}).items()}
    expected=business_run.remap_expression_keys(remap(raw,reverse),reverse)
    assert decode(request)==expected and context==before
    assert json.dumps(decode(request),ensure_ascii=False)==json.dumps(expected,ensure_ascii=False)
    assert request['schema']==original['schema'] and request['reference_map']==original['reference_map']
    assert request['evidence_reference_map']==original['evidence_reference_map']
    assert request['messages'][0]['content']==original['messages'][0]['content']+business_run.APPLICATION_EVIDENCE_NOTICE
    assert len(request['messages'][1]['content'])<len(original['messages'][1]['content'])
    payload=json.loads(request['messages'][1]['content'])
    apps=payload['source']['meanings'][0]['requirement_applications']
    assert apps[0]['source_evidence_refs']==apps[1]['source_evidence_refs']==[dict(
        evidence_ref='e1',span=[0,len(run['blocks'][0]['text'])],context_only=False,precision='chunk')]
    assert apps[2]['evidence']==[] and apps[3]['evidence'] is None
    assert [a['item_id'] for a in decode(request)['source']['meanings'][0]['requirement_applications']]==['answer','reference','pending','legacy']
    assert decode(request)['required_content_targets'][0]['evidence']==context['required_content_targets'][0]['evidence']


@pytest.mark.parametrize('fault',['unknown_ref','duplicate_ref','span','ref_metadata','owner','reason','row_duplicate',
    'version','parse','quote','context','precision','ambiguous_view','binding','mixed_original'])
def test_unregistered_changed_duplicate_or_other_owner_source_is_rejected(fault):
    run,context=case();request=business_run.json_request(run,'requirement_representation','고정',context,ContributionReviewCheck)
    payload=json.loads(request['messages'][1]['content']);views=deepcopy(request['evidence_reference_map'])
    row=payload['source']['meanings'][0]['requirement_applications'][0]
    ref=row['source_evidence_refs'][0]
    if fault=='unknown_ref':ref['evidence_ref']='e999'
    if fault=='duplicate_ref':row['source_evidence_refs'].append(deepcopy(ref))
    if fault=='span':ref['span'][0]+=1
    if fault=='ref_metadata':ref.pop('context_only')
    if fault=='owner':row['item_id']='another-item'
    if fault=='reason':row['requirement_link']['reason']='다른 판단 이유'
    if fault=='row_duplicate':payload['source']['meanings'][0]['requirement_applications'].append(deepcopy(row))
    if fault=='version':views['e1']['source_version_id']='another-version'
    if fault=='parse':views['e1']['parse_run_id']='another-parse'
    if fault=='quote':views['e1']['text']='다른 원문'
    if fault=='context':views['e1']['context_only']=True
    if fault=='precision':ref['precision']='exact'
    if fault=='ambiguous_view':views['e2']=deepcopy(views['e1'])
    if fault=='binding':payload['application_evidence_binding']='changed'
    if fault=='mixed_original':row['evidence']=[]
    reverse={v:k for k,v in request['reference_map'].items()}
    payload=business_run.remap_expression_keys(remap(payload,reverse),reverse)
    before=deepcopy(payload)
    with pytest.raises(ValueError):business_run.restore_application_evidence(payload,views,request['application_evidence_bindings'])
    assert payload==before


@pytest.mark.parametrize('fault',['version','parse','quote','span','context_only','missing_identity'])
def test_unmatched_original_evidence_is_retained_without_address_repair(fault):
    run,context=case();ref=context['source']['meanings'][0]['requirement_applications'][0]['evidence'][0]
    if fault=='version':ref['source_version_id']='other'
    if fault=='parse':ref['parse_run_id']='other'
    if fault=='quote':ref['quote']='원문에 없는 인용'
    if fault=='span':ref['start_char']+=1
    if fault=='context_only':ref['context_only']=True
    if fault=='missing_identity':ref.pop('parse_run_id')
    before=deepcopy(context)
    wire=deepcopy(context);views={'e1':run['blocks'][0]}
    bindings=business_run.reference_application_evidence(wire,views)
    assert wire['source']['meanings'][0]['requirement_applications'][0]['source_evidence_refs']==[ref]
    assert business_run.restore_application_evidence(wire,views,bindings)==before


def test_reference_name_collision_does_not_change_caller_input():
    run,context=case();context['source']['meanings'][0]['requirement_applications'][0]['source_evidence_refs']=[]
    before=deepcopy(context)
    with pytest.raises(ValueError,match='reference_collision'):
        business_run.json_request(run,'requirement_representation','고정',context,ContributionReviewCheck)
    assert context==before


def test_non_address_role_and_uncertainty_metadata_remain_visible():
    run,context=case()
    ref=context['source']['meanings'][0]['requirement_applications'][0]['evidence'][0]
    ref.update(role='reference_only',address_status='unverified')
    wire=deepcopy(context);views={'e1':run['blocks'][0]}
    bindings=business_run.reference_application_evidence(wire,views)
    selected=wire['source']['meanings'][0]['requirement_applications'][0]['source_evidence_refs'][0]
    assert selected['precision']=='chunk' and selected['role']=='reference_only' and selected['address_status']=='unverified'
    assert business_run.restore_application_evidence(wire,views,bindings)==context


@pytest.mark.parametrize('key,value',[('evidence_ref','e999'),('span',[1,2])])
def test_original_reserved_metadata_cannot_overwrite_a_new_address(key,value):
    run,context=case();context['source']['meanings'][0]['requirement_applications'][0]['evidence'][0][key]=value
    before=deepcopy(context)
    with pytest.raises(ValueError,match='reserved_key_collision'):
        business_run.json_request(run,'requirement_representation','고정',context,ContributionReviewCheck)
    assert context==before


@pytest.mark.parametrize('stage',['business_qa','requirement_application','requirement_repair'])
def test_other_stages_do_not_change_their_application_evidence(stage):
    run,context=case();request=business_run.json_request(run,stage,'고정',context,ContributionReviewCheck)
    assert 'application_evidence_bindings' not in request
    assert business_run.APPLICATION_EVIDENCE_NOTICE not in request['messages'][0]['content']
    assert 'application_evidence_contract' not in json.loads(request['messages'][1]['content'])


def test_product_json_call_saves_bindings_and_api_get_keeps_full_original(monkeypatch,tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers import knowledge
    from app.knowledge.service import KnowledgeService,encode
    run,context=case();run.update(id='application-wire-synthetic',kind='business',status='partial')
    service=KnowledgeService(tmp_path/'wire.db')
    def fake_call(s,r,stage,messages,schema,**kwargs):
        r['units'].append(dict(id='synthetic',stage=stage,status='succeeded',error=None,
            messages=messages,schema=schema,reference_map=kwargs['reference_map']))
        return dict(parsed=dict(checks=[],requirement_checks=[],dependencies=[],source_challenges=[],meaning_challenges=[],candidate_challenges=[]))
    monkeypatch.setattr(business_run,'call',fake_call)
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    try:
        with service.repository.connect() as db:db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
        assert business_run.json_call(service,run,'requirement_representation','고정',context,ContributionReviewCheck) is not None
        unit=run['units'][-1]
        assert unit['application_evidence_contract']==business_run.APPLICATION_EVIDENCE_INPUT
        assert unit['application_evidence_bindings'] and unit['restored_evidence_output']['checks']==[]
        app=FastAPI();app.include_router(knowledge.router);app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
        with TestClient(app) as client:reply=client.get('/knowledge/runs/'+run['id'])
        assert reply.status_code==200 and reply.json()['data']['units'][-1]==unit
        assert decode(dict(unit,evidence_reference_map=unit['evidence_reference_map']))['source']['meanings']==context['source']['meanings']
    finally:service.shutdown()
