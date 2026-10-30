"""Role boundaries and downstream holds, with synthetic data and no model/network."""
from copy import deepcopy
import json

import pytest

from app.knowledge import business_role_review as roles, business_run as execution


@pytest.fixture
def case():
    text='재료 돼지고기 120g. 싱거우면 간장이나 소금.'
    block=dict(id='block1',source_version_id='v1',parse_run_id='p1',run_id='p1',source_id='s1',
        text=text,span=[0,len(text)],type='paragraph',metadata={})
    ref=dict(block_id='block1',source_version_id='v1',parse_run_id='p1',quote='돼지고기 120g',start_char=3,end_char=12,precision='exact')
    claim=dict(id='c1',role='relation',source_version_ids=['v1'],raw=dict(Head='조리',Relation='재료',Tail='돼지고기'),
        statement='조리 — 재료 — 돼지고기',semantic_status='unknown',evidence=[dict(ref,quote=text,start_char=0,end_char=len(text))],
        interpretation=dict(contract='unverified',semantic_status='unverified',target_status='addressed',
            evidence=[dict(quote='EVIDENCE_ONLY_200g')],meanings=[dict(id='m1',statement_type='rule',relation_kind='other',
                subject='조리',action='재료',object='돼지고기',applies_to='조리',modality='unresolved',
                conditions=dict(state='present',text='싱거우면'),exceptions=dict(state='absent',text=None),
                time=dict(state='unresolved',text=None),local_negation=dict(state='absent',text=None),
                references=dict(state='absent',text=None),premises=dict(state='unresolved',meaning_indices=[]),premise_ids=[],
                evidence=[dict(quote='MEANING_EVIDENCE_ONLY')],participants=[dict(value='돼지고기',evidence=[dict(quote='PARTICIPANT_ONLY_200g')])])]))
    requirement=dict(id='req',revision=1,question='돼지고기 재료를 확인한다',criterion='필요한 재료 확인',
        target='조리',situation='대조',period='현재',source_ids=['s1'])
    target=dict(key='t1',ref=ref)
    source=dict(meanings=[dict(key='t1',statement='돼지고기 120g',conditions=[],exceptions=[],period='',references=[],
        source_status='supported',availability='provided',premise_keys=[],evidence=[ref],required_for_requirement=True)],
        completeness='complete',gaps=[],meaning_gaps=[],meaning_conjunctions=[],findings=[],
        public_scope=dict(input_contract='public-source-applicability-only-v2'),requirement_content_contract='question-required-content-v1')
    run=dict(id='run',recipe=dict(review_contract='requirement-local-review-v8-owned-errors',
        options=dict(context_tokens=49152,review_tokens=8192,representation_tokens=8192,think=False,timeout=1800)),
        claims=[claim],blocks=[block],sources={'v1':dict(source_id='s1',title='SOURCE_TITLE_SHOULD_NOT_LEAK')},
        role_review=dict(contract=roles.CONTRACT,claim_ids=['c1'],blocks=[block],block_ids=['block1'],targets=[target]),
        units=[dict(id='u1'),dict(id='u2'),dict(id='u3')],assessments=[],repairs=[],requirements=[requirement])
    row=dict(meaning_key='t1',status='partial',claim_ids=['c1'],reason='재료는 저장, 수량은 미발견',
        represented_content='돼지고기',missing_content='120g',missing_evidence=[dict(ref,quote='120g',start_char=8,end_char=12)],
        expression_quotes=[dict(claim_id='c1',field='raw.Tail',quote='돼지고기')],requirement_scope_id=None,
        source_statement='돼지고기 120g',field_checks={k:'supported' if k=='statement' else 'not_applicable'
            for k in ['statement','conditions','exceptions','period','references']},evidence=[ref],
        incorrect_claim_ids=[],error_fields={},error_evidence=[])
    raw_source=dict(checks=[row],source_challenges=[],meaning_challenges=[],dependencies=[],preservation_checks=[])
    decision=dict(item='재료',importance='required',requirement_quote='돼지고기 재료',status='partial',claim_ids=['c1'],
        expression_quotes=deepcopy(row['expression_quotes']),represented_content='돼지고기',missing_content='120g',
        reason='필요한 재료의 부분 표현',target_id='t1',source_result_ids=['t1'])
    initial=dict(items=[{k:v for k,v in decision.items() if k not in {'target_id','source_result_ids'}}],
        inspections=[dict(item_index=0,subject_quote='조리',attribute_quote='재료',source_version_ids=['v1'],
            claim_ids=['c1'],facets=['quantity'],reason='NEVER_FORWARD_VERDICT')],reason='원문 확인')
    final=dict(decisions=[decision],overall='insufficient_in_scope',reason='국소 부족함')
    return run,requirement,source,claim,target,raw_source,initial,final


def test_business_packet_keeps_actual_structure_but_not_source_quotes(case):
    run,req,_,claim,*_=case
    packet=roles.business_input(run,req,[claim]);serialized=json.dumps(packet,ensure_ascii=False)
    assert '120g' not in serialized and '200g' not in serialized
    assert 'EVIDENCE_ONLY' not in serialized and 'PARTICIPANT_ONLY' not in serialized
    assert 'SOURCE_TITLE_SHOULD_NOT_LEAK' not in serialized
    meaning=packet['stored_candidates'][0]['stored_interpretation']['meanings'][0]
    original=claim['interpretation']['meanings'][0]
    for key in ['statement_type','relation_kind','conditions','exceptions','time','local_negation','references','premises','premise_ids']:
        assert meaning[key]==original[key]
    assert '싱거우면' in serialized and meaning['time']['state']=='unresolved'
    request=execution.json_request(run,'requirement_representation',roles.BUSINESS_PROMPT,packet,roles.BusinessReview)
    assert all(secret not in request['messages'][1]['content'] for secret in ['120g','200g','NEVER_FORWARD_VERDICT'])


def test_real_stored_condition_is_not_removed_because_source_has_same_text(case):
    run,req,_,claim,*_=case;claim['raw']['Event']='싱거우면 간장이나 소금.'
    packet=roles.business_input(run,req,[claim])
    assert packet['stored_candidates'][0]['fields']['raw.Event']=='싱거우면 간장이나 소금.'


def test_source_handoff_drops_business_verdict_and_reason(case):
    run,req,_,claim,target,_,initial,_=case
    initial['items']=[dict(status='missing',reason='BUSINESS_EXPECTED_ANSWER')]
    packet,errors=roles.source_input(initial,roles.business_input(run,req,[claim]),[claim],[target],run['blocks'])
    text=json.dumps(packet,ensure_ascii=False)
    assert not errors and 'BUSINESS_EXPECTED_ANSWER' not in text and 'NEVER_FORWARD_VERDICT' not in text
    assert set(packet['diagnostic_targets'][0])=={'target_id','source_version_id','parse_run_id','block_id','span'}
    assert 'required' not in packet['diagnostic_targets'][0] and 'statement' not in packet['diagnostic_targets'][0]
    assert packet['inspection_requests'][0]['item_index']==0
    assert packet['inspection_requests'][0]['attribute_quote']=='재료'


def test_unprovided_answer_cannot_be_forwarded_as_inspection_attribute(case):
    run,req,_,claim,target,_,initial,_=case
    initial['inspections'][0]['attribute_quote']='120g 누락'
    packet,errors=roles.source_input(initial,roles.business_input(run,req,[claim]),[claim],[target],run['blocks'])
    assert not packet['inspection_requests'] and errors


def test_final_handoff_contains_observations_separate_from_storage_without_source_body(case):
    run,req,_,claim,target,raw,initial,_=case
    bound=roles.bind_source(raw,[claim],[target],run['blocks'])
    packet=roles.final_input(roles.business_input(run,req,[claim]),initial,raw,bound)
    assert packet['observations_are_stored_knowledge'] is False
    assert 'blocks' not in packet and run['blocks'][0]['text'] not in json.dumps(packet,ensure_ascii=False)
    assert all('quote' not in address for o in packet['source_observations'] for address in o['source_locations'])
    assert packet['stored_candidates'][0]['fields']['raw.Tail']=='돼지고기'
    assert packet['source_observations'][0]['missing_content']=='120g'


def test_source_missing_quantity_preserves_normal_material_contribution(case):
    run,_,_,claim,target,raw,*_=case
    bound=roles.bind_source(raw,[claim],[target],run['blocks'])['checks'][0]
    assert bound['status']=='partial' and not bound['consumer_errors']
    assert bound['represented_content']=='돼지고기' and bound['missing_content']=='120g'
    assert bound['expression_bindings'][0]['span']==[0,4]


@pytest.mark.parametrize('mutation',['quote','owner','duplicate','outside','source_version'])
def test_invalid_locations_never_become_supported_expression(case,mutation):
    run,_,_,claim,target,raw,*_=case;row=raw['checks'][0]
    if mutation=='quote':row['expression_quotes'][0]['quote']='120g'
    elif mutation=='owner':claim['source_version_ids']=['other']
    elif mutation=='duplicate':row['missing_evidence']*=2
    elif mutation=='outside':row['missing_evidence']=[dict(target['ref'],quote='싱거우면',start_char=14,end_char=18)]
    else:row['missing_evidence'][0]['source_version_id']='other'
    bound=roles.bind_source(raw,[claim],[target],run['blocks'])['checks'][0]
    assert bound['status']=='unknown' and bound['consumer_errors']
    assert raw['checks'][0]['status']=='partial'


def test_local_missing_scope_is_hold_and_reference_is_not_requirement(case,monkeypatch):
    run,req,source,claim,target,raw,initial,final=case
    monkeypatch.setattr(roles.review,'candidate_pool',lambda *args:[claim,dict(claim,id='outside_local')])
    monkeypatch.setattr(roles.review,'pool_hash',lambda *args:'pool')
    bound=roles.bind_source(raw,[claim],[target],run['blocks'])
    assessment=roles.consume(run,req,source,[claim],[target],initial,raw,bound,final,['u1','u2','u3'])
    assert assessment['actions'][0]['action']=='hold'
    assert 'whole_candidate_inventory_not_accounted_for' in assessment['actions'][0]['reason']
    final['decisions'][0]['importance']='reference'
    assessment=roles.consume(run,req,source,[claim],[target],initial,raw,bound,final,['u1','u2','u3'])
    assert assessment['representation']['source_checks'][0]['required_for_requirement'] is False
    assert 'reference_not_required' in assessment['actions'][0]['reason']
    assert 'public_scope' not in assessment['source'] and 'required_for_requirement' not in assessment['source']['meanings'][0]


def test_bound_partial_reaches_existing_repair_selection_without_model_or_claim_edit(case,monkeypatch):
    run,req,source,claim,target,raw,initial,final=case
    monkeypatch.setattr(roles.review,'candidate_pool',lambda *args:[claim]);monkeypatch.setattr(roles.review,'pool_hash',lambda *args:'pool')
    bound=roles.bind_source(raw,[claim],[target],run['blocks'])
    assessment=roles.consume(run,req,source,[claim],[target],initial,raw,bound,final,['u1','u2','u3'])
    assert assessment['actions'][0]['action']=='recover'
    before=deepcopy(run['claims']);captured={}
    monkeypatch.setattr(roles.review,'related_blocks',lambda *args:run['blocks'])
    monkeypatch.setattr(execution,'missing_tabular_rows',lambda *args:([],[]))
    class StopBeforeModel(Exception):pass
    def inspect(service,run,stage,instruction,context,schema):
        captured.update(context);raise StopBeforeModel
    monkeypatch.setattr(execution,'json_call',inspect)
    with pytest.raises(StopBeforeModel):execution.repair(None,run,req,assessment)
    task=captured['tasks'][0]['meanings'][0]
    assert task['contributing_claim_ids']==['c1'] and task['missing_content']=='120g'
    assert task['missing_evidence']==bound['checks'][0]['missing_evidence']
    assert run['claims']==before


def test_source_existence_cannot_promote_final_nonexistent_storage(case,monkeypatch):
    run,req,source,claim,target,raw,initial,final=case
    monkeypatch.setattr(roles.review,'candidate_pool',lambda *args:[claim]);monkeypatch.setattr(roles.review,'pool_hash',lambda *args:'pool')
    bound=roles.bind_source(raw,[claim],[target],run['blocks'])
    final['decisions'][0].update(status='represented',represented_content='돼지고기 120g',missing_content='',
        expression_quotes=[dict(claim_id='c1',field='raw.Tail',quote='120g')])
    assessment=roles.consume(run,req,source,[claim],[target],initial,raw,bound,final,['u1','u2','u3'])
    assert assessment['representation']['checks'][0]['status']=='unknown'
    assert assessment['actions'][0]['action']=='hold'


@pytest.mark.parametrize('bad',['source_address','outside_error_id','unknown_requirement','outside_error_field','error_address','evidence_as_error_field'])
def test_unverified_error_never_becomes_correction(case,monkeypatch,bad):
    run,req,source,claim,target,raw,initial,final=case
    monkeypatch.setattr(roles.review,'candidate_pool',lambda *args:[claim]);monkeypatch.setattr(roles.review,'pool_hash',lambda *args:'pool')
    row=raw['checks'][0];row.update(incorrect_claim_ids=['c1'],error_fields={'c1':['raw.Relation']},error_evidence=[target['ref']])
    if bad=='source_address':row['evidence'][0]['source_version_id']='other'
    elif bad=='outside_error_id':row['incorrect_claim_ids']=['outside'];row['error_fields']={'outside':['raw.Relation']}
    elif bad=='unknown_requirement':final['decisions'][0]['importance']='unknown'
    elif bad=='error_address':row['error_evidence']=[dict(target['ref'],quote='not in source')]
    elif bad=='evidence_as_error_field':row['error_fields']={'c1':['interpretation.evidence.0.quote']}
    else:row['error_fields']={'c1':['raw.NotAField']}
    bound=roles.bind_source(raw,[claim],[target],run['blocks'])
    assessment=roles.consume(run,req,source,[claim],[target],initial,raw,bound,final,['u1','u2','u3'])
    assert not any(a['action'] in {'correct','recover'} for a in assessment['actions'])
    assert raw['checks'][0]['incorrect_claim_ids']


def test_attributed_source_error_can_reach_correction_with_normal_part_preserved(case,monkeypatch):
    run,req,source,claim,target,raw,initial,final=case
    monkeypatch.setattr(roles.review,'candidate_pool',lambda *args:[claim]);monkeypatch.setattr(roles.review,'pool_hash',lambda *args:'pool')
    claim['raw']['Relation']='금지한다';claim['statement']='조리 — 금지한다 — 돼지고기'
    raw['checks'][0].update(incorrect_claim_ids=['c1'],error_fields={'c1':['raw.Relation']},error_evidence=[target['ref']])
    bound=roles.bind_source(raw,[claim],[target],run['blocks'])
    assessment=roles.consume(run,req,source,[claim],[target],initial,raw,bound,final,['u1','u2','u3'])
    correct=[a for a in assessment['actions'] if a['action']=='correct']
    assert correct and correct[0]['claim_ids']==['c1']
    assert assessment['representation']['checks'][0]['represented_content']=='돼지고기'
    assert assessment['preservation_complete'] is False


def test_source_error_with_business_uncertainty_can_be_corrected_without_claiming_coverage(case,monkeypatch):
    run,req,source,claim,target,raw,initial,final=case
    monkeypatch.setattr(roles.review,'candidate_pool',lambda *args:[claim]);monkeypatch.setattr(roles.review,'pool_hash',lambda *args:'pool')
    claim['raw']['Relation']='금지한다';claim['statement']='조리 — 금지한다 — 돼지고기'
    raw['checks'][0].update(status='incorrect',represented_content='',missing_content='',missing_evidence=[],expression_quotes=[],
        incorrect_claim_ids=['c1'],error_fields={'c1':['raw.Relation']},error_evidence=[target['ref']])
    final['decisions'][0].update(status='unknown',represented_content='',missing_content='',expression_quotes=[])
    bound=roles.bind_source(raw,[claim],[target],run['blocks'])
    assessment=roles.consume(run,req,source,[claim],[target],initial,raw,bound,final,['u1','u2','u3'])
    assert assessment['representation']['checks'][0]['status']=='unknown'
    assert any(a['action']=='correct' for a in assessment['actions'])


def test_opt_in_assess_replaces_legacy_calls_without_changing_default(case,monkeypatch):
    run,req,source,*_=case;calls=[]
    monkeypatch.setattr(roles,'assess',lambda *args:calls.append('roles') or {'status':'partial'})
    monkeypatch.setattr(execution.business_review,'source',lambda *args:(_ for _ in ()).throw(AssertionError('legacy source call')))
    assert execution.assess(None,run,req,source=source)=={'status':'partial'} and calls==['roles']
    with pytest.raises(ValueError):execution.assess(None,run,req)
    run.pop('role_review')
    with pytest.raises(AssertionError,match='legacy source call'):execution.assess(None,run,req)
    assert calls==['roles']


def test_diagnostic_storage_never_replaces_latest_requirement_assessment(case,monkeypatch):
    run,req,source,claim,target,raw,initial,final=case
    old=deepcopy(run['assessments']);responses=[initial,raw,final]
    def local_call(*args,**kwargs):
        run['units'].append(dict(id='probe'+str(len(run['units']))));return responses.pop(0)
    monkeypatch.setattr(execution,'json_call',local_call)
    monkeypatch.setattr(execution,'request_budget',lambda *args:dict(prompt_exact=True,estimate_tokens=100))
    monkeypatch.setattr(execution,'save',lambda *args:None)
    monkeypatch.setattr(roles.review,'pool_hash',lambda *args:'pool')
    from app.knowledge import business_store
    monkeypatch.setattr(business_store,'save_assessment',lambda *args:(_ for _ in ()).throw(AssertionError('must not update current requirement')))
    got=roles.assess(None,run,req,source)
    assert got['diagnostic_only'] and run['assessments']==old
    assert run['role_review_assessments']==[got]
    assert run['role_reviews'][-1]['assessment_id']==got['id']
