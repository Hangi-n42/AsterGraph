"""Repair input references preserve data, roles and candidate ownership exactly."""
from copy import deepcopy
import json

import pytest

from app.knowledge import business_run
from app.knowledge.business_models import Repairs
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_business_local_review import local_run


FIELDS = ('conditions', 'exceptions', 'time', 'local_negation', 'references', 'premises')


def repair_input(same_id=False):
    run = local_run()
    candidates = []
    for index, claim in enumerate(run['claims']):
        key = 'interpretation_' + ('a' if same_id else str(index)) * 24
        candidates.append(dict(id=claim['id'], role=claim['role'], semantic_status='unknown',
            interpretation=dict(contract='unverified-local-extraction-scope-v3', semantic_status='unverified',
                errors=['원래 오류'], meanings=[dict(id=key, subject=f'주체{index}',
                    conditions=dict(state='absent', text=None), exceptions=dict(state='unresolved', text=None),
                    time=dict(state='present', text=f'기간 {index}'),
                    premises=dict(state='absent', meaning_indices=[]),
                    evidence=[dict(block_id='body', quote=f'원문 {index}')],
                    participants=[dict(value=f'주체{index}', meaning_refs=[key])], premise_ids=[])])))
    context = dict(reuse_candidates=candidates, before=[], source=dict(status='unknown', quote='원문 그대로'))
    return run, context


def restored_payload(request):
    payload = json.loads(request['messages'][1]['content'])
    shared = payload.pop('shared_interpretation_fields', {})
    for claim in payload['reuse_candidates']:
        for meaning in claim['interpretation']['meanings']:
            for field in FIELDS:
                if isinstance(meaning.get(field), str) and meaning[field] in shared:
                    meaning[field] = deepcopy(shared[meaning[field]])
    return remap(payload, {alias: original for original, alias in (request['reference_map'] or {}).items()})


@pytest.mark.parametrize('same_id', [False, True])
def test_repair_references_restore_every_value_without_merging_claims(same_id):
    run, context = repair_input(same_id)
    original = deepcopy(context)
    request = business_run.json_request(run, 'requirement_repair', '고정 지시', context, Repairs)
    payload = json.loads(request['messages'][1]['content'])
    assert 'shared_interpretation_fields' in payload
    assert json.dumps(restored_payload(request), ensure_ascii=False, sort_keys=True) == json.dumps(original, ensure_ascii=False, sort_keys=True)
    assert context == original and len(payload['reuse_candidates']) == 2
    assert payload['reuse_candidates'][0]['id'] != payload['reuse_candidates'][1]['id']
    assert all(c['semantic_status'] == 'unknown' and c['interpretation']['semantic_status'] == 'unverified'
               for c in payload['reuse_candidates'])
    assert request['messages'][1]['content'] == json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    expected_ids = {m['id'] for c in original['reuse_candidates'] for m in c['interpretation']['meanings']}
    assert expected_ids <= request['reference_map'].keys()
    assert len({request['reference_map'][key] for key in expected_ids}) == len(expected_ids)
    assert request['schema'] == Repairs.model_json_schema()


@pytest.mark.parametrize('collision', ['literal_id', 'short_id', 'shared_id', 'existing_map', 'existing_shared_key'])
def test_repair_aliases_do_not_change_literal_text_or_reuse_existing_names(collision):
    run, context = repair_input()
    key = context['reuse_candidates'][0]['interpretation']['meanings'][0]['id']
    mapping = {}
    if collision == 'literal_id': context['source']['quote'] = key
    if collision == 'short_id': context['source']['quote'] = 'i1'
    if collision == 'shared_id': context['source']['quote'] = 'sf1'
    if collision == 'existing_map': mapping['already-reserved'] = 'i1'
    if collision == 'existing_shared_key': mapping['sf1'] = 'b9'
    request = business_run.json_request(run, 'requirement_repair', '고정 지시', context, Repairs, reference_map=mapping)
    payload = json.loads(request['messages'][1]['content'])
    assert restored_payload(request) == context
    assert payload['source']['quote'] == context['source']['quote']
    if collision == 'literal_id': assert key not in request['reference_map']
    if collision in {'short_id', 'existing_map'}: assert request['reference_map'][key] != 'i1'
    if collision == 'shared_id': assert 'sf1' not in payload['shared_interpretation_fields']
    if collision == 'existing_shared_key': assert 'sf1' not in payload['shared_interpretation_fields']


@pytest.mark.parametrize('stage', ['business_qa', 'source_literal_participants'])
def test_other_stages_keep_the_original_interpretation_and_serialization(stage):
    run, context = repair_input()
    request = business_run.json_request(run, stage, '고정 지시', context, Repairs)
    payload = json.loads(request['messages'][1]['content'])
    assert 'shared_interpretation_fields' not in payload
    assert request['messages'][0]['content'] == '고정 지시'
    assert request['messages'][1]['content'] == business_run.encode(payload)
    assert restored_payload(request) == context


@pytest.mark.parametrize('field,value', [
    ('conditions', dict(state='absent')),
    ('exceptions', dict(state='unknown', text=None)),
    ('premises', dict(state='absent', meaning_indices=None)),
])
def test_missing_null_unknown_and_empty_arrays_are_not_interchangeable(field, value):
    run, context = repair_input()
    context['reuse_candidates'][0]['interpretation']['meanings'][0][field] = value
    request = business_run.json_request(run, 'requirement_repair', '고정 지시', context, Repairs)
    restored = restored_payload(request)
    assert json.dumps(restored, ensure_ascii=False, sort_keys=True) == json.dumps(context, ensure_ascii=False, sort_keys=True)
    assert restored['reuse_candidates'][0]['interpretation']['meanings'][0][field] == value


def test_an_existing_shared_table_name_is_rejected_without_overwriting_input():
    run, context = repair_input()
    context['shared_interpretation_fields'] = dict(original='보존')
    before = deepcopy(context)
    with pytest.raises(ValueError, match='repair_input_reference_name_collision'):
        business_run.json_request(run, 'requirement_repair', '고정 지시', context, Repairs)
    assert context == before
