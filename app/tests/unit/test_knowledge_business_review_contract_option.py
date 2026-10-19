"""Choose existing contracts through the real start service before enqueue."""
import pytest
from pydantic import ValidationError

from app.knowledge import autoschema, business_review, business_run
from app.knowledge.business_models import BusinessRunRequest
from app.knowledge.schemas import SourceRegistration, RunRequest
from app.knowledge.service import KnowledgeService


@pytest.fixture
def service_boundary(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    executor = service.executor
    queued = []
    monkeypatch.setattr(executor, 'submit', lambda fn, *args: queued.append((fn, args)))
    class Client:
        def __init__(self, *args): pass
        def identities(self, *args): return dict(draft='fixture', review='fixture')
        async def generate(self, *args): pytest.fail('This boundary must not execute a model')
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    vid = service.register('fixture.txt', '기관은 신청을 접수한다.'.encode(),
        SourceRegistration(title='fixture', publisher='fixture', namespace='test'))['source_version_id']
    parse_id = service.start(RunRequest(source_version_ids=[vid]))['run_id']
    service._execute(parse_id)
    queued.clear()
    try:
        yield service, vid, queued
    finally:
        service.closed = True
        executor.shutdown(wait=False, cancel_futures=True)


def saved(service, run_id):
    with service.repository.connect() as db:
        return service.repository.get(db, 'runs', run_id)


def parent_run(service, vid, contract):
    result = service.start_business(BusinessRunRequest(source_version_ids=[vid], repair=False, conceptualize=False))
    run = saved(service, result['run_id'])
    run.update(status='partial', finished_at='fixture-complete')
    run['recipe']['review_contract'] = contract
    # A historical parent need not have the new request option.
    run['recipe']['options'].pop('review_contract')
    claim = autoschema.graph_record(run['chunks'][0], 'entity_relation', dict(Head='기관', Relation='접수', Tail='신청'), 0)
    run['claims'] = [claim]; run['graph'] = autoschema.graph(run['claims'], run['blocks'])
    with service.repository.connect() as db:
        service.repository.save(db, 'runs', run)
    return run


@pytest.mark.parametrize('requested', [None, business_review.CONTRACT, business_review.SOURCE_APPLICATION_CONTRACT])
def test_start_persists_selected_contract_before_enqueue(service_boundary, requested):
    service, vid, queued = service_boundary
    result = service.start_business(BusinessRunRequest(source_version_ids=[vid], review_contract=requested))
    run = saved(service, result['run_id'])
    selected = requested or business_review.CONTRACT
    assert run['status'] == 'queued' and run['units'] == []
    assert run['recipe']['review_contract'] == run['recipe']['options']['review_contract'] == selected
    assert queued == [(business_run.execute, (service, run['id']))]


@pytest.mark.parametrize('parent_contract', [business_review.CONTRACT, business_review.SOURCE_APPLICATION_CONTRACT,
    'requirement-local-review-v4', business_review.MEANING_SELECTION_EXPERIMENT, None])
def test_unspecified_resume_inherits_exact_historical_contract(service_boundary, parent_contract):
    service, vid, queued = service_boundary
    parent = parent_run(service, vid, parent_contract); queued.clear()
    result = service.start_business(BusinessRunRequest(source_version_ids=[vid], resume_run_id=parent['id']))
    child = saved(service, result['run_id'])
    assert child['recipe']['review_contract'] == parent_contract
    assert child['recipe']['options']['review_contract'] == (parent_contract if parent_contract in
        {business_review.CONTRACT, business_review.SOURCE_APPLICATION_CONTRACT} else None)
    assert saved(service, parent['id']) == parent


@pytest.mark.parametrize('parent_contract,requested', [
    (business_review.CONTRACT, business_review.SOURCE_APPLICATION_CONTRACT),
    (business_review.SOURCE_APPLICATION_CONTRACT, business_review.CONTRACT),
    ('requirement-local-review-v4', business_review.CONTRACT),
    (business_review.MEANING_SELECTION_EXPERIMENT, business_review.SOURCE_APPLICATION_CONTRACT)])
def test_explicit_resume_mismatch_rejects_before_new_run_or_enqueue(service_boundary, parent_contract, requested):
    service, vid, queued = service_boundary
    parent = parent_run(service, vid, parent_contract); queued.clear()
    with pytest.raises(ValueError, match='부모 검수 계약'):
        service.start_business(BusinessRunRequest(source_version_ids=[vid], resume_run_id=parent['id'], review_contract=requested))
    assert queued == [] and saved(service, parent['id']) == parent
    with service.repository.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 2  # parse and parent only


@pytest.mark.parametrize('contract', [business_review.CONTRACT, business_review.SOURCE_APPLICATION_CONTRACT])
def test_explicit_matching_resume_is_allowed(service_boundary, contract):
    service, vid, _ = service_boundary
    parent = parent_run(service, vid, contract)
    result = service.start_business(BusinessRunRequest(source_version_ids=[vid], resume_run_id=parent['id'], review_contract=contract))
    child = saved(service, result['run_id'])
    assert child['recipe']['review_contract'] == child['recipe']['options']['review_contract'] == contract


@pytest.mark.parametrize('previous', [business_review.CONTRACT, business_review.MEANING_SELECTION_EXPERIMENT])
def test_explicit_reassessment_marks_new_profile_and_preserves_parent_and_candidates(service_boundary, previous):
    service, vid, _ = service_boundary
    parent = parent_run(service, vid, previous)
    result = service.start_business(BusinessRunRequest(source_version_ids=[vid], reassess_run_id=parent['id'],
        review_contract=business_review.SOURCE_APPLICATION_CONTRACT))
    child = saved(service, result['run_id'])
    assert child['id'] != parent['id'] and child['stored_pool']['approval_inherited'] is False
    assert child['claims'] == parent['claims'] and child['blocks'] == parent['blocks']
    assert child['stored_pool']['construction_recipe'] == parent['recipe']
    assert child['review_contract_change'] == dict(parent_run_id=parent['id'], previous=previous,
        selected=business_review.SOURCE_APPLICATION_CONTRACT, explicitly_requested=True)
    assert saved(service, parent['id']) == parent


def test_unrequested_contract_is_rejected_by_public_request_type():
    with pytest.raises(ValidationError):
        BusinessRunRequest(source_version_ids=['v'], review_contract=business_review.MEANING_SELECTION_EXPERIMENT)
