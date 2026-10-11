"""Public work cannot disappear because the current candidate covers only one case."""
from copy import deepcopy

import pytest

from app.knowledge import business_review as review, business_run
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning
from app.tests.unit.test_knowledge_business_scope import block


@pytest.mark.parametrize('field,valid', [('Relation',True),('Missing',False)])
def test_own_source_field_alias_restores_only_existing_literal_raw_key(monkeypatch,field,valid):
    from app.tests.unit.test_knowledge_business_responsibilities import setup_direct_receipt
    def alias(output):
        output['checks'][1]['error_fields']=[field]
    run,receipt=setup_direct_receipt(monkeypatch,transform=alias)
    cid=run['claims'][1]['id']
    assert receipt['output']['checks'][1]['error_fields']==[field]
    if valid:
        assert not receipt['errors'] and receipt['checks'][1]['error_fields']=={cid:['raw.Relation']}
        assert receipt['field_address_restorations'][0]['original_fields']==[field]
        assert cid in review.current_candidate_reviews(run)
    else:
        assert receipt['errors'][0]['reason']=='candidate_error_field_not_provided'
        assert cid not in review.current_candidate_reviews(run)


def test_reviewed_items_can_bind_to_snapshot_requirements_without_explicit_filter():
    from app.knowledge.business_models import BusinessQuery
    from app.knowledge.business_use import bind_answer_items
    request=BusinessQuery(question='신청 안내',snapshot_id='snapshot',answer_mode='reviewed_items',
        answer_items=[dict(id='item',requirement_id='r',requirement_revision=1,field='question',request_quote='신청')])
    assert request.requirement_ids==[] and request.answer_items[0].requirement_id=='r'
    assert len(bind_answer_items(request,[dict(id='r',revision=1,question='신청 안내')]))==1
    with pytest.raises(ValueError,match='revision'):
        bind_answer_items(request,[dict(id='r',revision=2,question='신청 안내')])


def test_direct_event_field_edit_keeps_other_fields_and_requires_fresh_review():
    from app.tests.unit.test_knowledge_business_preservation_fields import actual_change
    run,_,_=actual_change();old=deepcopy(run['claims'][0])
    old['evidence']=business_run.exact_evidence([dict(block_id=run['blocks'][0]['id'],quote=run['blocks'][0]['text'])],run['blocks'])
    second=dict(deepcopy(run['blocks'][0]),id='second',source_version_id='v2')
    run['blocks'].append(second);old['source_version_ids'].append('v2')
    old['evidence'].extend(business_run.exact_evidence([dict(block_id='second',quote=second['text'])],run['blocks']))
    patch=dict(raw=dict(Event=old['raw']['Event'],Entity=['모델의 임의 참여자']),evidence=old['evidence'][:1],
        conditions=['모델의 새 조건'],exceptions=['새 예외'],period='새 기간',references=['새 참조'],scope=dict(invalid=True))
    original=deepcopy(patch)
    value=business_run.materialize_patch(run,patch,old,'repair',run['blocks'],origin='model_event_field_edit')
    assert patch==original and value['raw']['Entity']==old['raw']['Entity']
    assert all(value[k]==old[k] for k in ('conditions','exceptions','period','references'))
    assert value['review_status']=='unreviewed' and value['edited_fields']==['raw.Event']
    assert set(value['source_version_ids'])=={e['source_version_id'] for e in value['evidence']}==set(old['source_version_ids'])
    assert 'interpretation' not in value and value['qualifier_status']=='unparsed_model_edit_requires_review'


@pytest.mark.parametrize('fields,role,applied', [(['raw.Event'],'event_entity',True),
    (['raw.Event','conditions'],'event_entity',False),(['interpretation'],'event_entity',False),
    (['raw.Event'],'entity_relation',False)])
def test_event_only_boundary_excludes_other_errors_and_role_conversion(monkeypatch,fields,role,applied):
    from app.tests.unit.test_knowledge_business_preservation_fields import actual_change
    run,_,_=actual_change();old=run['claims'][0];cid=old['id']
    old['raw']['Entity']=['원문에 문자 그대로 없는 참여자']
    old['evidence']=business_run.exact_evidence([dict(block_id=run['blocks'][0]['id'],quote=run['blocks'][0]['text'])],run['blocks'])
    check=dict(incorrect_claim_ids=[cid],error_fields={cid:fields},error_evidence=old['evidence'])
    monkeypatch.setattr(review,'current_candidate_reviews',lambda r:{cid:dict(receipt_id='own',unit_id='native',check=check)})
    action=dict(meaning_key='candidate:'+cid,action='correct',claim_ids=[cid],candidate_review_id='own',
        error_fields={cid:fields},error_evidence=old['evidence'])
    assessment=dict(id='a',source=dict(public_scope=dict(tasks=[],review_meaning_keys=[]),meanings=[]),representation=None,errors=[],issues=[],actions=[action])
    patch=dict(meaning_key=action['meaning_key'],target_id=cid,role=role,conversion_reason='',
        raw=deepcopy(old['raw']),evidence=old['evidence'],conditions=[],exceptions=[],period='',references=[],scope=dict(invalid=True))
    monkeypatch.setattr(business_run,'json_call',lambda *a:dict(patches=[patch],unresolved=[]))
    monkeypatch.setattr(business_run,'save',lambda *a:None)
    assert business_run.repair(None,run,run['requirements'][0],assessment)==applied


def setup(monkeypatch, *, support='supported'):
    run = local_run()
    requirement = dict(id='r', revision=1, question='기관의 신청 및 접수는?', criterion='조건과 공백',
        target='기관 안내 이용자', situation='개인·단체 안내', period='', source_ids=[])
    run['answer_items'] = [dict(id=k, requirement_id='r', requirement_revision=1, field='question', request_quote=q)
        for k,q in [('cancel','신청'), ('proof','접수')]]
    cid = run['claims'][0]['id']
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda r: {cid:dict(receipt_id='local', unit_id='own',
        check=dict(claim_support={cid:support}, incorrect_claim_ids=[], error_fields={}))})
    source = dict(meanings=[meaning('normal', required_for_requirement=True),
                            meaning('background', required_for_requirement=False)])
    return run, requirement, source, cid


def mock_scope(monkeypatch, run, cid, change=None, captured=None):
    def answer(_service, current, stage, instruction, packet, schema):
        assert stage == 'requirement_application'
        if captured is not None:
            captured.append(deepcopy(packet))
        rows = [dict(task_id=t['id'], meaning_keys=['normal'], candidate_ids=[cid], source_state='available',
            expression_state='represented', read_block_ids=[], gap='', reason='현재 표현의 기여') for t in packet['public_tasks']]
        if change:
            change(rows)
        schema.model_validate(dict(items=rows, meaning_challenges=[]))
        current['units'].append(dict(id='scope', status='succeeded', error=None,
            restored_evidence_output=dict(items=deepcopy(rows), meaning_challenges=[])))
        return dict(items=rows, meaning_challenges=[])
    monkeypatch.setattr(business_run, 'json_call', answer)


def test_public_case_tasks_are_independent_of_candidates_and_keep_unparsed_context():
    run = local_run()
    requirement = dict(id='r', revision=1, question='취소?', criterion='', target='관람객', situation='개인·단체 안내')
    run['answer_items'] = [dict(id='cancel',requirement_id='r',requirement_revision=1,field='question',request_quote='취소')]
    before = review.public_item_tasks(run, requirement)
    run['claims'] = []
    assert review.public_item_tasks(run, requirement) == before
    assert [t['context']['quote'] for t in before] == ['개인','단체']
    requirement['situation'] = '분기 없는 전체 상황'
    tasks = review.public_item_tasks(run, requirement)
    assert len(tasks) == 1 and tasks[0]['context']['quote'] == '관람객'
    assert requirement['situation'] == '분기 없는 전체 상황'


def test_missing_candidate_keeps_group_work_and_selects_existing_source_without_attacking_normal(monkeypatch):
    run, requirement, source, cid = setup(monkeypatch)
    before = deepcopy(source)
    def missing(rows):
        rows[1].update(candidate_ids=[], expression_state='not_found')
    mock_scope(monkeypatch, run, cid, missing)
    result = review.public_requirement_scope(None, run, requirement, source)
    scope = result['public_scope']
    assert source == before and not scope['errors'] and len(scope['tasks']) == 4
    assert scope['items'][1]['task_id'] == 'cancel/context2'
    assert scope['followup'][1]['action'] == 'check_candidate_pool'
    assert [m['key'] for m in review.review_meanings(result)] == ['normal']
    assert result['meanings'][1] == before['meanings'][1]
    assert scope['selection_is_not_expression_verdict_or_approval']


@pytest.mark.parametrize('fault', ['empty', 'unknown', 'incorrect'])
def test_presence_of_receipt_does_not_certify_current_expression(monkeypatch, fault):
    run, requirement, source, cid = setup(monkeypatch, support='supported' if fault=='empty' else fault)
    mock_scope(monkeypatch, run, cid, (lambda rows: rows[0].update(candidate_ids=[])) if fault=='empty' else None)
    result = review.public_requirement_scope(None, run, requirement, source)
    assert result['public_scope']['items'][0]['expression_state'] == 'unknown'
    assert result['public_scope']['errors']


def test_pending_read_and_missing_material_have_distinct_actions_and_preserve_sibling(monkeypatch):
    run, requirement, source, cid = setup(monkeypatch)
    def gaps(rows):
        rows[1].update(source_state='unread', expression_state='unknown', candidate_ids=[],
                       read_block_ids=['body'], gap='단체 조건을 추가로 읽어야 한다.')
        rows[2].update(source_state='not_provided', expression_state='unknown', candidate_ids=[], gap='참조 자료 미제공')
        rows[3].update(source_state='unselected', expression_state='unknown', candidate_ids=[],
                       read_block_ids=['body'], gap='제공 본문이 있으나 필요한 저장 의미를 선택하지 못함')
    mock_scope(monkeypatch, run, cid, gaps)
    result = review.public_requirement_scope(None, run, requirement, source)['public_scope']
    assert [r['action'] for r in result['followup']] == ['review_expression','read_source','specific_gap','lookup_stored_meanings']
    assert result['items'][0]['expression_state'] == 'represented' and not result['errors']


def test_unselected_source_catalog_contains_no_body_text(monkeypatch):
    run, requirement, source, cid = setup(monkeypatch)
    run['blocks'].extend(dict(block('hidden'+str(n), '미선택 원문 본문 '+str(n)), source_id='s') for n in range(5))
    monkeypatch.setattr(review, 'related_blocks', lambda *a: run['blocks'][:1])
    packets = []
    mock_scope(monkeypatch, run, cid, captured=packets)
    review.public_requirement_scope(None, run, requirement, source)
    assert packets[0]['source_inventory']
    assert all('text' not in row and row['provided'] is False for row in packets[0]['source_inventory'])


@pytest.mark.parametrize('change', ['public_context','candidate','source_fact','source_version'])
def test_scope_reuse_is_bound_to_public_context_candidate_and_source_versions(monkeypatch, change):
    run, requirement, source, cid = setup(monkeypatch)
    mock_scope(monkeypatch, run, cid)
    result = review.public_requirement_scope(None, run, requirement, source)
    assert review.public_scope_valid(run, requirement, result)
    assert review.public_requirement_scope(None, run, requirement, result) == result and len(run['units']) == 1
    if change == 'public_context':
        requirement['situation'] = '개인·단체 다른 상황'
    elif change == 'candidate':
        run['claims'][0]['raw']['Relation'] = '변경'
    elif change == 'source_fact':
        result['meanings'][0]['conditions'].append('실제 바뀐 조건')
    else:
        run['blocks'][0]['source_version_id'] = 'changed_version'
    assert not review.public_scope_valid(run, requirement, result)


def test_public_selection_keeps_conjunction_and_transitive_premises_without_unrelated_background():
    source = dict(public_scope=dict(review_meaning_keys=['answer']), review_contract=review.CONTRACT,
        meanings=[meaning('answer'), meaning('condition', required_for_requirement=False),
                  meaning('premise', required_for_requirement=False), meaning('background')],
        meaning_conjunctions=[dict(meaning_keys=['answer','condition'], text='명시된 연결')])
    source['meanings'][1]['premise_keys'] = ['premise']
    assert [m['key'] for m in review.review_meanings(source)] == ['answer','condition','premise']


def test_public_source_extraction_defers_applicability_to_scope_once(monkeypatch):
    run, requirement, _, _ = setup(monkeypatch)
    run['recipe']['review_contract'] = review.SOURCE_APPLICATION_CONTRACT
    monkeypatch.setattr(review, 'source_selection', lambda *a: (run['chunks'], {}))
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    calls=[]
    def answer(_s, current, stage, instruction, context, schema):
        calls.append(stage)
        current['units'].append(dict(id='fact'))
        return dict(examined_block_ids=['body'], inspection_status='complete', meanings=[meaning('m')],
                    findings=[], conjunctions=[], meaning_conjunctions=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(review, 'apply_requirement', lambda *a, **kw: pytest.fail('duplicate applicability call'))
    result=review.source(None, run, requirement)
    assert calls == ['requirement_source'] and result['meanings'][0]['source_status'] == 'supported'


def test_fieldless_scope_allegation_cannot_rejudge_normal_source(monkeypatch):
    run=local_run(); source=dict(public_scope={}, application_challenges=[])
    allegation=dict(meaning_key='normal', claim_ids=[], fields=[], evidence=[], reason='후보 오류 주장')
    source.update(public_scope=dict(tasks=[]), application_challenges=[allegation])
    assessment=dict(source=source, representation={}, source_record_challenges=[])
    monkeypatch.setattr(review, 'source_row_challenges', lambda *a: [])
    monkeypatch.setattr(review, 'answer_scope_challenges', lambda *a: [])
    monkeypatch.setattr(review, 'reassess_source', lambda *a: pytest.fail('normal source rejudged'))
    assert business_run.reassess_challenges(None, run, run['requirements'][0], assessment) == assessment
    assert assessment['rejected_public_source_challenges'] == [allegation]
    assert source['application_challenges'] == [allegation]


def test_public_r_batches_independent_facts_and_reuses_own_source_verdicts(monkeypatch):
    from app.knowledge.business_models import ContributionReviewCheck, ContributionSynthesisCheck
    run, requirement, source, cid=setup(monkeypatch)
    run['recipe']['review_contract']=review.CONTRACT
    source.update(public_scope=dict(review_meaning_keys=['normal','background'], tasks=[],items=[],errors=[],followup=[]),
        completeness='unknown', gaps=[], conjunctions=[], meaning_conjunctions=[], findings=[],source_batches=[],review_contract=review.CONTRACT)
    calls=[]
    monkeypatch.setattr(business_run,'cancelled',lambda *a:False)
    def answer(_s,current,stage,instruction,packet,schema):
        calls.append(packet['mode']); current['units'].append(dict(id='r'+str(len(calls))))
        output=dict(checks=[], dependencies=[],source_challenges=[],meaning_challenges=[],candidate_challenges=[],preservation_checks=[])
        if packet['mode']=='meaning_batch':
            assert schema is ContributionReviewCheck and len(packet['source']['meanings'])==2
            assert packet['whole_candidate_judgments'][0]['claim_id']==cid
            output.update(checks=[dict(meaning_key=m['key'],status='represented',claim_ids=[cid],reason='기여')
                for m in packet['source']['meanings']], dependencies=[dict(meaning_key=m['key'],premise_keys=[])
                for m in packet['source']['meanings']])
        else:
            assert schema is ContributionSynthesisCheck
            output.update(satisfied=True,conjunctions_satisfied=True,reason='연결',source_completeness='complete',
                unselected_source_required=False,finding_resolutions=[])
        return output
    monkeypatch.setattr(business_run,'json_call',answer)
    result,scope=review.represent(None,run,requirement,source,[])
    assert calls==['meaning_batch','requirement_join'] and scope['join_succeeded']
    assert all(row['claim_support'][cid]=='supported' for row in result['checks'])
    assert all(row['required_for_requirement'] for row in result['source_checks'])
    assert all(row['premise_keys']==[] for row in result['dependencies'])


def test_reviewed_qa_keeps_public_item_and_renders_each_context_with_its_own_gap(monkeypatch):
    from types import SimpleNamespace
    from app.knowledge import business_use
    from app.tests.unit.test_knowledge_business_conjunctions import setup as qa_setup
    from app.tests.unit.test_knowledge_business_local_review import judgments
    run,source=qa_setup(); requirement=run['requirements'][0]
    requirement['situation']='개인·단체 안내'
    original=deepcopy(run['answer_items'])
    run['answer_work_items']=[dict(t['item'],id=t['id'],public_item_id=t['item']['id'],context=t['context'])
        for t in review.public_item_tasks(run,requirement)]
    run['answer_work_records']=[dict(task_id=run['answer_work_items'][1]['id'],source_state='available',
        expression_state='not_found',read_block_ids=['body'],gap='제공 원문은 있으나 단체 후보 표현이 없음',
        followup=dict(action='check_existing_pool'),source_binding_valid=True,candidate_binding_valid=False,
        authority='previous_work_state_not_truth_or_approval')]
    representation=judgments(['m'],ids=[run['claims'][0]['id']])
    representation['checks'][0]['claim_support']={run['claims'][0]['id']:'supported'}
    snapshot=dict(assessments={'r':dict(id='a',source=source,representation=representation)},
        blocks=run['blocks'])
    run['reviewed_meanings']=business_use.reviewed_answer_meanings(snapshot,{run['claims'][0]['id']},['r'])
    def answer(_s,current,stage,instruction,packet,schema):
        assert packet['public_answer_items']==original and len(packet['answer_work_items'])==2
        assert packet['public_work_records']==run['answer_work_records']
        assert '현재 판정으로 사용하지 않는다' in instruction
        output=dict(items=[dict(item_id=run['answer_work_items'][0]['id'],selected=[dict(meaning_ref='m1',use='direct_fact')],unconfirmed=[]),
            dict(item_id=run['answer_work_items'][1]['id'],selected=[],unconfirmed=['단체 접수기관의 검토 후보 연결을 확인하지 못했습니다.'])])
        schema.model_validate(output)
        return output
    monkeypatch.setattr(business_run,'json_call',answer)
    output=business_use.reviewed_item_answer(None,run,SimpleNamespace(question=requirement['question']),[])
    assert run['answer_items']==original and not run['answer_item_errors']
    assert ' · 개인' in output['answer'] and ' · 단체' in output['answer']
    assert output['answer'].count('검토된 원문 의미:')==1 and '확인 불가: 단체 접수기관' in output['answer']


@pytest.mark.parametrize('change',['candidate','source','attributed_challenge'])
def test_own_source_usage_keeps_normal_facts_but_blocks_changed_or_challenged_candidates(monkeypatch,change):
    from app.knowledge import business_use
    from app.tests.unit.test_knowledge_business_responsibilities import setup_direct_receipt
    run,_=setup_direct_receipt(monkeypatch,states=('supported','supported'))
    ids={c['id'] for c in run['claims']}
    run['assessments']=[dict(requirement_id='r',source=dict(public_scope=dict(tasks=[])),representation=None)]
    assert business_use.eligibility(run)[0]==ids
    cid=run['claims'][0]['id']
    if change=='candidate':run['claims'][0]['raw']['Relation']='변경'
    elif change=='source':run['blocks'][0]['text']='다른 자료'
    else:run['candidate_challenges']=[dict(claim_ids=[cid],fields=['raw.Relation'],evidence=run['claims'][0]['evidence'],reason='실제 새로운 모순')]
    assert cid not in business_use.eligibility(run)[0]
    if change=='attributed_challenge':assert business_use.eligibility(run)[0]==ids-{cid}


def test_own_source_qa_carries_candidate_text_and_rejects_snapshot_version_drift(monkeypatch):
    from app.knowledge import business_use
    from app.tests.unit.test_knowledge_business_responsibilities import setup_direct_receipt
    run,_=setup_direct_receipt(monkeypatch,states=('supported','supported'))
    snapshot=dict(requirements=run['requirements'],blocks=deepcopy(run['blocks']),
        assessments={'r':dict(id='a',source=dict(public_scope=dict(tasks=[]),meanings=[dict(statement='R의 잘못된 전체 결론')]))},
        claims=[dict(c,review_status='accepted') for c in run['claims']],reviewed_claim_evidence={c['id']:dict(
            claim_version=review.autoschema.identifier('claim',c),original_review_status=c.get('review_status'),
            source_versions=c['source_version_ids'],source_fingerprint=review.preservation_source_version(run,c['source_version_ids']),
            receipt_id='own',unit_id='direct',evidence=c['evidence']) for c in run['claims']})
    ids={c['id'] for c in run['claims']}
    rows=business_use.reviewed_answer_meanings(snapshot,ids,['r'])
    assert len(rows)==2 and all(m['kind']=='own_source_candidate' for m in rows)
    assert {m['statement'] for m in rows}=={c['statement'] for c in run['claims']}
    assert all(m['judgment_origin']['scope']=='candidate_fact_only_not_whole_requirement_or_connection' for m in rows)
    assert business_use.reviewed_answer_connections(snapshot,run,['r'])==[]
    snapshot['claims'][0]['raw']['Relation']='changed'
    assert len(business_use.reviewed_answer_meanings(snapshot,ids,['r']))==1
    snapshot['blocks'][0]['text']='changed source'
    assert business_use.reviewed_answer_meanings(snapshot,ids,['r'])==[]
