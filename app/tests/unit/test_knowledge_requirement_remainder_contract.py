"""Synthetic contract cases; these are not semantic labels for the stored M03 run."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.knowledge import business_models, business_review as review, business_run
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments


def application(required, item_id='item'):
    return dict(item_id=item_id, required_for_requirement=required is not False, requirement_link=dict(
        requested_fact='신청 절차' if required is not False else '',
        applicability='unresolved' if required is None else 'applicable',
        contribution='background' if required is False else 'direct_answer',
        reason='합성 검증용 필수성', requirement_quote='신청 절차'))


def completion_case(status='partial', required=False):
    source = dict(meanings=[meaning('answer'), meaning('reference')], completeness='partial', gaps=['참고 원문 미확보'],
        meaning_gaps=[dict(meaning_keys=['reference'],text='참고 공백')], public_scope=dict(
            input_contract=review.PUBLIC_SOURCE_INPUT_CONTRACT,review_meaning_keys=['answer','reference'],
            public_items=[dict(id='item')],errors=[]))
    for m,state in zip(source['meanings'],[True,required]):
        link=application(state);m.update({k:v for k,v in link.items() if k!='item_id'},requirement_applications=[link])
    result=judgments(['answer','reference'],ids=['normal'])
    result['source_checks']=[review.source_judgment(m,require_application=True) for m in source['meanings']]
    result['checks'][1].update(status=status,claim_ids=[] if status in {'missing','unknown'} else ['normal'])
    result.update(source_completeness='complete',unselected_source_required=False,valid_public_item_ids=['item'],
        public_item_checks=[dict(item_id='item',status='represented')],public_item_check_errors=[])
    return dict(source=source,representation=result,errors=[],issues=[],preservation_complete=True)


@pytest.mark.parametrize('status',['partial','missing','unknown'])
def test_confirmed_background_gap_is_recorded_without_blocking_question(status):
    a=completion_case(status);before=deepcopy(a)
    assert business_run.requirement_completion(a)['status']=='satisfied'
    assert a==before


@pytest.mark.parametrize('fault',['unresolved','absent_application','incorrect','support_incorrect','support_unknown',
    'source_refuted','condition_refuted','shared_premise','preservation','record_error'])
def test_background_does_not_hide_uncertainty_or_actual_errors(fault):
    a=completion_case();c=a['representation']['checks'][1];m=a['source']['meanings'][1]
    if fault=='unresolved':m.update({k:v for k,v in application(None).items() if k!='item_id'})
    if fault=='absent_application':m.pop('requirement_link')
    if fault=='incorrect':c['status']='incorrect'
    if fault.startswith('support_'):c['claim_support']={'normal':fault.removeprefix('support_')}
    if fault=='source_refuted':m['source_status']='refuted'
    if fault=='condition_refuted':m['field_judgments']=dict(conditions=dict(status='refuted',statement_affected=True))
    if fault=='shared_premise':
        a['source']['meanings'][0]['premise_keys']=['reference'];c['status']='unknown'
        a['representation']['dependencies'][0]['premise_keys']=['reference']
    if fault=='preservation':a['preservation_complete']=False
    if fault=='record_error':a['issues']=[dict(meaning_key='reference',reason='잘못된 주소')];a['errors']=['잘못된 주소']
    assert business_run.requirement_completion(a)['status']=='partial'


@pytest.mark.parametrize('used',[False,True])
def test_public_unowned_candidate_error_only_blocks_when_used(monkeypatch,used):
    from app.knowledge import business_use
    run=local_run();run['recipe']['review_contract']=review.SOURCE_APPLICATION_CONTRACT
    normal,disputed=[c['id'] for c in run['claims']]
    a=completion_case('unknown');a.update(requirement_id='r',candidate_accuracy_contract='candidate-own-source-errors-v1')
    check=a['representation']['checks'][0]
    check.update(claim_ids=[disputed if used else normal],claim_support={normal:'supported',disputed:'unknown'},
        error_fields={disputed:['raw.Relation']},error_evidence=[],incorrect_claim_ids=[])
    a['representation']['checks'][1]['claim_ids']=[]
    run['assessments']=[a]
    monkeypatch.setattr(review,'current_candidate_reviews',lambda r:{cid:dict(check=dict(claim_support={cid:state},
        incorrect_claim_ids=[],error_fields={cid:['raw.Relation']} if state=='unknown' else {}))
        for cid,state in [(normal,'supported'),(disputed,'unknown')]})
    eligible,blocked=business_use.eligibility(run)
    assert eligible=={normal} and disputed in blocked
    assert (business_run.requirement_completion(a)['status']=='satisfied')==(not used)


def test_independent_reference_error_stays_recorded_without_blocking_question():
    a=completion_case();row=a['representation']['checks'][1]
    row.update(status='incorrect',claim_ids=['independent'],incorrect_claim_ids=['independent'],
        claim_support={'independent':'incorrect'},error_fields={'independent':['raw.Tail']})
    a['source']['meanings'][1]['source_status']='refuted'
    a['representation']['meaning_challenges']=[dict(meaning_key='reference',reason='독립 참고 오류')]
    before=deepcopy(a)
    assert business_run.requirement_completion(a)['status']=='satisfied' and a==before


def test_unknown_applicability_remains_in_answer_scope_and_never_becomes_reference():
    from app.knowledge import business_use
    a=completion_case(required=None)
    assert business_use.required_answer_meaning_keys(dict(assessments={'r':a}),['r'])=={'r':['answer','reference']}


@pytest.mark.parametrize('model',[business_models.ContributionCheck,business_models.ContributionRevision,
    business_models.ChallengedContributionRevision])
def test_ordinary_and_qa_require_the_same_explicit_remainder_fields(model):
    row=dict(meaning_key='m',status='partial',claim_ids=['normal'],reason='설명으로만 잔여를 쓰지 않는다')
    if model!=business_models.ContributionCheck:row.update(revision_basis='combined_expression',evidence=[])
    with pytest.raises(ValidationError) as exc:model.model_validate(row)
    assert {'represented_content','missing_content','missing_evidence'} <= {e['loc'][0] for e in exc.value.errors()}


@pytest.mark.parametrize('required',[True,False,None])
@pytest.mark.parametrize('qa',[False,True])
def test_invalid_partial_is_an_individual_hold_and_reference_does_not_fail_join(required,qa):
    from app.tests.unit.test_knowledge_business_separated_review import synthesis
    a=completion_case(required=required);compact=a['representation'];cid='normal'
    response=synthesis();response['checks']=[dict(meaning_key='reference',status='partial',claim_ids=[cid],
        incorrect_claim_ids=[],reason='근거 필드 불충분',represented_content='',missing_content='',missing_evidence=[],
        revision_basis='combined_expression',evidence=[dict(block_id='body',quote='기관은 신청을 접수한다.')])]
    result,joined,_,errors=review.retain_synthesis(compact,response,{'reference'},{cid},local_run()['blocks'],
        required_check_keys={'reference'} if qa or required is not False else set())
    assert joined==(required is False and not qa)
    assert bool(errors)==(not joined)
    if qa:assert result['satisfied'] is False
    assert compact['checks'][1]['status']=='partial'


@pytest.mark.parametrize('fault',['claim','duplicate_claim','evidence','missing_evidence','candidate_support'])
def test_reference_hold_never_bypasses_common_identity_and_evidence_checks(fault):
    from app.tests.unit.test_knowledge_business_separated_review import synthesis
    compact=completion_case()['representation'];response=synthesis()
    row=dict(meaning_key='reference',status='partial',claim_ids=['normal'],incorrect_claim_ids=[],reason='참고 보류',
        represented_content='',missing_content='',missing_evidence=[],revision_basis='combined_expression',
        evidence=[dict(block_id='body',quote='기관은 신청을 접수한다.')])
    if fault=='claim':row['claim_ids']=['not-stored']
    if fault=='duplicate_claim':row['claim_ids']*=2
    if fault=='evidence':row['evidence'][0]['quote']='없는 원문'
    if fault=='missing_evidence':row['missing_evidence']=[dict(block_id='body',quote='없는 잔여 원문')]
    if fault=='candidate_support':row.update(claim_support={'normal':'unknown'},error_fields={'normal':['raw.Tail']},error_evidence=row['evidence'])
    response['checks']=[row]
    result,joined,_,errors=review.retain_synthesis(compact,response,{'reference'},{'normal'},local_run()['blocks'])
    assert not joined and errors and result['checks']==compact['checks']


def install_synthetic_dispatch(monkeypatch,run,req,source,*,required=True,blank=False):
    calls=[]
    monkeypatch.setattr(business_run,'request_budget',lambda *a,**k:dict(estimate_tokens=0))
    monkeypatch.setattr(review,'public_requirement_scope',lambda s,r,q,f:review.resolve_public_read_scope(r,q,f))
    monkeypatch.setattr(review,'current_candidate_reviews',lambda r:{c['id']:dict(receipt_id='own',unit_id='own',
        check=dict(claim_support={c['id']:'supported'},incorrect_claim_ids=[],error_fields={},error_evidence=[],reason='합성 자기원문 검수')) for c in r['claims']})
    def dispatch(service,current,stage,instruction,packet,schema):
        calls.append((stage,deepcopy(packet)))
        if stage=='requirement_application':
            links=[]
            for m in packet['source_facts']:
                value=application(required if m['key']=='part' else None if m['key']=='pending' else False)
                value['key']=m['key'];value['requirement_link'].pop('requirement_quote')
                links.append(value)
            out=dict(links=links,meaning_challenges=[])
        else:
            keys=[m['key'] for m in packet['source']['meanings']]
            out=dict(checks=[],dependencies=[],source_challenges=[],meaning_challenges=[],candidate_challenges=[],preservation_checks=[])
            if packet['mode']=='meaning_batch':
                for key in keys:
                    out['checks'].append(dict(meaning_key=key,status='partial',claim_ids=[current['claims'][0]['id']],reason='합성 부분 기여',
                        represented_content='' if blank else '기관은 신청을 접수한다.',
                        missing_content='' if blank else '추가 서류를 확인한다.',
                        missing_evidence=[] if blank else business_run.exact_evidence([dict(block_id='body',quote='추가 서류를 확인한다.')],current['blocks'])))
                out['dependencies']=[dict(meaning_key=key,premise_keys=[]) for key in keys]
            else:
                out.update(satisfied=False,conjunctions_satisfied=True,reason='합성 검수',source_completeness='complete',
                    unselected_source_required=False,finding_resolutions=[],public_item_checks=[dict(item_id='item',status='partial',
                        meaning_keys=['part'],claim_ids=[current['claims'][0]['id']],evidence=source['meanings'][0]['evidence'],reason='합성 누락')])
                out['checks']=[dict(meaning_key='part',status='partial',claim_ids=[current['claims'][0]['id']],reason='전체 후보 대조',
                    represented_content='' if blank else '기관은 신청을 접수한다.',missing_content='' if blank else '추가 서류를 확인한다.',
                    missing_evidence=[] if blank else business_run.exact_evidence([dict(block_id='body',quote='추가 서류를 확인한다.')],current['blocks']),
                    revision_basis='combined_expression',evidence=source['meanings'][0]['evidence'])]
                out['checks'].append(dict(meaning_key='pending',status='unknown',claim_ids=[],reason='적용성과 잔여 미확정',
                    represented_content='',missing_content='',missing_evidence=[],revision_basis='new_evidence',
                    evidence=source['meanings'][0]['evidence']))
        normalized=schema.model_validate(out).model_dump()
        current['units'].append(dict(id='synthetic-'+str(len(current['units'])),stage=stage,status='succeeded',error=None,
            response=dict(request_id='synthetic-'+str(len(current['units']))),restored_evidence_output=deepcopy(normalized)))
        return normalized
    monkeypatch.setattr(business_run,'json_call',dispatch)
    return calls


def synthetic_run():
    run=local_run();run.update(id='synthetic',kind='business',status='partial',input_version_ids=['v'],model_identity={},metrics={})
    run['recipe']['review_contract']=review.SOURCE_APPLICATION_CONTRACT
    run['blocks'][0]['text']+=' 추가 서류를 확인한다.'
    req=dict(run['requirements'][0],question='신청 절차',criterion='필요 서류 보존',target='이용자',situation='신청',period='',history=[])
    run['requirements']=[req];run['answer_items']=[dict(id='item',requirement_id='r',requirement_revision=1,field='question',request_quote='신청 절차')]
    source=dict(meanings=[meaning('part'),meaning('reference'),meaning('pending')],examined_block_ids=['body'],completeness='complete',gaps=[],meaning_gaps=[],
        conjunctions=[],meaning_conjunctions=[],findings=[],source_batches=[],review_contract=review.SOURCE_APPLICATION_CONTRACT,
        public_scope=dict(input_contract=review.PUBLIC_SOURCE_INPUT_CONTRACT,review_meaning_keys=['part'],
            unit_id='synthetic-source-scope',
            public_items=deepcopy(run['answer_items']),tasks=[],items=[dict(item_id='item',meaning_keys=['part'],read_block_ids=['body'],source_state='available')],
            errors=[],followup=[],public_requirement={k:v for k,v in req.items() if k!='source_ids'}))
    for m in source['meanings']:m['evidence']=business_run.exact_evidence(m['evidence'],run['blocks'])
    source['source_batches']=[dict(unit_id='E',meaning_keys=['part','reference','pending'],errors=[],provided_block_ids=['body'],
        target_block_ids=['body'],output=dict(inspection_status='complete',examined_block_ids=['body']),
        target_evidence=business_run.exact_evidence([dict(block_id='body',quote=run['blocks'][0]['text'])],run['blocks']))]
    run['units']=[dict(id='E',stage='requirement_source',status='succeeded',error=None,response=dict(request_id='E',failure_kind=None))]
    return run,req,source


@pytest.mark.parametrize('required,blank,expected',[(True,False,'recover'),(True,True,'hold'),(False,True,'hold'),(None,False,'hold')])
def test_mixed_read_scope_to_action_save_and_real_api_get(monkeypatch,tmp_path,required,blank,expected):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers import knowledge
    from app.knowledge.service import KnowledgeService,encode
    run,req,source=synthetic_run();before=deepcopy(run['claims'])
    calls=install_synthetic_dispatch(monkeypatch,run,req,source,required=required,blank=blank)
    service=KnowledgeService(tmp_path/'copy.db')
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    app=FastAPI();app.include_router(knowledge.router);app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
            db.execute('INSERT INTO requirements VALUES(?,?)',(req['id'],encode(req)))
        a=business_run.assess(service,run,req,source=source)
        action=next(t for t in a['actions'] if t['meaning_key']=='part')
        assert action['action']==expected and run['claims']==before
        assert a['source']['public_scope']['review_meaning_keys']==['part','pending','reference']
        assert review.requirement_states(a['source'],a['representation'])=={'part':required,'reference':False,'pending':None}
        assert next(c for c in a['representation']['source_checks'] if c['meaning_key']=='part')['required_for_requirement'] is required
        if expected=='recover':
            assert action['claim_ids']==[] and action['contributing_claim_ids']==[before[0]['id']]
            assert action['missing_evidence'][0]['parse_run_id']=='p'
            captured=[]
            def repair_packet(s,r,stage,instruction,packet,schema):captured.append(deepcopy(packet));return None
            monkeypatch.setattr(business_run,'json_call',repair_packet)
            business_run.repair(service,run,req,a)
            task=captured[0]['tasks'][0]['meanings'][0]
            assert task['contributing_claim_ids']==action['contributing_claim_ids']
            assert task['missing_content']==action['missing_content'] and task['missing_evidence']==action['missing_evidence']
            assert any(c['id']==before[0]['id'] for c in captured[0]['reuse_candidates'])
        elif required is None:assert 'requirement_application_unresolved' in action['reason']
        elif blank:assert 'partial_remainder_unconfirmed' in action['reason']
        with TestClient(app) as client:
            data=client.get('/knowledge/runs/'+run['id']).json()['data']
        saved=data['assessments'][-1]
        assert saved['actions']==a['actions'] and saved['representation']==a['representation']
        assert business_run.requirement_completion(saved,claims=data['claims'])['status']==a['status']=='partial'
        assert data['claims']==before
        assert [stage for stage,_ in calls].count('requirement_application')==1
    finally:service.shutdown()


def test_application_reuses_only_same_completed_request_and_decisions(monkeypatch):
    run,req,source=synthetic_run();calls=install_synthetic_dispatch(monkeypatch,run,req,source)
    applied=review.public_requirement_application(None,run,req,source)
    assert review.public_requirement_application(None,run,req,applied)==applied and len(calls)==1
    for fault in ['revision','fact','decision','raw','identity']:
        r,q,s=deepcopy(run),deepcopy(req),deepcopy(applied)
        if fault=='revision':
            q['revision']+=1
            with pytest.raises(ValueError):review.public_requirement_application(None,r,q,s)
            assert len(calls)==1
            continue
        if fault=='fact':s['meanings'][0]['source_status']='unknown'
        if fault=='decision':s['meanings'][0]['required_for_requirement']=False
        if fault=='raw':r['units'][-1]['restored_evidence_output']['links']=[]
        if fault=='identity':r['model_identity']={'model':'different'}
        previous=len(calls);review.public_requirement_application(None,r,q,s)
        assert len(calls)==previous+1


def test_missing_application_is_not_false_in_summary_or_stale_repair_selection():
    a=completion_case();a['source']['meanings'][1].pop('requirement_link')
    states=review.requirement_states(a['source'],a['representation'])
    assert states=={'answer':True,'reference':None}
    output=judgments(['reference']);output['source_checks'][0]['required_for_requirement']=None
    assert review.summarize_local([meaning('reference')],[output])['source_checks'][0]['required_for_requirement'] is None
    a['actions']=[dict(meaning_key='reference',action='recover',claim_ids=[],reason='과거 자동 행동')]
    assert business_run.repair(None,local_run(),{},a) is False
