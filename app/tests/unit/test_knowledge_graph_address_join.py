from copy import deepcopy

import pytest

from app.knowledge import business_html_debt_rows, source_segments, graph_retrieval as gr


def address_snapshot(monkeypatch, unlinked):
    def ref(version='v1', parse='missing', start=2, end=7, block='b'):
        row = dict(source_version_id=version, block_id=block, start_char=start,
                   end_char=end, quote='abcdefghij'[start:end])
        if parse != 'missing':
            row['parse_run_id'] = parse
        return row

    blocks = [dict(id='b', source_version_id=version, text='abcdefghij', **parse)
              for version, parse in [('v1', {'parse_run_id': 'p2'}),
                  ('v1', {'parse_run_id': 'p1'}), ('v1', {'parse_run_id': None}),
                  ('v1', {}), ('v2', {'parse_run_id': 'p1'})]]
    blocks.append(dict(blocks[1], id='other'))
    claims = [dict(id=cid, evidence=refs) for cid, refs in [
        ('wild', [ref(), ref()]), ('duplicate', [ref(block='other', start=0, end=4)]),
        ('none', [ref(parse=None, start=4, end=8)]),
        ('adjacent', [ref(parse='p1', start=8, end=10)]),
        ('version', [ref(version='v2', parse='p1', start=0, end=4)]),
        ('duplicate', [ref(version='v2', parse='p1', start=4, end=8)]),
        ('missing-address', [ref(block='absent')])]]
    nodes = [dict(id='head', kind='entity', label='기관',
                  claim_ids=['adjacent', 'none', 'wild', 'duplicate', 'version', 'wild']),
             dict(id='event', kind='event', label='접수', claim_ids=['wild']),
             dict(id='classification', kind='entity', label='분류', claim_ids=['wild', 'none'],
                  construction_method='verified_html_classification_row_v1',
                  evidence=[ref(start=4, end=8)]),
             dict(id='debt', kind='entity', label='비율', claim_ids=['wild'],
                  construction_method=business_html_debt_rows.PROFILE,
                  evidence=[ref(parse='p1', start=0, end=4)])]
    edges = [dict(id=eid, head='head', tail='event', relation=label, claim_id='wild')
             for eid, label in [('r1', '허용'), ('r2', '금지')]]
    monkeypatch.setattr(gr.autoschema, 'graph', lambda rows:
        deepcopy(dict(nodes=nodes, edges=edges) if rows else dict(nodes=[], edges=[])))
    monkeypatch.setattr(source_segments, 'split', lambda block: [
        dict(span=[0, 4], shared_spans=[[4, 8], [0, 4]]), dict(span=[8, 10], shared_spans=[])])
    concepts = [dict(target=dict(nodes[0]), concepts=['검색용', '검색용'], status='unreviewed'),
                dict(target=dict(kind='relation', label='허용', claim_ids=['wild']),
                     concepts=['권한'], status='accepted')]
    concepts.extend(dict(target=dict(id=tid, kind='entity', claim_ids=['wild']),
                         concepts=['누락'], status='unreviewed') for tid in ['gone2', 'gone1'])
    return dict(blocks=blocks, claims=claims, concepts=concepts, include_unlinked_blocks=unlinked)


@pytest.mark.parametrize('unlinked', [False, True])
@pytest.mark.parametrize('variant', ['entity', 'entity_event', 'full'])
def test_address_join_preserves_parse_span_claim_and_edge_order(monkeypatch, unlinked, variant):
    snapshot = address_snapshot(monkeypatch, unlinked)
    original = deepcopy(snapshot)
    graph, edges, passages, ignored = gr.build(snapshot, variant)
    assert snapshot == original
    assert ignored == (['gone2', 'gone1'] if variant == 'full' else [])
    assert [pid for pid in graph.successors('head') if pid in passages] == [
        pid for pid, row in passages.items() if set(row['claim_ids']) & set(graph.nodes['head']['claim_ids'])]
    if variant != 'entity':
        assert list(graph['head']['event']) == ['r1', 'r2']
        assert [edge['id'] for edge in edges[:2]] == ['r1', 'r2']
        if variant == 'full':
            assert graph.edges['head', 'event', 'r1']['concepts'] == ['권한']
    def locations(cid):
        return [(row['evidence']['source_version_id'], row['evidence'].get('parse_run_id'),
                 row['evidence']['block_id'], row['evidence']['start_char'], row['evidence']['end_char'])
                for row in passages.values() if cid in row['claim_ids']]
    if unlinked:
        assert len(passages) == 15  # Missing/None duplicate block overwrites its existing passage IDs.
        assert locations('wild') == [('v1', parse, 'b', start, end)
            for parse in ['p2', 'p1', None] for start, end in [(0, 4), (4, 8)]]
        assert locations('none') == [('v1', None, 'b', 4, 8)]
        assert locations('adjacent') == [('v1', 'p1', 'b', 8, 10)]
        assert locations('duplicate') == [('v2', 'p1', 'b', 4, 8)]
        assert locations('missing-address') == []
        assert [passages[pid]['evidence'] for pid in graph.successors('classification')] == [
            next(row['evidence'] for row in passages.values() if row['claim_ids'] == ['wild', 'none'])]
        assert [passages[pid]['evidence']['start_char'] for pid in graph.successors('debt')] == [0]
        assert all(passages[pid]['evidence']['parse_run_id'] == 'p1' for pid in graph.successors('debt'))
    else:
        assert len(passages) == 6
        assert locations('wild') == [('v1', None, 'b', 2, 7)]
        assert locations('missing-address') == [('v1', None, 'absent', 2, 7)]
        assert len(list(graph.successors('classification'))) == 2
        assert not list(graph.successors('debt'))
    assert all(len(row['claim_ids']) == len(set(row['claim_ids'])) for row in passages.values())


def test_build_has_no_address_state_between_changed_or_empty_snapshots(monkeypatch):
    snapshot = address_snapshot(monkeypatch, True)
    before = gr.build(snapshot, 'full')
    changed = deepcopy(snapshot)
    for block in changed['blocks']:
        block['source_version_id'] = 'new-version'
    graph, _, passages, _ = gr.build(changed, 'full')
    assert all(not row['claim_ids'] for row in passages.values())
    assert all(data['relation'] != 'mention in' for *_, data in graph.edges(data=True))
    empty = gr.build(dict(claims=[], blocks=[], concepts=[], include_unlinked_blocks=True), 'full')
    assert not empty[0] and empty[1:] == ([], {}, [])
    restored = gr.build(snapshot, 'full')
    assert list(restored[0].edges(keys=True, data=True)) == list(before[0].edges(keys=True, data=True))
    assert restored[1:] == before[1:]


def test_legacy_missing_and_none_parse_keep_first_evidence_and_claim_order(monkeypatch):
    snapshot = address_snapshot(monkeypatch, False)
    first = deepcopy(snapshot['claims'][0]['evidence'][0])
    snapshot['claims'] = [dict(id='first', evidence=[first]),
                          dict(id='second', evidence=[dict(first, parse_run_id=None)])]
    _, _, passages, _ = gr.build(snapshot, 'entity')
    assert len(passages) == 1
    assert list(passages.values())[0]['evidence'] == first
    assert 'parse_run_id' not in list(passages.values())[0]['evidence']
    assert list(passages.values())[0]['claim_ids'] == ['first', 'second']


@pytest.mark.parametrize('unlinked,missing', [(True, 'end_char'), (False, 'quote')])
def test_build_still_rejects_incomplete_matching_evidence(monkeypatch, unlinked, missing):
    snapshot = address_snapshot(monkeypatch, unlinked)
    del snapshot['claims'][0]['evidence'][0][missing]
    with pytest.raises(KeyError, match=missing):
        gr.build(snapshot, 'full')
