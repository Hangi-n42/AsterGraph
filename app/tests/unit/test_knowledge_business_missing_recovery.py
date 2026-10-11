"""Missing source knowledge must reach new candidates without rewriting a normal partial claim."""
from copy import deepcopy

import pytest

from app.knowledge import business_review as review, business_run
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning


def fixture(monkeypatch):
    run = local_run()
    run['recipe']['review_contract'] = review.CONTRACT
    req = dict(run['requirements'][0], question='신청과 접수 안내는?', criterion='조건 보존', target='이용자', situation='개인·단체', period='')
    run['requirements'] = [req]
    source = dict(meanings=[meaning(k, required_for_requirement=True) for k in ('part', 'other')],
        examined_block_ids=['body'], completeness='complete', gaps=[], meaning_gaps=[], conjunctions=[],
        meaning_conjunctions=[], findings=[], source_batches=[], review_contract=review.CONTRACT,
        public_scope=dict(review_meaning_keys=['part', 'other'], tasks=[], items=[], errors=[], followup=[],
            public_requirement={k:v for k,v in req.items() if k!='source_ids'}, unit_id='scope'))
    for m in source['meanings']:
        m['evidence'] = business_run.exact_evidence(m['evidence'], run['blocks'])
    direct = {c['id']:dict(receipt_id='own'+c['id'], unit_id='own', check=dict(claim_support={c['id']:'supported'},
        incorrect_claim_ids=[], error_fields={}, error_evidence=[], reason='원문')) for c in run['claims']}
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda r:deepcopy(direct))
    monkeypatch.setattr(business_run, 'cancelled', lambda *a:False)
    monkeypatch.setattr(business_run, 'save', lambda *a:None)
    monkeypatch.setattr(business_run.business_store, 'save_assessment', lambda *a:None)
    return run, req, source


def native_contract(monkeypatch, run, *, status='partial', evidence=True, location=True, join=True, confirm=True):
    calls=[]
    def response(_s,current,stage,instruction,packet,schema):
        assert stage=='requirement_representation'
        calls.append(deepcopy(packet));current['units'].append(dict(id='unit'+str(len(calls))))
        out=dict(checks=[], dependencies=[], source_challenges=[], meaning_challenges=[],
            candidate_challenges=[], preservation_checks=[])
        if packet['mode']=='meaning_batch':
            out['checks']=[dict(meaning_key=m['key'],status=status,
                claim_ids=[run['claims'][0]['id']] if location else [],reason='부분 기여와 잔여',
                represented_content='기관은 신청을 접수한다.', missing_content='잔여 조건',
                missing_evidence=[dict(block_id='body',quote=run['blocks'][0]['text'])] if evidence else [])
                for m in packet['source']['meanings']]
            out['dependencies']=[dict(meaning_key=m['key'],premise_keys=[]) for m in packet['source']['meanings']]
        else:
            if not join:return None
            out.update(satisfied=True, conjunctions_satisfied=True, reason='연결 확인',source_completeness='complete',
                unselected_source_required=False,finding_resolutions=[])
            if status=='partial' and confirm:
                out['checks']=[dict({k:row[k] for k in ('meaning_key','status','claim_ids','reason',
                    'represented_content','missing_content','missing_evidence') if k in row},
                    revision_basis='combined_expression',evidence=[dict(block_id='body',quote=run['blocks'][0]['text'])])
                    for row in packet['local_judgments']['checks']]
        return schema.model_validate(out).model_dump()
    monkeypatch.setattr(business_run,'json_call',response)
    return calls


@pytest.mark.parametrize('evidence,join,confirm,action', [(True,True,True,'recover'),(False,True,True,'hold'),
    (True,False,True,'hold'),(True,True,False,'hold')])
def test_public_assess_preserves_partial_claim_and_requires_grounded_whole_pool_remainder(monkeypatch,evidence,join,confirm,action):
    run,req,source=fixture(monkeypatch);before=deepcopy(run['claims']);original=deepcopy(source)
    calls=native_contract(monkeypatch,run,evidence=evidence,join=join,confirm=confirm)
    a=business_run.assess(None,run,req,source=source,focus_meaning_keys=['part'])
    target=next(x for x in a['actions'] if x['meaning_key']=='part')
    assert target['action']==action and a['status']=='partial'
    assert a['source']['processing_scope']['pending_meaning_keys']==['other']
    assert a['source']['meanings']==original['meanings'] and source==original and run['claims']==before
    assert set(c['id'] for c in calls[0]['claims'])=={c['id'] for c in before}
    assert calls[1]['requirement']==req
    assert len([x for x in a['actions'] if x.get('candidate_review_id')])==2  # v8 public direct-review branch
    if action=='recover':
        assert target['claim_ids']==[] and target['contributing_claim_ids']==[before[0]['id']]
        assert target['missing_evidence'][0]['source_version_id']=='v'


def test_empty_represented_is_neither_maintained_nor_recovered(monkeypatch):
    run,req,source=fixture(monkeypatch)
    native_contract(monkeypatch,run,status='represented',location=False)
    a=business_run.assess(None,run,req,source=source,focus_meaning_keys=['part'])
    assert next(x for x in a['actions'] if x['meaning_key']=='part')['action']=='hold'
    assert 'part' in a['blocked_meaning_keys']
    assert a['review_scope']['failures'][0]['reason']=='expression_without_candidate_location'


def test_one_empty_location_does_not_discard_a_sibling_whole_pool_missing_check(monkeypatch):
    run,req,source=fixture(monkeypatch)
    native_contract(monkeypatch,run,status='missing',location=False)
    original=business_run.json_call
    def one_bad(*args):
        out=original(*args)
        if args[4]['mode']=='meaning_batch':
            out['checks'][0]['status']='represented'
        return out
    monkeypatch.setattr(business_run,'json_call',one_bad)
    a=business_run.assess(None,run,req,source=source,focus_meaning_keys=['part','other'])
    actions={t['meaning_key']:t['action'] for t in a['actions']}
    assert actions['part']=='hold' and actions['other']=='recover'
    assert a['blocked_meaning_keys']==['part']


def test_invalid_candidate_challenge_keeps_its_owner_and_does_not_rewrite_source(monkeypatch):
    run,req,source=fixture(monkeypatch)
    out=dict(checks=[dict(meaning_key='part',status='partial',claim_ids=[run['claims'][0]['id']])],
        source_challenges=[],meaning_challenges=[],candidate_challenges=[dict(meaning_key='part',
            claim_ids=[],fields=[],evidence=[],reason='실제 위치가 없는 후보 이의')])
    review.attach_candidate_support(run,out,run['claims'],run['blocks'])
    assert out['source_challenges']==[] and out['candidate_challenge_errors']
    assert out['meaning_challenges'][0]['source_reassessment_needed'] is False
    out['dependencies']=[dict(meaning_key=k,premise_keys=[]) for k in ('part','other')]
    assert review.blocked(dict(source=source,representation=out,errors=[],issues=[]))==({'part'},[])


def test_focused_processing_keeps_unattributed_findings_and_preserves_deferred_work(monkeypatch):
    run,req,source=fixture(monkeypatch)
    source['meanings'][0]['premise_keys']=['other']
    source['meanings'].append(meaning('later',required_for_requirement=True))
    source['public_scope']['review_meaning_keys'].append('later')
    def finding(key,keys):return dict(id=key,meaning_keys=keys,scope_meaning_keys=keys,claim_ids=[],fields=[],
        origin='source',kind='interpretation_uncertain',text=key,unit_id='old',provided_block_ids=['body'])
    source['findings']=[finding('later-finding',['later']),finding('free',[])]
    before=deepcopy(source)
    captured={}
    def local(_s,_run,_req,view,context,**options):
        captured.update(deepcopy(view))
        view['finding_resolutions']=[dict(finding_id='free',status='unresolved')]
        return {},{}
    monkeypatch.setattr(review,'_represent',local)
    source['processing_scope']=dict(requested_meaning_keys=['part'],pending_meaning_keys=['later'])
    result,scope=review.represent(None,run,req,source,[])
    assert {m['key'] for m in review.review_meanings(captured)}=={'part','other'}
    assert [f['id'] for f in captured['findings']]==['free']
    assert source['findings']==before['findings'] and source['meanings']==before['meanings']
    assert scope['processing_scope']['deferred_finding_ids']==['later-finding']


def test_focus_cannot_change_original_question_or_select_unrequested_meaning(monkeypatch):
    run,req,source=fixture(monkeypatch)
    with pytest.raises(ValueError,match='같은 공개 요구'):
        business_run.assess(None,run,dict(req,question='다른 질문'),source=source,focus_meaning_keys=['part'])
    with pytest.raises(ValueError,match='기존 선택 의미'):
        business_run.assess(None,run,req,source=source,focus_meaning_keys=['unknown'])


def test_remainder_uses_existing_evidence_ids_and_restores_the_source_address(monkeypatch):
    from app.knowledge.business_models import ContributionReviewCheck
    run,req,source=fixture(monkeypatch)
    raw=dict(checks=[dict(meaning_key='part',status='partial',claim_ids=[],reason='일부',
        represented_content='기존 부분',missing_content='나머지',missing_evidence=['e1'])],
        dependencies=[],source_challenges=[],meaning_challenges=[],candidate_challenges=[])
    def response(*args,**kwargs):
        run['units'].append(dict(id='remainder'))
        return dict(parsed=deepcopy(raw))
    monkeypatch.setattr(business_run,'call',response)
    output=business_run.json_call(None,run,'requirement_representation','',dict(blocks=run['blocks']),ContributionReviewCheck)
    ref=output['checks'][0]['missing_evidence'][0]
    assert ref['source_version_id']=='v' and ref['parse_run_id']=='p' and ref['quote']==run['blocks'][0]['text']
    assert raw['checks'][0]['missing_evidence']==['e1']


def test_recovery_keeps_model_sentence_and_leaves_unverified_relation_scope_unused(monkeypatch):
    run,req,source=fixture(monkeypatch)
    proposal=dict(statement='기관은 신청을 접수한다.',head='기관',relation='의무',tail='합성한 기간',
        role=None,evidence=[dict(block_id='body',quote=run['blocks'][0]['text'])],scope=dict(invalid_modality='obligation'),
        conditions=[],exceptions=[],period='',references=[])
    before=deepcopy(proposal)
    patch=business_run.recovered_statement_patch(proposal,run['blocks'])
    value=business_run.materialize_patch(run,patch,None,'new',run['blocks'],origin=patch['origin'])
    assert proposal==before and value['statement']==value['raw']['Event']==proposal['statement']
    assert value['raw']['Entity']==['기관'] and 'interpretation' not in value
    assert value['review_status']=='unreviewed' and value['semantic_status']=='unknown'
    assert value['edit_participants'][0]['quote']=='기관'
    assert value['edit_participants'][0]['start_char']==0


@pytest.mark.parametrize('head,quote', [('없는 참여자','기관은 신청을 접수한다.'),('기관','기관과 기관은 신청을 접수한다.')])
def test_recovery_never_invents_or_chooses_an_ambiguous_participant(monkeypatch,head,quote):
    run,req,source=fixture(monkeypatch)
    run['blocks'][0]['text']=quote
    patch=dict(statement='모델 문장',head=head,role=None,evidence=[dict(block_id='body',quote=quote)])
    with pytest.raises(ValueError,match='유일하지 않음'):
        business_run.recovered_statement_patch(patch,run['blocks'])


@pytest.mark.parametrize('role', ['entity_relation', 'event_relation'])
def test_recovery_preserves_an_explicit_relation_role(monkeypatch,role):
    from app.tests.unit.test_knowledge_business_scope import scope_for
    run,req,source=fixture(monkeypatch)
    native_contract(monkeypatch,run,status='missing',location=False)
    assessment=business_run.assess(None,run,req,source=source,focus_meaning_keys=['part'])
    scope=scope_for(dict(source_reference_map={'body':dict(block_id='body')}),run['blocks'][0]['text'])
    scope['meanings'][0]['conditions']=dict(state='absent',text=None)
    patch=dict(meaning_key='part',target_id=None,role=role,statement=run['blocks'][0]['text'],
        head='기관',relation='접수',tail='신청',evidence=source['meanings'][0]['evidence'],
        conditions=[],exceptions=[],period='',references=[],scope=scope)
    monkeypatch.setattr(business_run,'json_call',lambda *a:dict(patches=[patch],unresolved=[]))
    monkeypatch.setattr(business_run,'recovered_statement_patch',lambda *a:pytest.fail('Explicit relation role was changed'))
    assert business_run.repair(None,run,req,assessment)
    assert run['claims'][-1]['role']==role and run['claims'][-1]['raw']==dict(Head='기관',Relation='접수',Tail='신청')


def test_own_review_reuses_recorded_empty_challenges_without_ignoring_real_changes(monkeypatch):
    import json
    from app.tests.unit.test_knowledge_business_responsibilities import setup_direct_receipt
    run,receipt=setup_direct_receipt(monkeypatch,states=('supported','supported'))
    unit=run['units'][-1]
    packet=json.loads(unit['messages'][-1]['content'])
    versions=packet.pop('source_versions')
    packet['candidate_challenges']=[]
    packet['source_versions']=versions
    unit['messages'][-1]['content']=json.dumps(packet,ensure_ascii=False)
    assert set(review.current_candidate_reviews(run))==set(receipt['claim_ids'])
    run['candidate_challenges']=[dict(claim_ids=[receipt['claim_ids'][0]],fields=['raw.Relation'])]
    assert set(review.current_candidate_reviews(run))=={receipt['claim_ids'][1]}
    run['claims'][1]['raw']['Relation']='changed'
    assert review.current_candidate_reviews(run)=={}


def test_focused_merge_does_not_duplicate_unscoped_gaps_or_deferred_resolutions(monkeypatch):
    run,req,source=fixture(monkeypatch)
    source.update(processing_scope=dict(requested_meaning_keys=['part']),
        meaning_gaps=[dict(meaning_keys=[],text='unattributed'),dict(meaning_keys=['other'],text='deferred')],
        finding_resolutions=[dict(finding_id='outside',status='unresolved')])
    before=deepcopy(source)
    monkeypatch.setattr(review,'_represent',lambda *args,**kwargs:({},{}))
    review.represent(None,run,req,source,[])
    assert source['meaning_gaps']==before['meaning_gaps']
    assert source['finding_resolutions']==before['finding_resolutions']
