"""Explicit interpretation corrections keep producer records and never run models."""
from copy import deepcopy

import pytest
from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import knowledge
from app.generation import model_input_budget
from app.generation.model_client import ModelClient
from app.knowledge import autoschema, business_review, business_run, business_use, concept_work, interpretation_edit
from app.knowledge.business_models import InterpretationEditRequest
from app.knowledge.service import KnowledgeConflict, KnowledgeService, encode
from app.tests.unit.test_knowledge_business_scope import block, scope_for


@pytest.fixture
def editing(tmp_path, monkeypatch):
    text = '기관은 본인이 신청한 경우 접수할 수 있다.'
    blocks = [dict(block('body', text), source_id='source')]
    chunk = autoschema.chunks(blocks, 49152, 8192)[0]
    scope = scope_for(chunk, text)
    scope['meanings'][0]['conditions'] = dict(state='present', text='null')
    claim = autoschema.graph_record(chunk, 'entity_relation', dict(Head='기관',Relation='접수',Tail='신청'),0,scope=scope)
    sibling = deepcopy(claim); sibling['id'] = 'sibling'
    graph = autoschema.graph([claim, sibling], blocks)
    targets = autoschema.concept_targets(graph)
    run = dict(id='parent',kind='business',status='partial',claims=[claim,sibling],blocks=blocks,chunks=[chunk],
        sources={'v':dict(title='합성 원문',sha256='fixture')},input_version_ids=['v'],requirements=[],assessments=[],
        units=[],candidate_reviews=[],repairs=[],graph=graph,
        model_identity={},recipe=dict(generation=dict(provider='ollama',endpoint='http://localhost:11434'),
            models=dict(review='fixture',draft='fixture'),review_contract=business_review.SOURCE_APPLICATION_CONTRACT,
            options=dict(neighbor_mode='plain',context_tokens=49152,review_tokens=8192,think=False,timeout=30)),
        concepts=[dict(id='concept'+str(n),target=target,status='unreviewed',approved_is_a=False,relation='has_concept')
            for n,target in enumerate(targets)],
        concept_bindings=[dict(concept_id='concept'+str(n),status='unreviewed') for n in range(len(targets))],
        concept_work={'producer':dict(status='complete')})
    service = KnowledgeService(tmp_path/'knowledge.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO sources VALUES(?,?,?,?)',('source','fixture',None,encode(dict(id='source'))))
        db.execute('INSERT INTO versions(id,source_id,sha256,payload) VALUES(?,?,?,?)',
                   ('v','source','fixture',encode(dict(id='v',sha256='fixture'))))
        db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
    change = business_use.publish(service,run)
    m=claim['interpretation']['meanings'][0]
    payload=dict(expected_revision=0,idempotency_key='fixture-key',actor='explicit fixture reviewer',reason='원문 한정 정정',
        claims=[dict(claim_id=claim['id'],expected_claim_version=autoschema.identifier('claim',claim),
            expected_source_fingerprint=interpretation_edit.source_fingerprint(run,claim),
            changes=[dict(meaning_id=m['id'],expected_meaning_version=concept_work.digest(m),field='conditions',
                before=m['conditions'],after=dict(state='present',text='본인이 신청한 경우'),
                evidence=[dict(block_id='body',quote=text)],reason='실제 조건 문구 보존')])])
    def denied(*a,**k):pytest.fail('No model/counter/automatic work in an explicit field edit')
    monkeypatch.setattr(service.executor,'submit',denied)
    monkeypatch.setattr(ModelClient,'generate',denied)
    monkeypatch.setattr(ModelClient,'identities',denied)
    monkeypatch.setattr(model_input_budget,'count',denied)
    yield service,run,change,payload
    service.shutdown()


def test_api_saves_only_current_field_with_history_ids_and_no_approval(editing,monkeypatch):
    service,parent,change,payload=editing
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    client=TestClient(app);url='/api/v1/knowledge/business/changes/'+change['id']+'/interpretation-edits'
    reply=client.post(url,json=payload);assert reply.status_code==200,reply.text
    result=reply.json()['data'];child=service.run(result['run_id']);old=parent['claims'][0];new=child['claims'][0]
    assert result['changeset_revision']==business_use.change_view(service,result['changeset_id'])['revision']==0
    assert result['parent_changeset_revision']==1
    assert new['raw']==old['raw'] and new['evidence']==old['evidence'] and child['blocks']==parent['blocks']
    assert child['claims'][1]==parent['claims'][1]
    assert new['interpretation']['raw']==old['interpretation']['raw']
    assert new['interpretation_history'][-1]==old['interpretation']
    a,b=old['interpretation']['meanings'][0],new['interpretation']['meanings'][0]
    assert b['conditions']==dict(state='present',text='본인이 신청한 경우') and a['id']!=b['id']
    assert b['modality']==a['modality'] and b['evidence']==a['evidence']
    assert old['interpretation']['meanings'][0]['id'] not in str(new['interpretation']['mentions'])
    compact=business_run.compact_claim(new)['interpretation']
    assert 'raw' not in compact and compact['meanings'][0]['conditions']==b['conditions']
    assert new['review_status']=='unreviewed' and new['semantic_status']=='unknown'
    assert child['metrics']['llm_calls']==0 and child['concept_work']==parent['concept_work']
    assert child['interpretation_edit']['affected_concept_ids']
    assert business_use.change_view(service,result['changeset_id'])['eligible_ids']==[]
    assert client.post(url,json=payload).json()['data']['duplicate_request']
    assert service.run(parent['id'])['claims']==parent['claims']
    assert business_use.snapshots(service)['items']==[]


@pytest.mark.parametrize('fault',['revision','claim_version','source','meaning','before','quote','other_claim'])
def test_conflict_or_foreign_evidence_leaves_everything_unchanged(editing,fault):
    service,parent,change,payload=editing
    item=payload['claims'][0];patch=item['changes'][0]
    if fault=='revision':payload['expected_revision']=99
    elif fault=='claim_version':item['expected_claim_version']='stale'
    elif fault=='source':item['expected_source_fingerprint']='stale'
    elif fault=='meaning':patch['expected_meaning_version']='stale'
    elif fault=='before':patch['before']=dict(state='absent',text=None)
    elif fault=='quote':patch['evidence'][0]['quote']='원문에 없음'
    else:item['claim_id']='missing'
    with pytest.raises((KnowledgeConflict,ValueError)):
        interpretation_edit.start(service,change['id'],InterpretationEditRequest(**payload))
    assert service.run(parent['id'])['claims']==parent['claims']
    assert business_use.change_view(service,change['id'])['revision']==0
    with service.repository.connect() as db:assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==1


def test_reusing_key_with_different_edit_is_conflict(editing):
    service,_,change,payload=editing
    interpretation_edit.start(service,change['id'],InterpretationEditRequest(**payload))
    payload['reason']='다른 요청'
    with pytest.raises(KnowledgeConflict):
        interpretation_edit.start(service,change['id'],InterpretationEditRequest(**payload))


def test_snapshot_invalidation_uses_requirement_ids_not_assessment_ids(editing):
    service,parent,change,payload=editing
    requirement=dict(id='r',revision=1,status='partial',source_ids=[])
    parent['requirements']=[requirement]
    source=dict(meanings=[])
    fingerprint=business_run.assessment_fingerprint(parent,requirement,source)
    parent['assessments']=[dict(id=i,requirement_id='r',source=source,representation=dict(checks=[]),
        status='partial',input_fingerprint=fingerprint) for i in ['assessment-one','assessment-two']]
    with service.repository.connect() as db:
        db.execute('INSERT INTO requirements VALUES(?,?)',('r',encode(requirement)))
        service.repository.save(db,'runs',parent)
        db.execute('INSERT INTO snapshots VALUES(?,?)',('fixture',encode(dict(
            id='fixture',run_id=parent['id'],kind='source_graph',claims=parent['claims']))))
    child=service.run(interpretation_edit.start(service,change['id'],InterpretationEditRequest(**payload))['run_id'])
    assert child['assessments']==parent['assessments']
    assert child['interpretation_edit']['affected_assessment_ids']==['assessment-one','assessment-two']
    with service.repository.connect() as db:
        import json
        event=json.loads(db.execute('SELECT payload FROM snapshot_events').fetchone()[0])
    assert event['requirement_ids']==['r']


def test_preserved_supported_receipt_is_not_a_current_review_after_edit(editing,monkeypatch):
    from app.tests.unit.test_knowledge_candidate_review_resume import own_review
    service,parent,change,payload=editing
    receipt=own_review(monkeypatch,service,parent)
    cid=parent['claims'][0]['id']
    assert cid in business_review.current_candidate_reviews(parent)
    with service.repository.connect() as db:service.repository.save(db,'runs',parent)
    child=service.run(interpretation_edit.start(service,change['id'],InterpretationEditRequest(**payload))['run_id'])
    assert child['candidate_reviews']==parent['candidate_reviews']
    assert child['candidate_reviews'][0]['checks'][0]['claim_support'][cid]=='supported'
    assert cid not in business_review.current_candidate_reviews(child)
    assert receipt['id'] in child['interpretation_edit']['affected_candidate_review_ids']


@pytest.mark.parametrize('field,after',[('raw','수정불가'),('modality','permission'),('relation_kind','new_type'),
    ('conditions',dict(state='present',text='null'))])
def test_only_existing_conditions_and_relation_kind_types_are_allowed(editing,field,after):
    payload=editing[-1];payload['claims'][0]['changes'][0].update(field=field,after=after)
    with pytest.raises(ValidationError):InterpretationEditRequest(**payload)
