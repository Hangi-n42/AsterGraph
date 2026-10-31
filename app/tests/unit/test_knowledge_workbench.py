"""Contract fixtures only; these are not semantic or real-model quality evidence."""
import json

import pytest

from app.knowledge.service import KnowledgeService
from app.knowledge import workbench


def test_claim_view_exposes_stored_interpretation_errors_without_changing_the_claim():
    from copy import deepcopy
    claim = dict(id='c', role='event_entity', statement='저장된 정상 문장', review_status='accepted',
        interpretation=dict(meanings=[dict(conditions=dict(state='present', text='싱거우면'))],
                            errors=['invalid premise state', 'quote not uniquely located in provided view']), evidence=[])
    before = deepcopy(claim)
    view = workbench._claim_view(claim, {}, {}, {})
    assert view['interpretation_errors'] == claim['interpretation']['errors']
    assert view['meanings'] == claim['interpretation']['meanings'] and view['review_status'] == 'accepted'
    assert claim == before
    normal = dict(claim, interpretation=dict(meanings=[], errors=[]))
    assert workbench._claim_view(normal, {}, {}, {})['interpretation_errors'] == []
    assert workbench._claim_view(dict(id='legacy'), {}, {}, {})['interpretation_errors'] == []


def test_snapshot_concepts_separate_known_history_but_keep_failed_and_unresolved_links(service, monkeypatch):
    from copy import deepcopy
    from app.knowledge import autoschema
    with service.repository.connect() as db:
        parent = service.repository.get(db, 'runs', 'run1')
        graph = dict(nodes=parent['graph']['nodes'][:2], edges=parent['graph']['edges'][:1])
        def record(rid, target, ids, status='unreviewed', kind='entity', label='같은 이름'):
            return dict(id=rid, target=dict(id=target, kind=kind, label=label, claim_ids=ids),
                        concepts=['검색 표현'], status=status)
        records = [record('current', 'n1', ['c0', 'c1']), record('history', 'n1', ['c1']),
            record('failed', 'n2', ['c0'], status='failed'), record('unlinked', 'missing', ['c0']),
            record('unknown_claim', 'n1', ['unknown']), record('no_claim_link', 'n2', []),
            record('relation', 'relation-target', ['c0', 'c1'], kind='relation', label='r')]
        snapshot = dict(id='selected', kind='source_graph', run_id='run1', source_versions={'v1': {}}, blocks=[],
            claims=[dict(parent['claims'][0], review_status='accepted')], concepts=records)
        db.execute('INSERT INTO snapshots VALUES(?,?)', ('selected', json.dumps(snapshot)))
    before = deepcopy(snapshot)
    monkeypatch.setattr(autoschema, 'graph', lambda *a: deepcopy(graph))
    view = workbench.explore(service, 'source_graph', 'selected', item_kind='concept', selected_id='current')
    assert view['counts']['concepts'] == 6 and view['counts']['stored_concepts'] == 7
    assert view['counts']['historical_concepts'] == 1 and view['counts']['failed_concepts'] == 1
    assert view['counts']['unresolved_concept_links'] == 3
    assert {r['id'] for r in view['items']} == {r['id'] for r in records} - {'history'}
    assert next(r for r in view['items'] if r['id'] == 'current')['claim_ids'] == ['c0']
    assert next(r for r in view['items'] if r['id'] == 'unlinked')['issue']
    assert all('history' not in r.get('concept_record_ids', []) for r in view['graph']['items'])
    assert view['detail']['claims'][0]['id'] == 'c0'
    with pytest.raises(KeyError):
        workbench.explore(service, 'source_graph', 'selected', selected_id='history')
    filtered = workbench.explore(service, 'source_graph', 'selected', item_kind='concept', source_id='s1', review_state='accepted')
    assert {r['id'] for r in filtered['items']} == {'current', 'failed', 'unlinked', 'relation'}
    assert all(set(r['claim_ids']) <= {'c0'} for r in filtered['items'] + filtered['graph']['items'])
    search_id = workbench.explore(service, 'source_graph', 'selected', item_kind='search_concept')['items'][0]['id']
    detail = workbench.explore(service, 'source_graph', 'selected', selected_id=search_id, source_id='s1')['detail']
    assert detail['concept_records'] and all(set(r['target']['claim_ids']) <= {'c0'} for r in detail['concept_records'])
    with service.repository.connect() as db:
        assert service.repository.get(db, 'snapshots', 'selected') == before
        assert service.repository.get(db, 'runs', 'run1') == parent


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


def test_explicit_interpretation_edit_keeps_field_provenance_in_read_history(service):
    from copy import deepcopy
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', 'run1')
        patch = dict(field='conditions', before=dict(state='present', text='null'),
            after=dict(state='absent', text=None), reason='자기 원문에 조건절 없음',
            meaning_id='old', after_meaning_id='new', evidence=[dict(block_id='b', source_version_id='v1')])
        run['interpretation_edit'] = dict(actor='Codex 검토', reason='일부 해석 필드 정정',
            records=[dict(claim_id='c0', changes=[patch])])
        run['parent_run_id'] = 'previous-edit'
        run['claims'][0]['qualifier_status'] = 'explicit_reviewer_correction_unverified'
        run['claims'][0]['interpretation'] = dict(meanings=[dict(conditions=patch['after'], relation_kind='other')])
        service.repository.save(db, 'runs', run)
    before = deepcopy(run)
    detail = workbench.explore(service, 'run', 'run1', item_kind='claim', selected_id='c0')['detail']
    history = detail['history'][0]
    assert history['actor'] == 'Codex 검토' and history['status'] == 'applied_awaiting_recheck'
    assert json.loads(history['changes'][0]['before']) == patch['before']
    assert json.loads(history['changes'][0]['after']) == patch['after']
    assert history['changes'][0]['evidence'] == patch['evidence']
    assert history['changes'][0]['after_meaning_id'] == 'new'
    assert detail['claims'][0]['meanings'][0]['relation_kind'] == 'other'
    assert detail['claims'][0]['review_status'] == 'unreviewed'
    assert detail['claims'][0]['qualifier_status'] == 'explicit_reviewer_correction_unverified'
    assert detail['parent_run_id'] == 'previous-edit'
    assert workbench.explore(service, 'run', 'run1', item_kind='claim', selected_id='c1')['detail']['history'] == []
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', 'run1') == before


def test_single_scope_counts_keep_homonyms_and_parallel_relations(service):
    assert len(workbench.catalog(service)['scopes']) == 2
    result = workbench.explore(service, 'run', 'run1', selected_id='n1', graph_root='n1')
    assert result['counts']['nodes'] == 3
    assert result['counts']['relations'] == 3
    assert len({i['id'] for i in result['graph']['items']}) == 6
    assert len(result['detail']['relations']) == 3
    assert result['scope']['partial'] is True


def test_catalog_labels_only_explicit_edit_runs_and_uses_recorded_save_time(service):
    with service.repository.connect() as db:
        for rid in ['run1','run2']:
            run=service.repository.get(db,'runs',rid)
            run['repairs']=[dict(origin='user',source_changeset_id='edited',created_at='2026-10-15T00:00:00Z'),dict(origin='model')]
            service.repository.save(db,'runs',run)
        db.execute('INSERT INTO changesets VALUES(?,?)',('edited',json.dumps(dict(edit_run_ids=['run1']))))
    scopes={s['id']:s for s in workbench.catalog(service)['scopes']}
    assert scopes['run1']['data_label']=='직접 수정 저장 결과 · 미승인'
    assert scopes['run1']['created_at']=='2026-10-15T00:00:00Z'
    assert scopes['run2']['data_label']=='자동 추출 결과 · 미승인'
    assert scopes['run2']['created_at'] is None


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


@pytest.mark.parametrize('root_id', ['c0', 'record'])
def test_claim_and_record_roots_keep_source_nodes_before_search_concepts(service, monkeypatch, root_id):
    monkeypatch.setattr(workbench, '_search_concept_graph', lambda value, graph: graph)
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', 'run1')
        run['concepts'] = [dict(id='record', target=dict(id='n1', kind='entity', label='같은 이름', claim_ids=['c0']),
                                concepts=['검색'], status='unreviewed')]
        for i in range(10):
            run['graph']['nodes'].append(dict(id=f'concept_{i}', kind='search_concept', label=f'검색 {i}', claim_ids=['c0']))
            run['graph']['edges'].append(dict(id=f'link{i}', head='n1', tail=f'concept_{i}', relation='has_concept', claim_id='c0'))
        service.repository.save(db, 'runs', run)
    view = workbench.explore(service, 'run', 'run1', selected_id=root_id, graph_root=root_id)['graph']
    assert {'n1', 'n2', 'e1'} <= {r['id'] for r in view['items']}
    assert view['nodes'] == 8 and view['relations'] <= 80 and view['omitted_nodes'] == 5
    for direct in ['n1', 'concept_0']:
        result = workbench.explore(service, 'run', 'run1', selected_id=direct, graph_root=direct)['graph']
        assert direct in {r['id'] for r in result['items']} and result['nodes'] <= 8


def test_saved_answers_separate_provided_citations_and_scope(service, monkeypatch):
    from app.knowledge import graph_retrieval
    def forbidden(*args, **kwargs):
        pytest.fail('Saved answers must not run retrieval or embedding')
    monkeypatch.setattr(graph_retrieval, 'embed', forbidden)
    monkeypatch.setattr(graph_retrieval, 'retrieve', forbidden)
    context = dict(context=[dict(id='q1', text='정확한 저장 인용', source_reference=dict(
        source_version_id='v1-alias', block_id='b1', start_char=0, end_char=9))])
    answer = dict(id='answer1', kind='business_query', status='succeeded', snapshot_id='run:run1', input_version_ids=['v1'], query=dict(source_run_id='run1', question='질문', retrieval='hybrid'),
                  answer=dict(answer='저장 답변', citations=['p1']), provided_ids=['p1', 'p2'],
                  retrieval=[dict(block_id='p1'), dict(block_id='p2'), dict(block_id='p3')],
                  passage_index=dict(texts=dict(p1='인용', p2='제공', p3='조회')),
                  units=[dict(reference_map=None, messages=None), dict(reference_map={'p1':'q1', 'v1':'v1-alias', 'block1':'b1'},
                              messages=[dict(role='user', content=json.dumps(context))])])
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('answer1', json.dumps(answer)))
    assert workbench.answers(service, 'run', 'run2')['items'] == []
    with pytest.raises(KeyError):
        workbench.answers(service, 'run', 'run2', 'answer1')
    result = workbench.answers(service, 'run', 'run1', 'answer1')['detail']
    assert 'answer_link_claims' not in result
    assert [(e['id'], e['cited'], e['provided']) for e in result['evidence']] == [
        ('p1', True, True), ('p2', False, True), ('p3', False, False)]
    assert result['evidence'][0]['evidence'][0]['quote'] == '정확한 저장 인용'
    assert result['evidence'][0]['evidence'][0]['source_title'] == '계약 테스트 자료'
    assert result['graph_links'] == []
    assert result['recorded_edge_count'] == 0
    assert result['snapshot_id'] is None
    assert result['used_versions'] == [dict(id='v1', title='계약 테스트 자료', filename=None, dates=None)]
    assert result['current_usage']['scope'] == dict(kind='run', id='run1')


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


def test_usage_keeps_activation_source_restrictions_and_requirement_causes_separate(service):
    from app.knowledge import availability as snapshots
    recorded = [dict(id='stable', question='비영향 요구', revision=1), dict(id='changed', question='영향 요구', revision=1)]
    snapshot = dict(id='selected', kind='source_graph', activation='explicit_query_only', run_id='run1',
                    source_versions={'v1': {}}, claims=[], blocks=[], requirements=recorded,
                    assessments={r['id']: dict(status='satisfied') for r in recorded})
    correction = dict(id='correction', event='business_correction', snapshot_id='selected',
                      requirement_ids=['changed'], claim_ids=['excluded'], block_ids=['block'])
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)', (snapshot['id'], json.dumps(snapshot)))
        db.execute('INSERT INTO snapshot_events VALUES(?,?)', (correction['id'], json.dumps(correction)))
        for current in [dict(recorded[0], status='unknown'), dict(recorded[1], status='partial', revision=2)]:
            db.execute('INSERT INTO requirements VALUES(?,?)', (current['id'], json.dumps(current)))
        db.execute('INSERT INTO snapshots VALUES(?,?)', ('separate-legacy', json.dumps(dict(id='separate-legacy'))))
        db.execute("UPDATE knowledge_state SET active_snapshot_id='separate-legacy' WHERE id=1")
    snapshots.set_availability(service, dict(expected_status_revision=0, targets=[dict(type='source_version', id='v1')],
        state='blocked', actor='fixture', reason='source restriction fixture'))
    with service.repository.connect() as db:
        before = {table: [tuple(r) for r in db.execute(f'SELECT * FROM {table}')]
                  for table in ['snapshots', 'requirements', 'snapshot_events', 'availability_history', 'knowledge_state', 'runs']}
    view = workbench.usage(service, 'source_graph', 'selected')
    assert view['activation'] == 'explicit_query_only' and view['active_snapshot_id'] == 'separate-legacy'
    assert view['source_restrictions'] == [dict(source_version_id='v1', state='blocked')]
    stable, changed = view['requirements']
    assert stable['current_status'] == 'unknown' and stable['revision_matches'] is True
    assert stable['source_change_requires_review'] is False
    assert changed['current_status'] == 'partial' and changed['recorded_status'] == 'satisfied'
    assert changed['source_change_requires_review'] is True and changed['revision_matches'] is False
    assert view['excluded_claim_ids'] == ['excluded'] and view['excluded_block_ids'] == ['block']
    assert 'usable' not in view and 'available' not in view
    with service.repository.connect() as db:
        for table, rows in before.items():
            assert rows == [tuple(r) for r in db.execute(f'SELECT * FROM {table}')]


def test_usage_does_not_turn_missing_current_requirement_or_version_into_permission(service, monkeypatch):
    from app.knowledge import business_use
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', 'run1')
        run.update(requirements=[dict(id='missing', revision=1)], changeset_id='change', input_version_ids=['missing-version'])
        service.repository.save(db, 'runs', run)
    monkeypatch.setattr(business_use, 'change_view', lambda *_: dict(eligible_ids=[], eligibility_blocks={'c0':['confirmed_expression_error']}, explicit_review_options=[]))
    view = workbench.usage(service, 'run', 'run1')
    assert view['activation'] is None and view['snapshot_id'] is None
    assert view['missing_version_ids'] == ['missing-version']
    assert view['requirements'][0]['current_status'] is None and view['requirements'][0]['revision_matches'] is False
    assert view['review']['blocks'] == {'c0':['confirmed_expression_error']}


def test_changes_use_explicit_scope_and_impact_ids_when_source_ids_are_empty(service):
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', 'run1')
        run['requirements'] = [dict(id='scope-linked', revision=1)]
        service.repository.save(db, 'runs', run)
        change = dict(id='change-linked', kind='business_change', status='succeeded', input_version_ids=['v1','v2'],
            request=dict(before_version_id='v1',after_version_id='v2'),
            impacts=[dict(requirement_id='impact-linked',status='unknown',reason='not confirmed')])
        db.execute('INSERT INTO runs VALUES(?,?)', (change['id'],json.dumps(change)))
        for id in ['scope-linked','impact-linked','unrelated']:
            row = dict(id=id,source_ids=[],question=id,status='partial',revision=1)
            db.execute('INSERT INTO requirements VALUES(?,?)',(id,json.dumps(row)))
    result = workbench.changes(service,'run','run1')
    assert {r['id'] for r in result['requirements']} == {'scope-linked','impact-linked'}
    assert result['snapshot_review_requirement_ids'] == []
    assert result['records'][0]['impacts'][0]['status'] == 'unknown'


@pytest.mark.parametrize('source_available, legacy_plan', [(True, False), (False, False), (True, True)])
def test_changes_link_rebuild_plan_to_exact_execution_review_and_snapshot(service, monkeypatch, source_available, legacy_plan):
    from app.knowledge import business_rebuild, concept_work
    blocks = {'v1': [dict(id='old', text='용도: 카레')], 'v2': [dict(id='new', text='용도: 카레, 볶음')]}
    plan = dict(id='rebuild', kind='business_rebuild_plan', contract='source-scoped-rebuild-v2', status='planned',
        input_version_ids=['v1', 'v2'], request=dict(before_version_id='v1', after_version_id='v2',
            parent_run_id='run1', base_snapshot_id=None, requirement_ids=['r1'], rebuild_scope='whole_source'),
        basis={side: dict(version=dict(id=vid, source_id='s1', filename=vid+'.md', latest_parse_run_id='frozen-'+vid),
                         blocks_sha256=concept_work.digest(blocks[vid])) for side, vid in [('before', 'v1'), ('after', 'v2')]},
        actions=[dict(action='preserve', claim_id='normal'), dict(action='rebuild_source', claim_id='changed')], rows=[],
        requirement_discovery=dict(candidate_ids=['r1'], unselected_review_ids=[], automatic_meaning_impact=False),
        execution_run_ids=['run2', 'missing', 'wrong-plan'], review_run_ids=['review'])
    if legacy_plan:
        plan['request'].pop('rebuild_scope')
    fingerprint = business_rebuild.fingerprint(plan)
    calls = []
    def parse(db, parse_id, version_id):
        calls.append((parse_id, version_id))
        return blocks[version_id] if source_available else [dict(id='wrong', text='다른 파싱 결과')]
    monkeypatch.setattr(service, 'parse_blocks', parse)
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (plan['id'], json.dumps(plan)))
        for rid, phase, status in [('run2', 'source_rebuild', 'failed'), ('review', 'source_rebuild_guard', 'partial'),
                                    ('wrong-plan', 'source_rebuild', 'succeeded')]:
            run = dict(id=rid, kind='business', status=status, input_version_ids=['v2'], claims=[], graph=dict(nodes=[], edges=[]))
            run[phase] = dict(plan_id='another' if rid == 'wrong-plan' else plan['id'], plan_fingerprint=fingerprint)
            db.execute('INSERT OR REPLACE INTO runs VALUES(?,?)', (rid, json.dumps(run)))
        for sid, rid in [('linked', 'review'), ('unrelated', 'wrong-plan')]:
            db.execute('INSERT INTO snapshots VALUES(?,?)', (sid, json.dumps(dict(id=sid, kind='source_graph', run_id=rid,
                source_versions={'v2': {}}, activation='explicit_query_only', claims=[], blocks=[]))))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)', ('v2', 's1', 'hash2', json.dumps(dict(id='v2', source_id='s1', latest_parse_run_id='newer-parse'))))
        db.execute('INSERT INTO requirements VALUES(?,?)', ('r1', json.dumps(dict(id='r1', question='용도 비교', source_ids=[], status='partial', revision=1))))
        before = {t: [tuple(row) for row in db.execute(f'SELECT * FROM {t}')] for t in ['runs', 'snapshots', 'requirements', 'versions']}
    view = workbench.changes(service, 'run', 'run1')
    assert view['records'] == []
    record, = view['rebuild_plans']
    assert record['id'] == 'rebuild' and record['status'] == 'planned'
    assert record['action_counts'] == {'preserve': 1, 'rebuild_source': 1}
    assert [(s['id'], s['status']) for s in record['execution_scopes']] == [('run2', 'failed')]
    assert [(s['id'], s['status']) for s in record['review_scopes']] == [('review', 'partial')]
    assert [s['id'] for s in record['snapshots']] == ['linked']
    assert record['unavailable_run_ids'] == ['missing', 'wrong-plan']
    assert record['requirement_discovery']['automatic_meaning_impact'] is False
    assert [r['id'] for r in view['requirements']] == ['r1']
    assert calls == [('frozen-v1', 'v1'), ('frozen-v2', 'v2')]
    for side, vid in [('before', 'v1'), ('after', 'v2')]:
        source = record['source_comparison'][side]
        assert source['status'] == ('available' if source_available else 'unavailable')
        assert source['blocks'] == (blocks[vid] if source_available else [])
    with service.repository.connect() as db:
        assert before == {t: [tuple(row) for row in db.execute(f'SELECT * FROM {t}')] for t in before}


def link_input_run():
    """Synthetic stored QA input, not model-quality evidence."""
    claims = [dict(id=f'c{i}', source_version_ids=['v1'], raw=dict(Event=f'생성 당시 본문 {i}')) for i in range(2)]
    context = dict(question='기록 질문', context=[dict(id=f'q{i+1}', file_id='v1-alias', text=json.dumps(c)) for i,c in enumerate(claims)])
    return dict(id='linked-answer', kind='business_query', status='succeeded', query=dict(question='기록 질문', source_run_id='run1', retrieval='hybrid'),
        answer=dict(answer='그대로 보존할 답변', citations=['c0','c1'], limitations=['기존 한계']),
        answer_status='answered', input_version_ids=['v1'], provided_ids=['c0','c1'], retrieval=[],
        answer_links=dict(status='recorded', relation='model_declared', semantic_support='not_assessed',
            links=[dict(status='resolved', declaration=dict(target='answer', anchor='그대로', claim_refs=['c0','c1'], quote_refs=['sq_a']))]),
        units=[dict(id='qa-unit', stage='business_qa', reference_map={'c0':'q1','c1':'q2','v1':'v1-alias'},
            messages=[dict(role='user',content=json.dumps(context))])])


def test_link_claim_bodies_use_recorded_input_without_changing_snapshot_or_response(service):
    from copy import deepcopy
    run=link_input_run();before=deepcopy(run)
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],json.dumps(run)))
        payloads={r['id']:r['payload'] for r in db.execute('SELECT id,payload FROM runs')}
    detail=workbench.answers(service,'run','run1',run['id'])['detail']
    assert detail['evidence'][0]['statement']=='조건 0'  # Selected scope remains separate.
    assert detail['answer_link_claims']['claims']['c0']==dict(status='recorded',statement='생성 당시 본문 0',body_origin='raw_duplicate',source_version_ids=['v1'])
    assert detail['answer_link_claims']['unit_id']=='qa-unit'
    assert detail['answer_links']==run['answer_links'] and detail['answer']==run['answer']
    assert run==before
    with service.repository.connect() as db:
        assert {r['id']:r['payload'] for r in db.execute('SELECT id,payload FROM runs')}==payloads


@pytest.mark.parametrize('fault',['missing_unit','multiple_units','alias_collision','multiple_user_messages','wrong_question','broken_json'])
def test_ambiguous_qa_input_does_not_choose_a_unit_or_current_snapshot(fault):
    from copy import deepcopy
    run=link_input_run();unit=run['units'][0]
    if fault=='missing_unit':run['units']=[]
    elif fault=='multiple_units':run['units'].append(deepcopy(unit))
    elif fault=='alias_collision':unit['reference_map']['other']='q1'
    elif fault=='multiple_user_messages':unit['messages'].append(deepcopy(unit['messages'][0]))
    elif fault=='broken_json':unit['messages'][0]['content']='{'
    else:
        context=json.loads(unit['messages'][0]['content']);context['question']='다른 질문';unit['messages'][0]['content']=json.dumps(context)
    before=deepcopy(run);result=workbench._answer_link_claims(run)
    assert result['status']=='unresolved' and all(v==dict(status='unresolved') for v in result['claims'].values())
    assert run==before


@pytest.mark.parametrize('fault',['duplicate_id','missing_row','wrong_id','invalid_id_type','wrong_version','missing_version','wrong_file_version','invalid_file_type','missing_body','invalid_body','broken_text'])
def test_bad_claim_input_only_withholds_its_body(fault):
    run=link_input_run();unit=run['units'][0];context=json.loads(unit['messages'][0]['content']);row=context['context'][0];claim=json.loads(row['text'])
    if fault=='duplicate_id':context['context'].append(dict(row))
    elif fault=='missing_row':context['context']=context['context'][1:]
    elif fault=='wrong_id':claim['id']='different'
    elif fault=='invalid_id_type':claim['id']=[]
    elif fault=='wrong_version':claim['source_version_ids']=['unregistered']
    elif fault=='missing_version':claim.pop('source_version_ids')
    elif fault=='wrong_file_version':row['file_id']='different'
    elif fault=='invalid_file_type':row['file_id']=[]
    elif fault=='missing_body':claim['raw']={};claim['interpretation']=dict(statement='해석을 본문으로 대체 금지')
    elif fault=='invalid_body':claim['statement']=[]
    if fault=='broken_text':row['text']='not JSON'
    else:row['text']=json.dumps(claim)
    unit['messages'][0]['content']=json.dumps(context);result=workbench._answer_link_claims(run)
    assert result['status']=='unresolved' and result['claims']['c0']==dict(status='unresolved')
    assert result['claims']['c1']['statement']=='생성 당시 본문 1'


def test_literal_statement_triple_reconstruction_and_review_gate():
    run=link_input_run();unit=run['units'][0];context=json.loads(unit['messages'][0]['content'])
    a=json.loads(context['context'][0]['text']);a.update(raw=dict(Head='김치찌개',Relation='재료',Tail='돼지고기(등심)'),interpretation=dict(statement='120g으로 바꾸지 않음'))
    b=json.loads(context['context'][1]['text']);b['statement']='q13 그대로인 명시 본문'
    context['context'][0]['text']=json.dumps(a);context['context'][1]['text']=json.dumps(b);unit['messages'][0]['content']=json.dumps(context)
    result=workbench._answer_link_claims(run)
    assert result['claims']['c0']['statement']=='김치찌개 — 재료 — 돼지고기(등심)'
    assert '120g' not in result['claims']['c0']['statement']
    assert result['claims']['c1']['statement']=='q13 그대로인 명시 본문' and result['claims']['c1']['body_origin']=='statement'
    run['answer_status']='needs_review'
    assert workbench._answer_link_claims(run)==dict(status='needs_review',claims={})
