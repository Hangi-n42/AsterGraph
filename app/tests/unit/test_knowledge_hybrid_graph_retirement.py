"""New executions stop before side effects; stored queries remain readable."""
import json
import socket
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import knowledge
from app.core.config import settings
from app.knowledge import business_use
from app.knowledge.business_models import BusinessQuery, BusinessSearchRequest, HYBRID_GRAPH_RETIRED
from app.knowledge.service import KnowledgeService


@pytest.fixture(autouse=True)
def enabled_for_contract_test(monkeypatch):
    monkeypatch.setattr(settings, 'KNOWLEDGE_ENABLED', True)


@pytest.mark.parametrize('source', ['snapshot_id', 'source_run_id'])
def test_new_api_rejects_hg_before_database_or_model(tmp_path, monkeypatch, source):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('Network/model forbidden'))
    service = KnowledgeService(tmp_path / 'knowledge.db')
    app = FastAPI(); app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post('/api/v1/knowledge/business/search', json={
                source: 'missing', 'question': '질문', 'retrieval': 'hybrid_graph'})
        assert response.status_code == 422 and HYBRID_GRAPH_RETIRED in response.text
        with service.repository.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0
        schema = app.openapi()['components']['schemas']['BusinessSearchRequest']
        legacy_modes = BusinessQuery.model_json_schema()['properties']['retrieval']['enum']
        assert set(schema['properties']['retrieval']['enum']) == set(legacy_modes) - {'hybrid_graph'}
        assert schema['properties']['retrieval']['default'] == 'hipporag2'
    finally:
        service.executor.shutdown(wait=True)


@pytest.mark.parametrize('context_mode', ['graph', 'document'])
def test_direct_service_rejects_before_accessing_service(context_mode):
    legacy = BusinessQuery(source_run_id='old', question='질문', retrieval='hybrid_graph')
    with pytest.raises(ValueError, match='hipporag2'):
        business_use.query(None, legacy, context_mode=context_mode)


def test_legacy_get_keeps_mode_and_review_state(tmp_path, monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('Network/model forbidden'))
    service = KnowledgeService(tmp_path / 'knowledge.db')
    query = BusinessQuery(source_run_id='origin', question='과거 질문', retrieval='hybrid_graph')
    record = dict(id='old', kind='business_query', query=query.model_dump(), status='needs_review',
                  answer_status='needs_review', units=[], answer=dict(answer='당시 본문'),
                  graph_retrieval=dict(contract='hybrid-graph-rrf-source-passages-v1'))
    before = deepcopy(record)
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('old', json.dumps(record)))
    app = FastAPI(); app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get('/api/v1/knowledge/runs/old')
        assert response.status_code == 200
        restored = response.json()['data']
        assert restored.pop('counts') == dict(queued=0, running=0, succeeded=0, failed=0, cancelled=0)
        assert restored == before
        assert BusinessQuery.model_validate(restored['query']).retrieval == 'hybrid_graph'
    finally:
        service.executor.shutdown(wait=True)


def test_new_request_preserves_non_hg_modes_and_hybrid_source_scope():
    assert BusinessSearchRequest(snapshot_id='s', question='q').retrieval == 'hipporag2'
    for mode in ['bm25', 'dense', 'hipporag2']:
        assert BusinessSearchRequest(snapshot_id='s', question='q', retrieval=mode).retrieval == mode
    assert BusinessSearchRequest(source_run_id='r', question='q', retrieval='hybrid').retrieval == 'hybrid'
    with pytest.raises(ValueError, match='source_run_id'):
        BusinessSearchRequest(snapshot_id='s', question='q', retrieval='hybrid')


@pytest.mark.parametrize('explicit_null', [False, True])
def test_new_api_model_keeps_omitted_defaults_and_explicit_null_separate(explicit_null):
    fields = dict(candidate_contract='r2_g1_w1', evidence_union='ranked_preserved_claims_v2',
                  source_citation_contract='provided_source_quote_links_v1')
    request = BusinessSearchRequest(snapshot_id='s', question='q', **(dict.fromkeys(fields) if explicit_null else {}))
    effective, defaulted = business_use.resolve_query_defaults(request, 'graph')
    assert defaulted == ([] if explicit_null else list(fields))
    assert {key: getattr(effective, key) for key in fields} == (dict.fromkeys(fields) if explicit_null else fields)
