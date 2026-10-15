"""Concept-entry source-map/cache checks; model client is a local stub, no native calls."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import json

import pytest

from app.knowledge import autoschema,business_concepts,business_run
from app.knowledge.business_models import ConceptRunRequest
from app.knowledge.service import KnowledgeService


def pool(version):
    block=dict(id='block-'+version,text='기관은 신청을 접수한다.',source_version_id=version,parse_run_id='fixture-parse',locator={})
    chunk=dict(id='legacy-fixed',source_version_id=version,blocks=[block])
    claim=autoschema.graph_record(chunk,'entity_relation',dict(Head='기관',Relation='참여',Tail='신청'),0)
    options=dict(concept_tokens=512,extraction_tokens=8192,review_tokens=4096,context_tokens=49152,think=False,timeout=1800,neighbor_mode='plain',repair=False,conceptualize=True)
    return dict(id=uuid4().hex,kind='business',status='partial',chunks=[chunk],blocks=[block],claims=[claim],graph=autoschema.graph([claim]),
        recipe=dict(models=dict(draft='fixture-stub',review='fixture-stub'),generation={},options=options),model_identity={},
        units=[],concepts=[],metrics=dict(llm_calls=0,model_total_s=0,elapsed_s=0),requirements=[],assessments=[],repairs=[],
        input_version_ids=[version],sources={version:{'title':'fixture'}},stored_pool=True)


@pytest.fixture
def environment(tmp_path,monkeypatch):
    service=KnowledgeService(tmp_path/'candidate.db');requests=[]
    class Stub:
        def __init__(self,*a,**kw):pass
        async def generate(self,request,cancelled=None):
            assert request.stage.startswith('concept_')
            requests.append(request)
            return dict(request_id=request.request_id,text='테스트 유형',failure_kind=None,elapsed_s=0,prompt_eval_count=1,eval_count=1)
    monkeypatch.setattr(business_run,'ModelClient',Stub)
    monkeypatch.setattr('app.knowledge.business_use.publish',lambda *a:dict(id='fixture-changeset'))
    assert Path(business_concepts.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[3])
    try:yield service,requests
    finally:service.shutdown()


def store(service,run):
    with service.repository.connect() as db:db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],json.dumps(run,ensure_ascii=False)))


def plans(run):
    return business_concepts.prepare(run,autoschema.concept_targets(run['graph']),'plain')


def assert_maps(run,expected,first):
    units=run['units'][first:]
    assert len(units)==len(expected)
    for unit,item in zip(units,expected):
        assert unit['reference_map']==item['selection']['source_reference_map']
        assert unit['messages']==item['messages'] and unit['reference_map']


@pytest.mark.parametrize('entry',['refresh_changed','whole_execute'])
def test_entry_same_mapping_reuses_and_different_mapping_does_not(environment,entry):
    service,requests=environment
    run=pool('a');old=plans(run)
    if entry=='whole_execute':
        run['source_projection']=dict(stop_new_requests_at='2099-01-01T00:00:00+00:00',blocks_without_selected_extraction_target=[],unattempted_extraction=[])
    store(service,run)
    def invoke():
        if entry=='refresh_changed':business_concepts.refresh_changed(service,run,{c['id'] for c in run['claims']})
        else:
            business_run.execute(service,run['id'])
            with service.repository.connect() as db:run.update(service.repository.get(db,'runs',run['id']))
            assert run['status']=='succeeded',run.get('error')
    invoke();count=len(old)
    assert len(requests)==count;assert_maps(run,old,0)
    replacement=pool('b')
    for key in ['chunks','blocks','claims','graph','input_version_ids','sources']:run[key]=replacement[key]
    new=plans(run)
    assert [i['target'] for i in old]==[i['target'] for i in new]
    assert [i['messages'] for i in old]==[i['messages'] for i in new]
    assert old[0]['selection']['source_reference_map']!=new[0]['selection']['source_reference_map']
    for concept in run['concepts']:concept['status']='needs_review'
    business_run.save(service,run);invoke()
    assert len(requests)==2*count;assert_maps(run,new,count)
    for concept in run['concepts']:concept['status']='needs_review'
    business_run.save(service,run);invoke()
    assert len(requests)==2*count;assert_maps(run,new,2*count)
    assert all(u.get('reused_from') for u in run['units'][2*count:])


def test_selected_entity_start_passes_actual_plan_source_map(environment):
    service,requests=environment;parent=pool('b');store(service,parent)
    target=next(t for t in autoschema.concept_targets(parent['graph']) if t['kind']=='entity')
    req=ConceptRunRequest(parent_run_id=parent['id'],target_ids=[target['id']],neighbor_mode='plain')
    expected=business_concepts.plan(service,req)[1]
    run=business_concepts.start(service,req)
    assert run['status']=='succeeded' and len(requests)==1
    assert_maps(run,expected,0)
    assert run['concepts'][0]['selection']==expected[0]['selection']
