"""Synthetic use/ownership/transport boundaries, not model-quality evidence."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app.knowledge import fixed_fact_application as fixed, required_unit_selection as selection
from app.knowledge import business_review as review, business_run as execution
from app.tests.unit.test_knowledge_business_role_review import case
from app.tests.unit.test_knowledge_question_inspection_selection import setup_selection


def prepare(case, monkeypatch):
    run, req, source, catalog, old = setup_selection(case, monkeypatch)
    run['request_reference_review'] = dict(contract=selection.CONTRACT, application_contract=fixed.CONTRACT)
    raw = dict(groups=[dict(item_id=g['item_id'], state='complete', reason='synthetic checked scope',
        uses=[dict(u, contribution='direct_answer', reason='synthetic required value')
            for row in g['facts'] for u in row['uses']]) for g in old['links']])
    monkeypatch.setattr(execution, 'json_call', lambda *a, **k: deepcopy(raw))
    return run, req, source, catalog, raw


def test_fact_owner_is_derived_and_cannot_be_generated(case, monkeypatch):
    run, req, source, catalog, raw = prepare(case, monkeypatch)
    # A second source meaning without a selected value must not borrow this fact.
    other = dict(deepcopy(source['meanings'][0]), key='other')
    facts = run['source_fact_grounding']['facts']; criteria = run['question_inspection']['criteria']
    items = [dict(id=g['item_id']) for g in raw['groups']]
    output = fixed.output_type(facts, items, criteria)
    output.model_validate(raw)
    before = deepcopy(raw)
    projected, _ = fixed.project(raw, facts, items, [*source['meanings'], other], criteria)
    assert raw == before
    assert all(not row['uses'] and not row['required_for_requirement'] for row in projected['links'] if row['key'] == 'other')
    assert all(facts[int(u['fact_id'][1:])-1]['meaning_key'] == row['key'] for row in projected['links'] for u in row['uses'])
    raw['groups'][0]['uses'][0]['key'] = 'other'
    with pytest.raises(ValidationError): output.model_validate(raw)


def test_real_application_preserves_facts_raw_response_and_rechecks_projection(case, monkeypatch):
    run, req, source, catalog, raw = prepare(case, monkeypatch); before = deepcopy((source, raw, run['claims']))
    result = review.apply_requirement(None, run, req, source, run['blocks'])
    scope = selection.bound_targets(result, catalog)
    assert scope['targets'] and not scope['blocked_ranges']
    assert result['application_history'][-1]['output'] == raw
    assert (source, raw, run['claims']) == before
    result['meanings'][0]['requirement_applications'][0]['selection_record']['selections'][0]['necessity'] = 'reference'
    with pytest.raises(ValueError, match='fixed_fact_application_consumption_changed'):
        selection.bound_targets(result, catalog)


@pytest.mark.parametrize('fault', ['omit', 'pending', 'duplicate', 'wrong_request', 'different_attribute'])
def test_missing_or_wrong_uses_cannot_complete_requirement(case, monkeypatch, fault):
    run, req, source, catalog, raw = prepare(case, monkeypatch)
    group = raw['groups'][0]
    if fault == 'omit': group['uses'] = []
    elif fault == 'pending': group['state'] = 'unresolved'
    elif fault == 'duplicate': group['uses'] *= 2
    elif fault == 'wrong_request': group['uses'][0]['criterion_id'] = 'criterion_2'
    else: group['uses'][0]['fact_id'] = 'f2'
    before = deepcopy(raw)
    result = review.apply_requirement(None, run, req, source, run['blocks'])
    scope = selection.bound_targets(result, catalog)
    assert scope['blocked_ranges'] or scope['criteria_without_necessary_source']
    assert raw == before == result['application_history'][-1]['output']


def test_shared_reference_transport_preserves_every_value_condition_and_block(case, monkeypatch):
    run, req, source, catalog, raw = prepare(case, monkeypatch)
    def capture(service, active, stage, prompt, packet, model):
        assert prompt == fixed.PROMPT and packet['contract'] == fixed.CONTRACT
        assert packet['blocks'] == run['blocks']
        assert 'source_property_catalog' not in packet and 'request_groups' not in packet
        for original, sent in zip(run['source_fact_grounding']['facts'], packet['fixed_source_facts']):
            for name in ('source_reference', 'identity_references', 'condition_references'):
                refs = [sent[name]] if name == 'source_reference' else sent[name]
                restored = [packet['source_references'][ref['reference_id']] for ref in refs]
                assert restored == ([original[name]] if name == 'source_reference' else original[name])
            assert sent['condition_state'] == original['condition_state']
        assert len(packet['source_references']) == 1
        assert json.dumps(packet, ensure_ascii=False).count('돼지고기 120g') < 6
        model.model_validate(raw)
        return deepcopy(raw)
    monkeypatch.setattr(execution, 'json_call', capture)
    result = review.apply_requirement(None, run, req, source, run['blocks'])
    assert not selection.bound_targets(result, catalog)['blocked_ranges']
