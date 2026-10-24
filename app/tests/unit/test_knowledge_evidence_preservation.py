"""Explicit fixtures; no model, embedding network or semantic-quality evaluation."""
from copy import deepcopy
import json
import socket

import httpx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import knowledge
from app.core.config import settings
from app.generation import model_input_budget
from app.generation.model_client import ModelClient
from app.knowledge import business_run, business_use as use, graph_retrieval as gr
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService

OPTION = 'ranked_preserved_claims_v2'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*a, **kw):
        raise AssertionError('Network/model/embedding calls are forbidden')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(model_input_budget, 'count', lambda *a, **kw: (None, 'explicit_fixture_no_counter'))
    monkeypatch.setattr(ModelClient, 'identities', denied)
    monkeypatch.setattr(ModelClient, 'execution_identity', denied)


def data():
    claims, blocks = [], []
    for i in range(5):
        text = 'Fixture fact ' + str(i)
        blocks.append(dict(id=f'b{i}', source_version_id='v', parse_run_id='p', text=text))
        claims.append(dict(id=f'c{i}', chunk_id=f'ch{i}', role='entity_relation', raw=dict(Head=f'item{i}', Relation='has', Tail=text),
            statement=text, source_version_ids=['v'], review_status='accepted', semantic_status='unknown',
            conditions=['fixture condition'], exceptions=[], period='', references=[],
            interpretation=dict(contract='fixture', semantic_status='unverified', errors=['inherited fixture error']),
            evidence=[dict(block_id=f'b{i}', source_version_id='v', parse_run_id='p', start_char=0,
                end_char=len(text), quote=text, precision='chunk')]))
    snapshot = dict(id='s', kind='source_graph', run_id='origin', claims=claims, blocks=blocks,
        concepts=[], requirements=[], assessments={}, source_versions={'v': dict(title='Fixture source')})
    recipe = dict(generation=dict(provider='ollama', endpoint='http://127.0.0.1:11434'),
        models=dict(review='fixture:local', draft='fixture:local'), options=dict(context_tokens=100000,
        review_tokens=8192, extraction_tokens=8192, think=False, timeout=30))
    original = dict(id='origin', kind='business', status='succeeded', units=[], recipe=recipe, model_identity={})
    candidates = [dict(id=c['id'], text=json.dumps(business_run.compact_claim(c), ensure_ascii=False),
        file_id='v', source_group='v') for c in claims]
    ranked = [dict(id='passage'+str(i), score=1.-i/10, evidence=claims[i]['evidence'][0],
        claim_ids=[claims[i]['id']]) for i in [1, 2, 0, 3, 4]]
    baseline = [dict(block_id='c1', file_id='v', score=.9, passage_id='passage1', selection_reason='hipporag2')]
    run = dict(recipe=recipe, model_identity={}, graph_retrieval=dict(ranked_passages=ranked,
        selected_factual_claim_ids=['c2']), units=[], metrics=dict(llm_calls=0, model_total_s=0))
    return snapshot, original, candidates, baseline, run


def request(**kw):
    return BusinessQuery(snapshot_id='s', question='Fixture question', limit=1, evidence_union=OPTION, **kw)


def test_first_excess_rolls_back_all_state_without_skipping(monkeypatch):
    snapshot, original, candidates, baseline, run = data()
    before = deepcopy(snapshot)
    monkeypatch.setattr(business_run, 'request_budget', lambda run, messages, schema, cap:
        dict(estimate_tokens=len(json.loads(messages[1]['content'])['context'])*10))
    run['recipe']['options']['context_tokens'] = 30
    hits = use.preserved_graph_hits(run, snapshot, original, request(), candidates, baseline)
    assert [h['block_id'] for h in hits] == ['c1', 'c2', 'c0']
    trace = run['evidence_assembly']
    assert trace['stopped_at_first_capacity_excess'] and len(trace['steps']) == 4
    assert trace['steps'][-1]['claim_ids'] == ['c1', 'c2', 'c0', 'c3']
    assert 'c4' not in trace['steps'][-1]['claim_ids']
    state, body, schema, refs = use.graph_qa_input(snapshot, original, run['recipe'], request(), candidates,
        hits, run['source_reference_order'])
    packet = business_run.json_request(run, 'business_qa', use.SYNTHESIS_PROMPT + use.REVIEWED_MEANINGS_PROMPT,
        body, schema, reference_map=refs)
    assert trace['request_fingerprint'] == business_run.autoschema.identifier('qa_input', packet)
    assert all(run[k] == v for k, v in state.items())
    assert all('b3' not in json.loads(key)['block_id'] for key in run['source_reference_order'])
    assert [c['id'] for c in body['context']] == ['c0', 'c1', 'c2']  # Original candidate order.
    assert [v['id'] for v in body['source_evidence']] == ['b1', 'b2', 'b0']
    assert snapshot == before and run['units'] == []


@pytest.mark.parametrize('contract', [None, 'provided_source_quotes_v1', 'provided_source_quote_links_v1'])
def test_combined_quote_contract_has_identical_preview_and_final_qa_input(monkeypatch, contract):
    snapshot, original, candidates, baseline, run = data()
    query = request(candidate_contract='r2_g1_w1', source_citation_contract=contract)
    run['query'] = query.model_dump()
    monkeypatch.setattr(business_run, 'request_budget', lambda *args: dict(estimate_tokens=1))
    hits = use.preserved_graph_hits(run, snapshot, original, query, candidates, baseline)
    _, body, schema, refs = use.graph_qa_input(snapshot, original, run['recipe'], query, candidates,
        hits, run['source_reference_order'])
    packet = business_run.json_request(run, 'business_qa',
        use.SYNTHESIS_PROMPT + use.REVIEWED_MEANINGS_PROMPT + use.source_citations_instruction(contract),
        body, schema, reference_map=refs)
    assert run['evidence_assembly']['request_fingerprint'] == business_run.autoschema.identifier('qa_input', packet)
    assert ('source_citations' in packet['schema']['properties']) == bool(contract)
    assert ('answer_links' in packet['schema']['properties']) == (contract == 'provided_source_quote_links_v1')
    assert run['units'] == []


@pytest.mark.parametrize('capacity', [0, 10])
def test_baseline_or_mandatory_overflow_is_not_silently_reduced(monkeypatch, capacity):
    snapshot, original, candidates, baseline, run = data()
    monkeypatch.setattr(business_run, 'request_budget', lambda r, m, s, cap:
        dict(estimate_tokens=len(json.loads(m[1]['content'])['context'])*10))
    run['recipe']['options']['context_tokens'] = capacity
    with pytest.raises(ValueError, match='mandatory_capacity'):
        use.preserved_graph_hits(run, snapshot, original, request(), candidates, baseline)
    assert 'source_reference_order' not in run and 'reviewed_meanings' not in run
    assert run['evidence_assembly']['mandatory_claim_ids'] == ['c1', 'c2']
    assert run['units'] == []


@pytest.mark.parametrize('broken', ['missing_rank', 'not_accepted', 'wrong_parse', 'wrong_quote'])
def test_unrepresentable_selected_fact_or_address_fails(monkeypatch, broken):
    snapshot, original, candidates, baseline, run = data()
    if broken == 'missing_rank':
        run['graph_retrieval']['selected_factual_claim_ids'] = ['absent']
    elif broken == 'not_accepted':
        snapshot['claims'][2]['review_status'] = 'rejected'
    else:
        snapshot['claims'][2]['evidence'][0]['parse_run_id' if broken == 'wrong_parse' else 'quote'] = 'absent'
    with pytest.raises(ValueError):
        use.preserved_graph_hits(run, snapshot, original, request(), candidates, baseline)
    assert run['units'] == [] and 'source_reference_order' not in run


@pytest.mark.parametrize('change', [dict(source_run_id='source', snapshot_id=None), dict(retrieval='bm25'),
    dict(retrieval='dense'), dict(answer_mode='source_quotes'), dict(requirement_ids=['r']),
    dict(evidence_union='selected_factual_claims_v1')])
def test_unsupported_contracts_are_rejected(change):
    values = dict(snapshot_id='s', question='fixture', evidence_union=OPTION)
    values.update(change)
    with pytest.raises(ValueError):
        BusinessQuery(**values)


def test_new_disconnected_span_is_appended_even_in_same_block():
    def row(block, start, quote, cid):
        return dict(evidence=dict(block_id=block, source_version_id='v', parse_run_id='p',
            start_char=start, end_char=start+len(quote), quote=quote, precision='chunk'), claim_ids=[cid])
    old = [row('b', 10, 'old', 'c1'), row('other', 0, 'other', 'c2')]
    before, order = use.source_evidence_views(old, [])
    after, actual_order = use.source_evidence_views([row('b', 0, 'new', 'c0'), *old], order)
    assert after[:2] == before and after[2]['span'] == [0, 3]
    assert actual_order[:len(order)] == order
    assert after[2]['claim_references'][0]['precision'] == 'chunk'


def test_meaning_bundle_expansion_preserves_old_claim_scope_and_unknown():
    snapshot, original, candidates, baseline, run = data()
    snapshot['requirements'] = original['requirements'] = [dict(id='r')]
    meaning = dict(key='m', statement='Fixture scope', conditions=['if fixture'], exceptions=[], period='',
        references=[], source_status='unknown', availability='provided', record_error='inherited',
        evidence=deepcopy(snapshot['claims'][1]['evidence']))
    snapshot['assessments'] = dict(r=dict(id='assessment', status='unknown', source=dict(meanings=[meaning]),
        representation=dict(checks=[dict(meaning_key='m', status='partial', claim_ids=['c1', 'c2'],
            claim_support=dict(c1='unknown', c2='unknown'))])))
    before = use.graph_qa_input(snapshot, original, run['recipe'], request(), candidates, baseline, [])[0]['reviewed_meanings'][0]
    after = use.graph_qa_input(snapshot, original, run['recipe'], request(), candidates,
        baseline+[dict(block_id='c2')], [])[0]['reviewed_meanings'][0]
    assert before['claim_ids'] == ['c1'] and after['claim_ids'] == ['c1', 'c2']
    for field in before.keys()-{'claim_ids', 'claim_support', 'complete_claim_bundle'}:
        assert before[field] == after[field]
    assert after['claim_support']['c1'] == before['claim_support']['c1'] == 'unknown'
    assert before['complete_claim_bundle'] is False and after['complete_claim_bundle'] is True
    assert after['source_status'] == 'unknown' and after['record_error'] == 'inherited'


def fixture_service(tmp_path, monkeypatch):
    snapshot, original, _, _, _ = data()
    original['graph'] = business_run.autoschema.graph(snapshot['claims'])
    service = KnowledgeService(tmp_path/'knowledge.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)', (snapshot['id'], json.dumps(snapshot)))
        db.execute('INSERT INTO runs VALUES(?,?)', (original['id'], json.dumps(original)))
    wires = []
    def handler(req):
        payload = json.loads(req.content); wires.append(payload)
        body = json.loads(payload['messages'][1]['content'])
        if 'candidate_facts' in body:
            output = dict(selected_ids=[body['candidate_facts'][0]['id']])
        elif 'candidate_fact_groups' in body:
            output = dict(selected_ids=[body['candidate_fact_groups'][0]['members'][0]['id']])
        else:
            output = dict(answer='Explicit fixture response', choice=None,
                citations=[body['context'][0]['id']], limitations=['Fixture, not model evidence'])
            properties = payload['format']['properties']
            if 'source_citations' in properties:
                ref = body['source_evidence'][0]
                output['source_citations'] = [dict(evidence_ref=ref['id'], quote=ref['text'])]
            if 'answer_links' in properties:
                output['source_citations'][0]['quote_id'] = 'sq_fixture'
                output['answer_links'] = [dict(target='answer', anchor=output['answer'],
                    claim_refs=output['citations'], quote_refs=['sq_fixture'])]
        return httpx.Response(200, json=dict(message=dict(content=json.dumps(output)), done=True, done_reason='stop'))
    init = ModelClient.__init__
    monkeypatch.setattr(ModelClient, '__init__', lambda self, config=None, **kw:
        init(self, config, transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(gr, 'embed', lambda texts, **kw: np.asarray([[1., float(len(t)%7+1)] for t in texts]))
    monkeypatch.setattr(settings, 'KNOWLEDGE_ENABLED', True)
    app = FastAPI(); app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    return service, TestClient(app), wires


def test_actual_api_common_dispatch_restore_store_and_question_isolation(tmp_path, monkeypatch):
    service, client, wires = fixture_service(tmp_path, monkeypatch)
    try:
        first = client.post('/api/v1/knowledge/business/search', json=request().model_dump())
        assert first.status_code == 200, first.text
        reply = first.json()['data']; assert reply['status'] == 'answered', reply
        saved = client.get('/api/v1/knowledge/runs/'+reply['run_id']).json()['data']
        assert len(reply['retrieval']) == 5 and len(wires) == 2
        assert saved['counts']['succeeded'] == 2 and len(saved['units']) == 2
        assert saved['graph_retrieval']['selected_factual_claim_ids']
        assert set(saved['graph_retrieval']['selected_factual_claim_ids']) <= set(saved['provided_ids'])
        assert reply['answer']['citations'][0].startswith('c')
        assert saved['units'][-1]['input_budget']['fallback_reason'] == 'explicit_fixture_no_counter'
        with service.repository.connect() as db:
            stored = service.repository.get(db, 'runs', reply['run_id'])
        assert {k:v for k,v in saved.items() if k!='counts'} == stored
        second = client.post('/api/v1/knowledge/business/search', json=dict(snapshot_id='s', question='Another fixture', limit=1,
            candidate_contract=None, evidence_union=None, source_citation_contract=None))
        assert second.json()['data']['status'] == 'answered'
        other = service.run(second.json()['data']['run_id'])
        assert len(other['retrieval']) == 1 and 'source_reference_order' not in other and 'evidence_assembly' not in other
    finally:
        service.executor.shutdown(wait=True)


def test_candidate_and_preservation_options_share_the_api_without_quote_contract(tmp_path, monkeypatch):
    service, client, wires = fixture_service(tmp_path, monkeypatch)
    try:
        with service.repository.connect() as db:
            original = service.repository.get(db, 'runs', 'origin')
            snapshot = service.repository.get(db, 'snapshots', 's')
            original['graph'] = business_run.autoschema.graph(snapshot['claims'])
            db.execute('UPDATE runs SET payload=? WHERE id=?', (json.dumps(original), 'origin'))
        response = client.post('/api/v1/knowledge/business/search', json=request(candidate_contract='r2_g1_w1').model_dump())
        reply = response.json()['data']
        assert reply['status'] == 'answered', reply
        saved = service.run(reply['run_id'])
        assert saved['query']['candidate_contract'] == 'r2_g1_w1'
        assert saved['query']['source_citation_contract'] is None
        assert saved['evidence_assembly']['final_claim_ids']
        assert 'candidate_fact_groups' in json.loads(wires[0]['messages'][1]['content'])
        assert 'source_citations' not in wires[-1]['format']['properties']
        assert 'answer_links' not in saved
        assert len(wires) == 2
    finally:
        service.executor.shutdown(wait=True)


@pytest.mark.parametrize('options,defaulted', [
    ({}, ['candidate_contract', 'evidence_union', 'source_citation_contract']),
    (dict(candidate_contract=None, evidence_union=None, source_citation_contract=None), []),
    (dict(candidate_contract=None, evidence_union=None), ['source_citation_contract']),
    (dict(source_citation_contract=None), ['candidate_contract', 'evidence_union']),
])
def test_raw_json_defaults_are_recorded_in_reply_and_saved_run(tmp_path, monkeypatch, options, defaulted):
    service, client, wires = fixture_service(tmp_path, monkeypatch)
    before = dict(options)
    try:
        response = client.post('/api/v1/knowledge/business/search',
            json=dict(snapshot_id='s', question='Explicit fixture question', limit=1, **options))
        assert response.status_code == 200, response.text
        reply = response.json()['data']
        assert reply['status'] == 'answered', reply
        saved = service.run(reply['run_id'])
        boundary = reply['execution_boundary']
        assert boundary == saved['execution_boundary']
        assert boundary['defaulted_query_fields'] == defaulted
        assert boundary['query_contracts'] == {k: saved['query'][k] for k in
            ('candidate_contract', 'evidence_union', 'source_citation_contract')}
        assert all(saved['query'][key] == value for key, value in options.items())
        assert all(saved['query'][key] is not None for key in defaulted)
        assert saved['answer']['answer'] == 'Explicit fixture response'
        assert len(wires) == 2
        with service.repository.connect() as db:
            stored = service.repository.get(db, 'runs', reply['run_id'])
        assert stored['query'] == saved['query']
        assert options == before
    finally:
        service.executor.shutdown(wait=True)


def test_api_mandatory_capacity_saves_failure_without_qa(tmp_path, monkeypatch):
    service, client, wires = fixture_service(tmp_path, monkeypatch)
    try:
        with service.repository.connect() as db:
            snapshot = service.repository.get(db, 'snapshots', 's')
            for claim in snapshot['claims']:
                claim['conditions'] = ['X' * 200000]
            db.execute('UPDATE snapshots SET payload=? WHERE id=?', (json.dumps(snapshot), 's'))
        response = client.post('/api/v1/knowledge/business/search', json=request().model_dump())
        reply = response.json()['data']; assert reply['status'] == 'input_capacity', reply
        assert reply['qa_model_called'] is False and len(wires) == 1
        saved = service.run(reply['run_id'])
        assert saved['status'] == 'failed' and saved['answer'] is None
        assert saved['evidence_assembly']['failure_kind'] == 'mandatory_capacity'
        assert len(saved['units']) == 1 and saved['units'][0]['stage'] == 'graph_retrieval_filter'
    finally:
        service.executor.shutdown(wait=True)


def test_api_bad_address_saves_failure_without_qa(tmp_path, monkeypatch):
    service, client, wires = fixture_service(tmp_path, monkeypatch)
    try:
        with service.repository.connect() as db:
            snapshot = service.repository.get(db, 'snapshots', 's')
            snapshot['claims'][2]['evidence'][0]['parse_run_id'] = 'different-parse'
            db.execute('UPDATE snapshots SET payload=? WHERE id=?', (json.dumps(snapshot), 's'))
        response = client.post('/api/v1/knowledge/business/search', json=request().model_dump())
        reply = response.json()['data']; assert reply['status'] == 'evidence_assembly_failed', reply
        assert reply['qa_model_called'] is False and len(wires) == 1
        assert service.run(reply['run_id'])['status'] == 'failed'
    finally:
        service.executor.shutdown(wait=True)
