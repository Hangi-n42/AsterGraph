"""Contract fixtures only; these are not semantic or real-model quality evidence."""
import json

import pytest

from app.knowledge.service import KnowledgeService
from app.knowledge import workbench


@pytest.fixture
def service(tmp_path, monkeypatch):
    value = KnowledgeService(tmp_path / 'knowledge.db')
    def no_execution(*args, **kwargs):
        pytest.fail('Browsing must not schedule inference or other background work')
    monkeypatch.setattr(value.executor, 'submit', no_execution)
    claims = [dict(id=f'c{i}', source_version_ids=['v1'], review_status='unreviewed', evidence=[],
                   role='event_entity', statement=f'조건 {i}') for i in range(3)]
    nodes = [dict(id=n, label='같은 이름', kind='entity', claim_ids=['c0']) for n in ['n1', 'n2', 'n3']]
    graph = dict(nodes=nodes, edges=[
        dict(id='e1', head='n1', tail='n2', relation='r', claim_id='c0'),
        dict(id='e2', head='n1', tail='n2', relation='r', claim_id='c1'),
        dict(id='e3', head='n3', tail='n1', relation='other', claim_id='c2')])
    with value.repository.connect() as db:
        db.execute('INSERT INTO sources VALUES(?,?,?,?)', ('s1', 'test', 's1', json.dumps(dict(id='s1', title='계약 테스트 자료'))))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)', ('v1', 's1', 'test-hash', json.dumps(dict(id='v1', source_id='s1'))))
        for run_id in ['run1', 'run2']:
            run = dict(id=run_id, kind='business', status='partial', input_version_ids=['v1'], claims=claims, graph=graph)
            db.execute('INSERT INTO runs VALUES(?,?)', (run_id, json.dumps(run)))
    yield value
    value.shutdown()


def test_single_scope_counts_keep_homonyms_and_parallel_relations(service):
    assert len(workbench.catalog(service)['scopes']) == 2
    result = workbench.explore(service, 'run', 'run1', selected_id='n1', graph_root='n1')
    assert result['counts']['nodes'] == 3
    assert result['counts']['relations'] == 3
    assert len({i['id'] for i in result['graph']['items']}) == 6
    assert len(result['detail']['relations']) == 3
    assert result['scope']['partial'] is True


def test_filters_and_directions_keep_counts_and_selection_explicit(service):
    result = workbench.explore(service, 'run', 'run1', selected_id='n1', graph_root='n1', direction='out', item_kind='node')
    assert result['filtered_count'] == 3
    assert {i['id'] for i in result['graph']['items']} == {'n1', 'n2', 'e1', 'e2'}
    assert result['graph']['omitted_relations'] == 1
    incoming = workbench.explore(service, 'run', 'run1', selected_id='n1', graph_root='n1', direction='in')
    assert {i['id'] for i in incoming['graph']['items']} == {'n1', 'n3', 'e3'}
    excluded = workbench.explore(service, 'run', 'run1', selected_id='n1', graph_root='n1', review_state='accepted')
    assert excluded['graph']['items'] == []
    assert excluded['filtered_count'] == 0
    assert excluded['graph']['selected_excluded'] is True
    assert excluded['detail']['item']['id'] == 'n1'
    relation = workbench.explore(service, 'run', 'run1', relation_type='r', item_kind='relation', offset=1, limit=1)
    assert relation['filtered_count'] == 2
    assert relation['items'][0]['id'] == 'e2'


def test_browsing_is_read_only_and_rejects_wrong_scope(service):
    with service.repository.connect() as db:
        before = [tuple(r) for r in db.execute('SELECT id,payload FROM runs')]
    workbench.catalog(service)
    workbench.explore(service, 'run', 'run1', q='없는 이름')
    with service.repository.connect() as db:
        assert before == [tuple(r) for r in db.execute('SELECT id,payload FROM runs')]
    with pytest.raises(ValueError):
        workbench.explore(service, 'ontology', 'run1')
    with pytest.raises(ValueError):
        workbench.explore(service, 'run', 'run1', depth=4)
    with pytest.raises(KeyError):
        workbench.explore(service, 'run', 'run1', selected_id='missing')


def test_dense_graph_is_bounded_without_merging_edges(service):
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', 'run1')
        run['graph']['nodes'] = [dict(id=f'n{i}', label='같은 이름', kind='entity', claim_ids=['c0']) for i in range(100)]
        run['graph']['edges'] = [dict(id=f'e{i}', head='n0', tail=f'n{i}', relation='r', claim_id='c0') for i in range(1, 100)]
        service.repository.save(db, 'runs', run)
    result = workbench.explore(service, 'run', 'run1', selected_id='n0', graph_root='n0')
    assert result['counts']['nodes'] == 100
    assert result['graph']['nodes'] == 8
    assert result['graph']['relations'] == 7
    assert result['graph']['omitted_relations'] == 92
    expanded = workbench.explore(service, 'run', 'run1', selected_id='n0', graph_root='n0', depth=3)
    assert expanded['graph']['nodes'] == 40
    assert expanded['graph']['relations'] == 39


def test_saved_answers_separate_provided_citations_and_scope(service, monkeypatch):
    from app.knowledge import graph_retrieval
    def forbidden(*args, **kwargs):
        pytest.fail('Saved answers must not run retrieval or embedding')
    monkeypatch.setattr(graph_retrieval, 'embed', forbidden)
    monkeypatch.setattr(graph_retrieval, 'retrieve', forbidden)
    context = dict(context=[dict(id='q1', text='정확한 저장 인용', source_reference=dict(
        source_version_id='v1-alias', block_id='b1', start_char=0, end_char=9))])
    answer = dict(id='answer1', kind='business_query', status='succeeded', query=dict(source_run_id='run1', question='질문', retrieval='hybrid'),
                  answer=dict(answer='저장 답변', citations=['p1']), provided_ids=['p1', 'p2'],
                  retrieval=[dict(block_id='p1'), dict(block_id='p2'), dict(block_id='p3')],
                  passage_index=dict(texts=dict(p1='인용', p2='제공', p3='조회')),
                  units=[dict(reference_map={'p1':'q1', 'v1':'v1-alias', 'block1':'b1'},
                              messages=[dict(role='user', content=json.dumps(context))])])
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('answer1', json.dumps(answer)))
    assert workbench.answers(service, 'run', 'run2')['items'] == []
    with pytest.raises(KeyError):
        workbench.answers(service, 'run', 'run2', 'answer1')
    result = workbench.answers(service, 'run', 'run1', 'answer1')['detail']
    assert [(e['id'], e['cited'], e['provided']) for e in result['evidence']] == [
        ('p1', True, True), ('p2', False, True), ('p3', False, False)]
    assert result['evidence'][0]['evidence'][0]['quote'] == '정확한 저장 인용'
    assert result['evidence'][0]['evidence'][0]['source_title'] == '계약 테스트 자료'
    assert result['graph_links'] == []
    assert result['recorded_edge_count'] == 0


def test_claim_count_drills_into_claims_including_excluded_records(service):
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', 'run1')
        run['claims'][0]['extraction_error'] = 'unit fixture failure'
        service.repository.save(db, 'runs', run)
    result = workbench.explore(service, 'run', 'run1', item_kind='claim', selected_id='c0')
    assert result['filtered_count'] == result['counts']['claims'] == 3
    assert result['detail']['claims'][0]['editable'] is False


def test_missing_graph_is_not_counted_as_zero_and_no_change_results_is_explicit(service):
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', 'run1')
        run.pop('graph')
        service.repository.save(db, 'runs', run)
    view = workbench.explore(service, 'run', 'run1')
    assert view['scope']['graph_available'] is False
    assert view['counts']['nodes'] is None
    assert view['counts']['relations'] is None
    assert workbench.changes(service, 'run', 'run1')['records'] == []


def test_change_history_uses_exact_versions_and_current_source_requirements(service):
    change = dict(id='change1', kind='business_change', status='partial', input_version_ids=['v1', 'v2'],
                  request=dict(before_version_id='v1', after_version_id='v2'),
                  diff=dict(comparison='ordered_source_text', changes=[dict(id='delta', kind='replace',
                      before=[dict(id='old', text='계약 테스트 이전')], after=[dict(id='new', text='계약 테스트 이후')])]),
                  impacts=[dict(requirement_id='r1', status='unknown', reason='판단 보류')])
    unrelated = dict(change, id='unrelated', input_version_ids=['v3', 'v4'])
    with service.repository.connect() as db:
        for run in [change, unrelated]:
            db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], json.dumps(run)))
        for requirement in [dict(id='r1', source_ids=['s1'], question='연결 요구', status='needs_review', revision=3),
                            dict(id='r2', source_ids=['s2'], question='다른 출처', status='satisfied', revision=1)]:
            db.execute('INSERT INTO requirements VALUES(?,?)', (requirement['id'], json.dumps(requirement)))
        before = [tuple(row) for row in db.execute('SELECT id,payload FROM requirements')]
    result = workbench.changes(service, 'run', 'run1')
    assert [r['id'] for r in result['records']] == ['change1']
    assert result['records'][0]['diff'] == change['diff']
    assert result['records'][0]['impacts'][0]['status'] == 'unknown'
    assert [(r['id'], r['status'], r['revision']) for r in result['requirements']] == [('r1', 'needs_review', 3)]
    with service.repository.connect() as db:
        assert before == [tuple(row) for row in db.execute('SELECT id,payload FROM requirements')]
