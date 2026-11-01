"""Synthetic repair safety checks; no native model quality claims."""
from copy import deepcopy

import pytest

from app.knowledge import business_selected_repair as repair, business_selected_review as final
from app.knowledge import business_bound_source_review as bound, business_run as execution, business_review as review
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_business_role_review import case
from app.tests.unit.test_knowledge_selected_business_review import prepared, output


def final_record(run, req, scope, coverage, contract=final.CONTRACT):
    context = final.packet(run, req, scope, run['blocks'], contract=contract)
    raw = output(context, coverage)
    for row in raw['items'].values():
        row['missing_required_content'] = '120g' if coverage == 'insufficient_in_scope' else ''
    request = execution.json_request(run, 'requirement_representation', final.instruction(contract), context, final.output_type(context))
    uid = 'final-unit-' + str(len(run['units']))
    run['units'].append(dict(id=uid, status='succeeded',
        **{k: request[k] for k in ('messages', 'schema', 'reference_map')},
        response=dict(request_id=uid, parsed=remap(raw, request['reference_map'] or {}))))
    result = final.consume(raw, context); result['review_unit_id'] = uid
    run.setdefault('selected_business_reviews', []).append(result)
    return result


def ready(case, monkeypatch, contract=final.CONTRACT):
    case[0]['answer_items'] = [dict(id='one', requirement_id=case[1]['id'], requirement_revision=1,
        field='question', request_quote=case[1]['question'])]
    run, req, scope = prepared(case, monkeypatch)
    final_record(run, req, scope, 'insufficient_in_scope', contract)
    monkeypatch.setattr(execution, 'save', lambda *a: None)
    return run, req, scope


def proposal(context):
    return dict(patches=[dict(meaning_key=t['meaning_key'], target_id=None, role='event_entity',
        raw=dict(Event='돼지고기의 수량은 120g이다.', Entity=['돼지고기']),
        evidence=[dict(t['selected_target']['ref'])], conditions=[], exceptions=[], period='', references=[],
        scope=None, reuse_claim_ids=[]) for t in context['missing_targets']], unresolved=[])


def apply_addition(run, req, scope, monkeypatch):
    context = repair.packet(run, req, scope, run['blocks'])
    raw = proposal(context)
    monkeypatch.setattr(execution, 'json_call', lambda *a: deepcopy(raw))
    # Graph structure is tested separately; this fixture is deliberately minimal.
    monkeypatch.setattr(repair.autoschema, 'graph', lambda *a: dict(synthetic=True))
    return repair.recover(None, run, req, scope, run['blocks']), raw


@pytest.mark.parametrize('contract', [final.CONTRACT, final.RELATION_CONTRACT])
def test_actual_dispatch_appends_only_gap_preserves_originals_and_raw(case, monkeypatch, contract):
    run, req, scope = ready(case, monkeypatch, contract); before = deepcopy(run['claims'])
    context = repair.packet(run, req, scope, run['blocks']); raw = proposal(context); original = deepcopy(raw); calls = []
    def generate(service, active, stage, instruction, packet, schema):
        calls.append(stage); assert packet == context; schema.model_validate(raw); return raw
    monkeypatch.setattr(execution, 'json_call', generate)
    monkeypatch.setattr(repair.autoschema, 'graph', lambda *a: dict(synthetic=True))
    result = execution.assess(None, run, req, phase='selected_repair')
    assert calls == ['requirement_repair'] and result['status'] == 'applied_awaiting_recheck'
    assert run['claims'][:len(before)] == before and len(result['changes']) == 1
    assert raw == original == result['patches'] and result['changes'][0]['before'] is None
    added = result['changes'][0]['after']
    assert added['raw']['Entity'] == ['돼지고기'] and added['edit_participants'][0]['quote'] == '돼지고기'
    assert added['review_status'] == 'unreviewed' and added['semantic_status'] == 'unknown'
    with pytest.raises(ValueError, match='final_review_source_scope_changed'):
        repair.recover(None, run, req, scope, run['blocks'])
    assert calls == ['requirement_repair']


@pytest.mark.parametrize('change', ['raw', 'saved', 'request', 'claim', 'source', 'unknown', 'not_required'])
def test_changed_or_unconfirmed_basis_blocks_generation(case, monkeypatch, change):
    run, req, scope = ready(case, monkeypatch)
    if change == 'raw': run['units'][-1]['response']['parsed']['items'].clear()
    elif change == 'saved': run['selected_business_reviews'][-1]['overall'] = 'sufficient_in_scope'
    elif change == 'request': run['units'][-1]['messages'] = []
    elif change == 'claim': run['claims'][0]['raw']['Tail'] = '다른 대상'
    elif change == 'source': run['blocks'][0]['text'] = '다른 원문'
    else:
        final_record(run, req, scope, 'unknown' if change == 'unknown' else 'sufficient_in_scope')
    monkeypatch.setattr(execution, 'json_call', lambda *a: pytest.fail('must not generate'))
    with pytest.raises((ValueError, KeyError)):
        repair.recover(None, run, req, scope, run['blocks'])


@pytest.mark.parametrize('bad', ['unresolved', 'duplicate', 'outside_target', 'outside_evidence', 'no_participant', 'invalid_raw', 'graph_failure'])
def test_invalid_proposal_preserves_claims_and_raw_receipt(case, monkeypatch, bad):
    run, req, scope = ready(case, monkeypatch); before = deepcopy(run['claims'])
    raw = proposal(repair.packet(run, req, scope, run['blocks']))
    if bad == 'unresolved': raw['unresolved'] = [raw['patches'][0]['meaning_key']]
    elif bad == 'duplicate': raw['patches'] *= 2
    elif bad == 'outside_target': raw['patches'][0]['meaning_key'] = 'not_selected'
    elif bad == 'outside_evidence': raw['patches'][0]['evidence'][0]['source_version_id'] = 'v2'
    elif bad == 'no_participant': raw['patches'][0]['raw']['Entity'] = ['존재하지 않는 대상']
    elif bad == 'invalid_raw': raw['patches'][0]['raw'].pop('Event')
    else:
        def fail(*a): raise ValueError('graph_failure')
        monkeypatch.setattr(repair.autoschema, 'graph', fail)
    monkeypatch.setattr(execution, 'json_call', lambda *a: deepcopy(raw))
    result = repair.recover(None, run, req, scope, run['blocks'])
    assert result['status'] == 'unresolved' and result['errors'] and result['changes'] == []
    assert run['claims'] == before and result['patches'] == raw


def rechecked_source(run, req, scope):
    claims, inventory = bound.selected_candidates(run, scope['targets'])
    added = run['repairs'][-1]['changes'][0]['after']
    raw = dict(checks={t['key']: dict(expression_quotes=[dict(claim_id=added['id'], field='raw.Event',
        quote=added['raw']['Event'])], represented_content=added['raw']['Event'], missing_content='',
        missing_evidence=[], reason='합성 재검수', status='represented') for t in scope['targets']})
    request = bound.request(run, 'B', claims, scope['targets'], run['blocks'])
    result = bound.consume(raw, 'B', claims, scope['targets'], run['blocks'])
    result.update(selection_scope=scope, candidate_scope=inventory, review_unit_id='source-after')
    run['units'].append(dict(id='source-after', status='succeeded',
        **{k: request[k] for k in ('messages', 'schema', 'reference_map')},
        response=dict(request_id='source-after', parsed=remap(raw, request['reference_map'] or {}))))
    run['bound_source_comparisons'].append(result)
    final_record(run, req, scope, 'sufficient_in_scope')


def test_fresh_recheck_and_own_source_review_required_without_approval(case, monkeypatch):
    run, req, scope = ready(case, monkeypatch); receipt, _ = apply_addition(run, req, scope, monkeypatch)
    before = deepcopy(run['claims']); rechecked_source(run, req, scope)
    with pytest.raises(ValueError, match='own_source_review'):
        repair.finish(None, run, req, scope, run['blocks'])
    receipt.update(candidate_review_id='own', candidate_review_options=deepcopy(run['recipe']['options']))
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda *a: {})
    with pytest.raises(ValueError, match='own_source_review'):
        repair.finish(None, run, req, scope, run['blocks'])
    cid = receipt['changes'][0]['after']['id']
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda *a: {
        cid: dict(receipt_id='own', check=dict(claim_support={cid:'supported'}))})
    result = repair.finish(None, run, req, scope, run['blocks'])
    assert result['status'] == 'rechecked_in_scope' and not result['recheck']['user_approval']
    assert run['claims'] == before and result['recheck']['original_claims_preserved'] == 1
    monkeypatch.setattr(execution, 'json_call', lambda *a: pytest.fail('no repeat generation'))
    assert repair.recover(None, run, req, scope, run['blocks'])['status'] == 'no_verified_gap'
