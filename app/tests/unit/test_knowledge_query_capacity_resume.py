"""Fixed-input continuation fixtures; no real retrieval or model execution."""
import pytest

from app.knowledge import business_run, business_use, concept_work, query_capacity_resume
from app.knowledge.business_models import QueryCapacityResume
from app.knowledge.service import KnowledgeService, KnowledgeConflict, encode
from app.tests.unit.test_knowledge_evidence_preservation import data, request


def test_existing_hippo_resume_api_never_repeats_retrieval(failed, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers import knowledge
    from app.core.config import settings
    from app.knowledge import graph_retrieval
    service, parent, _, packet, payload = failed
    monkeypatch.setattr(settings, 'KNOWLEDGE_ENABLED', True)
    monkeypatch.setattr(graph_retrieval, 'retrieve', lambda *a, **k: pytest.fail('No new retrieval'))
    seen = []
    def stored_qa(svc, child, stage, instruction, body, schema, **kw):
        assert stage == 'business_qa'
        assert business_run.json_request(child, stage, instruction, body, schema, **kw) == packet
        seen.append(stage)
        return dict(answer='Explicit fixture', choice=None, citations=['c2'], limitations=['Fixture only'])
    monkeypatch.setattr(business_run, 'json_call', stored_qa)
    app = FastAPI(); app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    with TestClient(app) as client:
        response = client.post('/api/v1/knowledge/business/runs/failed/capacity-resumes', json=payload.model_dump())
    assert response.status_code == 200 and response.json()['data']['status'] == 'answered'
    assert seen == ['business_qa']
    assert service.run(parent['id'])['query']['retrieval'] == 'hipporag2'


def test_legacy_hg_source_query_does_not_gain_capacity_resume(failed):
    from app.knowledge.business_models import BusinessQuery
    service, parent, _, _, payload = failed
    parent['query'] = BusinessQuery(source_run_id='origin', question='과거 원문', retrieval='hybrid_graph').model_dump()
    with service.repository.connect() as db:
        db.execute('UPDATE runs SET payload=? WHERE id=?', (encode(parent), parent['id']))
    payload = payload.model_copy(update=dict(expected_parent_fingerprint=concept_work.digest(parent)))
    with pytest.raises(ValueError, match='필수 입력 용량 실패'):
        query_capacity_resume.start(service, parent['id'], payload)
    with service.repository.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 2


@pytest.fixture
def failed(tmp_path, monkeypatch):
    snapshot, original, candidates, baseline, run = data()
    run['recipe']['options']['context_tokens'] = 49152
    run['model_identity'] = dict(review={})
    hits = baseline + [dict(block_id='c2', file_id='v', score=.8)]
    base = business_use.graph_qa_input(snapshot, original, run['recipe'], request(), candidates, baseline, [])[0]
    state, body, schema, refs = business_use.graph_qa_input(
        snapshot, original, run['recipe'], request(), candidates, hits, base['source_reference_order'])
    packet = business_run.json_request(run, 'business_qa', business_use.SYNTHESIS_PROMPT
        + business_use.REVIEWED_MEANINGS_PROMPT, body, schema, reference_map=refs)
    limits = dict(max_tokens=8192, context_tokens=49152, think=False)
    run.update(id='failed', kind='business_query', status='failed', error='mandatory_capacity',
        query=request().model_dump(), context_mode='graph', snapshot_id='s', answer_basis='reviewed_claims',
        answer_contract=business_use.ANSWER_CONTRACT,
        execution_boundary={}, units=[dict(id='selector', stage='graph_retrieval_filter', status='succeeded',
            requested_limits=limits, executed_limits=limits,
            response=dict(text='fixture selection', done=True, done_reason='stop', failure_kind=None))],
        evidence_assembly=dict(failure_kind='mandatory_capacity', baseline_claim_ids=['c1'],
            mandatory_claim_ids=['c1','c2'], rejected_input=dict(hits=hits, state=state, request=packet)))
    run['graph_retrieval']['contract'] = 'fixture graph'
    service = KnowledgeService(tmp_path/'knowledge.db')
    with service.repository.connect() as db:
        for table, row in [('runs', original), ('runs', run), ('snapshots', snapshot)]:
            db.execute('INSERT INTO '+table+' VALUES(?,?)', (row['id'], encode(row)))
    monkeypatch.setattr(business_run.ModelClient, 'identities', lambda *a, **k: dict(review={}))
    payload = QueryCapacityResume(expected_parent_fingerprint=concept_work.digest(run),
        expected_snapshot_fingerprint=concept_work.digest(snapshot), expected_packet_fingerprint=concept_work.digest(packet),
        context_tokens=57344)
    yield service, run, snapshot, packet, payload
    service.shutdown()


def test_resume_uses_same_packet_common_storage_and_is_idempotent(failed, monkeypatch):
    service, parent, snapshot, packet, payload = failed
    seen = []
    def generate(svc, child, stage, instruction, body, schema, **kw):
        actual = business_run.json_request(child, stage, instruction, body, schema, **kw)
        assert actual == packet and stage == 'business_qa'
        assert child['recipe']['options']['context_tokens'] == 49152
        assert child['recipe']['options']['qa_context_tokens'] == 57344
        assert child['units'] == [] and child['preserved_retrieval_units'] == parent['units']
        seen.append(stage)
        return dict(answer='Explicit fixture', choice=None, citations=['c2'], limitations=['Fixture only'])
    monkeypatch.setattr(business_run, 'json_call', generate)
    reply = query_capacity_resume.start(service, parent['id'], payload)
    assert reply['status'] == 'answered' and seen == ['business_qa']
    saved = service.run(reply['run_id'])
    assert saved['provided_ids'] == ['c1','c2'] and saved['answer']['citations'] == ['c2']
    assert saved['capacity_resume']['optional_additions'] == 0
    assert service.run(parent['id'])['evidence_assembly'] == parent['evidence_assembly']
    assert query_capacity_resume.start(service, parent['id'], payload)['duplicate_request']
    assert seen == ['business_qa']


@pytest.mark.parametrize('field', ['expected_parent_fingerprint','expected_snapshot_fingerprint','expected_packet_fingerprint'])
def test_changed_inputs_block_without_qa_or_child(failed, monkeypatch, field):
    service, parent, _, _, payload = failed
    setattr(payload, field, 'stale')
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: pytest.fail('No QA permitted'))
    with pytest.raises(KnowledgeConflict):
        query_capacity_resume.start(service, parent['id'], payload)
    with service.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0] == 2


def test_current_source_correction_blocks_saved_input(failed, monkeypatch):
    service, parent, snapshot, _, payload = failed
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshot_events VALUES(?,?)', ('changed', encode(dict(
            event='business_correction', snapshot_id=snapshot['id'], claim_ids=['c1'], requirement_ids=[]))))
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: pytest.fail('No QA permitted'))
    with pytest.raises(KnowledgeConflict):
        query_capacity_resume.start(service, parent['id'], payload)


@pytest.mark.parametrize('stage,exact,calls,error', [
    ('business_qa', True, [57344], None),
    ('graph_retrieval_filter', True, [], 'input_capacity'),
    ('business_qa', False, [], 'input_count_unverified')])
def test_qa_only_limit_override_and_exact_count_guard(failed, monkeypatch, stage, exact, calls, error):
    service, run, _, _, _ = failed
    run['units'] = []
    run['capacity_resume'] = dict(parent_run_id='fixture')
    run['recipe']['options']['qa_context_tokens'] = 57344
    run['metrics'] = dict(llm_calls=0, model_total_s=0)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_run, 'request_budget', lambda *a, **k:
        dict(estimate_tokens=51974, prompt_exact=exact))
    seen = []
    async def generate(client, request, cancelled):
        seen.append(request.context_tokens)
        return dict(failure_kind=None, elapsed_s=0)
    monkeypatch.setattr(business_run.ModelClient, 'generate', generate)
    business_run.call(service, run, stage, [], review=True)
    assert seen == calls and run['units'][-1]['error'] == error
