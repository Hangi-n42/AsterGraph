"""Literal boundary/coverage fixtures, not recipe meaning or model-quality tests."""
from copy import deepcopy

import pytest

from app.knowledge import source_list_comparison as lists


def field(text, source='v'):
    block = dict(id='b'+source, source_version_id=source, parse_run_id='p', text='앞말: '+text+' 끝말')
    ref = dict(source_version_id=source, parse_run_id='p', block_id=block['id'],
               start_char=4, end_char=4+len(text), quote=text)
    return ref, [block]


def parse(text, source='v'):
    return lists.parse_field(*field(text, source))


def test_lossless_parts_and_absolute_addresses_preserve_names_amounts_and_parentheses():
    text = '재료소개 재료량(5인분) 재료(유형, 하위) 20g(1/4개), 비타민B12 3mg , 원료 약간'
    ref, blocks = field(text); before = deepcopy((ref, blocks))
    result = lists.parse_field(ref, blocks)
    assert result['status'] == 'ready' and result['roundtrip_exact']
    assert ''.join(p['evidence']['quote'] for p in result['parts']) == text
    assert [r['name']['quote'] for r in result['items']] == ['재료(유형, 하위)', '비타민B12', '원료']
    assert [r['quantity']['quote'] for r in result['items']] == ['20g(1/4개)', '3mg', '약간']
    cursor = ref['start_char']
    for part in result['parts']:
        e = part['evidence']; assert e['start_char'] == cursor; cursor = e['end_char']
    assert cursor == ref['end_char']
    for item in result['items']:
        for e in item.values():
            assert blocks[0]['text'][e['start_char']:e['end_char']] == e['quote']
    assert result['condition_state'] == result['exception_state'] == 'unreviewed'
    assert (ref, blocks) == before


@pytest.mark.parametrize('text', ['재료 3g 추가 2g', '재료', '재료 20oz', ' 3g',
    '재료 3g,, 원료 2g', '재료(형 3g', '재료] 3g', '"재료" 3g', '재료 3g 추가',
    '재료 약간 3g', '재료 3g,'])
def test_ambiguous_syntax_stays_unresolved_and_blocks_comparison(text):
    result = parse(text)
    assert result['status'] == 'unresolved' and result['issues']
    assert ''.join(p['evidence']['quote'] for p in result['parts']) == text
    comparison = lists.compare_lists(result, parse('원료 2g', 'other'))
    assert comparison['status'] == 'unresolved' and comparison['common'] is None


def test_exact_name_comparison_keeps_all_duplicates_one_sided_items_and_source_addresses():
    left = parse('공통 1g, 재료 A 2g, Oil 3g, 공통 4g')
    right = parse('재료A 5g, 공통 6g, oil 7g', 'other')
    before = deepcopy((left, right))
    result = lists.compare_lists(left, right)
    assert result['status'] == 'ready' and [r['name'] for r in result['common']] == ['공통']
    row = result['common'][0]
    assert [len(items) for items in row['occurrences']] == [2, 1]
    assert row['occurrences'][0][0]['name']['source_version_id'] == 'v'
    assert row['occurrences'][1][0]['name']['source_version_id'] == 'other'
    assert [[r['name'] for r in rows] for rows in result['only']] == [['재료 A', 'Oil'], ['재료A', 'oil']]
    assert result['condition_state'] == result['exception_state'] == 'unreviewed'
    assert result['relation'] == 'literal_name_in_both_lists_not_necessity'
    assert (left, right) == before


@pytest.mark.parametrize('fault', ['quote', 'span', 'version', 'parse'])
def test_wrong_source_address_is_rejected_before_parsing(fault):
    ref, blocks = field('재료 3g')
    if fault == 'quote': ref['quote'] = '다른 3g'
    elif fault == 'span': ref['start_char'] += 1
    elif fault == 'version': ref['source_version_id'] = 'unprovided'
    else: ref['parse_run_id'] = 'unprovided'
    with pytest.raises(ValueError): lists.parse_field(ref, blocks)
