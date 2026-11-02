"""Output contract checks; all generation is a stub or mocked HTTP, never a native call."""
import asyncio
from copy import deepcopy
import json

import httpx
import pytest

from app.generation.model_client import ModelClient
from app.knowledge import autoschema, business_concepts, business_run, business_use, concept_work
from app.knowledge.business_models import ConceptRunRequest
from app.tests.unit.test_knowledge_concept_source_map_entrypoints import environment, pool, plans, store


@pytest.fixture(autouse=True)
def no_tokenizer_network(monkeypatch):
    monkeypatch.setattr('app.generation.model_input_budget.count', lambda *a, **k: (None, 'fixture'))


@pytest.mark.parametrize('text', [
    '설명: 식재료, 식품', '설명: ["식재료"]', '```json\n["식재료"]\n```',
    '"식재료"', '{"concepts":["식재료"]}', '["식재료", 1]', '[null]', '[]', '[""]', '[" "]',
    '["식재료"] trailing', '["식재료",',
])
def test_invalid_output_is_preserved_but_cannot_be_stored_as_concepts(environment, monkeypatch, text):
    service, requests = environment
    parent = pool('v'); store(service, parent)
    original = business_run.ModelClient.generate
    async def invalid(self, request, cancelled=None):
        response = await original(self, request, cancelled)
        # A valid parsed field must not hide a malformed raw response.
        response.update(text=text, parsed=['식재료'])
        return response
    monkeypatch.setattr(business_run.ModelClient, 'generate', invalid)
    target = autoschema.concept_targets(parent['graph'])[0]
    child = business_concepts.start(service, ConceptRunRequest(parent_run_id=parent['id'], target_ids=[target['id']], neighbor_mode='plain'))
    assert len(requests) == 1 and child['status'] == 'partial'
    assert child['concepts'][0]['concepts'] == [] and child['concepts'][0]['status'] == 'failed'
    unit = child['units'][0]
    assert unit['response']['text'] == text and unit['error'] == 'invalid_concept_output'
    assert not concept_work.complete(unit)
    assert not any(business_use.concept_hints(dict(claims=parent['claims'], concepts=child['concepts'])).values())
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', parent['id']) == parent
        assert service.repository.get(db, 'runs', child['id']) == child


def test_strict_array_keeps_label_boundaries_and_legacy_consumer():
    schema = autoschema.concept_schema(autoschema.CONCEPT_OUTPUT_CONTRACT)
    assert autoschema.concepts('[" 식품 ", "식품", "A, B"]', schema=schema) == ['식품', 'a, b']
    assert autoschema.concepts('식품, 식재료, 식품') == ['식품', '식재료']
    assert autoschema.concepts('설명: 식품, 식재료') == ['설명: 식품', '식재료']


def test_new_product_request_does_not_reuse_legacy_and_reuses_only_matching_array(environment):
    service, requests = environment
    parent = pool('v'); store(service, parent)
    old_item = plans(parent)[0]
    old = business_concepts.apply(service, parent, old_item)
    old['status'] = parent['concept_bindings'][0]['status'] = 'accepted'
    business_run.save(service, parent); before = deepcopy(parent)
    request = ConceptRunRequest(parent_run_id=parent['id'], target_ids=[old_item['target']['id']], neighbor_mode='plain')
    _, planned = business_concepts.plan(service, request)
    child = business_concepts.start(service, request)
    unit = child['units'][0]
    assert child['status'] == 'succeeded' and len(requests) == 2 and not unit.get('reused_from')
    assert unit['schema'] == planned[0]['schema'] == autoschema.concept_schema(autoschema.CONCEPT_OUTPUT_CONTRACT)
    assert unit['concept_work_input']['schema_sha256'] == concept_work.digest(unit['schema'])
    assert planned[0]['selection'] == old_item['selection']
    assert unit['input_budget']['estimate_tokens'] == business_run.request_tokens(unit['messages'], unit['schema'], 512)
    assert child['concepts'][0]['concepts'] == ['테스트 유형'] and not child['concepts'][0]['approved_is_a']
    reused = business_concepts.start(service, request.model_copy(update=dict(donor_run_id=child['id'])))
    assert reused['status'] == 'succeeded' and len(requests) == 2
    assert reused['units'][0]['reused_from']['run_id'] == child['id']
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', parent['id']) == before
        view, _ = business_use.concept_read_view(service, db, parent, child['id'])
        assert view[-1]['concepts'] == ['테스트 유형']
        child['concepts'][0]['concepts'] = ['not in raw response']
        service.repository.save(db, 'runs', child)
        with pytest.raises(ValueError):
            business_use.concept_read_view(service, db, parent, child['id'])


def test_actual_ollama_payload_has_generation_schema_and_unchanged_source(environment):
    service, requests = environment
    parent = pool('v'); store(service, parent)
    target = autoschema.concept_targets(parent['graph'])[0]
    business_concepts.start(service, ConceptRunRequest(parent_run_id=parent['id'], target_ids=[target['id']], neighbor_mode='plain'))
    request = requests[0]; payloads = []
    def respond(http_request):
        payloads.append(json.loads(http_request.content))
        return httpx.Response(200, json=dict(message=dict(content='["식재료", "식품"]'), done=True, done_reason='stop'))
    client = ModelClient(dict(provider='ollama', endpoint='http://127.0.0.1:11434'), transport=httpx.MockTransport(respond))
    response = asyncio.run(client.generate(request))
    assert response['parsed'] == ['식재료', '식품'] and response['failure_kind'] is None
    assert payloads[0]['format'] == request.schema and payloads[0]['messages'] == request.messages
    assert '기관은 신청을 접수한다.' in request.messages[-1]['content']
    assert 'Your answer: ["movie", "film"]' in request.messages[-1]['content']
    assert 'phrases1, phrases2' not in request.messages[-1]['content']


def test_concept_validation_does_not_change_completed_retrieval_unit():
    unit = dict(stage='graph_retrieval_filter', schema=dict(type='object'), status='succeeded',
        response=dict(text='{"relations":[]}', done=True, done_reason='stop', failure_kind=None))
    assert concept_work.complete(unit)
