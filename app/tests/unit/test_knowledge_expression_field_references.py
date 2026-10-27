"""Synthetic wire/binding contracts; no source-truth or model-quality labels."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app.knowledge import business_run as execution, business_review as review
from app.knowledge.business_models import ContributionReviewCheck, ContributionSynthesisCheck, Repairs
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_required_content import content_case, target_check


def case():
    run, source, claims = content_case()
    context = dict(blocks=run['blocks'], claims=[execution.compact_claim(c) for c in claims],
        source=source, required_content_targets=[review.requirement_content_target(source, source['meanings'][0])])
    output = dict(checks=[], requirement_checks=[target_check(source, claims)], source_challenges=[],
        meaning_challenges=[], candidate_challenges=[], preservation_checks=[], dependencies=[])
    return run, source, context, output


def wire(run, context, output):
    refs = execution.expression_references(run, context, ContributionReviewCheck)
    lookup = {(v['claim_id'], v['field'], v['quote']):k for k,v in refs.items()}
    result = deepcopy(output)
    for row in result['requirement_checks']:
        row['expression_quotes'] = [lookup[(q['claim_id'], q['field'], q['quote'])] for q in row['expression_quotes']]
    return result, refs


def consume(monkeypatch, run, context, output, mutate=None):
    request = execution.json_request(run, 'requirement_representation', '고정 의미 검수', context, ContributionReviewCheck)
    original = deepcopy(output)
    def respond(service, active, stage, messages, schema, **options):
        assert messages == request['messages'] and schema == request['schema']
        if mutate:
            mutate()
        parsed = remap(output, request['reference_map'] or {})
        active['units'].append(dict(id='synthetic', stage=stage, status='succeeded', response=dict(parsed=deepcopy(parsed))))
        return dict(parsed=parsed)
    monkeypatch.setattr(execution, 'call', respond)
    monkeypatch.setattr(execution, 'save', lambda *args: None)
    result = execution.json_call(None, run, 'requirement_representation', '고정 의미 검수', context, ContributionReviewCheck)
    assert output == original
    return result


def test_full_fields_restore_into_existing_binder_without_changing_judgment(monkeypatch):
    run, source, context, old = case()
    before = deepcopy(run['claims'])
    output, refs = wire(run, context, old)
    result = consume(monkeypatch, run, context, output)
    row = result['requirement_checks'][0]
    assert all(row[k] == v for k,v in old['requirement_checks'][0].items())
    bound = review.bind_requirement_check(row, context['required_content_targets'][0], run['claims'], run['blocks'])
    assert bound['status'] == 'represented' and bound['content_scope_bound']
    assert all(b['span'] == [0,len(b['quote'])] for b in bound['expression_bindings'])
    assert row['expression_reference_precision'] == 'whole_field_not_semantic_support'
    assert run['claims'] == before
    assert run['units'][-1]['expression_reference_map'] == refs


@pytest.mark.parametrize('invalid', ['unknown', 'duplicate', 'owner', 'legacy_partial', 'wrong_type'])
def test_invalid_reference_does_not_trigger_global_schema_loss(monkeypatch, invalid):
    run, source, context, old = case()
    old['requirement_checks'] *= 2
    old['requirement_checks'] = deepcopy(old['requirement_checks'])
    old['requirement_checks'][1] = deepcopy(old['requirement_checks'][1])
    old['requirement_checks'][1]['meaning_key'] = 'sibling'
    output, refs = wire(run, context, old)
    row = output['requirement_checks'][0]
    if invalid == 'unknown':
        row['expression_quotes'] = ['not-provided']
        with pytest.raises(ValidationError):
            execution.expression_reference_type(ContributionReviewCheck, refs).model_validate(output)
    elif invalid == 'duplicate':
        row['expression_quotes'] *= 2
    elif invalid == 'owner':
        row['claim_ids'] = []
    elif invalid == 'legacy_partial':
        row['expression_quotes'] = [dict(claim_id=run['claims'][0]['id'], field='raw.Tail', quote='등')]
    else:
        row['expression_quotes'] = 123
    result = consume(monkeypatch, run, context, output)
    bad, sibling = result['requirement_checks']
    assert bad['status'] == 'unknown' and bad['expression_reference_errors']
    assert sibling['status'] == 'represented' and not sibling['expression_reference_errors']
    bound = review.bind_requirement_check(bad, context['required_content_targets'][0], run['claims'], run['blocks'])
    assert not bound['content_scope_bound'] and bound['status'] == 'unknown'
    if invalid == 'legacy_partial':
        assert bad['expression_quotes'] == []
        assert run['units'][-1]['response']['parsed']['requirement_checks'][0]['expression_quotes'][0]['quote'] == '등'


@pytest.mark.parametrize('key,value', [('claim_version','changed'), ('field','raw.missing'), ('quote','changed'), ('span',[1,2])])
def test_changed_reference_address_value_or_version_is_unresolved(key, value):
    run, _, context, old = case()
    output, refs = wire(run, context, old)
    ref = output['requirement_checks'][0]['expression_quotes'][0]
    refs[ref][key] = value
    metadata = execution.restore_expression_references(output, ContributionReviewCheck, refs, run['claims'])
    assert output['requirement_checks'][0]['status'] == 'unknown'
    assert metadata['requirement_checks',0]['expression_reference_errors']


def test_changed_stored_claim_version_between_request_and_consumption(monkeypatch):
    run, _, context, old = case()
    output, _ = wire(run, context, old)
    result = consume(monkeypatch, run, context, output,
        lambda:run['claims'][0]['raw'].update(Tail='변경된 값'))
    assert result['requirement_checks'][0]['status'] == 'unknown'
    assert 'expression_reference_version_mismatch' in result['requirement_checks'][0]['expression_reference_errors']


def test_source_metadata_is_not_an_expression_and_equal_values_keep_owners():
    run, _, context, _ = case()
    for claim in run['claims']:
        claim['raw'].update(evidence=[dict(quote='원문에만 있음')], reason='설명', Tail='같은 값',
            Entity=['대상', dict(evidence=dict(quote='원문 메타데이터'))])
        claim['interpretation'] = dict(semantic_status='unverified', errors=['기존 오류'], meanings=[dict(
            subject='주체 미확정', conditions=dict(state='absent', text=None), exceptions=dict(state='unknown', text=None))])
        claim['conditions'] = dict(state='present', text='저장 조건', evidence=[dict(quote='출처 문장')])
    context['claims'] = [execution.compact_claim(c) for c in run['claims']]
    before = deepcopy(context)
    refs = execution.expression_references(run, context, ContributionReviewCheck)
    assert not any(v['field'].startswith(('raw.evidence', 'raw.reason')) for v in refs.values())
    assert not any(v['field'].startswith('raw.Entity.1') for v in refs.values())
    assert not any(v['field'].startswith('conditions.evidence') for v in refs.values())
    assert len([v for v in refs.values() if v['field']=='raw.Tail' and v['quote']=='같은 값']) == 2
    assert context == before
    synthesis = execution.json_request(run, 'requirement_representation', '종합', context, ContributionSynthesisCheck)
    assert synthesis['expression_reference_map'] == refs
    assert json.loads(synthesis['messages'][1]['content'])['claims'][0]['interpretation']['meanings'][0]['conditions']['text'] is None
    assert execution.expression_references(run, context, Repairs) is None
    with pytest.raises(ValueError, match='duplicate_expression_candidate'):
        execution.expression_references(run, dict(context, claims=context['claims']*2), ContributionReviewCheck)


def test_reference_index_reuses_delivered_values_and_unrelated_requests_are_unchanged(monkeypatch):
    run, _, context, _ = case()
    request = execution.json_request(run, 'requirement_representation', '고정', context, ContributionReviewCheck)
    fields = json.loads(request['messages'][1]['content'])['expression_fields']
    assert all(set(f) == {'expression_ref', 'claim_id', 'field'} for f in fields)
    unscoped = {k:v for k,v in context.items() if k != 'required_content_targets'}
    actual = execution.json_request(run, 'requirement_representation', '고정', unscoped, ContributionReviewCheck)
    assert actual['expression_reference_map'] is None
    monkeypatch.setattr(execution, 'expression_references', lambda *args:None)
    legacy = execution.json_request(run, 'requirement_representation', '고정', unscoped, ContributionReviewCheck)
    assert actual['messages'] == legacy['messages'] and actual['schema'] == legacy['schema']


def test_compacted_out_structured_event_gets_no_dangling_reference():
    run, _, context, _ = case()
    claim = run['claims'][0]
    claim['role'] = 'structured_row'
    claim['raw'] = dict(fields={'대상':'보존 값'})
    claim['raw']['Event'] = json.dumps(claim['raw']['fields'], ensure_ascii=False)
    context['claims'] = [execution.compact_claim(c) for c in run['claims']]
    refs = execution.expression_references(run, context, ContributionReviewCheck)
    assert not any(v['claim_id']==claim['id'] and v['field']=='raw.Event' for v in refs.values())
    assert any(v['claim_id']==claim['id'] and v['field']=='raw.fields.대상' for v in refs.values())


def test_literal_changed_by_existing_id_mapping_is_not_offered_as_exact_reference():
    run, _, context, _ = case()
    claim = run['claims'][0]
    claim['raw']['Tail'] = claim['id']
    context['claims'] = [execution.compact_claim(c) for c in run['claims']]
    request = execution.json_request(run, 'requirement_representation', '고정', context, ContributionReviewCheck,
        reference_map={claim['id']:'aliased-id'})
    assert not any(v['claim_id']==claim['id'] and v['field']=='raw.Tail'
        for v in request['expression_reference_map'].values())


@pytest.mark.parametrize('invalid', ['non_object', 'unrelated_row_shape'])
def test_unrelated_invalid_json_shape_keeps_existing_failure_boundary(monkeypatch, invalid):
    run, _, context, old = case()
    output, _ = wire(run, context, old)
    if invalid == 'non_object':
        output = []
    else:
        output['requirement_checks'].append(None)
    before = deepcopy(run['claims'])
    assert consume(monkeypatch, run, context, output) is None
    assert run['units'][-1]['status'] == 'failed' and run['units'][-1]['error'].startswith('schema_error:')
    assert run['claims'] == before
