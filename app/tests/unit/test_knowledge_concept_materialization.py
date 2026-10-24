"""Explicit mock child responses exercise persistence, not model quality."""
from copy import deepcopy

import pytest

from app.knowledge import business_concepts, business_run, concept_work
from app.knowledge.business_models import BusinessRunRequest, ConceptRunRequest
from app.tests.unit.test_knowledge_business import finish
from app.tests.unit.test_knowledge_source_concept_preservation import retained_source, whole, offline, natural


@pytest.fixture
def completed_child(retained_source):
    service, parent, donor, client, calls = retained_source
    preview = client.get('/api/v1/knowledge/business/source-concept-preservations/'+parent['id']).json()['data']
    retained = client.post('/api/v1/knowledge/business/source-concept-preservations',json=dict(
        parent_run_id=parent['id'],expected_parent_fingerprint=preview['parent_fingerprint'])).json()['data']
    child = business_concepts.start(service,ConceptRunRequest(parent_run_id=retained['run_id'],
        target_ids=[v['target']['id'] for v in preview['pending']],neighbor_mode='plain',include_events_and_relations=True))
    assert child['status']=='succeeded', child.get('error')
    return service, retained['run_id'], child, client, calls


def preview(client, parent, child):
    return client.get('/api/v1/knowledge/business/concept-view-materializations',params=dict(
        parent_run_id=parent,concept_run_id=child['id']))


def test_completed_child_persists_union_then_enters_existing_reassessment(completed_child):
    service,parent_id,child,client,calls=completed_child
    before=len(calls)
    response=preview(client,parent_id,child);assert response.status_code==200,response.text
    plan=response.json()['data']
    request=dict(parent_run_id=parent_id,concept_run_id=child['id'],expected_parent_fingerprint=plan['parent_fingerprint'],
        expected_child_fingerprint=plan['child_fingerprint'])
    with service.repository.connect() as db:
        parent=service.repository.get(db,'runs',parent_id)
    response=client.post('/api/v1/knowledge/business/concept-view-materializations',json=request)
    assert response.status_code==200,response.text
    result=response.json()['data']
    duplicate=client.post('/api/v1/knowledge/business/concept-view-materializations',json=request).json()['data']
    assert duplicate['run_id']==result['run_id'] and duplicate['duplicate_request']
    with service.repository.connect() as db:
        run=service.repository.get(db,'runs',result['run_id'])
        assert service.repository.get(db,'runs',parent_id)==parent
        assert service.repository.get(db,'runs',child['id'])==child
    assert run['claims']==parent['claims'] and run['graph']==parent['graph']
    targets={c['target']['id'] for c in parent['concepts']}|{c['target']['id'] for c in child['concepts']}
    assert {c['target']['id'] for c in run['concepts']}==targets
    assert run['stored_pool'] and run['source_rebuild_guard'] and run['status']=='partial'
    options=dict(parent['recipe']['options'],source_rebuild_plan_id=None,reassess_run_id=run['id'],resume_run_id=None,
        conceptualize=False,repair=False)
    rechecked=finish(service,service.start_business(BusinessRunRequest(**options))['run_id'])
    assert rechecked['concepts']==run['concepts'] and len(calls)==before
    assert rechecked['source_concept_materialization']['concept_run_id']==child['id']
    assert all(c['status']=='unreviewed' for c in rechecked['concepts'])


@pytest.mark.parametrize('corruption',['incomplete','work','source','duplicate','limits','names'])
def test_incomplete_or_polluted_child_cannot_be_materialized(completed_child,corruption):
    service,parent,child,client,_=completed_child
    value=deepcopy(child)
    if corruption=='incomplete':value['status']='partial'
    elif corruption=='work':next(iter(value['concept_work'].values()))['fingerprint']='wrong'
    elif corruption=='source':value['concepts'][0]['selection']['source_dependencies'][0]['text_sha256']='wrong'
    elif corruption=='limits':value['units'][0]['executed_limits']['max_tokens']+=1
    elif corruption=='names':value['concepts'][0]['concepts']=['not returned by the stored producer']
    else:value['concepts'].append(deepcopy(value['concepts'][0]))
    with service.repository.connect() as db:service.repository.save(db,'runs',value)
    response=preview(client,parent,value)
    assert response.status_code==422,response.text


def test_changed_parent_or_child_fingerprint_is_a_conflict(completed_child):
    _,parent,child,client,_=completed_child
    plan=preview(client,parent,child).json()['data']
    body=dict(parent_run_id=parent,concept_run_id=child['id'],expected_parent_fingerprint=plan['parent_fingerprint'],
        expected_child_fingerprint=plan['child_fingerprint'])
    for field in ['expected_parent_fingerprint','expected_child_fingerprint']:
        response=client.post('/api/v1/knowledge/business/concept-view-materializations',json=dict(body,**{field:'old'}))
        assert response.status_code==409,response.text


@pytest.mark.parametrize('field',['unit','concept','binding'])
def test_retained_parent_must_still_match_original_proofs(completed_child,field):
    service,parent_id,child,client,_=completed_child
    with service.repository.connect() as db:
        parent=service.repository.get(db,'runs',parent_id)
        if field=='unit':parent['units'][0]['response']['text']='changed producer text'
        elif field=='concept':parent['concepts'][0]['concepts']=['changed label']
        else:parent['concept_bindings'][0]['status']='accepted'
        service.repository.save(db,'runs',parent)
    assert preview(client,parent_id,child).status_code==422


def test_replacement_updates_retention_proofs_and_pending_summary(completed_child,monkeypatch):
    service,parent_id,_,client,_=completed_child
    with service.repository.connect() as db:parent=service.repository.get(db,'runs',parent_id)
    observe=business_run.ModelClient.execution_identity
    def upgraded(self,*args,**kwargs):
        value=observe(self,*args,**kwargs);value['engine_version']='fixture_changed_engine';return value
    monkeypatch.setattr(business_run.ModelClient,'execution_identity',upgraded)
    child=business_concepts.start(service,ConceptRunRequest(parent_run_id=parent_id,
        target_ids=[parent['concepts'][0]['target']['id']],neighbor_mode='plain',include_events_and_relations=True))
    assert child['status']=='succeeded'
    plan=preview(client,parent_id,child).json()['data']
    response=client.post('/api/v1/knowledge/business/concept-view-materializations',json=dict(
        parent_run_id=parent_id,concept_run_id=child['id'],expected_parent_fingerprint=plan['parent_fingerprint'],
        expected_child_fingerprint=plan['child_fingerprint']))
    assert response.status_code==200,response.text
    with service.repository.connect() as db:run=service.repository.get(db,'runs',response.json()['data']['run_id'])
    retained=run['source_concept_retention']
    assert retained['retained_targets']==len(parent['concepts'])-1
    assert len(retained['retained_target_ids'])==len(retained['proofs'])==retained['retained_targets']
    assert retained['pending']==parent['source_concept_retention']['pending']
    assert len(run['concepts'])==len(parent['concepts']) and len(run['source_concept_materialization']['proofs'])==1


def test_materialized_pool_reaches_requirement_review_without_reextraction(completed_child,monkeypatch):
    service,parent_id,child,client,calls=completed_child
    plan=preview(client,parent_id,child).json()['data']
    response=client.post('/api/v1/knowledge/business/concept-view-materializations',json=dict(
        parent_run_id=parent_id,concept_run_id=child['id'],expected_parent_fingerprint=plan['parent_fingerprint'],
        expected_child_fingerprint=plan['child_fingerprint']))
    identifier=response.json()['data']['run_id']
    requirement=dict(id='fixture-review',question_ids=['fixture'],question='fixture question',target='fixture',
        situation='fixture',period='fixture',criterion='fixture')
    assert client.put('/api/v1/knowledge/requirements/fixture-review',json=requirement).status_code==200
    observed=[]
    def boundary(service,run,requirement):
        observed.append((len(run['concepts']),bool(run['stored_pool']),run['source_concept_materialization']['concept_run_id']))
        raise RuntimeError('fixture reached requirement review before model dispatch')
    monkeypatch.setattr(business_run,'assess',boundary)
    with service.repository.connect() as db:parent=service.repository.get(db,'runs',identifier)
    before=len(calls)
    options=dict(parent['recipe']['options'],source_rebuild_plan_id=None,reassess_run_id=identifier,resume_run_id=None,
        requirement_ids=['fixture-review'],conceptualize=False,repair=False)
    result=finish(service,service.start_business(BusinessRunRequest(**options))['run_id'])
    assert observed==[(len(parent['concepts']),True,child['id'])] and len(calls)==before
    assert result['status']=='failed' and 'fixture reached requirement review' in result['error']
