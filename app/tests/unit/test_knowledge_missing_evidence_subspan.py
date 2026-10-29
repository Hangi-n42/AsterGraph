"""Synthetic evidence transport; these checks do not score model judgments."""
from copy import deepcopy

import pytest

from app.knowledge import business_run as execution, business_review as review
from app.knowledge.business_models import ContributionReviewCheck, ContributionSynthesisCheck, ExpressionReviewCheck
from app.tests.unit.test_knowledge_review_request_completeness import case, wire, consume


def subspan_case(status='missing'):
    run, source, context, output = case()
    block = run['blocks'][0]
    # The second occurrence must keep its explicit absolute address.
    block['text'] = '카레 / 상품의 부위는 등심이고 용도는 카레다.'
    block['span'] = [100, 100 + len(block['text'])]
    start = 100 + block['text'].rindex('카레')
    ref = execution.exact_evidence([dict(block_id=block['id'], quote='카레',
        start_char=start, end_char=start + 2)], run['blocks'])[0]
    target = context['required_content_targets'][0]
    target['evidence'] = [ref]
    row = output['requirement_checks'][0]
    row.update(status=status, claim_ids=[], expression_quotes=[], represented_content='',
        missing_content='상품 용도 카레', missing_evidence=[])
    if status == 'partial':
        claim = run['claims'][0]
        row.update(claim_ids=[claim['id']], represented_content='상품 부위 등심',
            expression_quotes=[dict(claim_id=claim['id'],field='raw.Tail',quote='등심')])
    output['checks'] = [deepcopy(row)]
    output, request = wire(run, context, output)
    selected = dict(evidence_ref='e1', span=[start, start + 2], quote='카레')
    for name in ('checks', 'requirement_checks'):
        output[name][0]['missing_evidence'] = [deepcopy(selected)]
    return run, context, output, ref


@pytest.mark.parametrize('status', ['missing', 'partial'])
def test_exact_selected_subspan_roundtrips_without_first_occurrence_guess(monkeypatch, status):
    run, context, output, ref = subspan_case(status)
    raw = deepcopy(output)
    result = consume(monkeypatch, run, context, output)
    assert result is not None
    row = result['requirement_checks'][0]
    assert row['missing_evidence'] == [ref]
    bound = review.bind_requirement_check(row, context['required_content_targets'][0], run['claims'], run['blocks'])
    assert bound['status'] == status and bound['content_scope_bound']
    assert bool(bound['expression_bindings']) == (status == 'partial')
    assert run['units'][-1]['response']['parsed'] == raw


@pytest.mark.parametrize('fault', ['unknown_ref', 'wrong_quote', 'offset', 'empty_span', 'past_end', 'version', 'duplicate'])
def test_invalid_selected_subspan_is_blocked_and_raw_is_preserved(monkeypatch, fault):
    run, context, output, _ = subspan_case()
    row = output['requirement_checks'][0]
    ref = row['missing_evidence'][0]
    if fault == 'unknown_ref': ref['evidence_ref'] = 'outside'
    elif fault == 'wrong_quote': ref['quote'] = '등심'
    elif fault == 'offset': ref['span'] = [0, 2]
    elif fault == 'empty_span': ref['span'][1] = ref['span'][0]
    elif fault == 'past_end': ref['span'][1] += 50
    elif fault == 'version': ref['source_version_id'] = 'other-version'
    else: row['missing_evidence'].append(deepcopy(ref))
    raw = deepcopy(output)
    assert consume(monkeypatch, run, context, output) is None
    assert run['units'][-1]['status'] == 'failed'
    assert run['units'][-1]['response']['parsed'] == raw


@pytest.mark.parametrize('fault', ['outside_target', 'other_source', 'other_parse'])
def test_valid_address_cannot_escape_target_owner(monkeypatch, fault):
    run, context, output, _ = subspan_case()
    selected = output['requirement_checks'][0]['missing_evidence'][0]
    if fault == 'outside_target':
        selected['span'] = [100, 102]
    else:
        other = deepcopy(run['blocks'][0])
        other['source_version_id'] = 'other-version' if fault == 'other_source' else other['source_version_id']
        if fault == 'other_parse': other['parse_run_id'] = 'other-parse'
        run['blocks'].append(other)
        selected['evidence_ref'] = 'e2'
    result = consume(monkeypatch, run, context, output)
    assert result is not None
    bound = review.bind_requirement_check(result['requirement_checks'][0], context['required_content_targets'][0], run['claims'], run['blocks'])
    assert bound['status'] == 'unknown'
    assert bound['expression_errors'] == ['required_remainder_outside_bound_content_source']


def test_duplicate_restored_address_is_blocked_within_list_capacity(monkeypatch):
    run, context, output, _ = subspan_case()
    run['blocks'].append(dict(run['blocks'][0], id='other', text='다른 원문', span=[0, 5]))
    row = output['requirement_checks'][0]
    row['missing_evidence'].append(deepcopy(row['missing_evidence'][0]))
    assert consume(monkeypatch, run, context, output) is None
    assert run['units'][-1]['error'] == 'schema_error: duplicate_missing_evidence_address'


def test_whole_block_compatibility_and_other_evidence_contract_unchanged(monkeypatch):
    run, _, context, output = case()
    output, _ = wire(run, context, output)
    output['requirement_checks'][0].update(status='missing', claim_ids=[], expression_quotes=[],
        represented_content='', missing_content='상품 속성', missing_evidence=['e1'])
    result = consume(monkeypatch, run, context, output)
    assert result['requirement_checks'][0]['missing_evidence'][0]['quote'] == run['blocks'][0]['text']
    legacy = execution.selected_evidence_type(ExpressionReviewCheck, {'e1':run['blocks'][0]}).model_json_schema()
    row = legacy['$defs'][legacy['properties']['checks']['items']['$ref'].split('/')[-1]]
    assert row['properties']['error_evidence']['items']['const'] == 'e1'


def test_synthesis_uses_the_same_missing_evidence_subspan_contract():
    run, context, output, ref = subspan_case()
    for output_type in (ContributionReviewCheck, ContributionSynthesisCheck):
        selected = execution.selected_evidence_type(output_type, {'e1':run['blocks'][0]})
        row_type = execution.evidence_fields(selected)['checks']
        row = deepcopy(output['checks'][0])
        if output_type is ContributionSynthesisCheck:
            row.update(revision_basis='new_evidence', evidence=[])
        assert row_type.model_validate(row).model_dump()['missing_evidence'][0]['span'] == [ref['start_char'],ref['end_char']]
