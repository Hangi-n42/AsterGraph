import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeConflict, KnowledgeService


@pytest.fixture
def ledger():
    with sqlite3.connect(':memory:') as db:
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE runs(id TEXT PRIMARY KEY, payload TEXT)')
        yield db


@pytest.mark.parametrize('payload', [
    *[json.dumps(dict(status=status)) for status in ['queued', 'running', 'cancel_requested',
        'succeeded', 'partial', 'failed', 'cancelled', 'review_ready', 'unknown', '', None, 0, True, False, [], {}]],
    '{}', 'not-json', '{"status":"running",}', '[]', 'null', '1', '"running"',
    '{"status":"failed","status":"running"}', '{"status":"running","status":"failed"}',
    '{"status":"failed","units":[{"status":"running"}]}',
    '{"status":"running","x":NaN}', '{"status":"failed","x":Infinity}',
    '{"status":"\\u0072unning"}',
])
def test_status_projection_preserves_legacy_result_or_exception(ledger, payload):
    ledger.execute('INSERT INTO runs VALUES(?,?)', ('one', payload))
    def outcome(call):
        try:
            return call()
        except Exception as error:
            return type(error), str(error)
    expected = outcome(lambda: any(json.loads(row['payload'])['status'] in
        {'queued', 'running', 'cancel_requested'} for row in ledger.execute('SELECT payload FROM runs')))
    assert outcome(lambda: KnowledgeRepository.has_active_runs(ledger)) == expected


@pytest.mark.parametrize('payloads,result', [
    ([], False), (['{"status":"failed"}', '{"status":"queued"}'], True),
    (['{"status":"running"}', 'not-json'], True),
    (['{"status":"cancel_requested"}', '{}'], True),
    (['not-json', '{"status":"running"}'], json.JSONDecodeError),
    (['{}', '{"status":"running"}'], KeyError),
])
def test_status_projection_preserves_short_circuit_errors(ledger, payloads, result):
    ledger.executemany('INSERT INTO runs VALUES(?,?)', [(str(i), raw) for i, raw in enumerate(payloads)])
    if isinstance(result, type):
        with pytest.raises(result):
            KnowledgeRepository.has_active_runs(ledger)
    else:
        assert KnowledgeRepository.has_active_runs(ledger) is result


def test_status_projection_reads_small_fragments_and_does_not_write(ledger, monkeypatch):
    from app.knowledge import repository
    payload = json.dumps(dict(status='failed', units=[dict(status='running', response='가'*100000)]))
    ledger.execute('INSERT INTO runs VALUES(?,?)', ('one', payload))
    reads, statements = [], []
    original = json.loads
    def loads(value):
        reads.append(len(value.encode()))
        return original(value)
    monkeypatch.setattr(repository.json, 'loads', loads)
    ledger.set_trace_callback(statements.append)
    assert not KnowledgeRepository.has_active_runs(ledger)
    assert reads and max(reads) < 100
    assert all(not sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'COMMIT', 'ROLLBACK'))
               for sql in statements)


def test_status_projection_observes_uncommitted_transitions_without_cache(ledger):
    ledger.execute('INSERT INTO runs VALUES(?,?)', ('one', '{"status":"failed"}'))
    ledger.commit()
    for status, active in [('queued', True), ('running', True), ('cancel_requested', True),
                           ('cancelled', False), ('failed', False), ('succeeded', False)]:
        ledger.execute('UPDATE runs SET payload=?', (json.dumps(dict(status=status)),))
        assert ledger.in_transaction
        assert KnowledgeRepository.has_active_runs(ledger) is active
        assert ledger.in_transaction
    ledger.rollback()
    assert not KnowledgeRepository.has_active_runs(ledger)


class GuardLock:
    held = False
    def __enter__(self):
        self.held = True
    def __exit__(self, *_):
        self.held = False


@pytest.mark.parametrize('entry', ['parse', 'query', 'business', 'edit', 'checkpoint', 'changes',
    'concepts', 'projection', 'html_rows', 'feedback', 'extract', 'search', 'discovery', 'analysis', 'ontology'])
@pytest.mark.parametrize('state', ['queued', 'running', 'cancel_requested', 'closed'])
def test_all_start_guards_keep_lock_closed_and_active_blocking(tmp_path, monkeypatch, entry, state):
    from app.knowledge import (business_use, business_run, business_edit, business_checkpoint,
        business_changes, business_concepts, business_projection, business_html_rows, business_feedback,
        extraction, search, discovery_run, discovery_analysis, ontology_run)
    from app.knowledge.business_models import BusinessQuery
    repository = KnowledgeRepository(tmp_path/'knowledge.db')
    service = SimpleNamespace(repository=repository, lock=GuardLock(), closed=state == 'closed')
    payload = 'not-json' if service.closed else json.dumps(dict(status=state))
    with repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('blocker', payload))
    calls = []
    original = KnowledgeRepository.has_active_runs
    def guarded(db):
        assert service.lock.held
        calls.append(db)
        return original(db)
    monkeypatch.setattr(KnowledgeRepository, 'has_active_runs', staticmethod(guarded))
    client = lambda *_: SimpleNamespace(identities=lambda *_: {})
    monkeypatch.setattr(business_run, 'ModelClient', client)
    monkeypatch.setattr(business_changes, 'ModelClient', client)
    monkeypatch.setattr(business_concepts, 'plan', lambda *_: ({}, []))
    request = SimpleNamespace(kind='parse', model=None, review_model=None, context_tokens=4096,
        representation_context_tokens=None, donor_run_id=None, retry_of_run_id=None,
        model_fields_set=set(), discovery_mode='ground')
    entries = {
        'parse': lambda: KnowledgeService.start(service, request),
        'query': lambda: business_use.query(service, BusinessQuery(source_run_id='absent', question='근거')),
        'business': lambda: business_run.start(service, request),
        'edit': lambda: business_edit.start(service, 'absent', request),
        'checkpoint': lambda: business_checkpoint.prepare(service, 'absent'),
        'changes': lambda: business_changes.analyze(service, request),
        'concepts': lambda: business_concepts.start(service, request),
        'projection': lambda: business_projection.start(service, 'absent', block_ids=[], chunk_ids=[],
            reason='고정 검사', stop_new_requests_at='2026-10-16T00:00:00+09:00'),
        'html_rows': lambda: business_html_rows.store(service, request),
        'feedback': lambda: business_feedback.start(service, 'absent', request),
        'extract': lambda: extraction.start(service, request),
        'search': lambda: search.search(service, dict(mode='local', query='근거')),
        'discovery': lambda: discovery_run.start(service, request),
        'analysis': lambda: discovery_analysis.start(service, request),
        'ontology': lambda: ontology_run.start(service, request),
    }
    with pytest.raises(KnowledgeConflict):
        entries[entry]()
    assert len(calls) == (0 if service.closed else 1)
    assert not service.lock.held
    with repository.connect() as db:
        assert db.execute('SELECT payload FROM runs').fetchall()[0]['payload'] == payload
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0] == 1


def test_parse_guard_still_blocks_before_later_corrupt_record(tmp_path):
    repository = KnowledgeRepository(tmp_path/'knowledge.db')
    with repository.connect() as db:
        db.executemany('INSERT INTO runs VALUES(?,?)', [('active', '{"status":"running"}'), ('bad', 'not-json')])
    service = SimpleNamespace(repository=repository, lock=GuardLock(), closed=False)
    # The old eager parse guard decoded the later corrupt row; both paths prohibit a new run.
    with pytest.raises(KnowledgeConflict):
        KnowledgeService.start(service, SimpleNamespace(kind='parse'))
