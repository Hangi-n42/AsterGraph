"""Only the existing R and final join may resolve source-only public work."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_review as review, business_run
from app.tests.unit.test_knowledge_public_bounded_flow import public_run, boundary_only
from app.tests.unit.test_knowledge_business_local_review import meaning
from app.tests.unit.test_knowledge_business_separated_review import synthesis


def required_fact(key):
    fact=meaning(key,required_for_requirement=True)
    link=dict(requested_fact='공개 질문',applicability='applicable',contribution='direct_answer',reason='합성 필수성')
    fact.update(requirement_link=deepcopy(link),requirement_applications=[dict(item_id='question',
        required_for_requirement=True,requirement_link=deepcopy(link))])
    return fact


@pytest.mark.parametrize('status', ['represented', 'unknown'])
def test_same_R_and_join_calls_resolve_public_items_with_actual_source_witnesses(monkeypatch, status):
    run, requirement = public_run()
    fact = required_fact('m')
    fact['evidence'] = business_run.exact_evidence(fact['evidence'], run['blocks'])
    items = deepcopy(run['answer_items'])
    scope = dict(input_contract=review.PUBLIC_SOURCE_INPUT_CONTRACT, public_items=items,
        tasks=review.public_item_tasks(run, requirement), unit_id='public', errors=[],
        items=[dict(item_id=items[0]['id'],source_state='available',meaning_keys=['m'],read_block_ids=[],gap='')],
        followup=[dict(item_id=items[0]['id'],action='review_expression')],
        review_meaning_keys=['m'], expression_review_pending=True, public_requirement=deepcopy(requirement),
        candidate_versions={c['id']:autoschema.identifier('claim',c) for c in run['claims']},
        source_version_fingerprint=autoschema.identifier('public_scope_source',run['blocks']))
    source = dict(meanings=[fact], completeness='unknown',gaps=[],meaning_gaps=[],findings=[],source_batches=[],
        conjunctions=[], public_scope=scope, review_contract=review.SOURCE_APPLICATION_CONTRACT)
    direct, calls = {}, []
    def own(service, current, claims, **kwargs):
        calls.append('own')
        for claim in claims:
            direct[claim['id']] = dict(receipt_id='own',unit_id='own-unit',check=dict(
                claim_support={claim['id']:'supported'},incorrect_claim_ids=[],error_fields={}))
    monkeypatch.setattr(review,'review_candidate_pool',own)
    monkeypatch.setattr(review,'current_candidate_reviews',lambda r:deepcopy(direct))
    cid = run['claims'][0]['id']
    def answer(service,current,stage,instruction,context,schema):
        calls.append(context['mode'])
        current['units'].append(dict(id=str(len(calls)),status='succeeded',error=None))
        if context['mode']=='meaning_batch':
            result=dict(checks=[dict(meaning_key='m',status='represented',claim_ids=[cid],reason='실제 후보의 정상 기여',
                represented_content='기관은 신청을 접수한다.',missing_content='',missing_evidence=[])],
                source_challenges=[],meaning_challenges=[],candidate_challenges=[],preservation_checks=[],
                dependencies=[dict(meaning_key='m',premise_keys=[])])
        else:
            assert 'public_item_checks' in schema.model_fields
            assert context['public_answer_items']==items
            assert cid not in {c['id'] for c in context['claims']}  # The R witness is not a repasted full Scope.
            result=synthesis()
            result.update(candidate_challenges=[], public_item_checks=[dict(item_id=items[0]['id'],status=status,meaning_keys=['m'],
                claim_ids=[cid],evidence=fact['evidence'],reason='실제 원문과 R 기여 대조')])
        schema.model_validate(result)
        return result
    monkeypatch.setattr(business_run,'json_call',answer)
    result, _ = review.represent(None,run,requirement,source,[])
    assert calls==['own','meaning_batch','requirement_join']
    assert result['public_item_checks'][0]['status']==status and result['satisfied'] is True
    assert not result['public_item_check_errors']
    assessment=dict(source=source,representation=result,errors=[],issues=[],preservation_complete=True)
    assert (business_run.requirement_completion(assessment)['status']=='satisfied')==(status=='represented')
    assert source['public_scope']['expression_review_pending']==(status!='represented')


@pytest.mark.parametrize('field_state', ['unknown','refuted'])
def test_qualified_source_uncertainty_cannot_be_promoted_by_item_success(monkeypatch, field_state):
    from app.tests.unit.test_knowledge_business_local_review import judgments
    run, _ = public_run(); cid=run['claims'][0]['id']
    fact=required_fact('m')
    fact['field_judgments']=dict(conditions=dict(status=field_state,statement_affected=True))
    source=dict(meanings=[fact],completeness='complete',gaps=[],meaning_gaps=[],
        public_scope=dict(input_contract=review.PUBLIC_SOURCE_INPUT_CONTRACT,public_items=[dict(id='question')],
            items=[dict(item_id='question',meaning_keys=['m'])],review_meaning_keys=['m']))
    result=judgments(['m'],ids=[cid])
    monkeypatch.setattr(review,'current_candidate_reviews',lambda r:{cid:dict(check=dict(
        claim_support={cid:'supported'},incorrect_claim_ids=[],error_fields={}))})
    output=[dict(item_id='question',status='represented',meaning_keys=['m'],claim_ids=[cid],
        evidence=fact['evidence'],reason='모델 성공 주장')]
    original=deepcopy(source['meanings'])
    review.retain_public_item_checks(run,source,result,output,run['blocks'])
    assert result['public_item_checks']==output and result['public_item_check_errors']
    assert source['meanings']==original
    assert business_run.requirement_completion(dict(source=source,representation=result,errors=[],issues=[],
        preservation_complete=True))['status']!='satisfied'


@pytest.mark.parametrize('linked_R_witness', [False, True])
def test_extra_quote_cannot_resolve_an_unselected_scope_without_its_R_meaning(monkeypatch, linked_R_witness):
    from app.tests.unit.test_knowledge_business_local_review import judgments
    from app.tests.unit.test_knowledge_business_scope import block
    run, _ = public_run(); cid=run['claims'][0]['id']
    needed=block('needed','단체 접수에는 다른 조건이 적용된다.')
    run['blocks'].append(needed)
    fact=required_fact('m')
    fact['evidence']=business_run.exact_evidence(fact['evidence'],run['blocks'])
    source=dict(meanings=[fact],completeness='complete',gaps=[],meaning_gaps=[],
        public_scope=dict(input_contract=review.PUBLIC_SOURCE_INPUT_CONTRACT,public_items=[dict(id='question')],
            items=[dict(item_id='question',source_state='unselected',meaning_keys=['m'],read_block_ids=['needed'])],
            review_meaning_keys=['m']))
    result=judgments(['m'],ids=[cid])
    result.update(source_completeness='complete',unselected_source_required=False)
    witness_ids=[cid]
    if linked_R_witness:
        chunk=autoschema.chunks([needed],49152,4096)[0]
        claim=autoschema.graph_record(chunk,'entity_relation',dict(Head='단체',Relation='접수 조건',Tail=needed['text']),0)
        run['claims'].append(claim)
        extra=required_fact('needed-meaning')
        extra.update(statement=needed['text'],evidence=business_run.exact_evidence(
            [dict(block_id='needed',quote=needed['text'])],run['blocks']))
        source['meanings'].append(extra)
        source['public_scope']['review_meaning_keys'].append(extra['key'])
        addition=judgments([extra['key']],ids=[claim['id']])
        for field in ['checks','source_checks','dependencies']:result[field].extend(addition[field])
        witness_ids.append(claim['id'])
    monkeypatch.setattr(review,'current_candidate_reviews',lambda r:{w:dict(check=dict(
        claim_support={w:'supported'},incorrect_claim_ids=[],error_fields={})) for w in witness_ids})
    evidence=[*fact['evidence'],*business_run.exact_evidence([dict(block_id='needed',quote=needed['text'])],run['blocks'])]
    output=[dict(item_id='question',status='represented',meaning_keys=source['public_scope']['review_meaning_keys'],claim_ids=witness_ids,
        evidence=evidence,reason='다른 블록의 정상 R에 새 인용만 덧붙인 주장')]
    before=deepcopy((source['meanings'],run['claims'],output))
    review.retain_public_item_checks(run,source,result,output,run['blocks'])
    assert bool(result['public_item_check_errors']) != linked_R_witness
    assert source['public_scope']['expression_review_pending'] != linked_R_witness
    assert (source['meanings'],run['claims'],output)==before
    assert result['public_item_checks']==output
    assert (business_run.requirement_completion(dict(source=source,representation=result,errors=[],issues=[],
        preservation_complete=True))['status']=='satisfied')==linked_R_witness
