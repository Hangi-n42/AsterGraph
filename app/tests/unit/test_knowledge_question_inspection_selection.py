"""Synthetic boundary regressions, never evidence of native selection quality."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app.knowledge import (question_inspection as question, required_unit_selection as selection,
    business_review as review, business_run as execution, business_bound_source_review as bound)
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_business_role_review import case


def setup_frame(run, req):
    items = question.public_items(run, req)
    output = dict(groups=[dict(item_id=i['id'], state='complete', reason='합성 경계 검사', inspections=[dict(
        attribute_ref=dict(field=i['field'], quote=i['request_quote']),
        comparison=dict(one_subject=dict(field=i['field'], quote=i['request_quote'])),
        context_refs=[])]) for i in items])
    frame = question.bind(output, req, items)
    run['question_inspection'] = frame
    return items, output, frame


def ground_fixture(run, source, catalog):
    criteria = run['question_inspection']['criteria']
    output = dict(rows=[dict(key='t1', state='complete', reason='합성 경계 검사', facts=[dict(
        property_ref='p1', scope_id=s['scope_id'], identity_refs=['p1'], condition_refs=[],
        condition_state='not_applicable') for s in selection.inspection_scopes(criteria)])])
    record = selection.bind_facts(output, catalog, criteria, source['meanings'], run['blocks'])
    assert record['ready']
    run['source_fact_grounding'] = record
    return output


def setup_selection(case, monkeypatch, comparison=False):
    run, req, source, claim, target, *_ = case
    source['meanings'][0]['reason'] = '합성 원문 사실'
    items, output, frame = setup_frame(run, req)
    if comparison:
        second = output['groups'][1]['inspections'][0]
        second['comparison'] = dict(between=dict(left_ref=second['comparison']['one_subject'],
            right_ref=dict(field='question', quote=req['question'])))
        run['question_inspection'] = question.bind(output, req, items)
    catalog = dict(contract=selection.CONTRACT, properties=[dict(property_ref='p1', kind='source_span',
        field_label='', item_ref='p1', parent_ref=None, meaning_keys=['t1'], source_reference=target['ref'])], issues=[])
    run['required_unit_selection_experiment'] = selection.CONTRACT
    monkeypatch.setattr(selection, 'property_catalog', lambda *a: deepcopy(catalog))
    ground_fixture(run, source, catalog)
    raw = dict(links=[dict(item_id=i['id'], facts=[dict(key='t1', required_for_requirement=True,
        requirement_link=dict(applicability='applicable', contribution='direct_answer', reason='합성 선택'),
        selection_state='complete', uses=[dict(fact_id='f'+str(n), criterion_id='criterion_'+str(n),
            necessity='necessary')])]) for n, i in enumerate(items, 1)], meaning_challenges=[])
    monkeypatch.setattr(execution, 'json_call', lambda *a, **k: deepcopy(raw))
    return run, req, source, catalog, raw


@pytest.mark.parametrize('prior_scope', ['public_scope', 'processing_scope'])
def test_fresh_grounding_keeps_source_facts_excluded_by_previous_selection(case, monkeypatch, prior_scope):
    run, req, source, catalog, _ = setup_selection(case, monkeypatch)
    source[prior_scope] = {('review_meaning_keys' if prior_scope == 'public_scope' else 'requested_meaning_keys'): []}
    before = deepcopy(source)
    expected = run.pop('source_fact_grounding')['model_output']
    def generate(service, active, stage, prompt, packet, model):
        assert [m['key'] for m in packet['source_facts']] == ['t1']
        model.model_validate(expected)
        return deepcopy(expected)
    monkeypatch.setattr(execution, 'json_call', generate)
    monkeypatch.setattr(execution, 'save', lambda *a: None)
    result = selection.ground(None, run, req, source, run['blocks'])
    assert result['ready'] and result['facts'] and source == before


@pytest.mark.parametrize('prior_scope', ['public_scope', 'processing_scope'])
def test_fresh_application_keeps_same_full_inventory_as_grounding(case, monkeypatch, prior_scope):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch)
    source[prior_scope] = {('review_meaning_keys' if prior_scope == 'public_scope' else 'requested_meaning_keys'): []}
    before = deepcopy(source)
    run['request_reference_review'] = dict(contract=selection.CONTRACT, block_ids=['block1'])
    monkeypatch.setattr(execution, 'save', lambda *a: None)
    def generate(service, active, stage, prompt, packet, model):
        assert [m['key'] for m in packet['source_facts']] == ['t1']
        model.model_validate(raw)
        return deepcopy(raw)
    monkeypatch.setattr(execution, 'json_call', generate)
    result = bound.assess_application(None, run, req, source, 'selection')
    assert selection.bound_targets(result, catalog)['targets'] and source == before


def apply(case, monkeypatch, comparison=False):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch, comparison)
    selected = review.apply_requirement(None, run, req, source, run['blocks'])
    return run, req, source, catalog, raw, selected, selection.bound_targets(selected, catalog)


@pytest.mark.parametrize('field', ['property_ref', 'binding_id', 'attribute_ref', 'identity_refs', 'condition_refs'])
def test_request_selection_cannot_reassign_source_fact(case, monkeypatch, field):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch)
    model = selection.application_type(run['source_fact_grounding']['facts'], question.public_items(run, req),
        source['meanings'], run['question_inspection']['criteria'])
    model.model_validate(raw)
    assert 'requested_fact' not in json.dumps(model.model_json_schema())
    raw['links'][0]['facts'][0]['uses'][0][field] = 'replacement'
    with pytest.raises(ValidationError): model.model_validate(raw)


def test_grounding_input_has_source_and_unique_scopes_but_no_request_decisions(case, monkeypatch):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch, True)
    criteria = run['question_inspection']['criteria']
    packet = selection.grounding_packet(catalog, criteria, source['meanings'], run['blocks'])
    assert set(packet) == {'source_facts', 'blocks', 'source_property_catalog', 'inspection_scopes'}
    assert len(packet['inspection_scopes']) == 3
    criteria.append(deepcopy(criteria[0]))
    assert len(selection.inspection_scopes(criteria)) == 3
    assert all(set(s) == {'scope_id', 'subject_ref', 'attribute_ref'} for s in packet['inspection_scopes'])


def test_same_literal_source_can_have_multiple_attributes_without_global_merge(case, monkeypatch):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch)
    facts = run['source_fact_grounding']['facts']
    assert len(facts) == 2 and facts[0]['source_reference'] == facts[1]['source_reference']
    assert facts[0]['criterion_reference'] != facts[1]['criterion_reference']


def test_product_selection_input_uses_fixed_facts_without_origin_request_decisions(case, monkeypatch):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch)
    facts = run['source_fact_grounding']['facts']
    def capture(service, active, stage, instruction, packet, model):
        assert stage == 'requirement_application'
        assert packet['fixed_source_facts'] == selection.model_facts(facts)
        assert all('question_inspection' not in f and 'question_binding' not in f for f in packet['fixed_source_facts'])
        for original, supplied in zip(facts, packet['fixed_source_facts']):
            assert supplied['attribute_ref'] == original['criterion_reference']
            assert supplied['source_reference'] == original['source_reference']
        model.model_validate(raw)
        return deepcopy(raw)
    monkeypatch.setattr(execution, 'json_call', capture)
    selected = review.apply_requirement(None, run, req, source, run['blocks'])
    assert not selection.bound_targets(selected, catalog)['blocked_ranges']


def test_selected_source_review_dispatch_does_not_reuse_old_diagnostic_cohorts(case, monkeypatch):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch)
    selected = review.apply_requirement(None, run, req, source, run['blocks'])
    run['selected_request_source'] = selected
    run['request_reference_review'] = dict(contract=selection.CONTRACT, block_ids=[b['id'] for b in run['blocks']],
        candidate_groups={'old-diagnostic': ['not-a-current-candidate']})
    captured = {}
    def capture(service, active, arm, claims, targets, blocks):
        captured.update(claims=claims, targets=targets, blocks=blocks)
        return dict(checks=[], whole_requirement_complete=False)
    monkeypatch.setattr(bound, 'assess', capture)
    monkeypatch.setattr(execution, 'save', lambda *a: None)
    result = execution.assess(None, run, req, phase='selected_source_review')
    assert captured['claims'] == run['claims']
    assert captured['targets'] == selection.bound_targets(selected, catalog)['targets']
    assert result['candidate_scope']['candidate_ids'] == ['c1']
    assert result['candidate_scope']['whole_graph_absence_assessed'] is False
    assert result['whole_requirement_complete'] is False
    assert run['selected_request_source'] == selected


def test_reference_use_keeps_actual_attribute_and_does_not_cover_other_attribute(case, monkeypatch):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch, True)
    raw['links'][1]['facts'][0]['uses'][0]['fact_id'] = 'f1'
    before = deepcopy((raw, source, run['claims']))
    selected = review.apply_requirement(None, run, req, source, run['blocks'])
    scope = selection.bound_targets(selected, catalog)
    assert (raw, source, run['claims']) == before
    assert len(scope['targets']) == 1 and not scope['blocked_ranges']
    target = scope['targets'][0]
    assert target['question_binding']['binding_id'] == 'criterion_1_side_1'
    assert target['request_uses'][1]['relation'] == 'comparison_context'
    assert not target['request_uses'][1]['matching_binding_ids']
    assert scope['criteria_without_necessary_source'] == ['criterion_2']
    assert scope['bindings_without_necessary_source'] == ['criterion_2_side_1', 'criterion_2_side_2']
    packet = bound.packet(run['claims'], scope['targets'], run['blocks'])
    assert packet['bound_targets'][target['key']]['request_uses'] == target['request_uses']
    assert selected['application_history'][-1]['output'] == raw
    row = dict(status='unknown', expression_quotes=[], represented_content='',
        missing_content='', missing_evidence=[], reason='합성 계약 검사')
    result = bound.consume(dict(checks={target['key']: row}), 'B', run['claims'], [target], run['blocks'])
    assert result['checks'][0]['request_uses'] == target['request_uses']


def test_same_subject_attribute_is_reused_and_covered_across_requests(case, monkeypatch):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch)
    output = deepcopy(run['question_inspection']['model_output'])
    output['groups'][1]['inspections'] = deepcopy(output['groups'][0]['inspections'])
    run['question_inspection'] = question.bind(output, req, question.public_items(run, req))
    ground_fixture(run, source, catalog)
    assert len(run['source_fact_grounding']['facts']) == 1
    raw['links'][1]['facts'][0]['uses'][0]['fact_id'] = 'f1'
    selected = review.apply_requirement(None, run, req, source, run['blocks'])
    scope = selection.bound_targets(selected, catalog)
    assert len(scope['targets']) == 1 and not scope['bindings_without_necessary_source']
    assert [u['matching_binding_ids'] for u in scope['targets'][0]['request_uses']] == [
        ['criterion_1_side_1'], ['criterion_2_side_1']]
    bound.packet(run['claims'], scope['targets'], run['blocks'])
    assert scope['whole_requirement_complete'] is False


@pytest.mark.parametrize('bad', ['missing', 'duplicate', 'unresolved', 'wrong_property_owner', 'condition', 'address'])
def test_invalid_grounding_preserves_raw_and_normal_facts(case, monkeypatch, bad):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch)
    output = deepcopy(run['source_fact_grounding']['model_output'])
    if bad == 'missing': output['rows'] = []
    elif bad == 'duplicate': output['rows'] *= 2
    elif bad == 'unresolved': output['rows'][0]['state'] = 'unresolved'
    elif bad == 'wrong_property_owner': catalog['properties'][0]['meaning_keys'] = ['other']
    elif bad == 'condition': output['rows'][0]['facts'][1]['condition_state'] = 'selected'
    else: catalog['properties'][0]['source_reference']['quote'] = 'not source'
    before = deepcopy(output)
    record = selection.bind_facts(output, catalog, run['question_inspection']['criteria'], source['meanings'], run['blocks'])
    assert not record['ready'] and record['model_output'] == output == before
    if bad in {'condition', 'unresolved'}: assert record['facts']


@pytest.mark.parametrize('bad', ['source', 'blocks', 'catalog', 'grounded_attribute', 'grounded_conditions', 'scope'])
def test_changed_grounding_cannot_enter_selection(case, monkeypatch, bad):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch)
    if bad == 'source': source['meanings'][0]['statement'] += ' changed'
    elif bad == 'blocks': run['blocks'][0]['text'] += ' changed'
    elif bad == 'catalog': catalog['properties'][0]['field_label'] = 'changed'
    elif bad == 'grounded_attribute': run['source_fact_grounding']['facts'][0]['criterion_reference']['quote'] = 'changed'
    elif bad == 'grounded_conditions': run['source_fact_grounding']['facts'][0]['condition_references'] = [] ; run['source_fact_grounding']['facts'][0]['condition_state'] = 'selected'
    else: run['source_fact_grounding']['scopes'][0]['subject_ref']['quote'] = 'changed'
    with pytest.raises(ValueError, match='changed'):
        review.apply_requirement(None, run, req, source, run['blocks'])


@pytest.mark.parametrize('bad', ['missing_id', 'wrong_request', 'duplicate_use', 'unresolved'])
def test_bad_fact_use_preserves_other_valid_selection(case, monkeypatch, bad):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch)
    row = raw['links'][0]['facts'][0]; use = row['uses'][0]
    if bad == 'missing_id': use['fact_id'] = 'missing'
    elif bad == 'wrong_request': use['criterion_id'] = 'criterion_2'
    elif bad == 'duplicate_use': row['uses'] *= 2
    else: use['necessity'] = 'unresolved'
    selected = review.apply_requirement(None, run, req, source, run['blocks'])
    scope = selection.bound_targets(selected, catalog)
    assert scope['blocked_ranges'] and scope['targets']
    assert any(u['inspection']['criterion_id'] == 'criterion_2' for t in scope['targets'] for u in t['request_uses'])


def test_condition_or_and_identity_are_preserved_once_and_in_all_uses(case, monkeypatch):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch, True)
    block = run['blocks'][0]; start = block['text'].index('싱거우면')
    condition = dict(catalog['properties'][0]['source_reference'], quote=block['text'][start:],
        start_char=start, end_char=len(block['text']))
    catalog['properties'].append(dict(catalog['properties'][0], property_ref='p2', source_reference=condition))
    source['meanings'][0]['evidence'].append(condition)
    output = deepcopy(run['source_fact_grounding']['model_output'])
    output['rows'][0]['facts'][0].update(condition_refs=['p2'], condition_state='selected')
    run['source_fact_grounding'] = selection.bind_facts(output, catalog, run['question_inspection']['criteria'], source['meanings'], run['blocks'])
    raw['links'][1]['facts'][0]['uses'][0]['fact_id'] = 'f1'
    selected = review.apply_requirement(None, run, req, source, run['blocks'])
    scope = selection.bound_targets(selected, catalog)
    packet = bound.packet(run['claims'], scope['targets'], run['blocks'])
    target = scope['targets'][0]
    assert target['identity_references'] == [catalog['properties'][0]['source_reference']]
    assert target['condition_references'] == [condition]
    assert '간장이나 소금' in target['condition_references'][0]['quote']
    assert packet['bound_targets'][target['key']]['condition_references'] == target['condition_references']


def test_no_selected_facts_does_not_mean_global_absence_or_completion(case, monkeypatch):
    run, req, source, catalog, raw = setup_selection(case, monkeypatch)
    for group in raw['links']:
        row = group['facts'][0]; row.update(required_for_requirement=False, uses=[])
        row['requirement_link'].update(applicability='outside_scope', contribution='background')
    selected = review.apply_requirement(None, run, req, source, run['blocks'])
    scope = selection.bound_targets(selected, catalog)
    assert not scope['targets'] and len(scope['criteria_without_necessary_source']) == 2
    assert scope['whole_requirement_complete'] is False


@pytest.mark.parametrize('bad', ['attribute', 'condition', 'destination', 'coverage'])
def test_changed_fact_or_use_is_rejected_before_source_review(case, monkeypatch, bad):
    run, req, source, catalog, raw, selected, scope = apply(case, monkeypatch)
    fact = selected['meanings'][0]['requirement_applications'][0]['selection_record']['selections'][0]
    if bad == 'attribute': fact['criterion_reference']['quote'] = 'changed'
    elif bad == 'condition': fact['condition_state'] = 'selected'
    elif bad == 'destination': fact['request_inspection']['item_id'] = 'other'
    else: fact['matching_binding_ids'] = []
    with pytest.raises(ValueError, match='changed'): selection.bound_targets(selected, catalog)


def test_fact_ids_do_not_collide_with_source_version_aliases():
    value = dict(fact_id='f1', scope_id='s1', property_ref='p1', source_reference=dict(source_version_id='s1'),
        matching_binding_ids=['b1'])
    mapped = remap(value, {'f1': 'fact-alias', 's1': 'source-alias', 'p1': 'property-alias', 'b1': 'binding-alias'})
    assert {k: v for k,v in mapped.items() if k != 'source_reference'} == {k: v for k,v in value.items() if k != 'source_reference'}
    assert mapped['source_reference']['source_version_id'] == 'source-alias'


def test_question_only_product_request_has_no_source_or_stored_answer_values(case):
    run, req, *_ = case
    items = question.public_items(run, req)
    payload = question.packet(req, items)
    request = execution.json_request(run, 'requirement_inspection', question.PROMPT, payload, question.output_type(items))
    wire = json.loads(request['messages'][1]['content'])
    assert set(wire) == {'answer_request', 'public_answer_items', 'application_context', 'criterion_sources'}
    assert wire['answer_request'] == {k: req[k] for k in ('question', 'criterion')}
    assert wire['public_answer_items'] == items
    assert all(s not in request['messages'][1]['content'] for s in ['120g', '200g', 'SOURCE_TITLE_SHOULD_NOT_LEAK'])


@pytest.mark.parametrize('bad', ['missing', 'duplicate', 'unresolved', 'nonliteral', 'empty'])
def test_bad_scope_preserves_raw_and_normal_inspections_without_ready(case, bad):
    run, req, *_ = case
    items, raw, _ = setup_frame(run, req)
    if bad == 'missing': raw['groups'].pop()
    elif bad == 'duplicate': raw['groups'][1] = deepcopy(raw['groups'][0])
    elif bad == 'unresolved': raw['groups'][1]['state'] = 'unresolved'
    elif bad == 'nonliteral': raw['groups'][1]['inspections'][0]['attribute_ref']['quote'] = '원문에 없는 구절'
    else: raw['groups'][1]['inspections'] = []
    original = deepcopy(raw)
    frame = question.bind(raw, req, items)
    assert not frame['ready'] and frame['errors'] and frame['model_output'] == original == raw
    if bad != 'duplicate': assert frame['criteria']
    with pytest.raises(ValueError, match='unresolved'): question.validate(frame, req, items)


@pytest.mark.parametrize('bad', ['revision', 'question', 'criterion', 'context', 'frame'])
def test_changed_requirement_or_fixed_frame_cannot_be_consumed(case, bad):
    run, req, *_ = case
    items, _, frame = setup_frame(run, req)
    if bad == 'frame': frame['criteria'][0]['bindings'][0]['subject_ref']['quote'] = '다른 대상'
    elif bad == 'revision': req['revision'] += 1
    elif bad == 'context': req['situation'] += ' 변경'
    else: req[bad] += ' 변경'
    with pytest.raises(ValueError, match='changed'): question.validate(frame, req, items)


def test_alias_mapping_keeps_public_text_and_binding_id_literal():
    value = dict(answer_request=dict(question='v1', criterion='c1'),
        selected=dict(property_ref='p1', binding_id='criterion_1_side_1'),
        literal=dict(field='question', quote='v1'),
        context=dict(requirement_id='r', requirement_revision=1, field='question', occurrences=[[0, 2]], quote='v1'))
    mapping = {'v1': 'long-version', 'c1': 'long-claim', 'question': 'long-question', 'criterion_1_side_1': 'long-id'}
    assert remap(value, mapping) == value


def test_repeated_quote_retains_all_exact_occurrences_without_scope_guess():
    req = dict(id='r', revision=1, question='상품 부위와 레시피 부위를 비교', criterion='')
    raw = dict(field='question', quote='부위')
    resolved = question.resolve_quote(raw, req)
    assert resolved['occurrences'] == [[3, 5], [11, 13]] and 'span' not in resolved
    with pytest.raises(ValueError, match='not_literal'):
        question.resolve_quote(dict(raw, field='criterion'), req)


def test_overlapping_quote_matches_are_not_treated_as_unique():
    resolved = question.resolve_quote(dict(field='question', quote='aa'), dict(id='r', revision=1, question='aaa'))
    assert resolved['occurrences'] == [[0, 2], [1, 3]]


def test_incomplete_quote_is_not_extended_or_semantically_approved():
    req = dict(id='r', revision=1, question='레시피에서 지정한 부위', criterion='')
    raw = dict(groups=[dict(item_id='a', state='complete', reason='', inspections=[dict(
        attribute_ref=dict(field='question', quote='지정한 부'),
        comparison=dict(one_subject=dict(field='question', quote='레시피')), context_refs=[])])])
    frame = question.bind(raw, req, [dict(id='a', field='question', request_quote=req['question'])])
    assert frame['criteria'][0]['bindings'][0]['attribute_ref']['quote'] == '지정한 부'
    assert frame['model_output'] == raw and frame['semantic_status'] == 'not_assessed'


def test_literal_schema_rejects_previous_span_only_response(case):
    run, req, *_ = case
    items, raw, _ = setup_frame(run, req)
    model = question.output_type(items)
    assert all(k not in json.dumps(model.model_json_schema()) for k in ('span', 'within_item_id', 'occurrences'))
    raw['groups'][0]['inspections'][0]['attribute_ref'] = dict(field='question', span=[0, 1])
    with pytest.raises(ValidationError): model.model_validate(raw)


@pytest.mark.parametrize('bad', ['one_side', 'duplicate_side'])
def test_cross_target_comparison_requires_two_distinct_bindings(case, bad):
    run, req, *_ = case
    items, raw, _ = setup_frame(run, req)
    inspection = raw['groups'][0]['inspections'][0]
    subject = inspection['comparison']['one_subject']
    pair = dict(left_ref=subject)
    if bad == 'duplicate_side': pair['right_ref'] = deepcopy(subject)
    inspection['comparison'] = dict(between=pair)
    original = deepcopy(raw)
    frame = question.bind(raw, req, items)
    assert not frame['ready'] and frame['model_output'] == original
    assert frame['errors'][0]['reason'] == ('comparison_form_invalid' if bad == 'one_side' else 'duplicate_comparison_subject')


@pytest.mark.parametrize('bad', ['removed', 'added', 'changed_revision'])
def test_recomputed_quote_occurrences_cannot_be_forged(case, bad):
    run, req, *_ = case
    _, _, frame = setup_frame(run, req)
    inspection = frame['criteria'][0]
    ref = inspection['bindings'][0]['attribute_ref']
    if bad == 'removed': ref['occurrences'].pop()
    elif bad == 'added': ref['occurrences'].append([0, 1])
    else: ref['requirement_revision'] += 1
    with pytest.raises(ValueError, match='inspection_changed'): question.validate_inspection(inspection, req)


def test_product_dispatch_uses_binding_contract(case, monkeypatch):
    run, req, *_ = case
    run['request_reference_review'] = dict(contract=selection.CONTRACT)
    monkeypatch.setattr(bound, 'assess_application', lambda service, active, requirement, source, phase:
        dict(requirement=requirement['id'], phase=phase))
    assert execution.assess(None, run, req, phase='selection_criteria') == dict(requirement=req['id'], phase='selection_criteria')
    with pytest.raises(ValueError, match='requires_fresh'):
        execution.assess(None, run, req, previous_run=run)


def test_same_subject_different_attributes_are_not_two_comparison_subjects():
    req = dict(id='r', revision=1, question='등록된 돼지고기 두 상품은 부위와 용도가 어떻게 다른가요?', criterion='')
    literal = lambda quote: question.resolve_quote(dict(field='question', quote=quote), req)
    inspection = dict(criterion_id='criterion_1', item_id='item1', comparison_kind='between_targets',
        bindings=[dict(binding_id='criterion_1_side_' + str(i),
            subject_ref=literal('등록된 돼지고기 두 상품'), attribute_ref=literal(attribute))
            for i, attribute in enumerate(['부위', '용도'], 1)], context_refs=[literal('어떻게 다른가요?')])
    original = deepcopy(inspection)
    with pytest.raises(ValueError, match='duplicate_comparison_subject'):
        question.validate_inspection(inspection, req)
    assert inspection == original


def test_shared_attribute_is_bound_without_rewriting_raw_or_per_subject_attributes(case):
    run, req, *_ = case
    items, raw, _ = setup_frame(run, req)
    inspection = raw['groups'][0]['inspections'][0]
    inspection['comparison'] = dict(between=dict(left_ref=inspection['comparison']['one_subject'],
        right_ref=dict(field='criterion', quote=req['criterion'])))
    original = deepcopy(raw)
    frame = question.bind(raw, req, items)
    assert frame['ready'] and frame['model_output'] == original == raw
    left, right = frame['criteria'][0]['bindings']
    assert left['attribute_ref'] == right['attribute_ref']
    assert left['subject_ref'] != right['subject_ref']
    inspection['comparison']['between']['attribute_ref'] = dict(field='criterion', quote=req['criterion'])
    with pytest.raises(ValidationError): question.output_type(items).model_validate(raw)


@pytest.mark.parametrize('form, kind, sides', [
    ('members_of', 'within_group', 1), ('between', 'between_targets', 2),
    ('one_subject', 'single_target', 1)])
def test_exclusive_comparison_forms_restore_canonical_bindings_without_raw_edits(case, form, kind, sides):
    run, req, *_ = case
    items = question.public_items(run, req)
    left = dict(field='question', quote=req['question'])
    right = dict(field='criterion', quote=req['criterion'])
    comparison = {form: dict(left_ref=left, right_ref=right) if form == 'between' else left}
    raw = dict(groups=[dict(item_id=i['id'], state='complete', reason='합성 경계 검사',
        inspections=[dict(attribute_ref=left, comparison=deepcopy(comparison), context_refs=[right])]) for i in items])
    original = deepcopy(raw)
    question.output_type(items).model_validate(raw)
    frame = question.bind(raw, req, items)
    assert frame['ready'] and frame['model_output'] == raw == original
    for inspection in question.validate(frame, req, items):
        assert inspection['comparison_kind'] == kind and len(inspection['bindings']) == sides
        assert inspection['context_refs'] == [question.resolve_quote(right, req)]
        assert [b['subject_ref'] for b in inspection['bindings']] == [
            question.resolve_quote(r, req) for r in ([left, right] if sides == 2 else [left])]
        assert all(b['attribute_ref'] == question.resolve_quote(left, req) for b in inspection['bindings'])
        question.validate_inspection(inspection, req)


@pytest.mark.parametrize('bad', ['two_forms', 'missing_right', 'extra_side', 'unknown_form', 'empty'])
def test_mixed_or_incomplete_comparison_forms_are_rejected_without_repair(case, bad):
    run, req, *_ = case
    items, raw, _ = setup_frame(run, req)
    inspection = raw['groups'][0]['inspections'][0]
    ref = inspection['comparison']['one_subject']
    forms = dict(two_forms=dict(members_of=ref, one_subject=ref),
        missing_right=dict(between=dict(left_ref=ref)),
        extra_side=dict(members_of=ref, right_ref=ref),
        unknown_form=dict(compare=ref), empty={})
    inspection['comparison'] = forms[bad]
    original = deepcopy(raw)
    with pytest.raises(ValidationError): question.output_type(items).model_validate(raw)
    frame = question.bind(raw, req, items)
    assert not frame['ready'] and frame['model_output'] == raw == original
    assert frame['errors'][0]['reason'] == 'comparison_form_invalid'
    assert len(frame['criteria']) == len(items) - 1


def test_previous_flat_comparison_response_is_not_silently_reinterpreted(case):
    run, req, *_ = case
    items, raw, _ = setup_frame(run, req)
    inspection = raw['groups'][0]['inspections'][0]
    subject = inspection.pop('comparison')['one_subject']
    inspection.update(comparison_kind='between_targets', bindings=[dict(subject_ref=subject)] * 2)
    original = deepcopy(raw)
    with pytest.raises(ValidationError): question.output_type(items).model_validate(raw)
    frame = question.bind(raw, req, items)
    assert not frame['ready'] and frame['model_output'] == raw == original
