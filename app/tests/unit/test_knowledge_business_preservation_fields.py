from copy import deepcopy

import pytest

from app.knowledge import business_review as review, business_run
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning


def actual_change():
    run = local_run()
    before = deepcopy(run['claims'][0])
    before.update(role='event_entity', raw=dict(Event='어린이박물관의 모든 관람객은 방문 전에 꼭 유선 및 서면으로 사전 승인을 받아야 합니다.',
                           Entity=['어린이박물관', '모든 관람객']), conditions=[], references=[])
    after = deepcopy(before)
    after.update(raw=dict(Event='어린이박물관 현장 답사를 희망하시는 분들은 방문 전에 꼭 유선 및 서면으로 사전 승인을 받으시기 바랍니다.',
                          Entity=['어린이박물관', '현장 답사를 희망하시는 분들']),
                 conditions=['어린이박물관 현장 답사를 희망하는 경우'], references=['어린이박물관 누리집'])
    run['claims'][0] = after
    run['blocks'][0]['text'] = after['raw']['Event'] + '\n어린이박물관 누리집 참고'
    if 'span' in run['blocks'][0]:
        run['blocks'][0]['span'] = [0, len(run['blocks'][0]['text'])]
    context = [dict(id='repair', changes=[dict(before=before, after=after, replacements=[])])]
    def row(change, before_field, before_quote, after_field, after_quote, status='supported', same=True):
        return dict(change=change, before_field=before_field, before_quote=before_quote,
                    after_id=after['id'], after_field=after_field, after_quote=after_quote,
                    source_block_ids=[run['blocks'][0]['id']], before_source_status=status,
                    same_normal_meaning=same, reason='원문·실제 전후 의미 대조')
    check = dict(target_id=before['id'], status='preserved', before_normal_meanings=[], after_locations=[], reason='보존과 정정·추가를 구분', comparisons=[
        row('retained', 'raw.Event', '방문 전에 꼭 유선 및 서면으로 사전 승인', 'raw.Event', '방문 전에 꼭 유선 및 서면으로 사전 승인'),
        row('corrected', 'raw.Entity.1', '모든 관람객', 'raw.Entity.1', '현장 답사를 희망하시는 분들', 'unsupported', False),
        row('added', None, None, 'references.0', '어린이박물관 누리집', 'not_present', None)])
    return run, context, check


def test_actual_before_after_views_keep_new_fields_separate_and_do_not_judge_character_changes():
    run, context, _ = actual_change()
    view = review.preservation_views(context)[0]
    assert view['before_fields']['raw.Entity.1'] == '모든 관람객'
    assert 'references.0' not in view['before_fields']
    assert view['after_fields'][run['claims'][0]['id']]['references.0'] == '어린이박물관 누리집'
    assert any(r['field'] == 'references.0' and r['character_changes'][0]['operation'] == 'insert' for r in view['character_changes'])
    assert 'source_status' not in view and 'preserved' not in view


def test_grounded_model_comparison_retains_actual_normal_parts_without_rewriting_raw_judgment():
    run, context, raw = actual_change()
    original = deepcopy(raw)
    check = review.grounded_preservation(raw, context, run['blocks'])
    assert raw == original and check['status'] == 'preserved'
    assert check['before_normal_meanings'] == ['방문 전에 꼭 유선 및 서면으로 사전 승인']
    assert check['after_locations'] == [run['claims'][0]['id']]
    assert [r['change'] for r in check['comparison_bindings']] == ['retained', 'corrected', 'added']
    assert review.preservation_valid(check, run['claims'])


def test_candidate_request_sends_field_text_once_and_keeps_empty_derived_location_constraint():
    run, context, raw = actual_change()
    instruction, packet, schema = review.candidate_request(run, run['claims'], context)
    cid = run['claims'][0]['id']
    assert 'raw' not in packet['claims'][0]
    assert packet['claims'][0]['preservation_view'] == cid
    assert packet['repair_context'] == [dict(id='repair', target_ids=[cid])]
    assert all('before' not in row and 'after' not in row for row in packet['preservation_views'][0]['character_changes'])
    request = business_run.json_request(run, 'candidate_source_review', instruction, packet, schema)
    checks = [d for d in request['schema']['$defs'].values() if 'comparisons' in d.get('properties', {})]
    assert checks and all(d['properties']['after_locations']['maxItems'] == 0 for d in checks)
    schema.model_validate(dict(checks=[], preservation_checks=[raw]))


def test_source_and_preservation_claims_are_not_replaced_by_unchanged_text():
    run, context, raw = actual_change()
    raw['status'] = 'lost'
    raw['comparisons'] = [dict(raw['comparisons'][0], change='lost', after_id=None, after_field=None,
                              after_quote=None, same_normal_meaning=False)]
    check = review.grounded_preservation(raw, context, run['blocks'])
    assert check['status'] == 'lost' and not review.preservation_valid(check, run['claims'])


@pytest.mark.parametrize('state', ['incorrect', 'unknown'])
def test_changed_candidate_field_error_is_validated_against_actual_claim_not_packet_view(monkeypatch, state):
    run, context, raw = actual_change()
    claim = run['claims'][0]
    def answer(service, current, stage, instruction, packet, schema):
        assert 'raw' not in packet['claims'][0]
        ref = dict(block_id=run['blocks'][0]['id'], quote=run['blocks'][0]['text'])
        run['units'].append(dict(id='direct', status='succeeded', error=None))
        return dict(checks=[dict(claim_id=claim['id'], claim_support=state, evidence=[ref],
                                error_fields=['raw.Event'], error_evidence=[ref], reason='실제 Event 필드 대조')],
                    preservation_checks=[raw])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    receipt = review.review_candidates(None, run, [claim], repair_context=context)
    assert not receipt['errors']
    assert receipt['checks'][0]['claim_support'][claim['id']] == state
    assert receipt['checks'][0]['error_fields'][claim['id']] == ['raw.Event']


@pytest.mark.parametrize('fault', ['after_as_before', 'new_reference_as_before', 'foreign_after', 'missing_comparisons', 'unknown_equivalence', 'foreign_source'])
def test_wrong_before_or_unconfirmed_semantics_cannot_supply_a_preservation_receipt(fault):
    run, context, raw = actual_change()
    if fault == 'after_as_before':
        raw['comparisons'][0].update(before_field='raw.Entity.1', before_quote='현장 답사를 희망하시는 분들')
    elif fault == 'new_reference_as_before':
        raw['comparisons'][0].update(before_field='references.0', before_quote='어린이박물관 누리집')
    elif fault == 'foreign_after':
        raw['comparisons'][0]['after_id'] = 'outside'
    elif fault == 'missing_comparisons':
        raw['comparisons'] = []
    elif fault == 'unknown_equivalence':
        raw['comparisons'][0]['same_normal_meaning'] = None
    else:
        raw['comparisons'][0]['source_block_ids'] = ['outside']
    check = review.grounded_preservation(raw, context, run['blocks'])
    assert check['status'] == 'unknown' and not review.preservation_valid(check, run['claims'])


def test_direct_preservation_is_consumed_by_existing_reuse_and_repair_context_without_question_success(monkeypatch):
    run, context, raw = actual_change()
    claim = run['claims'][0]; check = review.grounded_preservation(raw, context, run['blocks'])
    run.update(candidate_reviews=[dict(id='direct', unit_id='unit', preservation_checks=[check])],
               repairs=[dict(context[0], requirement_id=run['requirements'][0]['id'])])
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda r: {claim['id']: dict(receipt_id='direct')})
    m = meaning('kept')
    m['evidence'] = [dict(block_id=run['blocks'][0]['id'], quote=run['blocks'][0]['text'],
                          source_version_id=run['blocks'][0]['source_version_id'])]
    rows = review.valid_preservation_reuses(run, run['requirements'][0], [m])
    assert len(rows) == 1 and rows[0]['check'] == check
    assert rows[0]['scope'] == 'local_preservation_only_not_requirement_independence'
    assert review.repair_context(run, run['requirements'][0], [m]) == []
    assert not review.valid_preservation_reuses(run, run['requirements'][0], [m],
        challenges=[dict(claim_ids=[claim['id']], meaning_key='kept')])
    assert not run['assessments']
