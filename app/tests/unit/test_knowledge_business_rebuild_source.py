"""Whole-source product boundaries using explicit response fixtures, never inference."""
from copy import deepcopy
import json
import socket

import pytest

from app.generation import model_input_budget
from app.knowledge import business_rebuild, business_rebuild_source, business_run
from app.knowledge.business_models import BusinessRunRequest, SourceRebuildPlanRequest
from app.knowledge.schemas import SourceRegistration, RunRequest
from app.knowledge.service import KnowledgeConflict
from app.tests.unit.test_knowledge_business import finish
from app.tests.unit.test_knowledge_business_rebuild_natural import natural


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(model_input_budget, 'count', lambda *a, **k: (None, 'fixture'))
    def deny(*a, **k):
        raise AssertionError('native/network calls are forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)


@pytest.fixture
def whole(natural):
    service, _, _, _, _, options, calls, _ = natural
    def register(name, text):
        result = service.register(name+'.md', text.encode(), SourceRegistration(
            title='명시 fixture '+name, publisher='fixture', namespace='fixture', external_id=name))
        vid = result['source_version_id']
        finish(service, service.start(RunRequest(source_version_ids=[vid]))['run_id'])
        return vid
    unchanged = register('one', '기관은 신청을 처리한다.')
    before = register('two', '관청은 허가를 처리한다.')
    after = register('two', '관청은 허가를 처리한다.\n단, 별도 검토가 필요하다.')
    options = dict(options, source_unit_policy='whole', conceptualize=False)
    parent = finish(service, service.start_business(BusinessRunRequest(
        source_version_ids=[unchanged, before], **options))['run_id'])
    with service.repository.connect() as db:
        parent = service.repository.get(db, 'runs', parent['id'])
    request = SourceRebuildPlanRequest(parent_run_id=parent['id'], before_version_id=before,
        after_version_id=after, rebuild_scope='whole_source')
    return service, parent, request, options, calls


def test_one_document_rebuild_preserves_other_document_raw_and_source_scope(whole):
    service, parent, request, options, calls = whole
    saved = deepcopy(parent)
    plan = business_rebuild.plan(service, request)
    assert business_rebuild.plan(service, request) == plan
    replacement = [request.after_version_id if v == request.before_version_id else v for v in parent['input_version_ids']]
    start = len(calls)
    result = service.start_business(BusinessRunRequest(source_version_ids=replacement,
        source_rebuild_plan_id=plan['id'], **options))
    run = finish(service, result['run_id'])
    assert run['status'] == 'succeeded', run.get('error')
    assert calls[start:] == ['entity_relation', 'event_entity', 'event_relation', 'direct_definitions']
    old = [c for c in parent['claims'] if request.before_version_id not in c['source_version_ids']]
    assert [c for c in run['claims'] if c['id'] in {c['id'] for c in old}] == old
    assert all(request.before_version_id not in c['source_version_ids'] for c in run['claims'])
    target = {b['id'] for b in run['blocks'] if b['source_version_id'] == request.after_version_id}
    assert set(run['source_rebuild']['target_block_ids']) == target
    assert run['source_rebuild']['whole_source_policy'] == business_rebuild_source.POLICY
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', parent['id']) == saved
    duplicate = service.start_business(BusinessRunRequest(source_version_ids=replacement,
        source_rebuild_plan_id=plan['id'], **options))
    assert duplicate['run_id'] == run['id'] and duplicate['duplicate_request']


def test_changed_producer_is_rejected_and_existing_plan_is_invalidated(whole):
    service, parent, request, *_ = whole
    plan = business_rebuild.plan(service, request)
    with service.repository.connect() as db:
        changed = deepcopy(parent)
        changed['units'][0]['messages'][1]['content'] += ' altered input'
        service.repository.save(db, 'runs', changed)
        with pytest.raises(KnowledgeConflict):
            business_rebuild.validate(service, db, plan)
    with pytest.raises(ValueError, match='실제 원문'):
        business_rebuild.plan(service, request)


def test_cross_document_read_cycle_and_empty_document_are_not_assumed_independent(whole):
    service, parent, request, *_ = whole
    with service.repository.connect() as db:
        version = service.repository.get(db, 'versions', request.before_version_id)
        old = service.parse_blocks(db, version['latest_parse_run_id'], version['id'])
        with pytest.raises(ValueError, match='전체 삭제'):
            business_rebuild_source.unit_plan(parent, request.before_version_id, request.after_version_id, old, [])
        mixed = deepcopy(parent)
        mixed['claims'][0]['source_version_ids'].append(request.before_version_id)
        with pytest.raises(ValueError, match='교차 근거'):
            business_rebuild_source.unit_plan(mixed, request.before_version_id, request.after_version_id, old, old)
        cyclic = deepcopy(parent)
        cyclic.update(id='cyclic', units=[], parent_run_id='cyclic')
        db.execute('INSERT INTO runs VALUES(?,?)', (cyclic['id'], json.dumps(cyclic)))
        with pytest.raises(ValueError, match='생산자'):
            business_rebuild_source.inventory(service, db, cyclic)


def test_diagnostic_order_keeps_original_hash_and_rejects_error_or_source_changes():
    stored = dict(id='fixture', conditions=['if fixture'], evidence=[dict(block_id='b', quote='source')],
        interpretation=dict(errors=['missing endpoint selector: Event', 'missing endpoint selector: Entity[1]'],
                            meanings=[dict(conditions=['first', 'second'])]))
    changed = deepcopy(stored)
    changed['interpretation']['errors'].reverse()
    differences = business_rebuild_source.verify_claims([stored], [changed])
    assert differences['fixture']['original_sha256'] != differences['fixture']['replay_sha256']
    assert stored['interpretation']['errors'][0].endswith('Event')
    for variant in ['add', 'remove', 'duplicate', 'conditions', 'address', 'meaning_order']:
        bad = deepcopy(changed)
        if variant == 'add': bad['interpretation']['errors'].append('new error')
        elif variant == 'remove': bad['interpretation']['errors'].pop()
        elif variant == 'duplicate': bad['interpretation']['errors'].append(bad['interpretation']['errors'][0])
        elif variant == 'conditions': bad['conditions'] = ['different']
        elif variant == 'address': bad['evidence'][0]['block_id'] = 'other'
        else: bad['interpretation']['meanings'][0]['conditions'].reverse()
        with pytest.raises(ValueError):
            business_rebuild_source.verify_claims([stored], [bad])
