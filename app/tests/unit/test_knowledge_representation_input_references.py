"""Local R input references preserve every delivered value and ownership path."""
from copy import deepcopy
import json

import pytest

from app.knowledge import business_run as execution
from app.knowledge.business_models import ContributionReviewCheck
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_business_local_review import local_run


def packet():
    evidence = dict(block_id='body', quote='기관은 조건을 유지한다. ' * 80, source_version_id='v',
        parse_run_id='parser', start_char=0, end_char=960, precision='exact', context_only=False,
        extra=dict(status='unknown', null=None, values=[False, 0, '']))
    return dict(mode='meaning_batch', source=dict(meanings=[dict(key='m', evidence=[deepcopy(evidence)],
        conditions=None, exceptions=[], period='', reason='지우지 않는다')]),
        claims=[dict(id='candidate', raw=dict(Head='literal er1', Tail='er2'),
            interpretation=dict(status='unverified', evidence=[deepcopy(evidence)]))],
        whole_candidate_judgments=[dict(status='unknown', evidence=[deepcopy(evidence)])],
        repair_context=[dict(before=dict(evidence=[deepcopy(evidence)]), after=None)])


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def test_reference_restores_all_fields_types_order_and_owners_without_mutation():
    original = packet(); context = deepcopy(original)
    notice = execution.reference_representation_evidence(context, {'reserved': 'er3'}, {'literal': 'er4'})
    assert notice and len(context['shared_input_evidence']) == 1
    alias = next(iter(context['shared_input_evidence']))
    assert alias not in {'er2', 'er3', 'er4'}
    assert context['claims'][0]['id'] == 'candidate'
    assert context['claims'][0]['raw'] == original['claims'][0]['raw']
    compressed = deepcopy(context)
    restored = execution.restore_representation_evidence(context)
    assert encoded(restored) == encoded(original)
    assert context == compressed


@pytest.mark.parametrize('field,value', [('source_version_id', 'v2'), ('parse_run_id', 'parser2'),
    ('start_char', 1), ('precision', 'chunk'), ('context_only', True), ('context_only', None),
    ('extra', dict(status='unknown', null=None, values=[0, False, '']))])
def test_same_quote_with_different_address_context_or_types_is_not_shared(field, value):
    context = packet(); context['claims'][0]['interpretation']['evidence'][0][field] = value
    original = deepcopy(context)
    execution.reference_representation_evidence(context, {}, {})
    assert context['claims'][0]['interpretation']['evidence'] == original['claims'][0]['interpretation']['evidence']
    assert encoded(execution.restore_representation_evidence(context)) == encoded(original)


def test_marker_collision_falls_back_and_table_collision_never_overwrites():
    context = packet(); context['claims'][0]['raw']['literal'] = {'input_evidence_ref': 'er1'}
    original = deepcopy(context)
    assert execution.reference_representation_evidence(context, {}, {}) == ''
    assert context == original
    context['shared_input_evidence'] = dict(original='preserve')
    original = deepcopy(context)
    with pytest.raises(ValueError, match='representation_input_reference_name_collision'):
        execution.reference_representation_evidence(context, {}, {})
    assert context == original


def test_shared_value_does_not_merge_different_owner_conditions_or_roles():
    context = packet()
    other = deepcopy(context['source']['meanings'][0])
    other.update(key='other', conditions=['다른 조건'], exceptions=['다른 예외'], period='다른 기간')
    context['source']['meanings'].append(other)
    original = deepcopy(context)
    execution.reference_representation_evidence(context, {}, {})
    assert len(context['source']['meanings']) == 2
    assert context['source']['meanings'][1]['conditions'] == ['다른 조건']
    assert encoded(execution.restore_representation_evidence(context)) == encoded(original)


def test_restore_rejects_an_unknown_reference_and_preserves_a_literal_without_table():
    literal = dict(claims=[dict(input_evidence_ref='er1')])
    assert execution.restore_representation_evidence(literal) == literal
    with pytest.raises(ValueError, match='representation_input_reference_missing'):
        execution.restore_representation_evidence(dict(shared_input_evidence={}, **literal))


@pytest.mark.parametrize('mode,stage', [('requirement_join', 'requirement_representation'),
    ('meaning_batch', 'requirement_application'), ('meaning_batch', 'requirement_repair'),
    ('meaning_batch', 'business_qa')])
def test_join_and_other_stages_do_not_use_local_R_references(monkeypatch, mode, stage):
    context = packet(); context['mode'] = mode
    monkeypatch.setattr(execution, 'request_budget', lambda *a, **k: pytest.fail('unexpected count'))
    request = execution.json_request(local_run(), stage, '고정', context, ContributionReviewCheck)
    assert 'shared_input_evidence' not in json.loads(request['messages'][1]['content'])


@pytest.mark.parametrize('verified,gain', [(True, True), (True, False), (False, False)])
def test_product_gate_requires_verified_net_prompt_savings(monkeypatch, verified, gain):
    context = packet(); original = deepcopy(context); counts = []
    def budget(run, messages, schema, output):
        shared = 'shared_input_evidence' in messages[1]['content']
        counts.append(shared)
        return dict(prompt_exact=verified, prompt_tokens=100 if shared and gain else 200)
    monkeypatch.setattr(execution, 'request_budget', budget)
    with monkeypatch.context() as baseline_patch:
        baseline_patch.setattr(execution, 'reference_representation_evidence', lambda *a: '')
        baseline = execution.json_request(local_run(), 'requirement_representation', '고정', context, ContributionReviewCheck)
    request = execution.json_request(local_run(), 'requirement_representation', '고정', context, ContributionReviewCheck)
    assert all(request[k] == baseline[k] for k in ('schema', 'reference_map', 'evidence_reference_map', 'max_tokens'))
    payload = json.loads(request['messages'][1]['content'])
    assert ('shared_input_evidence' in payload) == (verified and gain)
    assert context == original
    assert counts == ([False, True] if verified else [False])
    if verified and gain:
        restored = execution.restore_representation_evidence(payload)
        restored = remap(restored, {v:k for k,v in request['reference_map'].items()})
        assert restored['source'] == original['source'] and restored['claims'] == original['claims']
        assert '참조 자체는' in request['messages'][0]['content']


def test_no_repeat_needs_no_extra_count(monkeypatch):
    monkeypatch.setattr(execution, 'request_budget', lambda *a, **k: pytest.fail('unexpected count'))
    context = dict(mode='meaning_batch', claims=[], source=dict(meanings=[]))
    request = execution.json_request(local_run(), 'requirement_representation', '고정', context, ContributionReviewCheck)
    assert request['messages'][0]['content'].startswith('고정')
    assert 'shared_input_evidence' not in json.loads(request['messages'][1]['content'])
