"""Synthetic fixtures only; preparation does not invoke a model or token counter."""
from copy import deepcopy
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import knowledge
from app.knowledge import autoschema, business_candidate_review as limited, business_review, business_store, business_use, concept_work
from app.knowledge.business_models import RequirementInput
from app.tests.unit.test_knowledge_interpretation_edit import editing


@pytest.fixture
def prepared_input(editing, monkeypatch):
    service,parent,_,_=editing
    third=deepcopy(parent['claims'][0]);third['id']='third'
    parent['claims'].append(third)
    req=business_store.put_requirement(service,RequirementInput(id='r',question_ids=['Q'],question='기관의 접수 조건은?',
        criterion='자기 원문에 맞게 비교한다.',target='기관',situation='신청',period='저장 버전',source_ids=['source']))
    parent.update(requirements=[req],answer_items=[dict(id='item',requirement_id='r',requirement_revision=1,
        field='question',request_quote='접수 조건')],requirement_link=dict(usage='review_draft_only',model_work_submitted=False))
    parent['graph']=autoschema.graph(parent['claims'],parent['blocks'])
    parent['stored_pool']={kind+'_hash':autoschema.identifier(kind,parent[field])
        for field,kind in [('claims','claims'),('blocks','source'),('graph','graph')]}
    with service.repository.connect() as db:
        version=service.repository.get(db,'versions','v');version['processing_status']='parsed'
        service.repository.save(db,'versions',version)
        service.repository.save(db,'runs',parent)
    payload=dict(expected_parent_fingerprint=concept_work.digest(parent),requirement_id='r',expected_requirement_revision=1,
        claim_ids=[c['id'] for c in parent['claims']],idempotency_key='fixture-only',actor='fixture reviewer',reason='합성 범위 검증')
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    return service,parent,payload,TestClient(app)


def prepare(data):
    _,parent,payload,client=data
    reply=client.post('/api/v1/knowledge/business/runs/'+parent['id']+'/candidate-review-preparations',json=payload)
    assert reply.status_code==200,reply.text
    return reply.json()['data']['run_id']


def test_prepare_persists_only_a_frozen_draft_and_exact_duplicate(prepared_input):
    service,parent,payload,client=prepared_input
    before=business_review.candidate_request(parent,parent['claims'])
    rid=prepare(prepared_input);child=service.run(rid);scope=child['candidate_review_scope']
    assert scope['phase']=='prepared' and scope['claim_ids']==payload['claim_ids']
    assert scope['executed_unit_ids']==[] and child['metrics']['llm_calls']==0
    for field in ['claims','blocks','sources','graph','concepts','concept_work','units','candidate_reviews',
                  'requirements','answer_items','recipe','requirement_link']:
        assert child[field]==parent[field]
    assert child['assessments']==[] and 'changeset_id' not in child
    assert business_use.eligibility(child)[0]==set()
    assert service.run(parent['id'])['claims']==parent['claims']
    assert prepare(prepared_input)==rid
    reply=client.post('/api/v1/knowledge/business/runs/'+parent['id']+'/candidate-review-preparations',
        json=dict(payload,reason='different'))
    assert reply.status_code==409
    assert business_review.candidate_request(parent,parent['claims'])==before
    assert client.get('/api/v1/knowledge/runs/'+rid).json()['data']['candidate_review_scope']==scope
    assert business_use.snapshots(service)['items']==[]


@pytest.mark.parametrize('fault',['parent','revision','duplicate','outside','four','source_version','quote',
    'missing_evidence','foreign_evidence','approved_parent','assessed_parent','pool'])
def test_bad_basis_cannot_create_a_preparation(prepared_input,fault):
    service,parent,payload,client=prepared_input
    if fault=='parent':payload['expected_parent_fingerprint']='stale'
    elif fault=='revision':payload['expected_requirement_revision']=2
    elif fault=='duplicate':payload['claim_ids'][1]=payload['claim_ids'][0]
    elif fault=='outside':payload['claim_ids'][0]='outside'
    elif fault=='four':payload['claim_ids'].append('four')
    elif fault=='source_version':
        with service.repository.connect() as db:
            version=service.repository.get(db,'versions','v');version['sha256']='changed'
            service.repository.save(db,'versions',version)
    else:
        claim=parent['claims'][0]
        if fault=='quote':claim['interpretation']['meanings'][0]['evidence'][0]['quote']='원문에 없음'
        elif fault=='missing_evidence':claim['evidence']=[]
        elif fault=='foreign_evidence':claim['evidence'][0]['source_version_id']='foreign'
        elif fault=='approved_parent':parent['requirement_link']={}
        elif fault=='assessed_parent':parent['assessments']=[dict(id='historical')]
        else:parent['stored_pool']['claims_hash']='stale'
        if fault!='pool':parent['stored_pool']['claims_hash']=autoschema.identifier('claims',parent['claims'])
        with service.repository.connect() as db:service.repository.save(db,'runs',parent)
        payload['expected_parent_fingerprint']=concept_work.digest(parent)
    reply=client.post('/api/v1/knowledge/business/runs/'+parent['id']+'/candidate-review-preparations',json=payload)
    assert reply.status_code in {409,422},reply.text
    with service.repository.connect() as db:assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==1


def runtime_stubs(monkeypatch, service, parent, *, mode='supported'):
    from app.knowledge import business_run
    calls=[];tasks=[]
    monkeypatch.setattr(service.executor,'submit',lambda fn,*args:tasks.append((fn,args)))
    monkeypatch.setattr(business_run.ModelClient,'identities',lambda *a,**k:
        {'changed':'fixture'} if mode=='identity' else deepcopy(parent['model_identity']))
    monkeypatch.setattr(business_run,'request_budget',lambda *a,**k:dict(estimate_tokens=100,prompt_exact=mode!='unverified'))
    async def generate(self,request,cancelled=None):
        content=json.loads(request.messages[-1]['content'])
        calls.append(content)
        if mode=='transport':raise RuntimeError('fixture transport failure')
        checks=[dict(claim_id=c['id'],claim_support='supported',error_fields=[],error_evidence=[],
            evidence=[content['blocks'][0]['evidence_ref']],reason='합성 fixture 판정') for c in content['claims']]
        if mode=='unknown':
            for check in checks:check.update(claim_support='unknown',error_fields=['interpretation.meanings.0.modality'],
                error_evidence=[content['blocks'][0]['evidence_ref']])
        if mode=='outside':checks.append(dict(checks[0],claim_id='outside'))
        preservation=[]
        for view in content.get('preservation_views',[]):
            field=next(iter(view['before_fields']));after_id=next(iter(view['after_fields']))
            preservation.append(dict(target_id=view['target_id'],status='unknown',before_normal_meanings=[],
                after_locations=[],reason='합성 입력 전달 검사',comparisons=[dict(change='unknown',
                    before_field=field,before_quote=view['before_fields'][field],after_id=after_id,after_field=field,
                    after_quote=view['after_fields'][after_id][field],source_block_ids=[content['blocks'][0]['id']],
                    before_source_status='unknown',same_normal_meaning=None,reason='의미 검증 결과가 아닌 대역 응답')]))
        return dict(failure_kind=None,elapsed_s=0,parsed=dict(checks=checks,preservation_checks=preservation))
    monkeypatch.setattr(business_run.ModelClient,'generate',generate)
    def denied(*a,**k):pytest.fail('No chained source/R/repair/concept/QA/publication work')
    for owner,names in [(business_run,['execute','assess','repair','reassess_challenges']),
                        (business_review,['source','public_requirement_scope','public_source_scope','represent','review_candidate_pool']),
                        (business_use,['publish','decide'])]:
        for name in names:monkeypatch.setattr(owner,name,denied)
    return calls,tasks


@pytest.mark.parametrize('mode',['supported','unknown','outside','transport','unverified','identity'])
def test_execution_is_one_synthetic_candidate_call_then_stops(prepared_input,monkeypatch,mode):
    service,parent,payload,client=prepared_input;rid=prepare(prepared_input)
    scope=service.run(rid)['candidate_review_scope'];calls,tasks=runtime_stubs(monkeypatch,service,parent,mode=mode)
    url='/api/v1/knowledge/business/runs/'+rid+'/candidate-review-execution'
    body=dict(expected_input_fingerprint=scope['input_fingerprint'])
    assert client.post(url,json=body).status_code==200
    assert client.post(url,json=body).json()['data']['duplicate_request']
    assert len(tasks)==1
    fn,args=tasks[0];fn(*args)
    child=service.run(rid)
    assert len(calls)==(0 if mode in {'unverified','identity'} else 1)
    if calls:assert len(calls[0]['claims'])==3
    assert child['candidate_review_scope']['phase']==('completed' if mode in {'supported','unknown'} else 'failed')
    if mode=='transport':assert child['units'][-1]['status']=='failed'
    assert child['claims']==parent['claims'] and child['graph']==parent['graph']
    assert child['assessments']==[] and child['requirement_link']==parent['requirement_link']
    assert 'changeset_id' not in child and business_use.eligibility(child)[0]==set()
    assert business_use.snapshots(service)['items']==[]
    assert client.post(url,json=body).json()['data']['duplicate_request']
    assert len(tasks)==1


@pytest.mark.parametrize('fault',['parent','requirement','packet','selection','context','contract','busy','submission'])
def test_changed_preparation_and_submission_failure_do_not_dispatch_twice(prepared_input,monkeypatch,fault):
    service,parent,_,client=prepared_input;rid=prepare(prepared_input)
    child=service.run(rid);child.pop('counts',None);scope=child['candidate_review_scope']
    if fault=='parent':parent['metrics']={'changed':True}
    elif fault=='packet':scope['packet']['messages'][0]['content']='changed'
    elif fault=='selection':scope['claim_ids']=['outside']
    elif fault=='context':scope['source_block_ids']=[]
    elif fault=='contract':scope['input_contract']='different'
    with service.repository.connect() as db:
        service.repository.save(db,'runs',parent)
        service.repository.save(db,'runs',child)
        if fault=='requirement':
            req=service.repository.get(db,'requirements','r');req['revision']=2
            service.repository.save(db,'requirements',req)
        if fault=='busy':
            busy=dict(deepcopy(parent),id='busy',status='running');db.execute('INSERT INTO runs VALUES(?,?)',('busy',json.dumps(busy)))
    if fault=='submission':
        def broken(*a,**k):raise RuntimeError('fixture executor unavailable')
        monkeypatch.setattr(service.executor,'submit',broken)
        with pytest.raises(RuntimeError):
            client.post('/api/v1/knowledge/business/runs/'+rid+'/candidate-review-execution',
                json=dict(expected_input_fingerprint=scope['input_fingerprint']))
        assert service.run(rid)['candidate_review_scope']['phase']=='failed'
    else:
        reply=client.post('/api/v1/knowledge/business/runs/'+rid+'/candidate-review-execution',
            json=dict(expected_input_fingerprint=scope['input_fingerprint']))
        assert reply.status_code==409,reply.text


def test_nonempty_repair_context_is_the_same_frozen_and_executed_input(prepared_input,monkeypatch):
    from app.knowledge import business_run
    service,parent,payload,client=prepared_input
    parent['prior_repairs']=[dict(id='synthetic-preservation',changes=[dict(before=deepcopy(parent['claims'][0]),
        after=deepcopy(parent['claims'][0]))])]
    with service.repository.connect() as db:service.repository.save(db,'runs',parent)
    payload['expected_parent_fingerprint']=concept_work.digest(parent)
    rid=prepare(prepared_input);run=service.run(rid);scope=run['candidate_review_scope']
    context=business_review.candidate_repair_context(run,set(payload['claim_ids']));assert context
    instruction,content,schema=business_review.candidate_request(run,run['claims'],context)
    assert business_run.json_request(run,'candidate_source_review',instruction,content,schema)==scope['packet']
    calls,tasks=runtime_stubs(monkeypatch,service,parent)
    assert client.post('/api/v1/knowledge/business/runs/'+rid+'/candidate-review-execution',
        json=dict(expected_input_fingerprint=scope['input_fingerprint'])).status_code==200
    fn,args=tasks[0];fn(*args)
    assert len(calls)==1 and calls[0]['repair_context'] and calls[0]['preservation_views']
    final=service.run(rid)
    assert final['candidate_review_scope']['phase']=='completed', (final.get('error'), final['units'][-1].get('error'), final['candidate_reviews'][-1]['errors'])


def test_cancelled_queued_review_stops_without_invocation(prepared_input,monkeypatch):
    service,parent,_,client=prepared_input;rid=prepare(prepared_input)
    scope=service.run(rid)['candidate_review_scope'];calls,tasks=runtime_stubs(monkeypatch,service,parent)
    client.post('/api/v1/knowledge/business/runs/'+rid+'/candidate-review-execution',
        json=dict(expected_input_fingerprint=scope['input_fingerprint']))
    service.cancel(rid)
    fn,args=tasks[0];fn(*args)
    assert not calls and service.run(rid)['status']=='cancelled'
    with service.repository.connect() as db:assert not service.repository.has_active_runs(db)
