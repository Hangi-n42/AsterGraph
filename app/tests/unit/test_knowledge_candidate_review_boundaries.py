"""Review input/field addressing only; no model semantic judgments from fixtures."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_review, business_run
from app.knowledge.business_models import BusinessRunRequest
from app.tests.unit.test_knowledge_business import finish
from app.tests.unit.test_knowledge_business_local_review import local_run
from app.tests.unit.test_knowledge_business_rebuild_natural import natural


@pytest.fixture
def review_input(natural):
    service, register, _, _, _, options, _, _ = natural
    version = register('<h2>공통 상위 조건</h2><section id="one"><p>기관은 신청을 처리한다.</p>'
        '<p>단, 별도 절차가 적용된다.</p></section><section id="two"><p>관청은 허가를 처리한다.</p></section>'
        '<p>상세 기준은 별도 안내를 참조한다.</p>')
    current = finish(service, service.start_business(BusinessRunRequest(
        source_version_ids=[version], conceptualize=False, **options))['run_id'])
    assert current['status'] == 'succeeded', current.get('error')
    assert current['recipe']['scope_contract'] == autoschema.SCOPE_CONTRACT
    claim = next(c for c in current['claims'] if c['role'] == 'entity_relation' and c['raw']['Head'] == '기관')
    return current, claim


def test_review_preserves_actual_stored_support_context_and_legacy_request(review_input):
    current, claim = review_input
    original = deepcopy([current, claim])
    instruction, context, schema = business_review.candidate_request(current, [claim])
    assert context['blocks'] == current['chunks'][0]['blocks']
    legacy = deepcopy(current);legacy['recipe']['options']['source_unit_policy'] = 'whole'
    old_instruction, old_context, old_schema = business_review.candidate_request(legacy, [claim])
    basis = [dict(evidence=[dict(block_id=b['id']) for b in business_review.candidate_source_basis(claim, legacy['blocks'])])]
    expected = business_review.related_blocks(legacy, basis,
        chunks=autoschema.chunks(legacy['blocks'], 49152, 4096, 1))
    assert old_context['blocks'] == expected
    assert old_context['claims'] == context['claims'] and instruction == old_instruction and schema is old_schema
    reference = next(b['id'] for b in current['blocks'] if b['text'].startswith('상세 기준'))
    assert reference not in {b['id'] for b in expected}
    assert reference in {b['id'] for b in context['blocks']}
    assert [current, claim] == original


@pytest.mark.parametrize('field,value', [('text', '바뀐 문구'), ('locator', dict(other=True)),
                                        ('parse_run_id', '다른 파싱'), ('span', [1, 2])])
def test_review_rejects_changed_stored_source_view(review_input, field, value):
    current, claim = review_input
    current['chunks'][0]['blocks'][-1][field] = value
    with pytest.raises(ValueError, match='보존 문맥'):
        business_review.candidate_request(current, [claim])


@pytest.mark.parametrize('field,valid', [
    ('interpretation.meanings', True), ('interpretation.meanings.0.modality', True),
    ('raw.Entity.1', True), ('raw.Event', True),
    ('interpretation.meanings.-1.modality', False), ('interpretation.meanings.1.modality', False),
    ('interpretation.meanings.00.modality', False), ('interpretation.meanings.x.modality', False),
    ('interpretation.meanings.0.missing', False), ('raw.Entity.2', False), ('raw.Event.0', False),
])
def test_both_review_connections_validate_real_field_paths(monkeypatch, field, valid):
    current = local_run();claim = current['claims'][0]
    claim['raw'] = dict(Event='검사', Entity=['갑', '을'])
    claim['interpretation'] = dict(meanings=[dict(modality='obligation')])
    original = deepcopy(claim)
    def answer(service, run, stage, instruction, context, schema):
        run['units'].append(dict(id='review', status='succeeded', error=None))
        return dict(checks=[dict(claim_id=claim['id'], claim_support='incorrect', evidence=claim['evidence'],
            error_fields=[field], error_evidence=claim['evidence'], reason='fixture field address')], preservation_checks=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *args: None)
    receipt = business_review.review_candidates(None, current, [claim])
    assert bool(receipt['checks']) is valid
    assert bool(receipt['errors']) is not valid
    if valid:
        assert receipt['checks'][0]['error_fields'][claim['id']] == [field]
    output = dict(checks=[], candidate_challenges=[dict(claim_ids=[claim['id']], fields=[field],
        evidence=claim['evidence'], reason='fixture field address')])
    business_review.attach_candidate_support(current, output, [claim], current['blocks'])
    assert bool(current.get('candidate_challenges')) is valid
    assert bool(output.get('candidate_challenge_errors')) is not valid
    assert claim == original


@pytest.mark.parametrize('fault', [None, 'foreign_version', 'sibling', 'unprovided', 'outside_span', 'wrong_unit', 'legacy'])
def test_error_ownership_uses_only_delivered_same_unit_view(review_input, fault):
    current, claim = review_input
    blocks = deepcopy(current['chunks'][0]['blocks'])
    ref = business_run.exact_evidence([dict(block_id=blocks[-1]['id'], quote=blocks[-1]['text'])], blocks)[0]
    if fault == 'foreign_version': ref['source_version_id'] = 'foreign'
    elif fault == 'sibling':
        sibling = next(b for b in current['blocks'] if b['text'].startswith('관청'))
        blocks.append(sibling)
        ref = business_run.exact_evidence([dict(block_id=sibling['id'], quote=sibling['text'])], blocks)[0]
    elif fault == 'unprovided': blocks.pop()
    elif fault == 'outside_span': ref['end_char'] += 1
    elif fault == 'wrong_unit': current['source_structure']['chunk_units'][claim['chunk_id']] = 'other'
    elif fault == 'legacy': current['recipe']['options']['source_unit_policy'] = 'whole'
    assert business_review.candidate_error_evidence(current, claim, [ref], blocks) == ([ref] if fault is None else [])


@pytest.mark.parametrize('state', ['incorrect', 'unknown', 'supported'])
def test_three_error_connections_accept_support_view_without_promoting_supported_claim(review_input, monkeypatch, state):
    current, claim = review_input;current.update(units=[], repairs=[], claims=[claim])
    original = deepcopy(claim)
    ref = business_run.exact_evidence([dict(block_id=current['blocks'][-1]['id'], quote=current['blocks'][-1]['text'])], current['blocks'])[0]
    def answer(service, run, stage, instruction, context, schema):
        run['units'].append(dict(id='review', status='succeeded', error=None))
        return dict(checks=[dict(claim_id=claim['id'], claim_support=state, evidence=[ref],
            error_fields=[] if state == 'supported' else ['interpretation.meanings.0.references'],
            error_evidence=[] if state == 'supported' else [ref], reason='fixture support context')], preservation_checks=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *args: None)
    receipt = business_review.review_candidates(None, current, [claim])
    assert bool(receipt['checks']) is (state != 'supported')
    if state != 'supported':
        assert receipt['checks'][0]['claim_support'][claim['id']] == state
        if state == 'incorrect': assert receipt['checks'][0]['error_attributions'][0]['status'] == 'accepted'
    else:
        assert receipt['errors'][0]['reason'] == 'candidate_support_without_own_source'
    output = dict(checks=[], candidate_challenges=[dict(claim_ids=[claim['id']],
        fields=['interpretation.meanings.0.references'], evidence=[ref], reason='fixture support context')])
    business_review.attach_candidate_support(current, output, [claim], current['blocks'])
    assert not output.get('candidate_challenge_errors') and current['candidate_challenges']
    assert claim == original
