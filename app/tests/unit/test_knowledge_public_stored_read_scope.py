"""Requested physical blocks may link stored E meanings without correcting model verdicts."""
from copy import deepcopy

import pytest

from app.knowledge import business_review as review, business_run
from app.tests.unit.test_knowledge_public_bounded_flow import public_run
from app.tests.unit.test_knowledge_business_scope import block
from app.tests.unit.test_knowledge_business_local_review import meaning


def stored_read_case():
    run, requirement = public_run()
    requested = dict(block('requested', '추가 조건과 예외를 유지한다.'), source_id='s')
    other = dict(block('other', '별도 전제다.'), source_id='s')
    run['blocks'].extend([requested, other])
    original = meaning('original')
    linked = meaning('linked'); linked['evidence'] = [dict(block_id='requested', quote=requested['text'])]
    linked['premise_keys'] = ['premise']
    premise = meaning('premise'); premise['evidence'] = [dict(block_id='other', quote=other['text'])]
    unrelated = meaning('unrelated'); unrelated['evidence'] = deepcopy(premise['evidence'])
    for fact in [original, linked, premise, unrelated]:
        fact['evidence'] = business_run.exact_evidence(fact['evidence'], run['blocks'])
    row = dict(item_id='question', source_state='unread', meaning_keys=['original'],
        read_block_ids=['requested'], gap='추가 읽기 요청이라는 원 응답', reason='보존할 원 이유')
    source = dict(meanings=[original, linked, premise, unrelated],
        source_batches=[dict(unit_id='E-response', meaning_keys=['linked', 'premise', 'unrelated'], errors=[],
            provided_block_ids=['requested','other'],target_block_ids=['requested','other'],
            output=dict(inspection_status='complete',examined_block_ids=['requested','other']),
            target_evidence=business_run.exact_evidence([dict(block_id=b['id'],quote=b['text'])
                for b in [requested,other]],run['blocks']))],
        public_scope=dict(input_contract=review.PUBLIC_SOURCE_INPUT_CONTRACT,
            review_meaning_keys=['original'],items=[deepcopy(row)],output=dict(items=[deepcopy(row)]),
            followup=[dict(item_id='question',action='read_source',read_block_ids=['requested'])],
            expression_review_pending=True))
    run['units'] = [dict(id='E-unit',stage='requirement_source',status='succeeded',error=None,
        response=dict(request_id='E-response',failure_kind=None))]
    return run,requirement,source


def test_requested_block_links_exact_stored_meaning_and_only_its_premise_without_new_verdict():
    run,requirement,source=stored_read_case(); before=deepcopy((run,source))
    result=review.resolve_public_read_scope(run,requirement,source)
    assert result['public_scope']['review_meaning_keys']==['linked','original','premise']
    assert result['public_scope']['output']==source['public_scope']['output']
    assert result['public_scope']['items']==source['public_scope']['items']
    assert result['public_scope']['followup']==source['public_scope']['followup']
    assert result['public_scope']['expression_review_pending'] is True
    assert result['meanings']==source['meanings'] and (run,source)==before
    receipt=result['public_scope']['stored_read_scope'][0]
    assert receipt['item_id']=='question' and receipt['linked_meaning_keys']==['linked']
    assert receipt['unresolved_block_ids']==[]
    assert receipt['matches'][0]['unit_id']=='E-response'
    assert receipt['matches'][0]['evidence']==source['meanings'][1]['evidence']
    assert review.resolve_public_read_scope(run,requirement,result)==result


@pytest.mark.parametrize('fault',['version','parse','span','quote','missing_identity','different_block','context_only','duplicate_key'])
def test_address_mismatch_or_ambiguous_stored_meaning_stays_pending(fault):
    run,req,source=stored_read_case(); fact=source['meanings'][1]; ref=fact['evidence'][0]
    if fault=='version': ref['source_version_id']='different'
    if fault=='parse': ref['parse_run_id']='different'
    if fault=='span': ref['start_char']+=1
    if fault=='quote': ref['quote']='원문에 없는 인용'
    if fault=='missing_identity': ref['parse_run_id']=None
    if fault=='different_block': ref.update(source['meanings'][2]['evidence'][0])
    if fault=='context_only': ref['context_only']=True
    if fault=='duplicate_key': source['meanings'].append(deepcopy(fact))
    result=review.resolve_public_read_scope(run,req,source)
    assert result['public_scope']['review_meaning_keys']==['original']
    receipt=result['public_scope']['stored_read_scope'][0]
    assert receipt['linked_meaning_keys']==[] and receipt['unresolved_block_ids']==['requested']
    assert result['public_scope']['items']==source['public_scope']['items']


@pytest.mark.parametrize('fault',['failed_unit','missing_unit','unexamined','incomplete','wrong_target_span'])
def test_only_an_actual_successful_E_receipt_with_exact_target_coverage_is_used(fault):
    run,req,source=stored_read_case(); batch=source['source_batches'][0]
    if fault=='failed_unit':run['units'][0]['status']='failed'
    if fault=='missing_unit':run['units']=[]
    if fault=='unexamined':batch['output']['examined_block_ids']=['other']
    if fault=='incomplete':batch['output']['inspection_status']='partial'
    if fault=='wrong_target_span':batch['target_evidence'][0]['end_char']-=1
    result=review.resolve_public_read_scope(run,req,source)
    assert result['public_scope']['review_meaning_keys']==['original']
    assert result['public_scope']['stored_read_scope'][0]['unresolved_block_ids']==['requested']


def test_lookup_keeps_uncertain_qualifiers_and_legacy_contract_unchanged():
    run,req,source=stored_read_case()
    source['meanings'][1].update(source_status='unknown',field_judgments=dict(conditions=dict(status='unknown',statement_affected=True)))
    result=review.resolve_public_read_scope(run,req,source)
    assert 'linked' in result['public_scope']['review_meaning_keys']
    assert result['meanings']==source['meanings']
    source['public_scope']['input_contract']=review.PUBLIC_SCOPE_INPUT_CONTRACT
    assert review.resolve_public_read_scope(run,req,source)==source
