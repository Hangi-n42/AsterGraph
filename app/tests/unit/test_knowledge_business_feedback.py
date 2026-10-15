"""QA gaps are version-bound observations, not candidate or source corrections."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.knowledge import autoschema, business_feedback as feedback, business_review as review, business_run, business_use
from app.knowledge.business_models import BusinessAnswerRecheck
from app.knowledge.service import KnowledgeConflict, KnowledgeService, encode, utcnow
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning


@pytest.fixture
def bound():
    run=local_run()
    req=dict(run['requirements'][0],question_ids=['q'],question='접수 안내는?',criterion='조건 보존',target='이용자',
        situation='개인·단체',period='제공 문서',required=True,status='partial',history=[],current_assessment=dict(run_id='parent'))
    run.update(id='parent',kind='business',status='partial',requirements=[req],model_identity={},
        sources={'v':{'source_id':'s'}},input_version_ids=['v'],concepts=[],graph={'nodes':[],'edges':[]})
    run['recipe'].update(review_contract=review.CONTRACT,generation={},models={})
    run['answer_items']=[dict(id='item',requirement_id='r',requirement_revision=1,field='question',request_quote='접수 안내')]
    tasks=review.public_item_tasks(run,req)
    m=meaning('m',required_for_requirement=True)
    m['evidence']=business_run.exact_evidence(m['evidence'],run['blocks'])
    source=dict(meanings=[m],review_contract=review.CONTRACT,examined_block_ids=['body'],completeness='partial',
        gaps=[],meaning_gaps=[],meaning_conjunctions=[],conjunctions=[],findings=[])
    scope=dict(tasks=tasks,items=[dict(task_id=t['id'],meaning_keys=['m'],candidate_ids=[run['claims'][0]['id']],
        read_block_ids=['body'],source_state='available',expression_state='partial',gap='미검증',reason='이전') for t in tasks],
        errors=[],followup=[],unit_id='scope',review_meaning_keys=['m'],public_requirement={k:req[k] for k in
        ('id','revision','question','criterion','target','situation','period')},
        candidate_versions={c['id']:autoschema.identifier('claim',c) for c in run['claims']},
        source_version_fingerprint=autoschema.identifier('public_scope_source',run['blocks']))
    source['public_scope']=scope
    run['assessments']=[dict(id='assessment',requirement_id='r',revision=1,source=source,status='partial')]
    snapshot=dict(id='snapshot',kind='source_graph',run_id=run['id'],blocks=deepcopy(run['blocks']),
        assessments={'r':deepcopy(run['assessments'][0])})
    output=dict(items=[dict(item_id=t['id'],selected=[dict(meaning_ref='m1',use='direct_fact')],
                           unconfirmed=['검토된 표현에서 필요한 부분을 확인하지 못함']) for t in tasks])
    qa=dict(id='qa',kind='business_query',status='succeeded',answer_status='answered',answer_item_errors=[],
        query=dict(question=req['question'],answer_mode='reviewed_items',snapshot_id='snapshot'),snapshot_id='snapshot',
        execution_boundary=dict(source_review_run_id=run['id']),input_version_ids=['v'],answer_items=deepcopy(run['answer_items']),
        answer_work_items=[dict(t['item'],id=t['id'],public_item_id=t['item']['id'],context=t['context']) for t in tasks],
        answer_work_records=review.public_work_records(run,req,source),provided_ids=[c['id'] for c in run['claims']],
        answer_meaning_selection=dict(output=output,available={'m1':dict(claim_ids=[run['claims'][0]['id']])}),
        units=[dict(id='qa-unit',stage='business_qa',status='succeeded',error=None,response=dict(parsed=deepcopy(output)))])
    return run,qa,deepcopy(run),snapshot


def test_gap_reuses_current_qa_pool_despite_stale_public_scope_without_promoting_truth(bound):
    parent,qa,basis,snapshot=bound
    qa['answer_work_records'][0]['candidate_binding_valid']=False
    originals=deepcopy(bound)
    receipt=feedback.bind_gaps(*bound,['item/context1'])
    finding=receipt['findings'][0]
    assert finding['text']==qa['answer_meaning_selection']['output']['items'][0]['unconfirmed'][0]
    assert finding['meaning_keys']==['m'] and finding['origin']=='qa'
    assert finding['claim_ids']==finding['fields']==[]
    assert finding['related_claim_ids']==[parent['claims'][0]['id']]
    assert finding['task']['context']==dict(field='situation',quote='개인')
    assert 'action' not in finding and 'source_status' not in finding
    assert bound==originals


@pytest.mark.parametrize('fault',['candidate','block','question','meaning','address','task','raw_output','snapshot','work_address'])
def test_changed_or_unbound_inputs_are_rejected(bound,fault):
    parent,qa,basis,snapshot=bound
    if fault=='candidate':parent['claims'][0]['raw']['Tail']='changed'
    elif fault=='block':parent['blocks'][0]['text']='changed'
    elif fault=='question':parent['requirements'][0]['question']='다른 질문'
    elif fault=='meaning':parent['assessments'][0]['source']['meanings'][0]['statement']='changed'
    elif fault=='address':
        for source in [parent['assessments'][0]['source'],snapshot['assessments']['r']['source']]:
            source['meanings'][0]['evidence'][0]['quote']='원문에 없는 인용'
    elif fault=='task':qa['answer_work_items'][0]['context']['quote']='다른 상황'
    elif fault=='raw_output':qa['answer_meaning_selection']['output']['items'][0]['unconfirmed']=['changed']
    elif fault=='snapshot':qa['query']['snapshot_id']='other'
    else:qa['answer_work_records'][0]['read_block_ids']=[]
    with pytest.raises((ValueError,KnowledgeConflict)):
        feedback.bind_gaps(*bound,['item/context1'])


def test_multi_meaning_gap_is_kept_unmapped(bound):
    parent,qa,basis,snapshot=bound
    for source in [parent['assessments'][0]['source'],snapshot['assessments']['r']['source']]:
        source['meanings'].append(dict(deepcopy(source['meanings'][0]),key='second'))
        source['public_scope']['review_meaning_keys'].append('second')
        source['public_scope']['items'][0]['meaning_keys'].append('second')
    qa['answer_work_records'][0]['meaning_keys'].append('second')
    receipt=feedback.bind_gaps(*bound,['item/context1'])
    assert not receipt['findings'] and receipt['deferred'][0]['original_output']==qa['answer_meaning_selection']['output']['items'][0]


def test_public_scope_records_identify_stale_versions_and_leave_history_intact(bound):
    parent,qa,basis,snapshot=bound
    source=parent['assessments'][0]['source'];before=deepcopy(source)
    row=review.public_work_records(parent,parent['requirements'][0],source)[0]
    assert all(row[k] for k in ('source_binding_valid','candidate_binding_valid','requirement_binding_valid'))
    parent['claims'][0]['raw']['Tail']='new'
    row=review.public_work_records(parent,parent['requirements'][0],source)[0]
    assert row['source_binding_valid'] and not row['candidate_binding_valid']
    assert row['authority']=='previous_work_state_not_truth_or_approval' and source==before


def test_product_start_copies_receipt_and_worker_uses_only_existing_assessed_actions(bound,tmp_path,monkeypatch):
    parent,qa,basis,snapshot=bound
    service=KnowledgeService(tmp_path/'knowledge.db');submitted=[]
    monkeypatch.setattr(service.executor,'submit',lambda *args:submitted.append(args))
    with service.repository.connect() as db:
        for run in [parent,qa]:db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
        db.execute('INSERT INTO snapshots VALUES(?,?)',(snapshot['id'],encode(snapshot)))
        db.execute('INSERT INTO requirements VALUES(?,?)',('r',encode(parent['requirements'][0])))
    request=BusinessAnswerRecheck(qa_run_id='qa',task_ids=['item/context1'])
    result=feedback.start(service,'parent',request);child=service.run(result['run_id'])
    assert child['claims']==parent['claims'] and child['assessments']==parent['assessments']
    assert child['answer_gap_recheck']['findings'][0]['claim_ids']==[]
    assert submitted[0][0] is feedback.execute
    monkeypatch.setattr(business_run.ModelClient,'identities',lambda *a:{})
    observed=[]
    def assess(s,r,q,**kwargs):
        assert kwargs['focus_meaning_keys']==['m']
        assert kwargs['source']['findings'][-1]['origin']=='qa'
        a=dict(id='review',status='partial',actions=[dict(action='maintain')]);observed.append(a);return a
    monkeypatch.setattr(business_run,'assess',assess)
    rechecks=[]
    monkeypatch.setattr(business_run,'reassess_challenges',lambda s,r,q,a,**kw: rechecks.append((a,kw)) or a)
    monkeypatch.setattr(business_run,'repair',lambda s,r,q,a: observed.append(a) or False)
    monkeypatch.setattr(business_run,'refresh_repaired_graph',lambda *a:None)
    monkeypatch.setattr(business_use,'publish',lambda *a:dict(id='change'))
    feedback.execute(service,child['id'])
    assert observed[0] is observed[1] and len(observed)==2
    assert rechecks==[(observed[0],dict(focus_meaning_keys=['m']))]
    assert service.run(child['id'])['claims']==parent['claims']
    with service.repository.connect() as db:
        assert service.repository.get(db,'runs','qa')==qa
    service.shutdown()


def test_api_accepts_only_stored_qa_and_task_ids():
    for field in ['statement','meaning_key','action','source_status']:
        with pytest.raises(ValidationError):
            BusinessAnswerRecheck.model_validate(dict(qa_run_id='q',task_ids=['t'],**{field:'override'}))


def test_unresolved_qa_observation_does_not_request_source_reassessment(bound):
    parent,qa,basis,snapshot=bound;source=parent['assessments'][0]['source']
    finding=feedback.bind_gaps(*bound,['item/context1'])['findings'][0]
    result=dict(source_checks=[],checks=[],finding_resolutions=[],meaning_challenges=[],source_challenges=[],
                source_completeness='partial',unselected_source_required=False)
    review.resolve_findings(source,result,[finding],parent['blocks'],parent['claims'],joined=True)
    assert result['meaning_challenges'][0]['source_reassessment_needed'] is False
    assert not result['source_challenges'] and source['meanings'][0]['source_status']=='supported'


def test_start_rejects_a_non_query_id_before_reading_its_snapshot(bound,tmp_path):
    parent,qa,basis,snapshot=bound
    service=KnowledgeService(tmp_path/'knowledge.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)',(parent['id'],encode(parent)))
    with pytest.raises(ValueError,match='QA 실행 ID'):
        feedback.start(service,parent['id'],BusinessAnswerRecheck(qa_run_id=parent['id'],task_ids=['item/context1']))
    service.shutdown()


def test_real_source_challenge_uses_existing_reassessment_and_keeps_focus(bound,monkeypatch):
    parent,qa,basis,snapshot=bound
    req=parent['requirements'][0];a=deepcopy(parent['assessments'][0])
    a['source']['processing_scope']=dict(requested_meaning_keys=['m'])
    a['representation']=dict(meaning_challenges=[dict(meaning_key='m',fields=['statement'],
        reason='원문 해석 오류',source_reassessment_needed=True),
        dict(meaning_key='outside',fields=['statement'],reason='범위 밖')])
    observed=[]
    def reassess(s,r,q,assessment,challenges):
        assert len(challenges)==1 and challenges[0]['meaning_key']=='m'
        observed.extend(challenges)
        return deepcopy(assessment['source'])
    monkeypatch.setattr(review,'reassess_source',reassess)
    def assess(s,r,q,**kwargs):
        assert kwargs['focus_meaning_keys']==['m'] and kwargs['phase']=='source_reassessment'
        return dict(id='rechecked')
    monkeypatch.setattr(business_run,'assess',assess)
    assert business_run.reassess_challenges(None,parent,req,a,focus_meaning_keys=['m'])==dict(id='rechecked')
    assert observed[0]['source_reassessment_needed'] is True


def test_unresolved_qa_challenge_does_not_call_source_model(bound,monkeypatch):
    parent,qa,basis,snapshot=bound
    a=deepcopy(parent['assessments'][0])
    a['representation']=dict(meaning_challenges=[dict(meaning_key='m',fields=[],
        reason='미검증 QA 공백',source_reassessment_needed=False)])
    monkeypatch.setattr(business_run,'json_call',lambda *a,**kw: pytest.fail('QA gap must not rewrite source'))
    assert business_run.reassess_challenges(None,parent,parent['requirements'][0],a,focus_meaning_keys=['m']) is a


@pytest.mark.parametrize('repair',[True,False])
def test_new_recheck_uses_its_explicit_repair_policy_without_changing_parent(bound,tmp_path,monkeypatch,repair):
    parent,qa,basis,snapshot=bound
    parent['recipe']['options']['repair']=False
    service=KnowledgeService(tmp_path/'knowledge.db')
    monkeypatch.setattr(service.executor,'submit',lambda *args:None)
    with service.repository.connect() as db:
        for run in [parent,qa]:db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
        db.execute('INSERT INTO snapshots VALUES(?,?)',(snapshot['id'],encode(snapshot)))
        db.execute('INSERT INTO requirements VALUES(?,?)',('r',encode(parent['requirements'][0])))
    request=BusinessAnswerRecheck(qa_run_id='qa',task_ids=['item/context1'],repair=repair)
    result=feedback.start(service,'parent',request)
    assert service.run(result['run_id'])['recipe']['options']['repair'] is repair
    assert service.run('parent')['recipe']['options']['repair'] is False
    assert BusinessAnswerRecheck(qa_run_id='qa',task_ids=['item/context1']).repair is True
    service.shutdown()


@pytest.fixture
def completed_recheck(bound,tmp_path,monkeypatch):
    parent,qa,basis,snapshot=bound
    child=deepcopy(parent)
    child.update(id='child',parent_run_id=parent['id'],finished_at=utcnow(),
                 answer_gap_recheck=feedback.bind_gaps(*bound,['item/context1']))
    child['recipe']['options']['repair']=False
    assessment=deepcopy(child['assessments'][-1]);assessment['id']='child-assessment'
    assessment['source']['findings']=deepcopy(child['answer_gap_recheck']['findings'])
    assessment['source']['findings'][0]['candidate_binding_valid']=True
    assessment['input_fingerprint']=business_run.assessment_fingerprint(child,child['requirements'][0],assessment['source'])
    child['assessments'].append(assessment)
    child['answer_gap_recheck']['assessment_ids']=[assessment['id']]
    current=dict(deepcopy(parent['requirements'][0]),current_assessment=dict(
        run_id=child['id'],assessment_id=assessment['id'],source_version_ids=child['input_version_ids']))
    service=KnowledgeService(tmp_path/'knowledge.db');submitted=[]
    monkeypatch.setattr(service.executor,'submit',lambda *args:submitted.append(args))
    with service.repository.connect() as db:
        for run in [parent,qa,child]:db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
        db.execute('INSERT INTO snapshots VALUES(?,?)',(snapshot['id'],encode(snapshot)))
        db.execute('INSERT INTO requirements VALUES(?,?)',('r',encode(current)))
    yield service,parent,qa,child,current,submitted
    service.shutdown()


def test_completed_same_request_reuses_current_child_without_dispatch_or_writes(completed_recheck):
    service,parent,qa,child,current,submitted=completed_recheck
    before=[service.run(r['id']) for r in [parent,qa,child]]
    result=feedback.start(service,parent['id'],BusinessAnswerRecheck(
        qa_run_id=qa['id'],task_ids=['item/context1'],repair=False))
    assert result==dict(run_id=child['id'],status='partial',deferred=[],reused=True)
    assert not submitted and before==[service.run(r['id']) for r in [parent,qa,child]]


@pytest.mark.parametrize('fault',['requirement','stale','pointer','candidate','source','block','restriction'])
def test_completed_reuse_rejects_changed_current_state(completed_recheck,monkeypatch,fault):
    service,parent,qa,child,current,submitted=completed_recheck
    if fault=='requirement':current['question']='수정된 질문'
    elif fault=='stale':current['status']='needs_review'
    elif fault=='pointer':current['current_assessment']['run_id']='other'
    elif fault=='candidate':child['claims'][0]['raw']['Tail']='변경된 후보'
    elif fault=='source':child['assessments'][-1]['source']['meanings'][0]['statement']='변경된 해석'
    elif fault=='block':child['blocks'][0]['text']='변경된 원문'
    else:monkeypatch.setattr(business_use,'restricted_sources',lambda *a:[dict(state='restricted')])
    with service.repository.connect() as db:
        service.repository.save(db,'requirements',current)
        service.repository.save(db,'runs',child)
    with pytest.raises(KnowledgeConflict):
        feedback.start(service,parent['id'],BusinessAnswerRecheck(
            qa_run_id=qa['id'],task_ids=['item/context1'],repair=False))
    assert not submitted


@pytest.mark.parametrize('mode',['explicit','new_qa','new_policy','failed'])
def test_latest_child_allows_explicit_recheck_new_qa_policy_and_failure_retry(completed_recheck,mode):
    service,parent,qa,child,current,submitted=completed_recheck
    if mode=='new_qa':
        qa=dict(deepcopy(qa),id='new-qa')
        with service.repository.connect() as db:db.execute('INSERT INTO runs VALUES(?,?)',(qa['id'],encode(qa)))
    elif mode=='failed':
        child['status']='failed'
        with service.repository.connect() as db:service.repository.save(db,'runs',child)
    result=feedback.start(service,child['id'],BusinessAnswerRecheck(
        qa_run_id=qa['id'],task_ids=['item/context1'],repair=mode=='new_policy'))
    assert result['run_id'] not in {parent['id'],child['id']} and len(submitted)==1
    assert service.run(result['run_id'])['parent_run_id']==child['id']


def test_recheck_keeps_existing_observation_and_derived_validation_metadata(completed_recheck,monkeypatch):
    service,parent,qa,child,current,submitted=completed_recheck
    before=service.run(child['id'])
    result=feedback.start(service,child['id'],BusinessAnswerRecheck(
        qa_run_id=qa['id'],task_ids=['item/context1'],repair=False))
    observed=[]
    monkeypatch.setattr(business_run.ModelClient,'identities',lambda *a:{})
    def assess(s,r,q,**kwargs):
        observed.append(deepcopy(kwargs['source']))
        return dict(id='rechecked',status='partial')
    monkeypatch.setattr(business_run,'assess',assess)
    monkeypatch.setattr(business_run,'reassess_challenges',lambda s,r,q,a,**kw:a)
    monkeypatch.setattr(business_run,'refresh_repaired_graph',lambda *a:None)
    monkeypatch.setattr(business_use,'publish',lambda *a:dict(id='change'))
    feedback.execute(service,result['run_id'])
    assert observed[0]['findings']==child['assessments'][-1]['source']['findings']
    assert observed[0]['findings'][0]['candidate_binding_valid'] is True
    assert service.run(child['id'])==before


def test_completed_repair_result_is_reused_but_a_later_edit_invalidates_it(completed_recheck):
    service,parent,qa,child,current,submitted=completed_recheck
    child['claims'][0]['raw']['Tail']='완료된 교정 결과'
    assessment=child['assessments'][-1]
    assessment['input_fingerprint']=business_run.assessment_fingerprint(child,child['requirements'][0],assessment['source'])
    child['changeset_id']='change'
    change=dict(id='change',candidates=deepcopy(child['claims']))
    with service.repository.connect() as db:
        service.repository.save(db,'runs',child)
        db.execute('INSERT INTO changesets VALUES(?,?)',(change['id'],encode(change)))
    request=BusinessAnswerRecheck(qa_run_id=qa['id'],task_ids=['item/context1'],repair=False)
    assert feedback.start(service,parent['id'],request)['run_id']==child['id']
    change['invalidated_claim_ids']=[child['claims'][0]['id']]
    with service.repository.connect() as db:service.repository.save(db,'changesets',change)
    with pytest.raises(KnowledgeConflict):feedback.start(service,parent['id'],request)
    assert not submitted
