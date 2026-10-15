"""Product work/binding behavior; all generation and runtime HTTP use local stubs."""
from copy import deepcopy
import json

import httpx
import pytest

from app.generation.model_client import ModelClient
from app.knowledge import business_concepts, business_run, concept_work
from app.knowledge.business_models import ConceptRunRequest
from app.knowledge.service import KnowledgeConflict
from app.tests.unit.test_knowledge_concept_source_map_entrypoints import environment, pool, plans, store


def setup(environment):
    service, requests = environment
    run = pool('v');store(service,run)
    return service, requests, run, plans(run)[0]


def another_target(item):
    other = deepcopy(item)
    other['target']['id'] = 'separate-stored-target'
    return other


def test_identical_original_request_shares_work_without_merging_targets(environment):
    service, requests, run, item = setup(environment)
    original = deepcopy(item['target'])
    first = business_concepts.apply(service,run,item)
    second = business_concepts.apply(service,run,another_target(item))
    assert len(requests)==1 and run['metrics']['llm_calls']==1
    assert len(run['concept_work'])==1 and len(run['concept_bindings'])==2
    assert first['work_id']==second['work_id']
    assert first['target']==original and second['target']['id']=='separate-stored-target'
    assert first['status']==second['status']=='unreviewed'
    assert not first['approved_is_a'] and not second['approved_is_a']
    assert run['units'][1]['reused_from']['unit_id']==run['units'][0]['id']
    assert run['units'][1]['response']==run['units'][0]['response']
    assert run['concept_bindings'][1]['source_reference_map']==item['selection']['source_reference_map']


def test_unknown_runtime_retains_existing_approval_without_new_binding(environment,monkeypatch):
    service, requests, run, item = setup(environment)
    result = business_concepts.apply(service,run,item)
    result['status']='accepted';run['concept_bindings'][0]['status']='accepted'
    monkeypatch.setattr(business_run.ModelClient,'execution_identity',lambda *a,**k: None)
    assert business_concepts.apply(service,run,item) is result
    assert len(requests)==1 and result['status']=='accepted'
    assert len(run['concept_bindings'])==1 and run['concept_bindings'][0]['status']=='accepted'
    assert not run['concept_link_checks'][0]['new_work_connected']
    assert run['concept_link_checks'][0]['unknown_contract_fields']


def test_unknown_runtime_never_shares_a_new_target(environment,monkeypatch):
    service, requests, run, item = setup(environment)
    monkeypatch.setattr(business_run.ModelClient,'execution_identity',lambda *a,**k: None)
    business_concepts.apply(service,run,item)
    business_concepts.apply(service,run,another_target(item))
    assert len(requests)==2 and len(run['concept_work'])==2
    assert not any(u.get('reused_from') for u in run['units'])


def test_same_target_changed_source_is_refreshed_and_binding_tracks_status(environment):
    service, requests, run, item = setup(environment)
    old = business_concepts.apply(service,run,item)
    run['chunks'][0]['blocks'][0]['text'] += ' 추가 조건을 따른다.'
    changed = plans(run)[0]
    assert changed['target']==item['target'] and changed['messages']!=item['messages']
    new = business_concepts.apply(service,run,changed,refreshed=True)
    assert len(requests)==2 and old['status']=='needs_review' and new['status']=='unreviewed'
    assert run['concept_bindings'][0]['status']==old['status']
    assert run['concept_bindings'][0]['previous_status']=='unreviewed'
    assert run['concept_bindings'][1]['status']==new['status']
    assert old['target']==new['target']


def test_changed_input_keeps_history_but_consumers_use_current_revision(environment,monkeypatch):
    from app.knowledge import business_use, graph_retrieval
    service, requests, run, item = setup(environment)
    original=business_run.ModelClient.generate
    async def labelled(self,request,cancelled=None):
        result=await original(self,request,cancelled)
        result['text']='이전 전용 개념' if len(requests)==1 else '새 전용 개념'
        return result
    monkeypatch.setattr(business_run.ModelClient,'generate',labelled)
    old=business_concepts.apply(service,run,item)
    run['chunks'][0]['blocks'][0]['text']+=' 새 조건.'
    business_concepts.apply(service,run,plans(run)[0],refreshed=True)
    assert old in run['concepts'] and old['concepts']==['이전 전용 개념']
    graph,_,_,_=graph_retrieval.build(run,'full')
    labels={n['label'] for _,n in graph.nodes(data=True) if n['kind']=='concept'}
    assert labels=={'새 전용 개념'}
    hints=business_use.concept_hints(run)
    assert all('이전 전용 개념' not in values for values in hints.values())
    assert any('새 전용 개념' in values for values in hints.values())


def test_explicit_discard_is_not_reusable(environment):
    service, requests, run, item = setup(environment)
    old = business_concepts.apply(service,run,item)
    old['status']='rejected';old['discarded']=True
    business_concepts.apply(service,run,another_target(item))
    assert len(requests)==2 and not run['units'][-1].get('reused_from')


@pytest.mark.parametrize('fault',['truncated','empty','failed'])
def test_incomplete_outputs_are_kept_but_never_reused(environment,monkeypatch,fault):
    service, requests, run, item = setup(environment)
    original = business_run.ModelClient.generate
    async def damaged(self,request,cancelled=None):
        response = await original(self,request,cancelled)
        if fault=='truncated':response.update(done=False,done_reason='length',failure_kind='truncated')
        elif fault=='empty':response['text']=' , '
        else:response.update(failure_kind='cancelled')
        return response
    monkeypatch.setattr(business_run.ModelClient,'generate',damaged)
    result = business_concepts.apply(service,run,item)
    assert result['status']=='failed' and run['units'][0].get('response')
    monkeypatch.setattr(business_run.ModelClient,'generate',original)
    business_concepts.apply(service,run,another_target(item))
    assert len(requests)==2 and not run['units'][-1].get('reused_from')


@pytest.mark.parametrize('field',['engine_version','precision','sampling','unknown_defaults'])
def test_changed_runtime_contract_cannot_share_work(environment,monkeypatch,field):
    service, requests, run, item = setup(environment)
    old = business_concepts.apply(service,run,item)
    observe = business_run.ModelClient.execution_identity
    def changed(self,*args,**kwargs):
        result = observe(self,*args,**kwargs)
        if field=='engine_version':result['engine_version']='other'
        elif field=='precision':result['precision']['weights']='other'
        elif field=='sampling':result['sampling']['model_parameters']='other defaults'
        else:result['sampling']['model_parameters']=None
        return result
    monkeypatch.setattr(business_run.ModelClient,'execution_identity',changed)
    business_concepts.apply(service,run,another_target(item))
    assert len(requests)==2 and old['status']=='unreviewed'
    assert len(run['concept_work'])==2


def test_model_tag_digest_change_stops_before_generation(environment,monkeypatch):
    service, requests, run, item = setup(environment)
    observe = business_run.ModelClient.execution_identity
    def changed(self,*args,**kwargs):
        result=observe(self,*args,**kwargs);result['model_digest']='c'*64;return result
    monkeypatch.setattr(business_run.ModelClient,'execution_identity',changed)
    with pytest.raises(KnowledgeConflict,match='digest'):
        business_concepts.apply(service,run,item)
    assert not requests and not run['units']


def test_parent_donor_uses_same_product_start_and_keeps_parent_unchanged(environment):
    service, requests, parent, item = setup(environment)
    business_concepts.apply(service,parent,item)
    before=deepcopy(parent)
    request=ConceptRunRequest(parent_run_id=parent['id'],target_ids=[item['target']['id']],neighbor_mode='plain')
    child=business_concepts.start(service,request)
    assert child['status']=='succeeded',child.get('error')
    assert len(requests)==1 and child['metrics']['llm_calls']==0
    assert child['units'][0]['reused_from']['run_id']==parent['id']
    assert child['concepts'][0]['status']=='unreviewed' and child['concept_bindings'][0]['target_id']==item['target']['id']
    with service.repository.connect() as db:assert service.repository.get(db,'runs',parent['id'])==before


def test_explicit_completed_concept_donor_reuses_actual_product_response(environment):
    service, requests, parent, item = setup(environment)
    request=ConceptRunRequest(parent_run_id=parent['id'],target_ids=[item['target']['id']],neighbor_mode='plain')
    donor=business_concepts.start(service,request)
    request.donor_run_id=donor['id']
    receiver=business_concepts.start(service,request)
    assert donor['status']==receiver['status']=='succeeded'
    assert len(requests)==1 and receiver['metrics']['llm_calls']==0
    assert receiver['units'][0]['reused_from']['run_id']==donor['id']
    assert donor['units'][0]['response']==receiver['units'][0]['response']
    with service.repository.connect() as db:assert service.repository.get(db,'runs',donor['id'])==donor


def test_raw_response_saved_before_binding_recovers_without_generation(environment):
    service, requests, run, item = setup(environment)
    expected=deepcopy(item['work_input'])
    expected['runtime']=business_run.ModelClient({}).execution_identity('fixture-stub',0,max_tokens=512,context_tokens=49152,think=False)
    business_run.call(service,run,expected['stage'],item['messages'],max_tokens=512,
        reference_map=item['selection']['source_reference_map'],concept_work_input=expected)
    assert not run['concepts'] and len(requests)==1
    business_concepts.apply(service,run,item);business_concepts.apply(service,run,item)
    assert len(requests)==1 and len(run['concepts'])==1 and len(run['concept_bindings'])==1
    assert len(run['concept_work'])==1


def test_stale_work_contract_is_rejected_before_any_generation(environment):
    service, requests, run, item = setup(environment)
    expected=deepcopy(item['work_input']);expected['messages_sha256']='wrong'
    with pytest.raises(ValueError,match='실제 요청'):
        business_run.call(service,run,expected['stage'],item['messages'],max_tokens=512,
            reference_map=item['selection']['source_reference_map'],concept_work_input=expected)
    assert not requests and not run['units']


def test_legacy_direct_call_keeps_legacy_reuse_without_claiming_F1(environment):
    service, requests, run, item = setup(environment)
    run['recipe'].pop('concept_work_contract')
    for _ in range(2):
        business_run.call(service,run,'concept_entity',item['messages'],max_tokens=512,
            reference_map=item['selection']['source_reference_map'])
    assert len(requests)==1 and run['units'][1].get('reused_from')
    assert run['units'][1]['concept_reuse_contract']=='legacy'
    assert run['units'][1]['concept_work_input'] is None and not run.get('concept_bindings')


def test_reading_old_run_does_not_opt_in_or_reexecute_completed_targets(environment):
    service, requests, run, item = setup(environment)
    run['recipe'].pop('concept_work_contract')
    business_concepts.apply_selected_contract(service,run,item,refreshed=True)
    before=deepcopy(run)
    business_concepts.apply_selected_contract(service,run,item,refreshed=True)
    assert len(requests)==1 and run==before
    assert not run.get('concept_work') and not run.get('concept_bindings')


def test_runtime_contract_reads_provider_metadata_and_does_not_generate():
    paths=[]
    def handler(request):
        paths.append(request.url.path)
        if request.url.path=='/api/version':return httpx.Response(200,json=dict(version='observed'))
        if request.url.path=='/api/tags':return httpx.Response(200,json=dict(models=[dict(name='model',digest='d',details=dict(quantization_level='Q4'))]))
        assert request.url.path=='/api/show' and json.loads(request.content)==dict(model='model')
        return httpx.Response(200,json=dict(parameters='top_k 64',template='template',model_info={'context_length':49152}))
    client=ModelClient(dict(provider='ollama',endpoint='http://localhost:11434'),transport=httpx.MockTransport(handler))
    result=client.execution_identity('model',0,max_tokens=512,context_tokens=49152,think=False)
    assert paths==['/api/version','/api/tags','/api/show']
    assert result['model_digest']=='d' and result['precision']['weights']=='Q4'
    assert result['sampling']['request_options']==dict(temperature=0,num_predict=512,num_ctx=49152)
    assert result['sampling']['model_parameters']=='top_k 64'


def test_resume_of_legacy_parent_keeps_recorded_contract_before_any_worker(environment,monkeypatch):
    from app.knowledge.business_models import BusinessRunRequest
    service,requests,parent,_=setup(environment)
    parent['recipe'].pop('concept_work_contract')
    for block in parent['blocks']:block['source_id']='source'
    with service.repository.connect() as db:
        service.repository.save(db,'runs',parent)
        db.execute('INSERT INTO sources VALUES(?,?,?,?)',('source','fixture','fixture',json.dumps(dict(id='source',title='fixture'))))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)',('v','source','fixture',json.dumps(dict(id='v',processing_status='parsed',source_id='source',
            filename='fixture.txt',sha256='fixture',dates=[],latest_parse_run_id='parse'))))
    monkeypatch.setattr(service,'parse_blocks',lambda *a:deepcopy(parent['blocks']))
    monkeypatch.setattr(service.executor,'submit',lambda *a:None)
    monkeypatch.setattr(business_run.ModelClient,'identities',lambda *a:deepcopy(parent['model_identity']),raising=False)
    result=business_run.start(service,BusinessRunRequest(source_version_ids=['v'],resume_run_id=parent['id']))
    with service.repository.connect() as db:
        child=service.repository.get(db,'runs',result['run_id'])
        assert service.repository.get(db,'runs',parent['id'])==parent
    assert child['recipe']['concept_work_contract']=='legacy' and child['status']=='queued'
    assert requests==[]
