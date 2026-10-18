"""Small read-only fixtures; no real-model, semantic-quality, or browser evidence."""
from copy import deepcopy
import json

import pytest

from app.knowledge import autoschema, graph_retrieval, workbench
from app.tests.unit.test_knowledge_workbench import service


@pytest.fixture
def concepts(service, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Read projection must not load models or embeddings')
    monkeypatch.setattr(graph_retrieval, 'encoder', forbidden)
    monkeypatch.setattr(graph_retrieval, 'embed', forbidden)
    blocks, chunks, claims = [], [], []
    for number in (1, 2):
        block = dict(id=f'b{number}', source_id=f's{number}', source_version_id=f'v{number}',
            parse_run_id=f'p{number}', text='상품, 품목, 분류', locator=dict(format='md'))
        chunk = autoschema.chunks([block], 49152, 4096)[0]
        blocks.append(block); chunks.append(chunk)
        rows = [dict(Head='상품', Relation='이름', Tail='품목')]
        if number == 1:
            rows.append(dict(Head='상품', Relation='종류', Tail='분류'))
        for index, row in enumerate(rows):
            claim = autoschema.graph_record(chunk, 'entity_relation', row, index)
            claim['review_status'] = 'unreviewed' if number == 1 else 'accepted'
            claims.append(claim)
    graph = autoschema.graph(claims, blocks)
    records = []
    for number in (1, 2):
        own = {c['id'] for c in claims if c['source_version_ids'] == [f'v{number}']}
        target = next(n for n in graph['nodes'] if n['label'] == '상품' and own.intersection(n['claim_ids']))
        records.append(dict(id=f'record{number}', target=deepcopy(target), status='unreviewed',
            concepts=['공유 검색 개념'], request_id=f'request{number}', work_id=f'work{number}'))
    assert len(records[0]['target']['claim_ids']) == 2
    relation = next(t for t in autoschema.concept_targets(graph) if t['kind'] == 'relation' and t['label'] == '이름')
    records.append(dict(id='relation-record', target=relation, status='unreviewed', concepts=['명칭 속성'],
        request_id='relation-request', work_id='relation-work'))
    records.append(dict(deepcopy(records[0]), id='failed-record', status='failed', concepts=['실패 검색 개념']))
    run = dict(id='run1', kind='business', status='partial', input_version_ids=['v1', 'v2'],
        blocks=blocks, chunks=chunks, claims=claims, graph=graph, concepts=records)
    with service.repository.connect() as db:
        source = service.repository.get(db, 'sources', 's1')
        source.update(title='검사 자료 A', source_url='https://example.invalid/a', rights=dict(status='unknown', note='unit fixture'))
        db.execute('UPDATE sources SET payload=? WHERE id=?', (json.dumps(source), 's1'))
        db.execute('INSERT INTO sources VALUES(?,?,?,?)', ('s2', 'test', 's2', json.dumps(dict(id='s2', title='검사 자료 B'))))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)', ('v2', 's2', 'test-hash2', json.dumps(dict(id='v2', source_id='s2'))))
        service.repository.save(db, 'runs', run)
    return service, run


def test_search_concepts_are_distinct_from_records_and_relation_annotations(concepts):
    service, run = concepts
    view = workbench.explore(service, 'run', 'run1', item_kind='search_concept')
    assert view['filtered_count'] == view['counts']['search_concepts'] == 1
    assert view['counts']['concepts'] == 4
    assert view['counts']['nodes'] == len(run['graph']['nodes']) + 1
    assert view['counts']['relations'] == len(run['graph']['edges']) + 2
    node = view['items'][0]
    assert set(node['concept_record_ids']) == {'record1', 'record2'}
    detail = workbench.explore(service, 'run', 'run1', selected_id=node['id'], graph_root=node['id'], depth=3)['detail']
    assert len(detail['relations']) == 2 and len(detail['concept_records']) == 2
    for edge in detail['relations']:
        assert edge['relation'] == 'has_concept' and edge['approved_is_a'] is False
        assert 'claim_id' not in edge
        record = next(r for r in run['concepts'] if r['id'] == edge['concept_record_ids'][0])
        assert edge['claim_ids'] == record['target']['claim_ids']
    _, graph, _, _ = workbench._scope(service, 'run', 'run1')
    assert {n['id'] for n in run['graph']['nodes']} <= {n['id'] for n in graph['nodes']}
    assert not any(n['label'] in {'명칭 속성', '실패 검색 개념'} for n in graph['nodes'])
    assert any(e.get('concepts') == ['명칭 속성'] for e in graph['edges'])


@pytest.mark.parametrize('filters,version,record', [
    (dict(source_id='s1'), 'v1', 'record1'), (dict(review_state='accepted'), 'v2', 'record2')])
def test_shared_concept_list_graph_and_detail_keep_same_source_filter(concepts, filters, version, record):
    service, run = concepts
    node = workbench.explore(service, 'run', 'run1', item_kind='search_concept')['items'][0]
    view = workbench.explore(service, 'run', 'run1', item_kind='search_concept', selected_id=node['id'],
        graph_root=node['id'], depth=3, **filters)
    assert view['filtered_count'] == 1
    own = {c['id'] for c in run['claims'] if c['source_version_ids'] == [version]}
    assert {c['id'] for c in view['detail']['claims']} == own
    assert set(view['detail']['item']['claim_ids']) == own
    assert view['detail']['item']['request_ids'] == [record.replace('record', 'request')]
    assert set(next(i for i in view['graph']['items'] if i['kind'] == 'search_concept')['claim_ids']) == own
    assert [r['id'] for r in view['detail']['concept_records']] == [record]
    assert len(view['detail']['relations']) == 1
    assert {cid for item in view['graph']['items'] if item['kind'] == 'relation' for cid in item['claim_ids']} == own


def test_scope_projection_preserves_db_and_exposes_stored_source_metadata(concepts):
    service, run = concepts
    with service.repository.connect() as db:
        before = db.execute('SELECT payload FROM runs WHERE id=?', ('run1',)).fetchone()[0]
    target = run['concepts'][0]['target']['id']
    view = workbench.explore(service, 'run', 'run1', selected_id=target)
    assert '검사 자료 A' in view['detail']['item']['disambiguation']
    evidence = view['detail']['claims'][0]['evidence'][0]
    assert evidence['source_url'] == 'https://example.invalid/a'
    assert evidence['rights'] == dict(status='unknown', note='unit fixture')
    with service.repository.connect() as db:
        assert db.execute('SELECT payload FROM runs WHERE id=?', ('run1',)).fetchone()[0] == before


def test_snapshot_graph_receives_canonical_blocks(concepts, monkeypatch):
    service, run = concepts
    snapshot = dict(id='selected', kind='source_graph', run_id='run1', source_versions=dict(v1={}, v2={}),
        claims=deepcopy(run['claims']), blocks=deepcopy(run['blocks']), concepts=[])
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)', ('selected', json.dumps(snapshot)))
    original, seen = autoschema.graph, []
    def inspect(claims, blocks=None):
        seen.append(blocks)
        return original(claims, blocks)
    monkeypatch.setattr(autoschema, 'graph', inspect)
    workbench.explore(service, 'source_graph', 'selected')
    assert seen == [run['blocks']]
