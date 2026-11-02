"""Fixed-input continuation fixtures; no real retrieval or model execution."""
from copy import deepcopy
import json

import pytest

from app.knowledge import business_run, business_use, concept_work, query_capacity_resume, selected_review_answer
from app.knowledge.business_models import QueryCapacityResume
from app.knowledge.service import KnowledgeService, KnowledgeConflict, encode
from app.tests.unit.test_knowledge_evidence_preservation import data, request as query_request, no_network
from app.tests.unit.test_knowledge_selected_review_answer import reviewed_source


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
        saved = client.get('/api/v1/knowledge/runs/'+response.json()['data']['run_id']).json()['data']
    assert saved['snapshot_id'] == parent['snapshot_id']
    assert saved.get('selected_review_context') == parent.get('selected_review_context')
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


@pytest.fixture(params=['plain', 'selected_review', 'review_scope'])
def failed(tmp_path, monkeypatch, request):
    snapshot, original, candidates, baseline, run = data()
    run['recipe']['options']['context_tokens'] = 49152
    run['model_identity'] = dict(review={})
    query = query_request()
    reviewed = None
    if request.param != 'plain':
        reviewed = reviewed_source(snapshot)
        if request.param == 'review_scope':
            from app.tests.unit.test_knowledge_answer_links import bounded_review
            scope = bounded_review()
            scope.update(required_claim_ids=['c2'], source_observations=reviewed['source_observations'])
            scope['source_observations'][0].update(target_id='observation', represented_content='Fixture cut',
                condition_state='present')
            reviewed = scope
        run['selected_review_context'] = deepcopy(reviewed)
        query = query_request(selected_review=dict(run_id='review', unit_id='u'),
            source_citation_contract='provided_review_scope_links_v1' if request.param == 'review_scope' else 'provided_source_quote_links_v1')
        # Mandatory input starts with c2's source; a baseline-only preview would move c1 first.
        snapshot['claims'].reverse()
        candidates.reverse()
    run['query'] = query.model_dump()
    monkeypatch.setattr(selected_review_answer, 'load', lambda *a: deepcopy(reviewed))
    monkeypatch.setattr(business_run, 'request_budget', lambda run, messages, schema, cap:
        dict(estimate_tokens=49153 if len(json.loads(messages[-1]['content'])['context']) > 1 else 1))
    with pytest.raises(ValueError, match='mandatory_capacity'):
        business_use.preserved_graph_hits(run, snapshot, original, query, candidates, baseline)
    packet = run['evidence_assembly']['rejected_input']['request']
    limits = dict(max_tokens=8192, context_tokens=49152, think=False)
    run.update(id='failed', kind='business_query', status='failed', error='mandatory_capacity',
        query=query.model_dump(), context_mode='graph', snapshot_id='s', answer_basis='reviewed_claims',
        answer_contract=business_use.ANSWER_CONTRACT,
        execution_boundary={}, units=[dict(id='selector', stage='graph_retrieval_filter', status='succeeded',
            requested_limits=limits, executed_limits=limits,
            response=dict(text='fixture selection', done=True, done_reason='stop', failure_kind=None))])
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
    assert saved['source_reference_order'] == parent['evidence_assembly']['rejected_input']['state']['source_reference_order']
    if parent.get('selected_review_context'):
        assert saved['selected_review_context'] == parent['selected_review_context']
        assert [json.loads(ref)['block_id'] for ref in saved['source_reference_order']] == ['b2', 'b1', 'reviewed-title']
        assert 'reviewed-title' in packet['reference_map']
        assert selected_review_answer.INSTRUCTION in packet['messages'][0]['content']
    assert service.run(parent['id'])['evidence_assembly'] == parent['evidence_assembly']
    assert query_capacity_resume.start(service, parent['id'], payload)['duplicate_request']
    assert seen == ['business_qa']
    with service.repository.connect() as db:
        assert service.repository.get(db, 'snapshots', snapshot['id']) == snapshot
        assert db.execute('SELECT count(*) FROM decisions').fetchone()[0] == 0


@pytest.mark.parametrize('failed', [True], indirect=True)
def test_changed_review_blocks_without_qa_or_child(failed, monkeypatch):
    service, parent, _, _, payload = failed
    monkeypatch.setattr(selected_review_answer, 'load', lambda *a: dict(parent['selected_review_context'], changed=True))
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: pytest.fail('No QA permitted'))
    with pytest.raises(KnowledgeConflict, match='선택한 검수 결과'):
        query_capacity_resume.start(service, parent['id'], payload)
    with service.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0] == 2


@pytest.mark.parametrize('failed', [True], indirect=True)
def test_review_changed_during_resumed_qa_withholds_answer(failed, monkeypatch):
    service, parent, _, packet, payload = failed
    def generate(svc, child, stage, instruction, body, schema, **kw):
        assert business_run.json_request(child, stage, instruction, body, schema, **kw) == packet
        monkeypatch.setattr(selected_review_answer, 'load', lambda *a: dict(parent['selected_review_context'], changed=True))
        return dict(answer='Explicit fixture', choice=None, citations=['c2'], limitations=[])
    monkeypatch.setattr(business_run, 'json_call', generate)
    reply = query_capacity_resume.start(service, parent['id'], payload)
    assert reply['status'] == 'needs_review' and reply['answer'] is None
    saved = service.run(reply['run_id'])
    assert saved['selected_review_error'] == 'selected_review_input_changed'
    assert saved['answer_source_citations']['citations'] == []


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
