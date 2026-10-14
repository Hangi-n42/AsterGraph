"""Address projection checks; these fixtures are not semantic evaluation results."""
from copy import deepcopy
import pytest
from app.knowledge import autoschema
from app.tests.unit.test_knowledge_business_scope import block, scope_for


def claim(text, label, *, base=10, version='v', index=0):
    source = dict(block('body', text), span=[base, base + len(text)], source_version_id=version)
    chunk = dict(id=f'chunk:{version}:{base}', source_version_id=version, blocks=[source],
                 source_reference_map={'b1': dict(block_id='body', span=source['span'])})
    scope = scope_for(chunk, text, head=label)
    scope['meanings'][0]['participants'][0]['evidence'] = deepcopy(scope['evidence'])
    return autoschema.graph_record(chunk, 'entity_relation', dict(Head=label, Relation='접수', Tail='신청'), index, scope=scope)


def test_display_projection_keeps_original_offsets_quotes_and_raw_scope():
    text = '서두 기관\n  담당은 신청을 접수한다.'
    c = claim(text, '기관 담당')
    mention = c['interpretation']['mentions'][0]
    ref = mention['evidence'][0]
    assert mention['address_status'] == 'resolved' and mention['address_projection'] == 'whitespace_display_only'
    assert ref['start_char'] == 10 + text.index('기관')
    assert ref['quote'] == '기관\n  담당'
    assert text[ref['start_char'] - 10:ref['end_char'] - 10] == ref['quote']
    assert c['raw']['Head'] == c['interpretation']['raw']['meanings'][0]['subject'] == '기관 담당'
    assert c['interpretation']['semantic_status'] == 'unverified'


def test_display_and_literal_same_mention_share_node_without_losing_parallel_edges():
    text = '기관\n담당은 신청을 접수한다.'
    a, b = claim(text, '기관담당'), claim(text, '기관\n담당', index=1)
    graph = autoschema.graph([a, b])
    assert len(graph['nodes']) == 2 and len(graph['edges']) == 2
    assert set(next(n for n in graph['nodes'] if len(n['labels']) == 2)['labels']) == {'기관담당', '기관\n담당'}
    assert graph['interpretations'][a['id']]['raw'] == a['interpretation']['raw']


@pytest.mark.parametrize('text,label', [('기관\n담당과 기관 담당은 신청을 받는다.', '기관담당'),
    ('a b a b a 신청', 'aba'), ('1년 신청', '2년'), ('1,000 신청', '1000'), ('접수 가능 신청', '접수 불가')])
def test_ambiguous_numeric_punctuation_and_condition_changes_remain_unresolved(text, label):
    c = claim(text, label)
    assert c['interpretation']['mentions'][0]['address_status'] == 'unresolved'
    assert 'address_projection' not in c['interpretation']['mentions'][0]


def test_wrong_source_quote_and_invalid_selector_are_not_repaired():
    text = '기관\n담당은 신청을 받는다.'
    chunk = autoschema.chunks([block('body', text)], 49152, 4096)[0]
    scope = scope_for(chunk, text, head='기관담당')
    raw = dict(Head='기관담당', Relation='접수', Tail='신청')
    for selector in [False, True]:
        candidate = deepcopy(scope)
        participant = candidate['meanings'][0]['participants'][0]
        participant['evidence'] = [dict(block_id='b1', quote='기관담당')]
        if selector:
            participant['evidence'] = candidate['evidence']
            participant['entity_index'] = 0
        r = autoschema.scope_record(candidate, chunk, raw, 'entity_relation')
        assert r['mentions'][0]['address_status'] == 'unresolved'
        assert 'address_restorations' not in r


@pytest.mark.parametrize('base,version', [(30, 'v'), (10, 'different-version')])
def test_same_display_name_different_source_location_or_version_does_not_merge(base, version):
    text = '기관\n담당은 신청을 받는다.'
    graph = autoschema.graph([claim(text, '기관담당'), claim(text, '기관담당', base=base, version=version)])
    assert len(graph['nodes']) == 4 and len(graph['edges']) == 2
