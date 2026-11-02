"""A new quote-only producer, strict literal addresses, and historical span replay."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.knowledge import business_bound_source_review as bound, business_selected_review as final
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_business_role_review import case
from app.tests.unit.test_knowledge_business_bound_source_review import compact
from app.tests.unit.test_knowledge_selected_business_review import prepared


def output(case):
    run, _, _, claim, target, raw, *_ = case
    row = compact(raw['checks'][0]); ref = next(iter(bound.missing_references(target, run['blocks'])))
    row['missing_evidence'] = [dict(evidence_ref=ref, quote='120g')]
    return dict(checks={target['key']: row})


def test_new_quote_producer_resolves_unique_exact_span_without_editing_raw(case):
    run, _, _, claim, target, *_ = case; raw = output(case); before = deepcopy(raw)
    bound.output_type('B', [claim], [target], run['blocks'], contract=bound.QUOTE_CONTRACT).model_validate(raw)
    result = bound.consume(raw, 'B', [claim], [target], run['blocks'], contract=bound.QUOTE_CONTRACT)
    row = result['checks'][0]; ref = row['missing_evidence'][0]
    assert row['status'] == 'partial' and not row['consumer_errors']
    assert (ref['start_char'], ref['end_char'], ref['quote']) == (8, 12, '120g')
    assert raw == before == result['model_output']


@pytest.mark.parametrize('fault', ['wrong_span', 'empty', 'fuzzy', 'foreign_target', 'outside', 'version', 'duplicate'])
def test_new_quote_contract_does_not_relax_identity_scope_or_literal_guards(case, fault):
    run, _, _, claim, target, *_ = case; raw = output(case); ref = raw['checks']['t1']['missing_evidence'][0]
    if fault == 'wrong_span': ref['span'] = [1, 5]
    elif fault == 'empty': ref['quote'] = ''
    elif fault == 'fuzzy': ref['quote'] = '120 g'
    elif fault == 'foreign_target': ref['evidence_ref'] = 'foreign'
    elif fault == 'outside': ref['quote'] = '싱거우면'
    elif fault == 'version': ref['source_version_id'] = 'v2'
    else: raw['checks']['t1']['missing_evidence'] *= 2
    before = deepcopy(raw)
    row = bound.consume(raw, 'B', [claim], [target], run['blocks'], contract=bound.QUOTE_CONTRACT)['checks'][0]
    assert row['status'] == 'unknown' and row['consumer_errors'] and raw == before


def test_repeated_quote_is_not_silently_relocated_to_first_occurrence(case):
    run, _, _, _, target, *_ = case
    block = run['blocks'][0]; block.update(text='120g 또는 120g', span=[0, 12])
    target['ref'].update(quote=block['text'], start_char=0, end_char=len(block['text']))
    ref = next(iter(bound.missing_references(target, run['blocks'])))
    with pytest.raises(ValueError, match='not_unique'):
        bound.literal_missing_reference(dict(evidence_ref=ref, quote='120g'), target, run['blocks'])


def test_legacy_wrong_span_is_not_repaired_or_accepted_as_new_quote_contract(case):
    run, _, _, claim, target, *_ = case; raw = output(case)
    raw['checks']['t1']['missing_evidence'][0]['span'] = [3, 7]
    old = bound.consume(raw, 'B', [claim], [target], run['blocks'])
    assert old['checks'][0]['status'] == 'unknown' and old['model_output'] == raw
    with pytest.raises(ValidationError):
        bound.output_type('B', [claim], [target], run['blocks'], contract=bound.QUOTE_CONTRACT).model_validate(raw)


def test_final_role_replays_new_quote_producer_and_rejects_contract_switch(case, monkeypatch):
    run, req, scope = prepared(case, monkeypatch)
    run['request_reference_review']['source_review_contract'] = bound.QUOTE_CONTRACT
    old = run['bound_source_comparisons'][-1]; raw = deepcopy(old['model_output'])
    for target in scope['targets']:
        raw['checks'][target['key']]['missing_evidence'] = [dict(
            evidence_ref=next(iter(bound.missing_references(target, run['blocks']))), quote='120g')]
    claims, inventory = bound.selected_candidates(run, scope['targets'])
    request = bound.request(run, 'B', claims, scope['targets'], run['blocks'])
    result = bound.consume(raw, 'B', claims, scope['targets'], run['blocks'], contract=bound.QUOTE_CONTRACT)
    result.update(selection_scope=scope, candidate_scope=inventory, review_unit_id='new-source-unit')
    run['bound_source_comparisons'].append(result)
    run['units'].append(dict(id='new-source-unit', status='succeeded',
        **{k: request[k] for k in ('messages', 'schema', 'reference_map')},
        response=dict(request_id='new-source-unit', parsed=remap(raw, request['reference_map'] or {}))))
    packet = final.packet(run, req, scope, run['blocks'])
    assert all(o['consumer_status'] == 'partial' for o in packet['source_observations'])
    run['request_reference_review'].pop('source_review_contract')
    with pytest.raises(ValueError, match='source_scope_changed'):
        final.packet(run, req, scope, run['blocks'])
