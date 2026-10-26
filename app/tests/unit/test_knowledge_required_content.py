"""Synthetic scope and expression-location contracts, not M03 semantic labels."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_review as review, business_run
from app.tests.unit.test_knowledge_business_local_review import meaning, judgments, local_run


def content_case():
    run = local_run()
    text='상품의 부위는 등심이고 용도는 카레이며 중량은 500g이다.'
    run['blocks'][0]['text']=text
    run['chunks']=autoschema.chunks(run['blocks'],49152,4096)
    claims = [autoschema.graph_record(run['chunks'][0],'entity_relation',
        dict(Head='상품',Relation='부위' if n==0 else '용도',Tail='등심' if n==0 else '카레'),n) for n in range(2)]
    run['claims']=claims
    m = meaning('product', required_for_requirement=True)
    m.update(statement=text,evidence=business_run.exact_evidence([dict(block_id='body',quote=text)],run['blocks']))
    m['requirement_applications'] = [dict(item_id='item',required_for_requirement=True,
        requirement_link=dict(requested_fact='상품 부위와 용도',applicability='applicable',contribution='direct_answer',reason='질문에 명시'),
        required_content='상품의 부위는 등심이고 용도는 카레다.',evidence=m['evidence'],content_evidence_bound=True)]
    m.update({k:v for k,v in m['requirement_applications'][0].items() if k in {'requirement_link','required_for_requirement'}})
    source = dict(meanings=[m],requirement_content_contract=review.CONTENT_CONTRACT,
        public_scope=dict(input_contract=review.PUBLIC_SOURCE_INPUT_CONTRACT,review_meaning_keys=['product'],public_requirement=dict(id='r',revision=1)))
    m['requirement_applications'][0]['content_source_version']=review.required_source_version(source,m)
    return run,source,claims


def target_check(source,claims,*,status='represented'):
    target = review.requirement_content_target(source,source['meanings'][0])
    return dict(meaning_key='product',requirement_scope_id=target['scope_id'],status=status,
        claim_ids=[c['id'] for c in claims],represented_content='상품의 부위는 등심이고 용도는 카레다.',
        missing_content='',missing_evidence=[],reason='합성 기여 판단',
        expression_quotes=[dict(claim_id=c['id'],field='raw.Tail',quote=c['raw']['Tail']) for c in claims])


def test_required_scope_does_not_rewrite_original_fact_or_infer_legacy_content():
    _,source,_ = content_case(); before = deepcopy(source)
    target = review.requirement_content_target(source,source['meanings'][0])
    assert target['content']=='상품의 부위는 등심이고 용도는 카레다.' and source==before
    source['meanings'][0]['requirement_applications'][0].pop('required_content')
    assert review.requirement_content_target(source,source['meanings'][0]) is None
    assert review.application_required(source['meanings'][0]) is True


@pytest.mark.parametrize('interpretation',[False,True])
def test_paraphrase_and_multiple_claim_fields_keep_expression_locations(interpretation):
    run,source,claims = content_case(); check = target_check(source,claims)
    if interpretation:
        claims[0]['interpretation']=dict(meanings=[dict(object='등심')])
        check['expression_quotes'][0]['field']='interpretation.meanings.0.object'
    bound = review.bind_requirement_check(check,review.requirement_content_target(source,source['meanings'][0]),claims,run['blocks'])
    assert bound['status']=='represented' and len(bound['expression_bindings'])==2
    assert bound['represented_content']==check['represented_content'] and not bound.get('expression_errors')


def test_source_quote_cannot_supply_missing_stored_expression():
    run,source,claims = content_case()
    source['meanings'][0]['requirement_applications'][0]['required_content']='상품 중량은 500g이다.'
    source['meanings'][0]['requirement_link']['requested_fact']='상품 중량'
    check = target_check(source,claims)
    check['represented_content']='상품 중량은 500g이다.'
    check['expression_quotes'][0].update(field='evidence.0.quote',quote='500g')
    bound = review.bind_requirement_check(check,review.requirement_content_target(source,source['meanings'][0]),claims,run['blocks'])
    assert bound['status']=='unknown' and bound['expression_errors']
    assert bound['contract_errors'][0]['check']==check


def test_one_stored_field_can_support_a_paraphrased_required_summary():
    run,source,claims=content_case()
    claims=[dict(claims[0],raw=dict(Head='상품',Relation='속성',Tail='등심 부위이며 카레용'))]
    check=target_check(source,claims)
    check['expression_quotes']=[dict(claim_id=claims[0]['id'],field='raw.Tail',quote='등심 부위이며 카레용')]
    bound=review.bind_requirement_check(check,review.requirement_content_target(source,source['meanings'][0]),claims,run['blocks'])
    assert bound['status']=='represented' and len(bound['expression_bindings'])==1


def test_full_reference_remainder_survives_when_question_part_is_complete():
    run,source,claims = content_case()
    full = judgments(['product'],status='partial',ids=[claims[0]['id']])
    full['checks'][0].update(represented_content='상품 부위',missing_content='참고 중량 500g',missing_evidence=source['meanings'][0]['evidence'])
    q = review.bind_requirement_check(target_check(source,claims),review.requirement_content_target(source,source['meanings'][0]),claims,run['blocks'])
    full['requirement_checks']=[q]
    compact = review.summarize_local(source['meanings'],[full],source_owned=True,source=source)
    assert compact['checks'][0]['status']=='represented'
    assert compact['whole_expression_checks'][0]['status']=='partial'
    assert compact['whole_expression_checks'][0]['missing_content']=='참고 중량 500g'


def test_legacy_output_in_new_review_is_unknown_not_background_or_full_recovery():
    _,source,_ = content_case(); old = judgments(['product'],status='missing')
    result = review.question_representation(source,old)
    assert result['checks'][0]['status']=='unknown'
    assert result['whole_expression_checks'][0]['status']=='missing'
    assert review.requirement_states(source,result)['product'] is True


def test_scoped_missing_summary_keeps_the_exact_required_remainder():
    run,source,_=content_case()
    target=review.requirement_content_target(source,source['meanings'][0])
    check=dict(meaning_key='product',requirement_scope_id=target['scope_id'],status='missing',claim_ids=[],
        represented_content='',missing_content=target['content'],missing_evidence=target['evidence'],
        expression_quotes=[],reason='합성 묶음 미발견')
    full=judgments(['product'],status='missing')
    full['requirement_checks']=[review.bind_requirement_check(check,target,[],run['blocks'])]
    result=review.summarize_local(source['meanings'],[full],source_owned=True,source=source)
    assert result['checks'][0]['missing_content']==target['content']
    assert result['checks'][0]['missing_evidence']==target['evidence']
    assert result['checks'][0]['represented_content']==''


@pytest.mark.parametrize('field,value',[('conditions',['신규 조건']),('exceptions',['신규 예외']),('period','2026년'),('premise_keys',['other'])])
def test_source_judgment_change_invalidates_old_required_scope(field,value):
    run,source,claims = content_case(); target=review.requirement_content_target(source,source['meanings'][0])
    bound=review.bind_requirement_check(target_check(source,claims),target,claims,run['blocks'])
    source['meanings'][0][field]=value
    assert review.requirement_content_target(source,source['meanings'][0]) is None
    old=judgments(['product']);old['requirement_checks']=[bound]
    assert review.question_representation(source,old)['checks'][0]['status']=='unknown'


def test_expression_location_quote_does_not_turn_an_alias_literal_into_an_id():
    from app.knowledge.source_meanings import remap
    original=dict(expression_quotes=[dict(claim_id='claim-long',field='raw.Tail',quote='c1')])
    assert remap(remap(original,{'claim-long':'c1'}),{'c1':'claim-long'})==original


def install_product_dispatch(monkeypatch,run,source,*,suppress_use=False,whole_represented=False):
    from app.tests.unit.test_knowledge_business_separated_review import synthesis
    calls=[]
    monkeypatch.setattr(business_run,'request_budget',lambda *a,**k:dict(estimate_tokens=0))
    monkeypatch.setattr(review,'public_requirement_scope',lambda s,r,q,f:review.resolve_public_read_scope(r,q,f))
    monkeypatch.setattr(review,'current_candidate_reviews',lambda r:{c['id']:dict(receipt_id='synthetic-own',unit_id='synthetic-own',
        check=dict(claim_support={c['id']:'supported'},incorrect_claim_ids=[],error_fields={},error_evidence=[],reason='합성 자기 원문 판정')) for c in r['claims']})
    def scoped_check(target,claims):
        present=[c for c in claims if c['raw'].get('Tail') in ({'등심'} if suppress_use else {'등심','카레'})]
        values={c['raw']['Tail'] for c in present}
        absent={'등심','카레'}-values
        return dict(meaning_key='product',requirement_scope_id=target['scope_id'],
            status='partial' if absent and present else 'missing' if absent else 'represented',
            claim_ids=[c['id'] for c in present],represented_content='상품의 부위와 용도 일부' if absent and present else '상품은 등심 부위이며 카레용이다.' if present else '',
            missing_content=' / '.join(sorted(absent)),missing_evidence=deepcopy(target['evidence']) if absent else [],
            expression_quotes=[dict(claim_id=c['id'],field='raw.Tail',quote=c['raw']['Tail']) for c in present],reason='합성 필수부분 판정')
    def dispatch(service,current,stage,instruction,packet,schema):
        calls.append((stage,deepcopy(packet)))
        if stage=='requirement_application':
            out=dict(links=[dict(item_id=t['item_id'],key=t['key'],required_for_requirement=t['key']=='product',
                requirement_link=dict(requested_fact='상품 부위와 용도' if t['key']=='product' else '',
                    applicability='applicable' if t['key']=='product' else 'outside_scope',
                    contribution='direct_answer' if t['key']=='product' else 'background',reason='공개 질문에 필요한 부분과 참고 구분'),
                required_content='상품의 부위는 등심이고 용도는 카레다.' if t['key']=='product' else '',
                evidence=source['meanings'][0]['evidence'] if t['key']=='product' else []) for t in packet['application_tasks']],meaning_challenges=[])
        elif stage=='requirement_repair':
            target=packet['tasks'][0]['meanings'][0]
            assert target['missing_content']=='카레' and target['represented_content']
            assert target['contributing_claim_ids'] and target['requirement_scope_id']
            assert target['required_evidence'] and target['requirement_applications'][0]['requirement_link']['reason']
            assert target['review_records'] and all(r['check']['requirement_scope_id']==target['requirement_scope_id'] for r in target['review_records'])
            absent=dict(state='absent',text=None)
            scope=dict(evidence=source['meanings'][0]['evidence'],meanings=[dict(statement_type='definition',relation_kind='definition',
                subject='상품',action='용도',object='카레',applies_to='상품',modality='definition',conditions=absent,exceptions=absent,
                time=absent,local_negation=absent,references=absent,premises=dict(state='absent',meaning_indices=[]),
                evidence=source['meanings'][0]['evidence'],participants=[dict(field=field,entity_index=None,
                    evidence=business_run.exact_evidence([dict(block_id='body',quote=quote)],current['blocks']))
                    for field,quote in [('Head','상품'),('Tail','카레')]])])
            out=dict(patches=[dict(meaning_key='product',target_id=None,role='entity_relation',statement='상품의 용도는 카레다.',scope=scope,
                head='상품',relation='용도',tail='카레',conditions=[],exceptions=[],period='',references=[],
                evidence=source['meanings'][0]['evidence'])],unresolved=[])
        else:
            assert stage=='requirement_representation'
            if packet['mode']=='meaning_batch':
                ids=[c['id'] for c in packet['claims']]
                full=dict(meaning_key='product',status='partial',claim_ids=ids,represented_content='저장된 상품 속성',
                    missing_content='참고 중량 500g',missing_evidence=source['meanings'][0]['evidence'],reason='원문 전체의 참고 잔여')
                if whole_represented:
                    full.update(status='represented',missing_content='',missing_evidence=[],reason='합성 오류: 원문 전체 표현 과대 판정')
                full_rows=[full]
                if any(m['key']=='reference' for m in packet['source']['meanings']):
                    cut=next(c for c in packet['claims'] if c['raw']['Tail']=='등심')
                    full_rows.append(dict(full,meaning_key='reference',claim_ids=[cut['id']],represented_content='등심',missing_content='중량 500g'))
                out=dict(checks=full_rows,requirement_checks=[scoped_check(packet['required_content_targets'][0],packet['claims'])],
                    dependencies=[],source_challenges=[],meaning_challenges=[],candidate_challenges=[])
            else:
                existing=packet['local_judgments']['checks'][0]
                if packet['required_content_targets']:
                    row=scoped_check(packet['required_content_targets'][0],packet['claims'])
                    row.update(revision_basis='combined_expression',evidence=source['meanings'][0]['evidence'])
                    rows=[row]
                else:
                    row=existing;rows=[]
                if 'reference' in packet['review_meaning_keys']:
                    cut=next(c for c in packet['claims'] if c['raw']['Tail']=='등심')
                    rows.append(dict(meaning_key='reference',status='partial',claim_ids=[cut['id']],represented_content='등심',
                        missing_content='중량 500g',missing_evidence=source['meanings'][0]['evidence'],reason='참고 의미의 정상 부분과 잔여',
                        revision_basis='combined_expression',evidence=source['meanings'][0]['evidence']))
                complete=row['status']=='represented'
                out=dict(synthesis(),checks=rows,candidate_challenges=[],satisfied=complete,
                    public_item_checks=[dict(item_id='item',status='represented' if complete else 'partial',meaning_keys=['product'],
                        claim_ids=row['claim_ids'],evidence=source['meanings'][0]['evidence'],reason='필수부분 기준 합성 종합')])
        normalized=schema.model_validate(out).model_dump()
        identity='synthetic-'+str(len(current['units']))
        current['units'].append(dict(id=identity,stage=stage,status='succeeded',error=None,
            response=dict(request_id=identity),restored_evidence_output=deepcopy(normalized)))
        return normalized
    monkeypatch.setattr(business_run,'json_call',dispatch)
    return calls


def product_case(include_use,include_reference=False):
    run,source,claims=content_case()
    run['claims']=claims if include_use else claims[:1]
    run.update(id='synthetic-content',kind='business',status='partial',input_version_ids=['v'],model_identity={},metrics={},graph={},concepts=[])
    run['recipe']['review_contract']=review.SOURCE_APPLICATION_CONTRACT
    run['recipe']['options']['conceptualize']=False
    req=dict(run['requirements'][0],question='상품의 부위와 용도는?',criterion='표시된 부위와 용도',target='상품',situation='속성 확인',period='',history=[])
    run['requirements']=[req]
    run['answer_items']=[dict(id='item',requirement_id='r',requirement_revision=1,field='question',request_quote='상품의 부위와 용도')]
    source.update(review_contract=review.SOURCE_APPLICATION_CONTRACT,examined_block_ids=['body'],completeness='complete',gaps=[],
        meaning_gaps=[],conjunctions=[],meaning_conjunctions=[],findings=[],source_batches=[])
    source['public_scope'].update(unit_id='synthetic-scope',public_items=deepcopy(run['answer_items']),tasks=[],errors=[],followup=[],
        items=[dict(item_id='item',meaning_keys=['product'],read_block_ids=['body'],source_state='available')],
        public_requirement={k:v for k,v in req.items() if k!='source_ids'})
    source['source_batches']=[dict(unit_id='E',meaning_keys=['product'],errors=[],provided_block_ids=['body'],target_block_ids=['body'],
        output=dict(inspection_status='complete',examined_block_ids=['body']),target_evidence=source['meanings'][0]['evidence'])]
    run['units']=[dict(id='E',stage='requirement_source',status='succeeded',error=None,response=dict(request_id='E',failure_kind=None))]
    if include_reference:
        source['meanings'].append(dict(meaning('reference'),statement='등심 상품의 중량은 500g이다.',evidence=deepcopy(source['meanings'][0]['evidence'])))
        source['public_scope']['review_meaning_keys'].append('reference')
        source['public_scope']['items'][0]['meaning_keys'].append('reference')
        source['source_batches'][0]['meaning_keys'].append('reference')
    return run,req,source


@pytest.mark.parametrize('include_use,include_reference',[(True,False),(False,False),(True,True)])
def test_required_content_product_repair_save_get_and_recheck(monkeypatch,tmp_path,include_use,include_reference):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers import knowledge
    from app.knowledge.service import KnowledgeService,encode
    run,req,source=product_case(include_use,include_reference)
    before=deepcopy(run['claims']);calls=install_product_dispatch(monkeypatch,run,source)
    database=(tmp_path/'synthetic-content.db').resolve()
    assert database.parent==tmp_path.resolve()
    service=KnowledgeService(database)
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
            db.execute('INSERT INTO requirements VALUES(?,?)',(req['id'],encode(req)))
        a=business_run.assess(service,run,req,source=source)
        if include_use:
            assert a['status']=='satisfied'
            assert a['representation']['whole_expression_checks'][0]['missing_content']=='참고 중량 500g'
            assert not any(t['action']=='recover' for t in a['actions'])
            if include_reference:
                reference=next(c for c in a['representation']['checks'] if c['meaning_key']=='reference')
                assert reference['status']=='partial' and not reference.get('expression_errors')
        else:
            assert a['status']=='partial' and a['actions'][0]['action']=='recover'
            assert business_run.repair(service,run,req,a) is True
            assert run['claims'][0]==before[0] and len(run['claims'])==2
            business_run.refresh_repaired_graph(service,run)
            a=business_run.assess(service,run,req,source=a['source'],phase='after_repair')
            assert a['status']=='satisfied'
            assert business_run.repair(service,run,req,a) is False
            assert len([stage for stage,_ in calls if stage=='requirement_repair'])==1
        assert run['claims'][0]==before[0]
        business_run.save(service,run)
        monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
        app=FastAPI();app.include_router(knowledge.router)
        app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
        with TestClient(app) as client:
            reply=client.get('/knowledge/runs/'+run['id'])
        assert reply.status_code==200
        saved=reply.json()['data'];saved.pop('counts')
        assert saved==run and business_run.requirement_completion(saved['assessments'][-1],claims=saved['claims'])['status']=='satisfied'
    finally:
        service.shutdown()


def test_whole_represented_does_not_skip_remaining_required_part(monkeypatch,tmp_path):
    from app.knowledge.service import KnowledgeService,encode
    from app.knowledge.source_index import FrozenIndex
    run,req,source=product_case(True)
    cut=run['claims'][0]
    run['claims'][1]['evidence'][0]['precision']='chunk'
    calls=install_product_dispatch(monkeypatch,run,source,whole_represented=True)
    search=FrozenIndex.search
    def first_only(index,query,allowed,*args,**kwargs):
        return [dict(block_id=cut['id'])] if cut['id'] in allowed else search(index,query,allowed,*args,**kwargs)
    monkeypatch.setattr(FrozenIndex,'search',first_only)
    monkeypatch.setattr(review,'literal_relation_candidates',lambda *a:set())
    service=KnowledgeService((tmp_path/'remaining.db').resolve())
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)));db.execute('INSERT INTO requirements VALUES(?,?)',(req['id'],encode(req)))
        a=business_run.assess(service,run,req,source=source)
        local=[p for s,p in calls if s=='requirement_representation' and p['mode']=='meaning_batch']
        assert len(local)==2 and {p['claims'][0]['id'] for p in local}=={c['id'] for c in run['claims']}
        joined=next(p for s,p in calls if s=='requirement_representation' and p['mode']=='requirement_join')
        parts=joined['local_judgments']['checks'][0]['partial_contributions']
        assert {p['missing_content'] for p in parts}=={'등심','카레'}
        assert {cid for p in parts for cid in p['claim_ids']}=={c['id'] for c in run['claims']}
        assert all(p['represented_content'] and p['missing_evidence'] and p['review_unit_ids'] for p in parts)
        assert a['status']=='satisfied' and not any(t['action']=='recover' for t in a['actions'])
    finally:service.shutdown()


def test_already_stored_required_remainder_is_held_for_recheck_not_recovered(monkeypatch,tmp_path):
    from app.knowledge.service import KnowledgeService,encode
    run,req,source=product_case(True)
    before=deepcopy(run['claims']);calls=install_product_dispatch(monkeypatch,run,source,suppress_use=True)
    service=KnowledgeService((tmp_path/'duplicate.db').resolve())
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)));db.execute('INSERT INTO requirements VALUES(?,?)',(req['id'],encode(req)))
        a=business_run.assess(service,run,req,source=source)
        assert a['status']=='partial'
        assert business_run.repair(service,run,req,a) is False
        assert a['recovery_holds'][0]['reason']=='stored_remainder_position_requires_recheck'
        assert a['recovery_holds'][0]['matching_claim_ids']==[run['claims'][1]['id']]
        assert run['claims']==before and not run['repairs']
        assert all(s!='requirement_repair' for s,_ in calls)
    finally:service.shutdown()


def test_required_missing_keeps_empty_contribution_and_exact_repair_target(monkeypatch,tmp_path):
    from app.knowledge.service import KnowledgeService,encode
    run,req,source=product_case(False)
    run['claims'][0]['raw']=dict(Head='상품',Relation='중량',Tail='500g')
    before=deepcopy(run['claims']);install_product_dispatch(monkeypatch,run,source)
    service=KnowledgeService((tmp_path/'required-missing.db').resolve())
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
            db.execute('INSERT INTO requirements VALUES(?,?)',(req['id'],encode(req)))
        a=business_run.assess(service,run,req,source=source)
        target=a['actions'][0]
        assert target['action']=='recover' and target['contributing_claim_ids']==[]
        assert target['missing_content']=='등심 / 카레' and target['missing_evidence']
        packets=[]
        def capture(s,r,stage,instruction,packet,schema):
            assert stage=='requirement_repair';packets.append(deepcopy(packet));return None
        monkeypatch.setattr(business_run,'json_call',capture)
        assert business_run.repair(service,run,req,a) is False
        task=packets[0]['tasks'][0]['meanings'][0]
        assert task['review_records'] and task['required_content'] and task['requirement_scope_id']
        assert task['missing_content']==target['missing_content'] and run['claims']==before
    finally:service.shutdown()
