"""Final review handoff and consumer boundaries; synthetic, never model evidence."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.knowledge import business_selected_review as final, business_bound_source_review as bound
from app.knowledge import business_run as execution, required_unit_selection as selection, business_review as review
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_business_role_review import case
from app.tests.unit.test_knowledge_question_inspection_selection import setup_selection


def prepared(case, monkeypatch):
    run, req, source, catalog, _ = setup_selection(case, monkeypatch)
    selected = review.apply_requirement(None, run, req, source, run['blocks'])
    run['selected_request_source'] = selected
    run['request_reference_review'] = dict(contract=selection.CONTRACT, block_ids=['block1'])
    scope = selection.bound_targets(selected, catalog)
    claims, inventory = bound.selected_candidates(run, scope['targets'])
    raw = dict(checks={t['key']: dict(expression_quotes=[dict(claim_id='c1', field='raw.Tail', quote='돼지고기')],
        represented_content='돼지고기', missing_content='120g',
        missing_evidence=[dict(evidence_ref='e1', span=[8, 12], quote='120g')], reason='합성 검수', status='partial')
        for t in scope['targets']})
    request = bound.request(run, 'B', claims, scope['targets'], run['blocks'])
    result = bound.consume(raw, 'B', claims, scope['targets'], run['blocks'])
    result.update(selection_scope=scope, candidate_scope=inventory, review_unit_id='source-unit')
    run['units'].append(dict(id='source-unit', status='succeeded',
        **{k: request[k] for k in ('messages', 'schema', 'reference_map')},
        response=dict(request_id='source-unit', parsed=remap(raw, request['reference_map'] or {}))))
    run['bound_source_comparisons'] = [result]
    return run, req, scope


def output(context, status='unknown'):
    return dict(items={i['id']: dict(findings=[dict(source_result_ids=context['selected_for'][i['id']],
        status='undetermined', statement='현재 검수로 정확한 양을 확인하지 못한다', reason='합성 범위 검증')],
        missing_required_content='', reason='합성 결과', coverage=status) for i in context['public_answer_items']})


def test_final_packet_preserves_selection_and_exact_source_storage_observations(case, monkeypatch):
    run, req, scope = prepared(case, monkeypatch); before = deepcopy(run)
    context = final.packet(run, req, scope, run['blocks'])
    assert run == before and context['observations_are_stored_knowledge'] is False
    assert 'initial_business_review' not in context and 'blocks' not in context
    for observed, check in zip(context['source_observations'], run['bound_source_comparisons'][-1]['checks']):
        for key in ['evidence', 'missing_evidence', 'condition_references', 'request_uses', 'expression_bindings']:
            assert observed[key] == check[key]
        assert observed['consumer_status'] == 'partial'
    assert context['stored_candidates'][0]['fields']['raw.Tail'] == '돼지고기'
    assert all(context['selected_for'].values())


@pytest.mark.parametrize('change', ['claim', 'source_result', 'selection', 'response', 'request', 'unit_status', 'no_review'])
def test_stale_or_modified_review_cannot_be_used_for_final_judgment(case, monkeypatch, change):
    run, req, scope = prepared(case, monkeypatch)
    if change == 'claim': run['claims'][0]['raw']['Tail'] = '다른 값'
    elif change == 'source_result': run['bound_source_comparisons'][-1]['checks'][0]['status'] = 'represented'
    elif change == 'selection': scope['targets'][0]['condition_state'] = 'unresolved'
    elif change == 'response': run['units'][-1]['response']['parsed']['checks'][scope['targets'][0]['key']]['reason'] = 'edited'
    elif change == 'request': run['units'][-1]['messages'] = []
    elif change == 'unit_status': run['units'][-1]['status'] = 'failed'
    else: run['bound_source_comparisons'] = []
    with pytest.raises(ValueError, match='final_review_'):
        final.packet(run, req, scope, run['blocks'])


def test_limits_do_not_automatically_mean_requirement_gap(case, monkeypatch):
    run, req, scope = prepared(case, monkeypatch)
    context = final.packet(run, req, scope, run['blocks']); raw = output(context, 'sufficient_in_scope')
    result = final.consume(raw, context)
    assert result['overall'] == 'sufficient_in_scope'
    assert result['semantic_validation'] == 'not_assessed' and not result['whole_requirement_complete']
    assert result['model_output'] == raw and result['actions'] == []
    assert result['items'][0]['findings'][0]['source_reviews'][0] == context['source_observations'][0]


@pytest.mark.parametrize('change', ['omit_necessary', 'duplicate', 'unknown_source', 'confirmed_missing', 'gap', 'empty_gap', 'selection_hold'])
def test_final_consumer_holds_inconsistent_claims_without_editing_raw(case, monkeypatch, change):
    run, req, scope = prepared(case, monkeypatch)
    context = final.packet(run, req, scope, run['blocks']); raw = output(context, 'sufficient_in_scope')
    row = next(iter(raw['items'].values()))
    if change == 'omit_necessary': row['findings'] = []
    elif change == 'duplicate': row['findings'][0]['source_result_ids'] *= 2
    elif change == 'unknown_source': context['source_observations'][0]['consumer_status'] = 'unknown'
    elif change == 'confirmed_missing':
        row['findings'][0]['status'] = 'confirmed'; context['source_observations'][0]['consumer_status'] = 'missing'
    elif change == 'gap': row['missing_required_content'] = '필수 부족'
    elif change == 'empty_gap': row['coverage'] = 'insufficient_in_scope'
    else: context['selection_unresolved']['blocked_ranges'] = [dict(item_id=context['public_answer_items'][0]['id'])]
    before = deepcopy(raw); result = final.consume(raw, context)
    assert result['overall'] == 'unknown' and result['items'][0]['consumer_errors']
    assert raw == before == result['model_output'] and result['actions'] == []


def test_partial_normal_contribution_and_other_resolved_request_stay_visible(case, monkeypatch):
    run, req, scope = prepared(case, monkeypatch)
    context = final.packet(run, req, scope, run['blocks']); raw = output(context, 'sufficient_in_scope')
    first = context['public_answer_items'][0]['id']
    context['selection_unresolved']['blocked_ranges'] = [dict(item_id=first)]
    raw['items'][first]['findings'][0].update(status='confirmed', statement='돼지고기 재료 존재는 저장됐다')
    result = final.consume(raw, context)
    assert result['items'][0]['consumer_errors'] == ['selection_scope_unresolved']
    assert result['items'][0]['findings'][0]['source_reviews'][0]['represented_content'] == '돼지고기'
    assert result['items'][1]['effective_coverage'] == 'sufficient_in_scope'


def test_output_cannot_reselect_facts_or_invent_reference_ids(case, monkeypatch):
    run, req, scope = prepared(case, monkeypatch); context = final.packet(run, req, scope, run['blocks'])
    raw = output(context); row = next(iter(raw['items'].values()))
    row['findings'][0]['source_result_ids'] = ['not-examined']
    with pytest.raises(ValidationError): final.consume(raw, context)
    raw = output(context); next(iter(raw['items'].values()))['importance'] = 'reference'
    with pytest.raises(ValidationError): final.consume(raw, context)


def test_real_dispatch_calls_only_final_role_and_appends_separate_result(case, monkeypatch):
    run, req, scope = prepared(case, monkeypatch); before = deepcopy(run); calls = []
    def generate(service, active, stage, prompt, context, schema):
        calls.append((stage, prompt)); value = output(context); schema.model_validate(value); return value
    monkeypatch.setattr(execution, 'json_call', generate)
    monkeypatch.setattr(execution, 'save', lambda *a: None)
    result = execution.assess(None, run, req, phase='selected_business_review')
    assert calls == [('requirement_representation', final.PROMPT)]
    assert run.pop('selected_business_reviews') == [result] and run == before
