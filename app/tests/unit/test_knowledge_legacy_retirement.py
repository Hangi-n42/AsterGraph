"""Retire execution while preserving current guards and historical records; no model calls."""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routers import knowledge
from app.knowledge import availability, business_use
from app.knowledge.repository import VersionConflict
from app.knowledge.schemas import RunRequest
from app.knowledge.service import KnowledgeService


@pytest.fixture
def service(tmp_path):
    value = KnowledgeService(tmp_path/'knowledge.db')
    with value.repository.connect() as db:
        db.execute('INSERT INTO sources VALUES(?,?,?,?)', ('s', 'test', 'one', json.dumps(dict(id='s', title='자료'))))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)', ('v', 's', 'hash', json.dumps(dict(id='v', source_id='s', processing_status='parsed'))))
        db.execute('INSERT INTO runs VALUES(?,?)', ('parse', json.dumps(dict(id='parse', kind='parse', status='succeeded'))))
        block = dict(id='b', source_version_id='v', text='원문 조건', locator={'format':'md'})
        db.execute('INSERT INTO blocks VALUES(?,?,?,?,?,?)', ('b', 'v', 'parse', 'unit', 0, json.dumps(block)))
    yield value
    value.shutdown()


def test_retired_routes_do_not_start_jobs_and_current_routes_remain(service, monkeypatch):
    app = FastAPI(); app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', True)
    with TestClient(app) as client:
        for path in ['ontologies', 'candidates', 'entities', 'snapshots', 'search', 'discovery/sources']:
            response = client.post('/api/v1/knowledge/'+path, json={}) if path=='search' else client.get('/api/v1/knowledge/'+path)
            assert response.status_code == 404
        for kind in ['discovery', 'ontology', 'extract']:
            assert client.post('/api/v1/knowledge/runs', json={'kind':kind}).status_code == 422
            with pytest.raises(ValidationError): RunRequest(kind=kind)
        assert client.get('/api/v1/knowledge/sources').status_code == 200
        assert client.get('/api/v1/knowledge/business/snapshots').json()['data']['items'] == []
        assert client.get('/api/v1/knowledge/workbench/scopes').status_code == 200
        assert client.get('/api/v1/knowledge/evidence/b?run_id=old').status_code == 422
    with service.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0] == 1


def test_source_restrictions_and_conflicts_survive_module_removal(service):
    request=dict(expected_status_revision=0, targets=[dict(type='source_version',id='v')],
                 state='blocked',actor='reviewer',reason='원문 사용 제한')
    availability.set_availability(service, request)
    with pytest.raises(VersionConflict): availability.set_availability(service, request)
    detail = service.evidence('b')
    assert detail['block']['text'] == '원문 조건'
    assert detail['usage_restrictions'] == [dict(type='source_version',id='v',state='blocked')]
    with service.repository.connect() as db:
        assert business_use.restricted_sources(db,['v']) == [dict(source_version_id='v',state='blocked')]


def test_historical_extraction_read_does_not_restore_execution(service):
    run=dict(id='old-run',kind='extract',status='succeeded',units=[],changeset_id='old-change')
    claim=dict(id='old-claim',kind='assertion',review_status='proposed',validation_errors=[],origin='automatic')
    change=dict(id='old-change',kind='extraction',candidate_ids=['old-claim'])
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'],json.dumps(run)))
        db.execute('INSERT INTO changesets VALUES(?,?)', (change['id'],json.dumps(change)))
        db.execute('INSERT INTO assertions VALUES(?,?,?,?,?)',('old-claim','old-run','u','key',json.dumps(claim)))
    result = service.run('old-run')
    assert result['candidate_counts'] == dict(valid=1,invalid=0,manual=0,automatic=1,unresolved=1)
    with pytest.raises(ValueError,match='종료'): service.start(SimpleNamespace(kind='extract'))
    with service.repository.connect() as db:
        assert service.repository.get(db,'runs','old-run') == run
        assert service.repository.get(db,'assertions','old-claim') == claim
