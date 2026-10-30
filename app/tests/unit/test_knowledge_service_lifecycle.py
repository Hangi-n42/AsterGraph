from copy import deepcopy
import json

import pytest

from app.knowledge import service as lifecycle
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeService


@pytest.fixture
def history(tmp_path):
    service = KnowledgeService(tmp_path/'knowledge.db')
    version = dict(id='version', processing_status='parsed', latest_parse_run_id='previous-success',
                   latest_parse_attempt_run_id='previous-attempt', source_id='source')
    runs = []
    with service.repository.connect() as db:
        db.execute('INSERT INTO sources VALUES(?,?,?,?)', ('source', 'test', None, '{}'))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)',
                   ('version', 'source', 'hash', json.dumps(version)))
        for rid, status in [('z', 'queued'), ('done', 'succeeded'), ('a', 'running'),
                            ('partial', 'partial'), ('m', 'cancel_requested'),
                            ('failed', 'failed'), ('cancelled', 'cancelled')]:
            units = [dict(id=state, source_version_id='version', spec=dict(id=state), status=state,
                          error='saved', attempts=[]) for state in
                     ['queued', 'running', 'succeeded', 'failed', 'cancelled']]
            units[1]['attempts'] = [dict(outcome='failed', timeout_s=99),
                                    dict(outcome='started', timeout_s=7)]
            analysis = [dict(id='analysis', status='running', error=None,
                             attempts=[dict(outcome='started', timeout_s=11)]),
                        dict(id='planned', status='queued'),
                        dict(id='committed', status='running',
                             attempts=[dict(outcome='succeeded', timeout_s=100)]),
                        dict(id='no-attempt', status='running')]
            run = dict(id=rid, kind='parse', status=status, units=units, analysis_units=analysis,
                       input_version_ids=['version'], retry_of_run_id=None, finished_at=None,
                       metrics=dict(interrupted_time_reserve_s=2.5, llm_calls=0),
                       claims=[dict(condition='조건', evidence_id='evidence', correction='원본 교정')],
                       failure_lineage=['earlier-failure'])
            raw = json.dumps(run, ensure_ascii=False)
            db.execute('INSERT INTO runs VALUES(?,?)', (rid, raw))
            runs.append((run, raw))
    yield service, version, runs
    service.executor.shutdown()


def test_startup_recovers_every_active_run_once_in_history_order(history, monkeypatch):
    previous, version, runs = history
    previous.executor.shutdown()
    monkeypatch.setattr(lifecycle, 'utcnow', lambda: 'restart-time')
    writes = []
    save = KnowledgeRepository.save
    def tracked(db, table, value):
        writes.append((table, value['id']))
        return save(db, table, value)
    monkeypatch.setattr(KnowledgeRepository, 'save', staticmethod(tracked))
    resumed = KnowledgeService(previous.repository.path)
    try:
        with resumed.repository.connect() as db:
            for before, raw in runs:
                saved = db.execute('SELECT payload FROM runs WHERE id=?', (before['id'],)).fetchone()['payload']
                if before['status'] not in {'queued', 'running', 'cancel_requested'}:
                    assert saved == raw
                    continue
                expected = deepcopy(before)
                expected.update(status='failed', finished_at='restart-time')
                expected['metrics']['interrupted_time_reserve_s'] = 20.5
                for unit in expected['units'] + expected['analysis_units']:
                    if unit['status'] in {'queued', 'running'}:
                        if unit.get('attempts') and unit['attempts'][-1]['outcome'] == 'started':
                            unit['attempts'][-1]['outcome'] = 'interrupted_before_result_commit'
                        unit.update(status='failed', error='서버 재시작으로 중단됨')
                assert json.loads(saved) == expected
            assert resumed.repository.get(db, 'versions', 'version') == dict(version,
                processing_status='failed', latest_parse_attempt_run_id='m')
        assert writes == [('runs', 'z'), ('versions', 'version'), ('runs', 'a'),
                          ('versions', 'version'), ('runs', 'm'), ('versions', 'version')]
    finally:
        resumed.shutdown()


def test_shutdown_only_requests_active_runs_once_and_preserves_other_bytes(history, monkeypatch):
    service, version, runs = history
    writes = []
    save = KnowledgeRepository.save
    def tracked(db, table, value):
        writes.append((table, value['id']))
        return save(db, table, value)
    monkeypatch.setattr(KnowledgeRepository, 'save', staticmethod(tracked))
    service.shutdown()
    assert service.closed
    with service.repository.connect() as db:
        for before, raw in runs:
            saved = db.execute('SELECT payload FROM runs WHERE id=?', (before['id'],)).fetchone()['payload']
            if before['status'] in {'queued', 'running'}:
                assert json.loads(saved) == dict(before, status='cancel_requested')
            else:
                assert saved == raw
        assert service.repository.get(db, 'versions', 'version') == version
    assert writes == [('runs', 'z'), ('runs', 'a')]


@pytest.mark.parametrize('phase', ['startup', 'shutdown'])
@pytest.mark.parametrize('last_status', ['failed', 'queued'])
def test_lifecycle_keeps_last_duplicate_status_semantics(tmp_path, phase, last_status):
    service = KnowledgeService(tmp_path/'knowledge.db')
    raw = ('{"id":"one","kind":"business","status":"running","units":[],"metrics":{},'
           '"status":' + json.dumps(last_status) + '}')
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('one', raw))
    if phase == 'startup':
        service.executor.shutdown()
        service = KnowledgeService(service.repository.path)
    else:
        service.shutdown()
    try:
        with service.repository.connect() as db:
            saved = db.execute('SELECT payload FROM runs').fetchone()['payload']
        if last_status == 'failed':
            assert saved == raw
        else:
            assert json.loads(saved)['status'] == ('failed' if phase == 'startup' else 'cancel_requested')
    finally:
        service.shutdown()


@pytest.mark.parametrize('phase', ['startup', 'shutdown'])
def test_lifecycle_still_raises_on_later_malformed_json_and_rolls_back(tmp_path, phase):
    service = KnowledgeService(tmp_path/'knowledge.db')
    raw = '{"id":"one","kind":"business","status":"queued","units":[],"metrics":{}}'
    with service.repository.connect() as db:
        db.executemany('INSERT INTO runs VALUES(?,?)', [('one', raw), ('bad', 'not-json')])
    try:
        with pytest.raises(json.JSONDecodeError):
            if phase == 'startup':
                KnowledgeService(service.repository.path)
            else:
                service.shutdown()
        with service.repository.connect() as db:
            assert [(row['id'], row['payload']) for row in db.execute('SELECT * FROM runs')] == [
                ('one', raw), ('bad', 'not-json')]
    finally:
        service.executor.shutdown()
