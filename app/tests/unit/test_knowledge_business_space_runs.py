"""Space count restoration stays inside unique, explicitly provided source views."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema
from app.tests.unit.test_knowledge_business_scope import block, scope_for


def test_exact_quote_has_priority_over_another_space_count_match():
    chunk = autoschema.chunks([block('body', '안된 화학제품 / 안된  화학제품')], 49152, 4096)[0]
    refs, errors = autoschema.source_quotes([dict(block_id='b1', quote='안된 화학제품')], chunk)
    assert not errors and len(refs) == 1
    assert refs[0]['start_char'] == 0 and refs[0]['quote'] == '안된 화학제품'
    assert 'matching_method' not in refs[0]


def test_space_count_restores_exact_quote_and_mention_without_changing_raw_meaning():
    text = '기관 — 그 외 기타 분류 안된  화학제품 제조업'
    label = '그 외 기타 분류 안된 화학제품 제조업'
    chunk = autoschema.chunks([block('body', text)], 49152, 4096)[0]
    scope = scope_for(chunk, text.replace('안된  ', '안된 '), tail=label)
    scope['meanings'][0]['participants'][1]['evidence'] = [dict(block_id='b1', quote=label)]
    original = deepcopy(scope)
    claim = autoschema.graph_record(chunk, 'entity_relation', dict(Head='기관', Relation='포함', Tail=label), 0, scope=scope)
    record = claim['interpretation']
    assert record['raw'] == original == scope and claim['raw']['Tail'] == label
    assert not record['errors'] and record['semantic_status'] == 'unverified'
    assert record['evidence'][0]['quote'] == text
    assert record['evidence'][0]['matching_method'] == 'space_run_length_only'
    tail = next(m for m in record['mentions'] if m['field'] == 'Tail')
    assert tail['address_status'] == 'resolved' and tail['address_projection'] == 'space_run_length_only'
    ref = tail['evidence'][0]
    assert text[ref['start_char']:ref['end_char']] == ref['quote'] == label.replace('안된 ', '안된  ')
    assert {k: record['meanings'][0][k] for k in original['meanings'][0] if k not in {'evidence', 'participants'}} == {
        k: v for k, v in original['meanings'][0].items() if k not in {'evidence', 'participants'}}


@pytest.mark.parametrize('text,quote', [
    ('안된화학제품', '안된 화학제품'),
    ('안된 화학제품', '안된화학제품'),
    ('안된  화학제품 / 안된  화학제품', '안된 화학제품'),
    ('안된\t화학제품', '안된 화학제품'),
    ('안된  다른제품', '안된 화학제품'),
])
def test_new_quote_fallback_keeps_boundaries_characters_and_ambiguity(text, quote):
    chunk = autoschema.chunks([block('body', text)], 49152, 4096)[0]
    refs, errors = autoschema.source_quotes([dict(block_id='b1', quote=quote)], chunk)
    assert not refs and errors


def test_space_count_does_not_search_outside_addressed_view():
    chunk = dict(blocks=[dict(block('body', '안내'), span=[0, 2]), block('outside', '안된  화학제품')],
                 source_reference_map={'b1': dict(block_id='body', span=[0, 2])})
    refs, errors = autoschema.source_quotes([dict(block_id='b1', quote='안된 화학제품')], chunk)
    assert not refs and errors


def test_newly_restored_quote_does_not_remove_a_mention_space_boundary():
    text = '기관 — 그 외 기타 분류 안된  화학제품 제조업'
    quote = '그 외 기타 분류 안된 화학제품 제조업'
    chunk = autoschema.chunks([block('body', text)], 49152, 4096)[0]
    scope = scope_for(chunk, text.replace('안된  ', '안된 '), tail=quote)
    scope['meanings'][0]['participants'][1]['evidence'] = [dict(block_id='b1', quote=quote)]
    record = autoschema.scope_record(scope, chunk, dict(Head='기관', Tail=quote.replace('그 외', '그외')), 'entity_relation')
    assert record['evidence'] and record['errors']
    tail = next(m for m in record['mentions'] if m['field'] == 'Tail')
    assert tail['address_status'] == 'unresolved'


def test_parent_span_disambiguates_only_inside_the_provided_view():
    text = '안된  화학제품 / 안된  화학제품'
    chunk = dict(blocks=[dict(block('body', text), span=[20, 20 + len(text)])],
                 source_reference_map={'b1': dict(block_id='body', span=[20, 20 + len(text)])})
    start = text.rindex('안된')
    parent = dict(block_id='body', source_version_id='v', start_char=20 + start, end_char=20 + len(text))
    refs, errors = autoschema.source_quotes([dict(block_id='b1', quote='안된 화학제품')], chunk, within=[parent])
    assert not errors and len(refs) == 1
    assert refs[0]['start_char'] == 20 + start and refs[0]['end_char'] == 20 + len(text)
    assert refs[0]['quote'] == text[start:]


@pytest.mark.parametrize('head,projection', [('신청기관', 'whitespace_display_only'), ('기관', None)])
def test_mixed_refs_keep_the_selected_exact_ref_path_and_projection(head, projection):
    text = '신청 기관은 분류목록을 작성한다.'
    chunk = autoschema.chunks([block('body', text), block('other', '안된  화학제품')], 49152, 4096)[0]
    scope = scope_for(chunk, text, head=head, tail='분류목록')
    scope['meanings'][0]['participants'][0]['evidence'] = [dict(block_id='b1', quote='신청 기관')]
    baseline = autoschema.scope_record(scope, chunk, dict(Head=head, Tail='분류목록'), 'entity_relation')
    scope['meanings'][0]['participants'][0]['evidence'].append(dict(block_id='b2', quote='안된 화학제품'))
    mixed = autoschema.scope_record(scope, chunk, dict(Head=head, Tail='분류목록'), 'entity_relation')
    before = next(m for m in baseline['mentions'] if m['field'] == 'Head')
    after = next(m for m in mixed['mentions'] if m['field'] == 'Head')
    assert not mixed['errors'] and after == before
    assert after['address_status'] == 'resolved' and after.get('address_projection') == projection
    assert after['evidence'][0]['block_id'] == 'body' and 'matching_method' not in after['evidence'][0]
