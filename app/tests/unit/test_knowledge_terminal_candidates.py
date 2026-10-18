"""Explicit publication keeps candidate permission separate from unfinished work."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.knowledge import business_run, business_use
from app.knowledge.business_models import BusinessDecision
from app.knowledge.service import KnowledgeConflict, KnowledgeService, encode
from app.tests.unit.test_knowledge_business_local_review import meaning
from app.tests.unit.test_knowledge_business_responsibilities import setup_direct_receipt


@pytest.fixture
def terminal(tmp_path, monkeypatch):
    run, _ = setup_direct_receipt(monkeypatch, states=('supported', 'unknown'))
    run.update(kind='business', status='failed', error='source followup not completed',
               concepts=[], sources={}, input_version_ids=['v'])
    requirement = run['requirements'][0]
    requirement['status'] = 'partial'
    source = dict(meanings=[meaning('m')], public_scope=dict(tasks=[]), completeness='partial', gaps=[])
    assessment = dict(id='a', requirement_id=requirement['id'], status='partial', source=source,
        representation=None, errors=['join input_capacity'], issues=[dict(reason='unresolved')])
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, requirement, source)
    run['assessments'] = [assessment]
    service = KnowledgeService(tmp_path/'knowledge.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
        db.execute('INSERT INTO requirements VALUES(?,?)', (requirement['id'], encode(requirement)))
    yield service, run
    service.shutdown()


def save(service, run):
    with service.repository.connect() as db:
        service.repository.save(db, 'runs', run)


def test_explicit_api_publication_reuses_change_and_keeps_failed_work(terminal, monkeypatch):
    from app.api.routers import knowledge
    service, original = terminal
    app = FastAPI(); app.include_router(knowledge.router)
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', True)
    with TestClient(app) as client:
        url = f'/knowledge/business/runs/{original["id"]}/publish-candidates'
        response = client.post(url)
        assert response.status_code == 200
        change = response.json()['data']
        assert client.post(url).json()['data'] == change
        assert client.post('/knowledge/business/runs/absent/publish-candidates').status_code == 404
    assert change['eligible_ids'] == [original['claims'][0]['id']]
    assert change['candidates'] == original['claims']
    assert change['publication_context']['run_status'] == 'failed'
    assert change['publication_context']['run_error'] == original['error']
    assert change['publication_context']['recorded_assessments'][0]['errors'] == ['join input_capacity']
    with service.repository.connect() as db: stored = service.repository.get(db, 'runs', original['id'])
    stored.pop('changeset_id')
    assert stored == original
    with service.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM changesets').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM snapshots').fetchone()[0] == 0
    with pytest.raises(ValueError):
        business_use.decide(service, change['id'], BusinessDecision(expected_revision=0,
            actor='fixture-reviewer', reason='synthetic explicit selection', accept_ids=[original['claims'][1]['id']]))
    result = business_use.decide(service, change['id'], BusinessDecision(expected_revision=0,
        actor='fixture-reviewer', reason='synthetic explicit selection', accept_ids=change['eligible_ids']))
    with service.repository.connect() as db:
        snapshot = service.repository.get(db, 'snapshots', result['snapshot_id'])
    assert snapshot['publication_context'] == change['publication_context']
    assert result['decision']['publication_context'] == change['publication_context']
    assert snapshot['assessments']['r']['recorded_status'] == 'partial'
    assert snapshot['assessments']['r']['status'] != 'satisfied'
    selected = deepcopy(snapshot['claims'][0]); selected['review_status'] = original['claims'][0]['review_status']
    assert selected == original['claims'][0]
    assert business_use.publish_terminal_candidates(service, original['id'])['revision'] == 1


@pytest.mark.parametrize('fault', ['queued', 'running', 'cancel_requested', 'closed', 'other_run',
    'nonbusiness', 'no_assessment', 'stale_assessment', 'stale_own', 'changed_candidate',
    'requirement_revision', 'requirement_needs_review'])
def test_rejected_publication_creates_nothing(terminal, fault):
    service, run = terminal
    if fault in {'queued', 'running', 'cancel_requested'}: run['status'] = fault
    elif fault == 'closed': service.closed = True
    elif fault == 'other_run':
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)', ('busy', encode(dict(id='busy', status='running'))))
    elif fault == 'nonbusiness': run['kind'] = 'extract'
    elif fault == 'no_assessment': run['assessments'] = []
    elif fault == 'stale_assessment': run['assessments'][0]['input_fingerprint'] = 'stale'
    elif fault == 'stale_own': run['units'][0]['status'] = 'failed'
    elif fault == 'changed_candidate': run['claims'][0]['raw']['Relation'] = 'changed'
    else:
        requirement = deepcopy(run['requirements'][0])
        if fault == 'requirement_revision': requirement['revision'] += 1
        else: requirement['status'] = 'needs_review'
        with service.repository.connect() as db: service.repository.save(db, 'requirements', requirement)
    save(service, run)
    with pytest.raises(KnowledgeConflict): business_use.publish_terminal_candidates(service, run['id'])
    with service.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM changesets').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM snapshots').fetchone()[0] == 0


def test_duplicate_after_changed_review_is_conflict_and_publication_is_atomic(terminal, monkeypatch):
    service, run = terminal
    original_save = service.repository.save
    def broken(db, table, value):
        if table == 'runs': raise RuntimeError('synthetic storage failure')
        return original_save(db, table, value)
    monkeypatch.setattr(service.repository, 'save', broken)
    with pytest.raises(RuntimeError, match='storage failure'):
        business_use.publish_terminal_candidates(service, run['id'])
    with service.repository.connect() as db: assert db.execute('SELECT count(*) FROM changesets').fetchone()[0] == 0
    monkeypatch.setattr(service.repository, 'save', original_save)
    change = business_use.publish_terminal_candidates(service, run['id'])
    run = service.run(run['id']); run['units'][0]['status'] = 'failed'; save(service, run)
    with pytest.raises(KnowledgeConflict): business_use.publish_terminal_candidates(service, run['id'])
    with service.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM changesets').fetchone()[0] == 1
        assert service.repository.get(db, 'changesets', change['id']) == change


def test_concurrent_explicit_requests_have_one_changeset(terminal):
    service, run = terminal
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: business_use.publish_terminal_candidates(service, run['id']), range(2)))
    assert results[0] == results[1]
    with service.repository.connect() as db: assert db.execute('SELECT count(*) FROM changesets').fetchone()[0] == 1
