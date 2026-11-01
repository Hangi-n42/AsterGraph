"""Finite output and immutable target boundaries; no native/model calls."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app.knowledge import business_bound_source_review as bound, business_run as execution
from app.tests.unit.test_knowledge_business_role_review import case


def compact(row):
    return {k: deepcopy(row[k]) for k in ('expression_quotes', 'represented_content',
        'missing_content', 'missing_evidence', 'reason', 'status')}


def test_selected_candidate_inventory_uses_version_ownership_not_text_or_address(case):
    run, _, _, claim, target, *_ = case
    before = deepcopy(run)
    other_version = dict(deepcopy(claim), id='older', source_version_ids=['v0'], evidence=[])
    run['sources']['v0'] = dict(source_id='s1', title='same source old version')
    run['blocks'].append(dict(run['blocks'][0], id='old-block', source_version_id='v0'))
    bad_address = dict(deepcopy(claim), id='invalid-address', evidence=[dict(block_id='unknown', quote='bad')])
    unrelated_text = dict(deepcopy(claim), id='same-source-other-text', raw=dict(Head='다른 속성'), evidence=[])
    superseded = dict(deepcopy(claim), id='superseded', superseded_by=['c1'])
    run['claims'].extend([other_version, bad_address, unrelated_text, superseded])
    chosen, inventory = bound.selected_candidates(run, [target])
    assert [c['id'] for c in chosen] == ['c1', 'invalid-address', 'same-source-other-text']
    assert inventory['candidate_ids'] == [c['id'] for c in chosen]
    assert inventory['source_version_ids'] == ['v1']
    assert inventory['whole_graph_absence_assessed'] is False
    assert run['claims'][0] == before['claims'][0]


def test_selected_candidate_inventory_keeps_evidence_and_chunk_owned_claims(case):
    run, _, _, claim, target, *_ = case
    by_evidence = dict(deepcopy(claim), id='evidence-owned', source_version_ids=[])
    by_chunk = dict(deepcopy(claim), id='chunk-owned', source_version_ids=[], evidence=[], chunk_id='chunk')
    run['chunks'] = [dict(id='chunk', source_version_id='v1')]
    run['claims'] = [by_evidence, by_chunk]
    chosen, inventory = bound.selected_candidates(run, [target])
    assert inventory['candidate_ids'] == ['evidence-owned', 'chunk-owned']
    before = inventory['candidate_pool_hash']
    run['claims'][0]['raw']['Tail'] = 'changed stored fact'
    assert bound.selected_candidates(run, [target])[1]['candidate_pool_hash'] != before


@pytest.mark.parametrize('bad', ['unknown_version', 'unknown_owner', 'empty_pool'])
def test_selected_candidate_inventory_cannot_invent_scope_or_missing_fact(case, bad):
    run, _, _, _, target, *_ = case
    if bad == 'unknown_version': target['ref']['source_version_id'] = 'unknown'
    elif bad == 'unknown_owner': run['sources']['v1'].pop('source_id')
    else: run['claims'] = []
    with pytest.raises(ValueError, match='unavailable'): bound.selected_candidates(run, [target])


def test_common_input_is_identical_without_evaluator_labels(case):
    run, _, _, claim, target, *_ = case
    target.update(subject='EVALUATOR_SUBJECT', attribute='EVALUATOR_ATTRIBUTE', expected='EVALUATOR_STATUS')
    before = deepcopy((claim, target, run['blocks']))
    a = bound.request(run, 'A', [claim], [target], run['blocks'])
    b = bound.request(run, 'B', [claim], [target], run['blocks'])
    assert a['messages'][1] == b['messages'][1] and a['reference_map'] == b['reference_map']
    assert all(secret not in a['messages'][1]['content'] for secret in ['EVALUATOR_SUBJECT', 'EVALUATOR_ATTRIBUTE', 'EVALUATOR_STATUS'])
    assert (claim, target, run['blocks']) == before
    packet = json.loads(a['messages'][1]['content'])
    assert packet['bound_targets']['t1']['quote'] == '돼지고기 120g'
    assert packet['stored_candidates'][0]['stored_interpretation']['meanings'][0]['conditions']['text'] == '싱거우면'
    assert packet['stored_candidates'][0]['state']['semantic_status'] == 'unknown'


def test_fixed_slots_and_finite_evidence_first_compact_schema(case):
    run, _, _, claim, target, raw, *_ = case
    schema = bound.output_type('B', [claim], [target], run['blocks']).model_json_schema()
    ref = schema['$defs']['BoundTargetSlotsB']['properties']['t1']['$ref']
    row = schema['$defs'][ref.split('/')[-1]]
    assert list(row['properties'])[-1] == 'status'
    assert row['properties']['reason']['maxLength'] == 160
    assert row['properties']['represented_content']['maxLength'] == 500
    assert 'claim_ids' not in row['properties']
    assert schema['$defs']['CompactExpressionQuote']['properties']['claim_id']['const'] == 'c1'
    model = bound.output_type('B', [claim], [target], run['blocks'])
    value = dict(checks={'t1': compact(raw['checks'][0])})
    with pytest.raises(ValidationError): model.model_validate(dict(checks={'other': value['checks']['t1']}))
    value['checks']['t1']['reason'] = 'x' * 161
    with pytest.raises(ValidationError): model.model_validate(value)


def test_wide_generated_identity_cannot_replace_fixed_target(case):
    run, _, _, claim, target, raw, *_ = case
    row = deepcopy(raw['checks'][0]); row['meaning_key'] = 'other'
    with pytest.raises(ValueError, match='cannot_replace_bound_slot'):
        bound.consume(dict(checks={'t1': row}), 'A', [claim], [target], run['blocks'])


def test_compact_candidate_ids_come_only_from_quoted_locations(case):
    run, _, _, claim, target, raw, *_ = case
    other = dict(deepcopy(claim), id='same-text-copy')
    row = compact(raw['checks'][0])
    output = dict(checks={'t1': row}); original = deepcopy(output)
    check = bound.consume(output, 'B', [claim, other], [target], run['blocks'])['checks'][0]
    assert check['claim_ids'] == ['c1'] and not check['consumer_errors']
    assert check['status'] == 'partial' and output == original
    row['claim_ids'] = ['c1', 'same-text-copy']
    with pytest.raises(ValidationError):
        bound.output_type('B', [claim, other], [target], run['blocks']).model_validate(output)
    with pytest.raises(ValueError, match='must_use_expression_quotes'):
        bound.consume(output, 'B', [claim, other], [target], run['blocks'])


@pytest.mark.parametrize('bad', ['empty', 'duplicate'])
def test_compact_still_requires_real_nonduplicated_contribution(case, bad):
    run, _, _, claim, target, raw, *_ = case
    row = compact(raw['checks'][0])
    row['expression_quotes'] = [] if bad == 'empty' else row['expression_quotes'] * 2
    check = bound.consume(dict(checks={'t1': row}), 'B', [claim], [target], run['blocks'])['checks'][0]
    assert check['status'] == 'unknown' and check['consumer_errors']


@pytest.mark.parametrize('arm', ['A', 'B'])
def test_partial_preserves_normal_material_and_exact_missing_quantity(case, arm):
    run, _, _, claim, target, raw, *_ = case
    row = deepcopy(raw['checks'][0]); row['missing_evidence'] = [dict(evidence_ref='e1', span=[8, 12], quote='120g')]
    output = dict(checks={'t1': row if arm == 'A' else compact(row)})
    if arm == 'A': output['checks']['t1']['evidence'] = ['e1']
    result = bound.consume(output, arm, [claim], [target], run['blocks'])
    check = result['checks'][0]
    assert check['status'] == 'partial' and not check['consumer_errors']
    assert check['represented_content'] == '돼지고기' and check['missing_content'] == '120g'
    assert check['expression_bindings'][0]['span'] == [0, 4]
    assert check['missing_evidence'][0]['start_char'] == 8
    assert result['canonical_targets']['t1']['quote'] == '돼지고기 120g'
    assert result['model_output'] == output and result['actions'] == []


def test_complete_normal_contribution_is_not_forced_unknown(case):
    run, _, _, claim, target, raw, *_ = case
    target['ref'].update(quote='돼지고기', end_char=7)
    row = compact(raw['checks'][0]); row.update(status='represented', missing_content='', missing_evidence=[])
    result = bound.consume(dict(checks={'t1': row}), 'B', [claim], [target], run['blocks'])
    assert result['checks'][0]['status'] == 'represented'
    assert not result['checks'][0]['consumer_errors']
    assert result['candidate_correctness_not_assessed']


@pytest.mark.parametrize('bad', ['quote', 'owner', 'duplicate', 'outside', 'version'])
def test_existing_exact_address_and_owner_guards_remain(case, bad):
    run, _, _, claim, target, raw, *_ = case
    row = compact(raw['checks'][0]); row['missing_evidence'] = [dict(evidence_ref='e1', span=[8, 12], quote='120g')]
    if bad == 'quote': row['expression_quotes'][0]['quote'] = '120g'
    elif bad == 'owner': claim['source_version_ids'] = ['other']
    elif bad == 'duplicate': row['missing_evidence'] *= 2
    elif bad == 'outside': row['missing_evidence'] = [dict(evidence_ref='e1', span=[14, 18], quote='싱거우면')]
    else: target['ref']['source_version_id'] = 'other'
    if bad == 'version':
        with pytest.raises(ValueError): bound.packet([claim], [target], run['blocks'])
    else:
        check = bound.consume(dict(checks={'t1': row}), 'B', [claim], [target], run['blocks'])['checks'][0]
        assert check['status'] == 'unknown' and check['consumer_errors']
        assert row['status'] == 'partial'


def test_assess_only_appends_diagnostic_with_existing_json_call(case, monkeypatch):
    run, _, _, claim, target, raw, *_ = case
    before = deepcopy(run)
    def generate(*args, **kwargs):
        return dict(checks={'t1': compact(raw['checks'][0])})
    monkeypatch.setattr(execution, 'json_call', generate)
    monkeypatch.setattr(execution, 'save', lambda *a: None)
    result = bound.assess(None, run, 'B', [claim], [target], run['blocks'])
    assert result['checks'][0]['status'] == 'partial'
    assert run.pop('bound_source_comparisons') == [result]
    assert run == before


@pytest.mark.parametrize('arm', ['A', 'B'])
def test_exact_target_reference_is_selectable_and_restores_unchanged(case, arm):
    run, _, _, claim, target, raw, *_ = case
    refs = bound.missing_references(target, run['blocks'])
    selected = next(iter(refs))
    assert refs[selected] == execution.exact_evidence([target['ref']], run['blocks'])[0]
    assert 'e1' not in refs
    row = deepcopy(raw['checks'][0])
    row.pop('requirement_scope_id', None)
    row.update(status='missing', claim_ids=[], expression_quotes=[], represented_content='',
        missing_content=target['ref']['quote'], missing_evidence=[selected], evidence=['e1'])
    output = dict(checks={'t1': row if arm == 'A' else compact(row)})
    if arm == 'A': output.update(source_challenges=[], meaning_challenges=[], dependencies=[], preservation_checks=[])
    bound.output_type(arm, [claim], [target], run['blocks']).model_validate(output)
    result = bound.consume(output, arm, [claim], [target], run['blocks'])
    check = result['checks'][0]
    assert check['status'] == 'missing' and not check['consumer_errors']
    assert check['missing_evidence'] == [refs[selected]]
    assert result['model_output'] == output


@pytest.mark.parametrize('base', ['exact', 'block'])
def test_genuine_smaller_subspan_stays_valid(case, base):
    run, _, _, claim, target, raw, *_ = case
    selected = next(iter(bound.missing_references(target, run['blocks']))) if base == 'exact' else 'e1'
    row = compact(raw['checks'][0])
    row['missing_evidence'] = [dict(evidence_ref=selected, span=[8, 12], quote='120g')]
    output = dict(checks={'t1': row})
    bound.output_type('B', [claim], [target], run['blocks']).model_validate(output)
    check = bound.consume(output, 'B', [claim], [target], run['blocks'])['checks'][0]
    assert check['status'] == 'partial' and not check['consumer_errors']
    assert check['missing_evidence'][0]['quote'] == '120g'
    assert check['represented_content'] == '돼지고기'


@pytest.mark.parametrize('identical', [False, True])
def test_other_target_reference_is_rejected_even_when_contained(case, identical):
    run, _, _, claim, target, raw, *_ = case
    other = deepcopy(target); other['key'] = 't2'
    if not identical: other['ref'].update(quote='돼지고기', end_char=7)
    foreign = next(iter(bound.missing_references(other, run['blocks'])))
    own = next(iter(bound.missing_references(target, run['blocks'])))
    assert foreign != own
    row = compact(raw['checks'][0]); row['missing_evidence'] = [foreign]
    normal = compact(raw['checks'][0])
    if identical: normal['missing_evidence'] = [dict(evidence_ref='e1', span=[8, 12], quote='120g')]
    else: normal.update(status='represented', missing_content='', missing_evidence=[])
    output = dict(checks={'t1': row, 't2': normal})
    with pytest.raises(ValidationError): bound.output_type('B', [claim], [target, other], run['blocks']).model_validate(output)
    checks = bound.consume(output, 'B', [claim], [target, other], run['blocks'])['checks']
    assert checks[0]['status'] == 'unknown'
    assert any('outside_selected_target' in e for e in checks[0]['consumer_errors'])
    assert checks[1]['status'] == ('partial' if identical else 'represented') and not checks[1]['consumer_errors']


def test_reference_and_object_duplicate_same_address_is_blocked(case):
    run, _, _, claim, target, raw, *_ = case
    selected = next(iter(bound.missing_references(target, run['blocks'])))
    row = compact(raw['checks'][0])
    row['missing_evidence'] = [selected, dict(evidence_ref='e1', span=[3, 12], quote=target['ref']['quote'])]
    check = bound.consume(dict(checks={'t1': row}), 'B', [claim], [target], run['blocks'])['checks'][0]
    assert check['status'] == 'unknown' and 'duplicate_source_remainder_address' in check['consumer_errors']
    assert row['status'] == 'partial'


def test_legacy_whole_block_is_not_rewritten_as_exact_target(case):
    run, _, _, claim, target, raw, *_ = case
    row = compact(raw['checks'][0]); row['missing_evidence'] = ['e1']
    with pytest.raises(ValidationError): bound.output_type('B', [claim], [target], run['blocks']).model_validate(dict(checks={'t1': row}))
    result = bound.consume(dict(checks={'t1': row}), 'B', [claim], [target], run['blocks'])
    assert result['checks'][0]['status'] == 'unknown'
    assert 'remainder_outside_fixed_source_scope' in result['checks'][0]['consumer_errors']
    assert result['model_output']['checks']['t1']['missing_evidence'] == ['e1']


def test_whole_block_target_retains_its_valid_block_reference(case):
    run, _, _, claim, target, raw, *_ = case
    text = run['blocks'][0]['text']; target['ref'].update(quote=text, start_char=0, end_char=len(text))
    assert 'e1' in bound.missing_references(target, run['blocks'])
    row = compact(raw['checks'][0]); row.update(status='missing', expression_quotes=[], represented_content='', missing_content=text, missing_evidence=['e1'])
    output = dict(checks={'t1': row})
    bound.output_type('B', [claim], [target], run['blocks']).model_validate(output)
    check = bound.consume(output, 'B', [claim], [target], run['blocks'])['checks'][0]
    assert check['status'] == 'missing' and not check['consumer_errors']


def test_unselected_reference_is_never_autofilled(case):
    run, _, _, claim, target, raw, *_ = case
    row = compact(raw['checks'][0]); row['missing_evidence'] = []
    result = bound.consume(dict(checks={'t1': row}), 'B', [claim], [target], run['blocks'])
    assert result['checks'][0]['status'] == 'unknown'
    assert 'remainder_without_source_address' in result['checks'][0]['consumer_errors']
    assert result['model_output']['checks']['t1']['missing_evidence'] == []


@pytest.mark.parametrize('bad', ['quote', 'source_version_id', 'parse_run_id', 'outside', 'foreign_object'])
def test_exact_reference_objects_do_not_bypass_address_guards(case, bad):
    run, _, _, claim, target, raw, *_ = case
    selected = next(iter(bound.missing_references(target, run['blocks'])))
    ref = dict(evidence_ref=selected, span=[8, 12], quote='120g')
    if bad == 'quote': ref['quote'] = '200g'
    elif bad in {'source_version_id', 'parse_run_id'}: ref[bad] = 'other'
    elif bad == 'outside': ref.update(span=[14, 18], quote='싱거우면')
    else: ref['evidence_ref'] = 'another_target_reference'
    row = compact(raw['checks'][0]); row['missing_evidence'] = [ref]
    result = bound.consume(dict(checks={'t1': row}), 'B', [claim], [target], run['blocks'])
    assert result['checks'][0]['status'] == 'unknown' and result['checks'][0]['consumer_errors']
    assert result['model_output']['checks']['t1']['missing_evidence'] == [ref]
