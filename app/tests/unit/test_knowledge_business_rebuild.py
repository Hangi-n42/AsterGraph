from copy import deepcopy
import json
import sqlite3

import pytest

from app.knowledge import autoschema, business_rebuild, business_run, business_use
from app.knowledge.business_models import BusinessDecision, BusinessRunRequest, SourceRebuildPlanRequest
from app.knowledge.schemas import RunRequest, SourceRegistration
from app.knowledge.service import KnowledgeConflict, KnowledgeService, encode
from app.tests.unit.test_knowledge_business import finish


def row(identifier, fields, position):
    return dict(id=identifier, text=json.dumps(fields, ensure_ascii=False),
        locator=dict(format='json', json_pointer='/' + str(position), fields=fields))


def test_row_mapping_separates_moves_values_deletion_and_typed_duplicate_names():
    before = [row('a', dict(id=1, name='같은 이름', value=10), 0),
              row('b', dict(id=2, name='같은 이름', value=20), 1),
              row('c', dict(id='1', name='문자 키', value=30), 2)]
    after = [row('d', dict(id=2, name='같은 이름', value=21), 0),
             row('e', dict(id=1, name='같은 이름', value=10), 1)]
    saved = deepcopy([before, after])
    records = business_rebuild.row_correspondence(before, after, ['id'])
    by_key = {tuple(r['key']): r for r in records}
    assert by_key[(1,)]['action'] == 'rebind_row' and by_key[(1,)]['position_changed']
    assert by_key[(2,)]['action'] == 'rebuild_row' and by_key[(2,)]['changed_fields'] == ['value']
    assert by_key[('1',)]['action'] == 'remove'
    assert [before, after] == saved
    with pytest.raises(ValueError, match='중복'):
        business_rebuild.row_correspondence(before, after + [deepcopy(after[0])], ['id'])
    xlsx = deepcopy(before[:1])
    xlsx[0]['locator']['format'] = 'xlsx'
    with pytest.raises(ValueError, match='XLSX'):
        business_rebuild.row_correspondence(xlsx, xlsx, ['id'])
    same_position = business_rebuild.row_correspondence([before[0]], [row('new', dict(id=1, name='같은 이름', value=11), 0)], ['id'])[0]
    assert same_position['changed_fields'] == ['value'] and same_position['position_changed'] is False


@pytest.fixture
def environment(tmp_path):
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        versions = []
        for name, records, date in [('before', [dict(id=1, value=10), dict(id=2, value=20)], '2025-05-13'),
                                    ('after', [dict(id=2, value=21), dict(id=1, value=10)], '2025-06-24')]:
            versions.append(service.register(name+'.json', json.dumps(records).encode(),
                SourceRegistration(title='원문 표', publisher='검사', namespace='test', external_id='same',
                                   dates=[dict(role='file_snapshot', value=date)]))['source_version_id'])
        assert finish(service, service.start(RunRequest(source_version_ids=versions))['run_id'])['status'] == 'succeeded'
        with service.repository.connect() as db:
            version = service.repository.get(db, 'versions', versions[0])
            blocks = service.parse_blocks(db, version['latest_parse_run_id'], version['id'])
            for block in blocks:
                block['source_id'] = version['source_id']
            chunks = autoschema.chunks(blocks, 49152, 4096, 1000)
            claims = [business_run.direct_tabular_row(chunk, block, index)
                for chunk in chunks for index, block in enumerate(chunk['blocks']) if not block.get('context_only')]
            parent = dict(id='parent', kind='business', status='partial', input_version_ids=[versions[0]],
                claims=claims, blocks=blocks, chunks=chunks, graph=autoschema.graph(claims), concepts=[], units=[],
                recipe=dict(options=BusinessRunRequest(source_version_ids=[versions[0]]).model_dump()),
                requirements=[], assessments=[], repairs=[], metrics={})
            snapshot = dict(id='base', kind='source_graph', source_versions={versions[0]: {}}, claims=deepcopy(claims))
            db.execute('INSERT INTO runs VALUES(?,?)', ('parent', encode(parent)))
            db.execute('INSERT INTO snapshots VALUES(?,?)', ('base', encode(snapshot)))
        yield service, SourceRebuildPlanRequest(parent_run_id='parent', before_version_id=versions[0],
            after_version_id=versions[1], key_fields=['id'], base_snapshot_id='base')
    finally:
        service.shutdown()


def test_plan_is_idempotent_and_keeps_source_dates_and_approval_separate(environment):
    service, request = environment
    first = business_rebuild.plan(service, request)
    assert business_rebuild.plan(service, request) == first
    assert first['date_change_is_input_change']
    assert first['dates']['after'] == [dict(role='file_snapshot', value='2025-06-24')]
    assert not first['generation_reused'] and not first['approval_inherited']
    assert sorted(a['action'] for a in first['actions']) == ['rebind_row', 'rebuild_row']
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', 'parent')['claims'][0]['source_version_ids'] == [request.before_version_id]
        business_rebuild.validate(service, db, first)
        base = service.repository.get(db, 'snapshots', 'base')
        base['revision'] = 2
        db.execute('UPDATE snapshots SET payload=? WHERE id=?', (encode(base), base['id']))
        with pytest.raises(KnowledgeConflict, match='스냅샷'):
            business_rebuild.validate(service, db, first)


def test_changed_parse_and_duplicate_claims_cannot_silently_rebind(environment):
    service, request = environment
    plan = business_rebuild.plan(service, request)
    with service.repository.connect() as db:
        version = service.repository.get(db, 'versions', request.after_version_id)
        version['dates'] = []
        service.repository.save(db, 'versions', version)
        with pytest.raises(KnowledgeConflict, match='원문'):
            business_rebuild.validate(service, db, plan)
        parent = service.repository.get(db, 'runs', 'parent')
        parent['claims'].append(deepcopy(parent['claims'][0]))
        service.repository.save(db, 'runs', parent)
    with pytest.raises(ValueError, match='중복 주장'):
        business_rebuild.plan(service, request)


def run_request(plan, **extra):
    return BusinessRunRequest(source_version_ids=[plan['request']['after_version_id']],
        source_rebuild_plan_id=plan['id'], conceptualize=False, repair=False, **extra)


@pytest.fixture
def no_models(monkeypatch):
    class Client:
        def __init__(self, *_): pass
        def identities(self, *_): return dict(draft=dict(digest='draft'), review=dict(digest='review'))
    def forbidden(*args, **kwargs):
        raise AssertionError('정형 행 재구축에는 모델 호출이 없어야 합니다.')
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    monkeypatch.setattr(business_run, 'call', forbidden)


def test_product_rebuild_keeps_full_context_and_stores_new_claims_once(environment, no_models):
    service, request = environment
    plan = business_rebuild.plan(service, request)
    result = service.start_business(run_request(plan))
    run = finish(service, result['run_id'])
    assert run['status'] == 'succeeded', run.get('error')
    assert len(run['claims']) == 2 and len({c['id'] for c in run['claims']}) == 2
    assert all(c['source_version_ids'] == [request.after_version_id] for c in run['claims'])
    assert sorted(c['raw']['fields']['value'] for c in run['claims']) == [10, 21]
    assert len(run['source_rebuild']['row_bindings']) == 1
    assert len(run['blocks']) == 2 and run['metrics']['llm_calls'] == 0
    assert len(run['source_rebuild']['completed_extraction']) == 1
    repeated = service.start_business(run_request(plan))
    assert repeated['run_id'] == run['id'] and repeated['duplicate_request']
    with service.repository.connect() as db:
        assert len(service.repository.get(db, 'runs', 'parent')['claims']) == 2
        assert service.repository.get(db, 'snapshots', 'base')['claims'][0]['source_version_ids'] == [request.before_version_id]


def test_resume_does_not_repeat_successful_rows_or_units(environment, no_models):
    service, request = environment
    plan = business_rebuild.plan(service, request)
    run = finish(service, service.start_business(run_request(plan))['run_id'])
    with service.repository.connect() as db:
        run['status'] = 'cancelled'
        service.repository.save(db, 'runs', run)
    resumed = finish(service, service.start_business(run_request(plan, resume_run_id=run['id']))['run_id'])
    assert resumed['status'] == 'succeeded', resumed.get('error')
    assert resumed['claims'] == run['claims'] and resumed['units'] == run['units']
    assert resumed['source_rebuild']['completed_extraction'] == run['source_rebuild']['completed_extraction']
    assert resumed['metrics']['llm_calls'] == 0


@pytest.mark.parametrize('operation', ['publish', 'decide'])
def test_final_publication_transaction_rejects_changed_snapshot_basis(environment, no_models, operation):
    service, request = environment
    plan = business_rebuild.plan(service, request)
    run = finish(service, service.start_business(run_request(plan))['run_id'])
    with service.repository.connect() as db:
        base = service.repository.get(db, 'snapshots', 'base')
        base['revision'] = 2
        db.execute('UPDATE snapshots SET payload=? WHERE id=?', (encode(base), 'base'))
        count = db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]
    with pytest.raises(KnowledgeConflict, match='스냅샷'):
        if operation == 'publish':
            business_use.publish(service, run)
        else:
            business_use.decide(service, run['changeset_id'], BusinessDecision(expected_revision=0,
                accept_ids=[], actor='verification-only', reason='검증용 명시 행위'))
    with service.repository.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == count


def test_source_views_keep_every_physical_span_and_reject_stale_locators():
    block = dict(id='b', source_version_id='v', parse_run_id='p', text='같은 문구. 같은 문구.', locator=dict(path='section-1'))
    views = [dict(block, span=[0, 6], text=block['text'][:6]),
             dict(block, span=[6, len(block['text'])], text=block['text'][6:])]
    business_rebuild.validate_views(views, [block])
    views[1]['locator'] = dict(path='section-2')
    with pytest.raises(ValueError, match='위치'):
        business_rebuild.validate_views(views, [block])


def test_scope_materialization_is_atomic_and_repeated_storage_has_no_duplicates(monkeypatch):
    chunk = dict(id='chunk', source_version_id='v', blocks=[])
    run = dict(claims=[], recipe={}, source_rebuild=dict(plan_id='plan'))
    unit = {}; rows = [dict(value=dict(Event='첫째'), index=0, scope=None),
                      dict(value=dict(Event='둘째'), index=1, scope=None)]
    monkeypatch.setattr(autoschema, 'partition', lambda *args: (rows, []))
    original = autoschema.graph_record
    def fail_second(chunk, role, raw, index, **kwargs):
        if index == 1:
            raise ValueError('injected scope materialization failure')
        return original(chunk, role, raw, index, **kwargs)
    monkeypatch.setattr(autoschema, 'graph_record', fail_second)
    with pytest.raises(ValueError, match='injected'):
        business_run.store_extraction(run, chunk, 'event_entity', dict(parsed={}), unit)
    assert run['claims'] == []
    monkeypatch.setattr(autoschema, 'graph_record', original)
    business_run.store_extraction(run, chunk, 'event_entity', dict(parsed={}), unit)
    business_run.store_extraction(run, chunk, 'event_entity', dict(parsed={}), unit)
    assert len(run['claims']) == len({c['id'] for c in run['claims']}) == 2


def test_plan_and_execution_use_existing_http_business_entrypoints(environment, no_models, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers import knowledge
    service, request = environment
    app = FastAPI(); app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', True)
    with TestClient(app) as client:
        response = client.post('/api/v1/knowledge/business/source-rebuild-plans', json=request.model_dump())
        assert response.status_code == 200, response.text
        plan = response.json()['data']
        response = client.post('/api/v1/knowledge/business/runs', json=run_request(plan).model_dump())
        assert response.status_code == 200, response.text
        run = finish(service, response.json()['data']['run_id'])
        assert run['status'] == 'succeeded', run.get('error')
        assert client.get('/api/v1/knowledge/runs/'+run['id']).json()['data']['source_rebuild']['plan_id'] == plan['id']


def test_deleted_row_is_absent_only_from_new_candidate_version(environment, no_models):
    service, original = environment
    with service.repository.connect() as db:
        version = service.repository.get(db, 'versions', original.before_version_id)
    after = service.register('deleted.json', b'[{"id": 1, "value": 10}]',
        SourceRegistration(source_id=version['source_id']))['source_version_id']
    assert finish(service, service.start(RunRequest(source_version_ids=[after]))['run_id'])['status'] == 'succeeded'
    request = original.model_copy(update=dict(after_version_id=after))
    plan = business_rebuild.plan(service, request)
    removed = next(a['claim_id'] for a in plan['actions'] if a['action'] == 'remove')
    run = finish(service, service.start_business(run_request(plan))['run_id'])
    assert run['status'] == 'succeeded', run.get('error')
    assert [c['raw']['fields']['id'] for c in run['claims']] == [1]
    assert run['source_rebuild']['removed_claim_ids'] == [removed]
    with service.repository.connect() as db:
        assert removed in {c['id'] for c in service.repository.get(db, 'runs', 'parent')['claims']}
        assert removed in {c['id'] for c in service.repository.get(db, 'snapshots', 'base')['claims']}


@pytest.mark.parametrize('operation', ['publish', 'decide'])
def test_basis_validation_and_publication_hold_one_database_transaction(environment, no_models, monkeypatch, operation):
    service, request = environment
    plan = business_rebuild.plan(service, request)
    run = finish(service, service.start_business(run_request(plan))['run_id'])
    original = business_rebuild.validate_run
    checked = []
    def guarded(service, db, current):
        assert db.in_transaction
        original(service, db, current)
        with sqlite3.connect(service.repository.path, timeout=.01) as independent:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                independent.execute('UPDATE snapshots SET payload=payload WHERE id=?', ('base',))
        checked.append(True)
    monkeypatch.setattr(business_rebuild, 'validate_run', guarded)
    if operation == 'publish':
        business_use.publish(service, run)
    else:
        business_use.decide(service, run['changeset_id'], BusinessDecision(expected_revision=0,
            accept_ids=[], actor='verification-only', reason='검증용 명시 행위'))
    assert checked == [True]
    with sqlite3.connect(service.repository.path, timeout=.01) as independent:
        independent.execute('UPDATE snapshots SET payload=payload WHERE id=?', ('base',))


def test_second_rebuild_keeps_original_request_lineage_without_copying_responses(environment, no_models):
    service, request = environment
    unchanged = service.register('context.html', '<html><body><p>① 세금을 체납중인 기업</p></body></html>'.encode(),
        SourceRegistration(title='통제 원문', publisher='검사', namespace='test', external_id='context'))['source_version_id']
    assert finish(service, service.start(RunRequest(source_version_ids=[unchanged]))['run_id'])['status'] == 'succeeded'
    with service.repository.connect() as db:
        version = service.repository.get(db, 'versions', unchanged)
        blocks = service.parse_blocks(db, version['latest_parse_run_id'], unchanged)
        for b in blocks: b['source_id'] = version['source_id']
        chunk = autoschema.chunks(blocks, 49152, 4096, 1000)[0]
        parent = service.repository.get(db, 'runs', 'parent')
        claim = autoschema.graph_record(chunk, 'entity_relation',
            dict(Head='세금을 체납중인 기업', Relation='목록', Tail='융자제한기업'), 0)
        parent['blocks'].extend(blocks); parent['chunks'].append(chunk); parent['claims'].append(claim)
        parent['input_version_ids'].append(unchanged)
        parent['graph'] = autoschema.graph(parent['claims'])
        parent['units'].append(dict(id='original-unit', source_chunk_id=chunk['id'], stage='entity_relation',
            status='succeeded', messages=business_run.extraction_messages(parent, chunk, 'entity_relation'),
            schema=autoschema.extraction_schema('entity_relation'), reference_map=chunk['source_reference_map']))
        service.repository.save(db, 'runs', parent)
    plan = business_rebuild.plan(service, request)
    first_request = run_request(plan).model_copy(update=dict(source_version_ids=[request.after_version_id, unchanged]))
    first = finish(service, service.start_business(first_request)['run_id'])
    assert first['status'] == 'succeeded', first.get('error')
    assert not any(u['id'] == 'original-unit' for u in first['units'])
    with service.repository.connect() as db:
        version = service.repository.get(db, 'versions', request.after_version_id)
    next_version = service.register('next.json', b'[{"id": 2, "value": 21}, {"id": 1, "value": 11}]',
        SourceRegistration(source_id=version['source_id']))['source_version_id']
    assert finish(service, service.start(RunRequest(source_version_ids=[next_version]))['run_id'])['status'] == 'succeeded'
    next_plan = business_rebuild.plan(service, SourceRebuildPlanRequest(parent_run_id=first['id'],
        before_version_id=request.after_version_id, after_version_id=next_version, key_fields=['id']))
    next_request = run_request(next_plan).model_copy(update=dict(source_version_ids=[next_version, unchanged]))
    second = finish(service, service.start_business(next_request)['run_id'])
    assert second['status'] == 'succeeded', second.get('error')
    assert len(second['claims']) == 3
    assert next(c for c in second['claims'] if c['id'] == claim['id']) == claim
    proof = second['source_rebuild']['preserved_extraction_inputs'][0]
    assert proof['donor_run_id'] == 'parent' and proof['stored_unit_id'] == 'original-unit'
    assert not any(u['id'] == 'original-unit' for u in second['units'])
    with service.repository.connect() as db:
        donor = service.repository.get(db, 'runs', 'parent')
        donor['units'][0]['messages'][1]['content'] += 'changed'
        service.repository.save(db, 'runs', donor)
        with pytest.raises(ValueError, match='계보'):
            business_rebuild.extraction_donor(service, db, second, claim, {second['id']: second})


@pytest.mark.parametrize('operation', ['publish', 'decide'])
def test_stored_pool_reassessment_inherits_basis_guard_without_execution_markers(environment, no_models, operation):
    service, request = environment
    plan = business_rebuild.plan(service, request)
    parent = finish(service, service.start_business(run_request(plan))['run_id'])
    reviewed = finish(service, service.start_business(BusinessRunRequest(
        source_version_ids=parent['input_version_ids'], reassess_run_id=parent['id'],
        conceptualize=False, repair=False))['run_id'])
    assert reviewed['status'] == 'succeeded', reviewed.get('error')
    assert reviewed['claims'] == parent['claims'] and reviewed['units'] == []
    assert 'source_rebuild' not in reviewed
    assert reviewed['source_rebuild_guard']['plan_id'] == plan['id']
    assert reviewed['source_rebuild_guard']['construction_run_id'] == parent['id']
    with service.repository.connect() as db:
        base = service.repository.get(db, 'snapshots', 'base'); base['revision'] = 2
        db.execute('UPDATE snapshots SET payload=? WHERE id=?', (encode(base), 'base'))
    with pytest.raises(KnowledgeConflict, match='스냅샷'):
        if operation == 'publish':
            business_use.publish(service, reviewed)
        else:
            business_use.decide(service, reviewed['changeset_id'], BusinessDecision(expected_revision=0,
                accept_ids=[], actor='verification-only', reason='검증용 명시 행위'))


def test_definition_storage_is_atomic_and_does_not_duplicate_successful_records():
    block = dict(id='b', source_version_id='v', parse_run_id='p', text='공개 용어와 정의')
    chunk = dict(id='c', source_version_id='v', blocks=[block])
    run = dict(claims=[], source_rebuild=dict(plan_id='plan'))
    valid = dict(term='용어', definition='정의', evidence=[dict(block_id='b', quote='용어와 정의')])
    invalid = dict(term='다른 용어', definition='미확정', evidence=[dict(block_id='b', quote='없는 인용')])
    with pytest.raises(ValueError):
        business_run.store_definitions(run, chunk, dict(definitions=[valid, invalid]))
    assert run['claims'] == []
    business_run.store_definitions(run, chunk, dict(definitions=[valid]))
    business_run.store_definitions(run, chunk, dict(definitions=[valid]))
    assert len(run['claims']) == 1
