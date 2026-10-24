"""API retention of frozen knowledge, separate from exact-current-runtime work reuse."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import knowledge
from app.knowledge import business_concepts, business_rebuild, business_run, concept_work
from app.knowledge.business_models import BusinessRunRequest, ConceptRunRequest, ConceptPreservationRequest
from app.knowledge.service import KnowledgeConflict
from app.tests.unit.test_knowledge_business import finish
from app.tests.unit.test_knowledge_business_rebuild_source import whole, offline, natural


@pytest.fixture
def retained_source(whole, monkeypatch):
    service, first, request, options, calls = whole
    donor = finish(service, service.start_business(BusinessRunRequest(
        source_version_ids=first['input_version_ids'], **dict(options, conceptualize=True)))['run_id'])
    request = request.model_copy(update=dict(parent_run_id=donor['id']))
    plan = business_rebuild.plan(service, request)
    versions = [request.after_version_id if v == request.before_version_id else v for v in first['input_version_ids']]
    child = finish(service, service.start_business(BusinessRunRequest(source_version_ids=versions,
        source_rebuild_plan_id=plan['id'], **options))['run_id'])
    with service.repository.connect() as db:
        child = service.repository.get(db, 'runs', child['id'])
        donor = service.repository.get(db, 'runs', donor['id'])
    monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', True)
    app = FastAPI(); app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    return service, child, donor, TestClient(app), calls


def test_api_retains_original_work_without_native_calls_and_resumes_only_stored_pool(retained_source):
    service, parent, donor, client, calls = retained_source
    before = len(calls)
    preview = client.get('/api/v1/knowledge/business/source-concept-preservations/'+parent['id']).json()['data']
    assert preview['retained_targets'] and preview['pending_targets']
    request = dict(parent_run_id=parent['id'], expected_parent_fingerprint=preview['parent_fingerprint'])
    first = client.post('/api/v1/knowledge/business/source-concept-preservations', json=request)
    assert first.status_code == 200, first.text
    reply = first.json()['data']
    duplicate = client.post('/api/v1/knowledge/business/source-concept-preservations', json=request).json()['data']
    assert duplicate['run_id'] == reply['run_id'] and duplicate['duplicate_request']
    with service.repository.connect() as db:
        saved = service.repository.get(db, 'runs', reply['run_id'])
        assert service.repository.get(db, 'runs', parent['id']) == parent
    assert saved['metrics']['llm_calls'] == 0 and saved['claims'] == parent['claims']
    assert len(saved['concepts']) == preview['retained_targets'] and saved['stored_pool']
    by_id = {u['id']: u for u in donor['units']}
    assert all(u == by_id[u['id']] for u in saved['units'])
    assert all(c['status'] == 'unreviewed' and c['approved_is_a'] is False for c in saved['concepts'])
    assert all(p['new_work_connected'] is False for p in saved['concept_link_checks'])
    options = dict(parent['recipe']['options'], source_rebuild_plan_id=None, resume_run_id=saved['id'])
    resumed = finish(service, service.start_business(BusinessRunRequest(**options))['run_id'])
    assert resumed['status'] == 'partial' and len(calls) == before
    assert resumed['source_concept_retention']['pending_targets'] == preview['pending_targets']
    assert resumed['concepts'] == saved['concepts']


def test_old_fingerprint_and_polluted_producer_are_rejected(retained_source):
    service, parent, donor, client, _ = retained_source
    response = client.post('/api/v1/knowledge/business/source-concept-preservations', json=dict(
        parent_run_id=parent['id'], expected_parent_fingerprint='old'))
    assert response.status_code == 409
    with service.repository.connect() as db:
        changed = deepcopy(donor)
        unit = next(u for u in changed['units'] if u['stage'].startswith('concept_'))
        unit['executed_limits']['max_tokens'] += 1
        service.repository.save(db, 'runs', changed)
    with pytest.raises(KnowledgeConflict, match='변경'):
        business_concepts.source_preservation(service, parent['id'])


def test_interrupted_retention_is_atomic_and_pending_same_named_relation_uses_real_prepare(retained_source, monkeypatch):
    service, parent, _, _, _ = retained_source
    preview = business_concepts.source_preservation(service, parent['id'])
    request = ConceptPreservationRequest(parent_run_id=parent['id'], expected_parent_fingerprint=preview['parent_fingerprint'])
    with service.repository.connect() as db:
        count = db.execute('SELECT count(*) FROM runs').fetchone()[0]
    original = concept_work.same_input
    def interrupted(*a): raise RuntimeError('interrupted before commit')
    monkeypatch.setattr(concept_work, 'same_input', interrupted)
    with pytest.raises(RuntimeError, match='interrupted'):
        business_concepts.source_preservation(service, parent['id'], request=request)
    with service.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0] == count
    monkeypatch.setattr(concept_work, 'same_input', original)
    saved = business_concepts.source_preservation(service, parent['id'], request=request)
    pending_relation = next(p['target'] for p in preview['pending'] if p['target']['kind'] == 'relation')
    args = dict(parent_run_id=saved['run_id'], target_ids=[pending_relation['id']], neighbor_mode='plain')
    with pytest.raises(ValueError, match='종류'):
        business_concepts.plan(service, ConceptRunRequest(**args))
    _, planned = business_concepts.plan(service, ConceptRunRequest(**args, include_events_and_relations=True))
    assert planned[0]['target'] == pending_relation
    assert planned[0]['work_input']['context_dependencies']
