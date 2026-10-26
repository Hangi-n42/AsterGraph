"""An oversized public selector must not pre-approve candidate expressions."""
from copy import deepcopy
import json

import pytest

from app.knowledge import business_models, business_review as review, business_run
from app.knowledge.source_index import FrozenIndex
from app.tests.unit.test_knowledge_public_bounded_flow import public_run, boundary_only
from app.tests.unit.test_knowledge_business_local_review import meaning, judgments
from app.tests.unit.test_knowledge_business_scope import block


@pytest.mark.parametrize('oversized', [False, True])
def test_pending_or_oversized_selector_precedes_own_review_and_keeps_unselected_work(monkeypatch, oversized):
    run, requirement = public_run()
    requirement['situation'] = '개인·단체 안내'
    if oversized:
        run['claims'][0]['interpretation'] = dict(meanings=[dict(conditions='조건' * 80000)])
    source = dict(meanings=[meaning('m')])
    before = deepcopy((run['claims'], source))
    monkeypatch.setattr(FrozenIndex, 'search', lambda index, query, ids, limit=6:
        [dict(block_id=k) for k in ('m', 'body') if k in ids])
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda r: {})
    monkeypatch.setattr(review, 'review_candidate_pool', lambda *a, **kw: pytest.fail('broad own review before source selection'))
    def application(service, current, stage, instruction, context, schema):
        assert 'candidates' not in context and 'candidate_source_reviews' not in context
        assert len(context['public_tasks']) == 2
        row = dict(item_id=run['answer_items'][0]['id'], meaning_keys=[], source_state='unselected',
            read_block_ids=['body'], gap='기존 원문 의미 추가 조회 필요', reason='제공 의미에서 미선택')
        output = schema.model_validate(dict(items=[row], meaning_challenges=[])).model_dump()
        current['units'].append(dict(id='source-selection', status='succeeded', error=None, restored_evidence_output=output))
        return output
    monkeypatch.setattr(business_run, 'json_call', application)
    result = review.public_requirement_scope(None, run, requirement, source)
    scope = result['public_scope']
    assert scope['input_contract'] == review.PUBLIC_SOURCE_INPUT_CONTRACT
    assert len(scope['public_items']) == 1 and len(scope['tasks']) == 2
    assert 'expression_state' not in scope['items'][0]
    assert scope['followup'][0]['action'] == 'lookup_stored_meanings'
    assert scope['followup'][0]['read_block_ids'] == ['body']
    assert scope['expression_review_pending'] and (run['claims'], source) == before
    assert review.public_scope_valid(run, requirement, result)
    assert len(review.public_work_records(run, requirement, result)) == 1


@pytest.mark.parametrize('fault', [None, 'version', 'parse', 'span', 'gap', 'missing_identity'])
def test_source_input_reference_uses_exact_view_and_preserves_original_on_mismatch(fault):
    run, _ = public_run()
    whole = block('body', '가나다라마바사아')
    left = dict(whole, text=whole['text'][:4], span=[0, 4], context_only=True)
    right = dict(whole, text=whole['text'][4:], span=[4, 8])
    ref = dict(block_id='body', source_version_id='v', parse_run_id='p', start_char=1, end_char=3,
        quote=whole['text'][1:3], precision='exact', context_only=True)
    if fault == 'version': ref['source_version_id'] = 'other'
    if fault == 'parse': ref['parse_run_id'] = 'other'
    if fault == 'missing_identity':
        ref['parse_run_id'] = left['parse_run_id'] = right['parse_run_id'] = None
    if fault == 'span': ref['end_char'] = 99
    if fault == 'gap': ref.update(start_char=2, end_char=6, quote=whole['text'][2:6])
    fact = meaning('m'); fact['evidence'] = [ref]
    fact['conditions'] = ['본인이 신청한 경우']
    fact['field_judgments'] = dict(conditions=dict(status='unknown', statement_affected=True))
    context = dict(blocks=[right, left], source_facts=[fact])
    before = deepcopy(context)
    request = business_run.json_request(run, 'requirement_application', '원문 적용성만', context,
        business_models.PublicSourceScopeCheck)
    payload = json.loads(request['messages'][-1]['content'])
    supplied = payload['source_facts'][0]
    assert context == before and supplied['conditions'] == fact['conditions']
    assert supplied['field_judgments'] == fact['field_judgments']
    assert payload['blocks'][1]['context_only'] is True
    if fault:
        assert 'evidence_ref' not in supplied['source_evidence_refs'][0]
        assert supplied['source_evidence_refs'][0]['quote'] == ref['quote']
    else:
        assert supplied['source_evidence_refs'][0] == dict(evidence_ref='e2', span=[1, 3], context_only=True)
        assert request['source_fact_evidence_bindings']['m'] == [ref]
        view = request['evidence_reference_map']['e2']
        assert view['text'][1:3] == ref['quote']
        changed = deepcopy(context)
        changed['blocks'][1]['parse_run_id'] = 'p2'
        changed['source_facts'][0]['evidence'][0]['parse_run_id'] = 'p2'
        newer = business_run.json_request(run, 'requirement_application', '원문 적용성만', changed,
            business_models.PublicSourceScopeCheck)
        assert newer['messages'] != request['messages']


@pytest.mark.parametrize('status', ['represented', 'partial', 'missing', 'unknown', None])
def test_completion_requires_real_public_item_expression_witnesses(monkeypatch, status):
    run, _ = public_run(); cid = run['claims'][0]['id']
    fact = meaning('m', required_for_requirement=True)
    fact.update(requirement_link=dict(requested_fact='질문',applicability='applicable',contribution='direct_answer',reason='필수'),
        requirement_applications=[dict(item_id='question',required_for_requirement=True,
            requirement_link=dict(requested_fact='질문',applicability='applicable',contribution='direct_answer',reason='필수'))])
    fact['evidence'] = business_run.exact_evidence(fact['evidence'], run['blocks'])
    source = dict(meanings=[fact], completeness='complete', gaps=[], meaning_gaps=[],
        public_scope=dict(input_contract=review.PUBLIC_SOURCE_INPUT_CONTRACT,
            public_items=[dict(id='question')], items=[dict(item_id='question', source_state='available', meaning_keys=['m'])],
            review_meaning_keys=['m']))
    result = judgments(['m'], ids=[cid])
    result.update(source_completeness='complete',unselected_source_required=False)
    result['checks'][0].update(claim_support={cid:'supported'}, error_fields={})
    direct = {cid:dict(receipt_id='own',unit_id='own-unit',check=dict(claim_support={cid:'supported'},
        incorrect_claim_ids=[],error_fields={}))}
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda current: deepcopy(direct))
    output = [] if status is None else [dict(item_id='question',status=status,meaning_keys=['m'],claim_ids=[cid],
        evidence=fact['evidence'],reason='실제 원문과 R 기여를 대조')]
    review.retain_public_item_checks(run, source, result, output, run['blocks'])
    assessment=dict(source=source,representation=result,errors=[],issues=[],preservation_complete=True)
    completion=business_run.requirement_completion(assessment)
    assert (completion['status']=='satisfied') == (status=='represented')
    assert result['satisfied'] is True and result['public_item_checks']==output
    if status=='represented':
        direct[cid]['check']['claim_support'][cid]='unknown'
        review.retain_public_item_checks(run, source, result, output, run['blocks'])
        assert business_run.requirement_completion(assessment)['status']!='satisfied'
