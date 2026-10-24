"""Stored synthetic review records survive ordinary start; no worker or model runs."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import knowledge
from app.knowledge import autoschema, business_review, business_run
from app.knowledge.service import encode
from app.tests.unit.test_knowledge_interpretation_edit import editing


@pytest.fixture
def stored_review(editing, monkeypatch):
    service,parent,_,_=editing
    title=dict(deepcopy(parent['blocks'][0]), id='title', text='기관의 접수 안내', order=0)
    parent['blocks'].insert(0,title)
    parent['sources']['v']=dict(source_id='source',title='합성 원문',filename='fixture.md',sha256='fixture',dates={})
    parent.update(analysis_units=[],metrics=dict(llm_calls=1,model_total_s=1,elapsed_s=1))
    parent['stored_pool']={kind+'_hash':autoschema.identifier(kind,parent[field])
        for field,kind in [('claims','claims'),('blocks','source'),('graph','graph')]}
    parent['candidate_review_scope']=dict(input_contract=business_review.SCOPED_CANDIDATE_INPUT,
        claim_ids=[c['id'] for c in parent['claims']],source_block_ids=['title','body'],phase='completed')
    instruction,context,schema=business_review.candidate_request(parent,parent['claims'])
    packet=business_run.json_request(parent,'candidate_source_review',instruction,context,schema)
    parent['candidate_review_scope']['packet']=deepcopy(packet)
    output=dict(checks=[],preservation_checks=[])
    checks=[dict(claim_ids=[c['id']],claim_support={c['id']:'supported'},incorrect_claim_ids=[],error_fields={},
        evidence=[],error_evidence=[],reason='Synthetic stored result, not a model-quality judgment') for c in parent['claims']]
    options=parent['recipe']['options']
    limits=dict(max_tokens=options['review_tokens'],context_tokens=options['context_tokens'],think=options['think'])
    unit=dict(id='original-unit',stage='candidate_source_review',status='succeeded',error=None,**packet,
        request_configuration=dict(model='fixture',generation=deepcopy(parent['recipe']['generation']),
            identity={},temperature=0,timeout=options['timeout']),requested_limits=limits,executed_limits=deepcopy(limits),
        response=dict(request_id='original-unit',failure_kind=None,text='Synthetic stored raw output'),
        restored_evidence_output=deepcopy(output))
    parent['units']=[unit,dict(id='failed-unit',stage='candidate_source_review',status='failed',error='historical failure')]
    parent['candidate_reviews']=[dict(id='original-receipt',unit_id=unit['id'],review_contract=parent['recipe']['review_contract'],
        claim_ids=[c['id'] for c in parent['claims']],output=output,checks=checks,errors=[],candidate_challenges=[])]
    with service.repository.connect() as db:
        db.execute('UPDATE sources SET payload=? WHERE id=?',(encode(dict(id='source',title='합성 원문')),'source'))
        version=dict(id='v',source_id='source',sha256='fixture',filename='fixture.md',dates={},
            processing_status='parsed',latest_parse_run_id='fixture-parse')
        service.repository.save(db,'versions',version)
        service.repository.save(db,'runs',parent)
    monkeypatch.setattr(business_run,'configuration',lambda:deepcopy(parent['recipe']['generation']))
    monkeypatch.setattr(business_run.ModelClient,'identities',lambda *a,**k:deepcopy(parent['model_identity']))
    monkeypatch.setattr(service,'parse_blocks',lambda *a:deepcopy(parent['blocks']))
    tasks=[]
    monkeypatch.setattr(service.executor,'submit',lambda fn,*args:tasks.append((fn,args)))
    monkeypatch.setattr(business_run,'execute',lambda *a,**k:pytest.fail('Worker must not execute'))
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    return service,parent,TestClient(app),tasks


def start(data,mode):
    _,parent,client,_=data
    return client.post('/api/v1/knowledge/business/runs',json=dict(source_version_ids=['v'],**{mode:parent['id']},
        model='fixture',review_model='fixture',review_contract=parent['recipe']['review_contract'],
        review_tokens=8192,context_tokens=49152,timeout=30,repair=False,conceptualize=False))


@pytest.mark.parametrize('mode',['resume_run_id','reassess_run_id'])
@pytest.mark.parametrize('retained',[False,True])
def test_existing_start_inherits_bound_records_without_counting_new_calls(stored_review,mode,retained):
    service,parent,client,tasks=stored_review
    if retained:
        parent['source_concept_retention']=dict(inherited_failures=[dict(unit_id='failed-unit')])
    with service.repository.connect() as db:service.repository.save(db,'runs',parent)
    before=deepcopy(parent)
    reply=start(stored_review,mode);assert reply.status_code==200,reply.text
    child=client.get('/api/v1/knowledge/runs/'+reply.json()['data']['run_id']).json()['data']
    assert len(tasks)==1 and child['metrics']==dict(llm_calls=0,model_total_s=0,elapsed_s=0)
    assert child['candidate_reviews']==parent['candidate_reviews']
    assert child['candidate_review_scope']==parent['candidate_review_scope']
    assert child['units'].count(parent['units'][0])==1
    assert child['units']==parent['units'] if retained else child['units']==parent['units'][:1]
    assert child['reusable_units']==parent['units']
    assert set(business_review.current_candidate_reviews(child))=={c['id'] for c in parent['claims']}
    for field in ['claims','graph','concepts','blocks','sources']:assert child[field]==parent[field]
    assert child['assessments']==[] and 'changeset_id' not in child
    assert service.run(parent['id'])['claims']==parent['claims'] and parent==before
    with service.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM snapshots').fetchone()[0]==0
        assert service.repository.get(db,'runs',parent['id'])==parent


@pytest.mark.parametrize('fault',['claim','source','source_version','parse','model','limits','repair_context','challenge','remove_scope'])
def test_changed_input_rejects_current_reuse_and_preserves_history(stored_review,fault):
    _,parent,client,_=stored_review
    reply=start(stored_review,'reassess_run_id');assert reply.status_code==200,reply.text
    child=client.get('/api/v1/knowledge/runs/'+reply.json()['data']['run_id']).json()['data']
    assert set(business_review.current_candidate_reviews(child))=={c['id'] for c in parent['claims']}
    old=deepcopy(child['candidate_reviews']);units=deepcopy(child['units'])
    if fault=='claim':child['claims'][0]['raw']['Head']='다른 주체'
    elif fault=='source':child['blocks'][1]['text']+=' 새 원문'
    elif fault=='source_version':child['blocks'][1]['source_version_id']='different-version'
    elif fault=='parse':child['blocks'][1]['parse_run_id']='different-parse'
    elif fault=='model':child['model_identity']={'review':'changed'}
    elif fault=='limits':child['recipe']['options']['review_tokens']+=1
    elif fault=='repair_context':child['repairs']=[dict(id='new-repair',changes=[dict(before=deepcopy(parent['claims'][0]),after=deepcopy(child['claims'][0]))])]
    elif fault=='challenge':child['candidate_challenges']=[dict(claim_ids=[child['claims'][0]['id']],fields=['raw.Head'],reason='새 이의',evidence=[])]
    else:child.pop('candidate_review_scope')
    direct=business_review.current_candidate_reviews(child)
    assert child['claims'][0]['id'] not in direct
    assert child['candidate_reviews']==old and child['units']==units


def test_pending_parent_challenge_is_not_lost_during_start(stored_review):
    service,parent,client,_=stored_review
    parent['candidate_challenges']=[dict(claim_ids=[parent['claims'][0]['id']],fields=['raw.Head'],reason='미해결 이의',evidence=[])]
    with service.repository.connect() as db:service.repository.save(db,'runs',parent)
    reply=start(stored_review,'reassess_run_id');assert reply.status_code==200,reply.text
    child=client.get('/api/v1/knowledge/runs/'+reply.json()['data']['run_id']).json()['data']
    assert child['candidate_challenges']==parent['candidate_challenges']
    assert parent['claims'][0]['id'] not in business_review.current_candidate_reviews(child)


@pytest.mark.parametrize('retained',[False,True])
@pytest.mark.parametrize('conflict',[False,True])
def test_duplicate_unit_id_is_deduplicated_or_rejected(stored_review,retained,conflict):
    service,parent,_,tasks=stored_review
    if retained:parent['source_concept_retention']={'inherited_failures':[]}
    duplicate=deepcopy(parent['units'][0])
    if conflict:duplicate['response']['text']='different stored raw output'
    parent['units'].append(duplicate)
    with service.repository.connect() as db:service.repository.save(db,'runs',parent)
    reply=start(stored_review,'reassess_run_id')
    assert reply.status_code==(409 if conflict else 200),reply.text
    if conflict:assert tasks==[]
    else:
        child=service.run(reply.json()['data']['run_id'])
        assert sum(u['id']=='original-unit' for u in child['units'])==1


@pytest.mark.parametrize('phase,status',[('prepared','partial'),('completed','partial'),('failed','failed'),('cancelled','cancelled')])
def test_historical_states_remain_readable_and_retired_post_routes_are_absent(stored_review,phase,status):
    service,parent,client,tasks=stored_review
    parent.update(status=status);parent['candidate_review_scope']['phase']=phase
    with service.repository.connect() as db:service.repository.save(db,'runs',parent)
    response=client.get('/api/v1/knowledge/runs/'+parent['id']);assert response.status_code==200
    assert response.json()['data']['candidate_review_scope']==parent['candidate_review_scope']
    paths=client.get('/openapi.json').json()['paths']
    for suffix in ['candidate-review-preparations','candidate-review-execution']:
        assert not any(suffix in p for p in paths)
        assert client.post('/api/v1/knowledge/business/runs/'+parent['id']+'/'+suffix,json={}).status_code==404
    assert tasks==[]


def test_business_list_keeps_history_without_a_start_timestamp(stored_review):
    service,parent,client,tasks=stored_review
    current=deepcopy(parent);current.update(id='current',started_at='2026-10-23T00:00:00+00:00')
    with service.repository.connect() as db:db.execute('INSERT INTO runs VALUES(?,?)',(current['id'],encode(current)))
    response=client.get('/api/v1/knowledge/business/runs');assert response.status_code==200,response.text
    rows={row['id']:row for row in response.json()['data']['items']}
    assert rows[parent['id']]['started_at'] is None and rows['current']['started_at']==current['started_at']
    assert tasks==[]
