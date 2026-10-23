"""Actual API preparation fixtures; no model, counter, task submission, or approval."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import knowledge
from app.knowledge import business_run, business_store, business_use, concept_work, interpretation_edit
from app.knowledge.business_models import InterpretationEditRequest, RequirementInput
from app.knowledge.service import encode
from app.tests.unit.test_knowledge_interpretation_edit import editing


@pytest.fixture
def linked_input(editing, monkeypatch):
    service, original, change, edit = editing
    edited = interpretation_edit.start(service, change['id'], InterpretationEditRequest(**edit))
    req = business_store.put_requirement(service, RequirementInput(id='r', question_ids=['Q'],
        question='기관이 신청을 접수할 수 있는 조건은?', criterion='자기 원문의 조건을 보존한다.',
        target='기관', situation='신청', period='저장 버전', source_ids=['source']))
    reference = dict(deepcopy(original), id='reference', requirements=[req],
        answer_items=[dict(id='item', requirement_id='r', requirement_revision=1,
            field='question', request_quote='접수할 수 있는 조건')],
        assessments=[dict(id='historical', requirement_id='r', source=dict(public_scope={'old': True}))])
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('reference', encode(reference)))
        parent = service.repository.get(db, 'runs', edited['run_id'])
    payload=dict(expected_parent_fingerprint=concept_work.digest(parent), reference_run_id='reference',
        expected_reference_fingerprint=concept_work.digest(reference), requirement_id='r',
        expected_requirement_revision=1, idempotency_key='link', actor='Codex 검토', reason='검토 준비만 저장')
    monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', True)
    monkeypatch.setattr(business_run, 'execute', lambda *a, **k: pytest.fail('Preparation must not execute review'))
    app=FastAPI();app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    return service, parent, reference, payload, TestClient(app)


def test_api_links_public_requirement_preserves_pool_and_blocks_use(linked_input):
    service,parent,reference,payload,client=linked_input
    url='/api/v1/knowledge/business/runs/'+parent['id']+'/requirement-links'
    reply=client.post(url,json=payload);assert reply.status_code==200,reply.text
    result=reply.json()['data']
    with service.repository.connect() as db:child=service.repository.get(db,'runs',result['run_id'])
    for field in ['claims','blocks','chunks','sources','graph','concepts','concept_work','concept_bindings',
                  'units','candidate_reviews','interpretation_edit']:
        assert child[field]==parent[field]
    assert child['requirements'][0]['question']==reference['requirements'][0]['question']
    assert child['requirements'][0]['criterion']==reference['requirements'][0]['criterion']
    assert child['requirements'][0]['revision']==1
    assert 'current_assessment' not in child['requirements'][0]
    assert child['assessments']==[] and child['answer_items']==reference['answer_items']
    assert child['requirement_link']['historical_assessment_ids']==['historical']
    assert child['metrics']['llm_calls']==0 and not child['requirement_link']['model_work_submitted']
    assert business_use.change_view(service,result['changeset_id'])['eligible_ids']==[]
    assert client.post(url,json=payload).json()['data']['duplicate_request']
    usage=client.get('/api/v1/knowledge/workbench/usage',params=dict(kind='run',scope_id=child['id'])).json()['data']
    assert usage['requirements'][0]['recorded_status']=='unassessed'
    assert usage['requirement_link']['public_answer_items']==reference['answer_items']
    answer=client.post('/api/v1/knowledge/business/search',json=dict(source_run_id=child['id'],question='접수 조건은?')).json()['data']
    assert answer['status']=='needs_review' and answer['answer'] is None and not answer['model_called']
    approval=client.post('/api/v1/knowledge/business/changes/'+result['changeset_id']+'/decisions',
        json=dict(expected_revision=0,actor='fixture',reason='cannot approve',accept_ids=[]))
    assert approval.status_code==409
    assert business_use.snapshots(service)['items']==[]
    with service.repository.connect() as db:
        assert service.repository.get(db,'runs',parent['id'])==parent
        assert service.repository.get(db,'runs','reference')==reference


@pytest.mark.parametrize('fault',['parent','reference','revision','criterion','quote','pool'])
def test_stale_or_changed_basis_cannot_link_or_create_child(linked_input,fault):
    service,parent,reference,payload,client=linked_input
    if fault=='parent':payload['expected_parent_fingerprint']='stale'
    elif fault=='reference':payload['expected_reference_fingerprint']='stale'
    elif fault=='revision':payload['expected_requirement_revision']=2
    elif fault in {'criterion','quote'}:
        if fault=='criterion':reference['requirements'][0]['criterion']='다른 기준'
        else:reference['answer_items'][0]['request_quote']='원문에 없는 구절'
        with service.repository.connect() as db:service.repository.save(db,'runs',reference)
        payload['expected_reference_fingerprint']=concept_work.digest(reference)
    else:
        parent['stored_pool']['claims_hash']='stale'
        with service.repository.connect() as db:service.repository.save(db,'runs',parent)
        payload['expected_parent_fingerprint']=concept_work.digest(parent)
    with service.repository.connect() as db:before=db.execute('SELECT count(*) FROM runs').fetchone()[0]
    response=client.post('/api/v1/knowledge/business/runs/'+parent['id']+'/requirement-links',json=payload)
    assert response.status_code == (422 if fault=='quote' else 409)
    with service.repository.connect() as db:assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==before


def test_same_key_different_request_and_later_requirement_revision_conflict(linked_input):
    service,parent,_,payload,client=linked_input
    url='/api/v1/knowledge/business/runs/'+parent['id']+'/requirement-links'
    assert client.post(url,json=payload).status_code==200
    assert client.post(url,json=dict(payload,reason='different')).status_code==409
    with service.repository.connect() as db:
        req=service.repository.get(db,'requirements','r');req['revision']=2
        service.repository.save(db,'requirements',req)
    assert client.post(url,json=dict(payload,idempotency_key='later')).status_code==409
