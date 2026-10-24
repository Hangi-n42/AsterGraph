"""Synthetic stored-delivery tests, never model or semantic-quality evaluation."""
from copy import deepcopy
from hashlib import sha256
import json
import socket

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.knowledge import business_use, source_after_conditions as after, source_timing_consumer as timing, workbench
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService, KnowledgeConflict
from app.tests.unit.test_knowledge_source_list_service import case


@pytest.fixture
def stored(case, monkeypatch):
    service, snapshot, _, _ = case
    text = '1. 공통은 삶아 찬물에 담근 후 껍질을 벗긴다. 2. 팬에 기름을 두른다.\n'
    block = next(b for b in snapshot['blocks'] if b['id'] == 'method'); block['text'] = text
    with service.repository.connect() as db:
        a = service.repository.get(db, 'runs', 'conditions')
        context = json.loads(a['units'][0]['messages'][0]['content'])
        for row in context['context']:
            row['kind'] = 'method' if row['id'] == 'method' else 'ingredient_list'
        context['context'][-1].update(text=text)
        context['context'][-1]['source_reference']['end_char'] = len(text)
        cut = text.index('2. ')
        steps = [dict(id='step'+str(i), method_ref='method', ordinal=i, text=text[start:end],
            source_reference=dict(source_version_id='v1', parse_run_id='parse', block_id='method',
                                  start_char=start, end_char=end, quote=text[start:end]))
                 for i, (start, end) in enumerate([(0, cut), (cut, len(text))], 1)]
        context.update(method_steps=steps, method_prefixes=[])
        group = dict(kind='action_timing', quote=text[:cut], condition_quote='삶아 찬물에 담근 후',
            action_quote='껍질을 벗긴다', connector_quote='후', targets=[dict(item_ref='i1', quote='공통')],
            related_item_refs=[], reference_quotes=[], unresolved_reason='')
        output = dict(step1=dict(groups=[dict(group, kind='unqualified_action', condition_quote='', connector_quote='', action_quote='삶아'), group], unresolved_reason=''),
            step2=dict(groups=[dict(group, kind='unqualified_action', quote=text[cut:], condition_quote='', connector_quote='',
                action_quote='기름을 두른다', targets=[dict(item_ref='i2', quote='기름')])], unresolved_reason=''))
        recipe = dict(generation=dict(provider='fixture'), models=dict(review='fixture'),
            options=dict(review_tokens=8192, context_tokens=49152, think=False, timeout=1800))
        identity = dict(review=dict(name='fixture', digest='fixture'))
        instruction = 'supported fixture B contract'
        monkeypatch.setattr(timing, 'INSTRUCTION_SHA256', sha256(instruction.encode()).hexdigest())
        raw = json.dumps(output, ensure_ascii=False)
        unit = dict(id='b_unit', stage='source_step_conditions', status='succeeded', reference_map={},
            requested_limits=dict(max_tokens=8192, context_tokens=49152, think=False),
            executed_limits=dict(max_tokens=8192, context_tokens=49152, think=False),
            request_configuration=dict(model='fixture', generation=recipe['generation'], identity=identity, timeout=1800),
            schema=dict(type='object', properties={s['id']:dict(type='object') for s in steps}, required=[s['id'] for s in steps]),
            messages=[dict(role='system', content=instruction), dict(role='user', content=json.dumps(context))],
            response=dict(text=raw, parsed=output, raw_response=dict(message=dict(content=raw)), failure_kind=None,
                          provider='fixture', model='fixture', stage='source_step_conditions', done=True, done_reason='stop'))
        run = dict(id='b_run', kind='business_query', status='succeeded', snapshot_id='snap', query=dict(snapshot_id='snap'),
            units=[unit], recipe=recipe, model_identity=identity, input_version_ids=['v1','v2'], comparison_role='validation_on_own_snapshot',
            condition_validation=dict(version=timing.PRODUCER, record_integrity='valid', semantic_status='unverified'))
        thin = dict(id='snap', blocks=snapshot['blocks'], source_version_ids=['v1', 'v2'], human_approval=False)
        db.execute('UPDATE blocks SET payload=? WHERE id=?', (json.dumps(block), 'method'))
        db.execute('UPDATE snapshots SET payload=? WHERE id=?', (json.dumps(thin), 'snap'))
        db.execute('INSERT INTO runs VALUES(?,?)', ('b_run', json.dumps(run)))
        db.execute("DELETE FROM runs WHERE id='conditions'")
    def forbidden(*args, **kwargs): pytest.fail('No inference or outgoing network is allowed')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    from app.generation.model_client import ModelClient
    monkeypatch.setattr(ModelClient, 'execution_identity', forbidden)
    payload = dict(question='저장 기록', snapshot_id='snap', retrieval='explicit_sources',
        answer_mode='stored_after_conditions', stored_after_conditions=dict(run_id='b_run', unit_id='b_unit'))
    return service, thin, payload


def mutate(stored, edit):
    service, _, _ = stored
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', 'b_run'); edit(run); service.repository.save(db, 'runs', run)


def edit_output(stored, edit):
    def change(run):
        response = run['units'][0]['response']; edit(response['parsed'])
        raw = json.dumps(response['parsed'], ensure_ascii=False)
        response.update(text=raw, raw_response=dict(message=dict(content=raw)))
    mutate(stored, change)


def edit_context(stored, edit):
    def change(run):
        unit = run['units'][0]; value = json.loads(unit['messages'][1]['content']); edit(value)
        unit['messages'][1]['content'] = json.dumps(value)
    mutate(stored, change)


def query(stored):
    service, _, payload = stored
    return business_use.query(service, BusinessQuery.model_validate(payload))


def test_api_save_fresh_instance_workbench_exact_citations_without_A_or_approval(stored, monkeypatch):
    from app.api.routers import knowledge as api
    service, thin, payload = stored
    monkeypatch.setattr(api.settings, 'KNOWLEDGE_ENABLED', True)
    app = FastAPI(); app.include_router(api.router, prefix='/api/v1')
    app.dependency_overrides[api.get_knowledge_service] = lambda: service
    client = TestClient(app)
    response = client.post('/api/v1/knowledge/business/search', json=payload)
    assert response.status_code == 200, response.text
    result = response.json()['data']; rid = result['run_id']
    consumer = result['after_condition_consumer']
    assert len(consumer['records']) == 1 and len(consumer['not_consumed']) == 2
    record = consumer['records'][0]
    assert record['status'] == 'stored_after_fields'
    assert record['evidence']['condition']['quote'] == '삶아 찬물에 담근 후'
    assert record['evidence']['action']['quote'] == '껍질을 벗긴다'
    assert record['targets'][0]['evidence']['start_char'] < record['evidence']['action']['start_char']
    assert consumer['not_consumed'][1]['targets'][0]['quote'] == '기름'
    assert consumer['not_consumed'][1]['targets'][0]['item_evidence']['quote'] == '소금'
    assert record['semantic_status'] == 'unverified' and not record['human_approval']
    body = result['answer']['answer']
    assert after.LABEL in body and '→' not in body and result['answer']['choice'] is None
    assert '출처: source v1 · 1단계' in body and '[i1]' not in body
    assert '원문에서 확인한 관계' not in body
    with service.repository.connect() as db:
        assert service.repository.get(db, 'snapshots', 'snap') == thin
    fresh = KnowledgeService(service.repository.path)
    try:
        app.dependency_overrides[api.get_knowledge_service] = lambda: fresh
        saved = client.get('/api/v1/knowledge/runs/'+rid).json()['data']
        response = client.get('/api/v1/knowledge/workbench/answers', params=dict(kind='stored_conditions', scope_id='snap', answer_id=rid)).json()['data']
        assert [r['id'] for r in response['items']] == [rid]
        detail = response['detail']
        assert saved['answer'] == detail['answer'] == result['answer']
        assert saved['after_condition_consumer'] == consumer
        assert saved['metrics']['llm_calls'] == 0 and saved['units'] == []
        assert detail['graph_links'] == []
        refs = {row['id']:{k:row['evidence'][0][k] for k in after.ADDRESS} for row in detail['evidence']}
        assert refs == saved['source_reference_map'] == result['source_reference_map']
        blocks = {b['id']:b for b in thin['blocks']}
        assert all(blocks[r['block_id']]['text'][r['start_char']:r['end_char']] == r['quote'] for r in refs.values())
    finally:
        fresh.executor.shutdown(wait=False)


@pytest.mark.parametrize('fault', ['snapshot', 'input_versions', 'contract', 'instruction', 'limits', 'raw', 'parsed', 'wire', 'alias',
    'source', 'item', 'span', 'duplicate_item', 'duplicate_context', 'missing_step', 'overlap', 'parse', 'unregistered'])
def test_bad_stored_addresses_and_producer_contract_fail_without_active_run_leak(stored, fault):
    if fault == 'snapshot': mutate(stored, lambda r:r.update(snapshot_id='other'))
    elif fault == 'input_versions': mutate(stored, lambda r:r.update(input_version_ids=['other']))
    elif fault == 'contract': mutate(stored, lambda r:r['condition_validation'].update(version='C2'))
    elif fault == 'instruction': mutate(stored, lambda r:r['units'][0]['messages'][0].update(content='other'))
    elif fault == 'limits': mutate(stored, lambda r:r['units'][0]['executed_limits'].update(max_tokens=1))
    elif fault == 'raw': mutate(stored, lambda r:r['units'][0]['response'].update(text=''))
    elif fault == 'parsed': mutate(stored, lambda r:r['units'][0]['response'].update(parsed={}))
    elif fault == 'wire': mutate(stored, lambda r:r['units'][0]['response']['raw_response']['message'].update(content='{}'))
    elif fault == 'alias': mutate(stored, lambda r:r['units'][0].update(reference_map=dict(a='x', b='x')))
    elif fault == 'source': edit_context(stored, lambda c:c['sources'][0].update(source_version_id='other'))
    elif fault == 'item': edit_context(stored, lambda c:c['sources'][0]['items'][0].update(name='other'))
    elif fault == 'span': edit_context(stored, lambda c:c['sources'][0]['items'][0].update(name_span=[0,1]))
    elif fault == 'duplicate_item': edit_context(stored, lambda c:c['sources'][1]['items'][0].update(id='i1'))
    elif fault == 'duplicate_context': edit_context(stored, lambda c:c['context'].append(deepcopy(c['context'][0])))
    elif fault == 'missing_step': edit_context(stored, lambda c:c['method_steps'].pop())
    elif fault == 'overlap': edit_context(stored, lambda c:c['method_steps'][1]['source_reference'].update(start_char=0))
    elif fault == 'parse': edit_context(stored, lambda c:c['method_steps'][0]['source_reference'].update(parse_run_id='unknown'))
    else: edit_context(stored, lambda c:c['method_steps'][0]['source_reference'].update(block_id='unknown'))
    with pytest.raises((ValueError, KeyError)): query(stored)
    service = stored[0]
    with service.repository.connect() as db:
        assert not service.repository.has_active_runs(db)
        rows = [json.loads(r[0]) for r in db.execute("SELECT payload FROM runs WHERE json_extract(payload,'$.answer_status')='unverified'")]
        assert len(rows) == 1 and rows[0]['answer'] is None


@pytest.mark.parametrize('fault', ['duplicate', 'target_duplicate', 'target_unknown', 'cross_source', 'missing_quote', 'last_order'])
def test_bad_or_unsupported_group_is_unresolved_or_not_consumed_never_absence(stored, fault):
    def edit(output):
        g = output['step1']['groups'][1]
        if fault == 'duplicate': output['step1']['groups'].append(deepcopy(g))
        elif fault == 'target_duplicate': g['targets'].append(deepcopy(g['targets'][0]))
        elif fault == 'target_unknown': g['targets'][0]['item_ref'] = 'unknown'
        elif fault == 'cross_source': g['targets'][0]['item_ref'] = 'i3'
        elif fault == 'missing_quote': g['condition_quote'] = '없는 후'
        else: g['condition_quote'] = '마지막에'
    edit_output(stored, edit)
    result = query(stored)
    assert result['answer']['sections'] == []
    consumer = result['after_condition_consumer']
    assert consumer['empty_not_absence'] and not consumer['human_approval']
    assert all(r['status'] != 'stored_after_fields' for r in consumer['records'])


@pytest.mark.parametrize('mutation', ['restriction_entry', 'restriction_save', 'invalidation_entry', 'invalidation_save',
    'revision', 'snapshot', 'producer', 'cancel', 'closed'])
def test_entry_and_final_save_state_guards(stored, monkeypatch, mutation):
    service, thin, _ = stored
    thin['requirements'] = [dict(id='r', revision=1, status='ready')]
    with service.repository.connect() as db:
        db.execute('UPDATE snapshots SET payload=? WHERE id=?', (json.dumps(thin), 'snap'))
        db.execute('INSERT INTO requirements VALUES(?,?)', ('r', json.dumps(thin['requirements'][0])))
    calls = []
    if mutation.startswith('restriction'):
        def restricted(*args):
            calls.append(1)
            return [dict(state='blocked')] if mutation.endswith('entry') or len(calls) > 1 else []
        monkeypatch.setattr(business_use, 'restricted_sources', restricted)
    def change_state():
        with service.repository.connect() as db:
            if mutation.startswith('invalidation'):
                event = dict(event='business_correction', snapshot_id='snap', claim_ids=[], block_ids=['method'], requirement_ids=[])
                db.execute('INSERT INTO snapshot_events VALUES(?,?)', ('event', json.dumps(event)))
            elif mutation == 'revision': service.repository.save(db, 'requirements', dict(id='r', revision=2, status='ready'))
            elif mutation == 'snapshot': db.execute('UPDATE snapshots SET payload=? WHERE id=?', (json.dumps(dict(thin, changed=True)), 'snap'))
            elif mutation == 'producer':
                run = service.repository.get(db, 'runs', 'b_run'); run['status'] = 'cancelled'; service.repository.save(db, 'runs', run)
            elif mutation == 'cancel':
                row = db.execute("SELECT id FROM runs WHERE json_extract(payload,'$.status')='running'").fetchone()
                run = service.repository.get(db, 'runs', row['id']); run['status'] = 'cancel_requested'; service.repository.save(db, 'runs', run)
            elif mutation == 'closed': service.closed = True
    if mutation == 'invalidation_entry': change_state()
    original = after.assemble
    def changing(*args):
        result = original(*args); change_state(); return result
    if mutation != 'invalidation_entry': monkeypatch.setattr(after, 'assemble', changing)
    result = query(stored)
    assert result['status'] == ('cancelled' if mutation in {'cancel', 'closed'} else 'needs_review')
    assert result['answer'] is None
    with service.repository.connect() as db: assert not service.repository.has_active_runs(db)


def test_closed_service_entry_and_request_mode_cannot_fall_back_to_model(stored):
    service, _, payload = stored
    for change in [dict(retrieval='hipporag2'), dict(answer_mode='synthesis'), dict(requirement_ids=['r']),
                   dict(choices=['a']), dict(stored_after_conditions=None), dict(source_run_id='b_run')]:
        with pytest.raises(ValidationError): BusinessQuery.model_validate(dict(payload, **change))
    service.closed = True
    with pytest.raises(KnowledgeConflict): query(stored)


def test_different_documents_have_separate_titles_and_steps(stored):
    service, thin, _ = stored
    text = '1. 공통을 다진 후 옮긴다.\n'
    block = dict(id='method2', source_version_id='v2', parse_run_id='parse', text=text, locator={}, order=1)
    thin['blocks'].append(block)
    ref = dict(source_version_id='v2', parse_run_id='parse', block_id='method2', start_char=0, end_char=len(text), quote=text)
    with service.repository.connect() as db:
        db.execute('INSERT INTO blocks VALUES(?,?,?,?,?,?)', ('method2','v2','parse','v2:text',1,json.dumps(block)))
        db.execute('UPDATE snapshots SET payload=? WHERE id=?', (json.dumps(thin),'snap'))
    def context(c):
        c['context'].append(dict(id='method2', kind='method', text=text, source_reference=ref))
        c['method_steps'].append(dict(id='step3', method_ref='method2', ordinal=1, text=text, source_reference=ref))
    edit_context(stored, context)
    def output(o):
        o['step3'] = dict(groups=[dict(kind='action_timing', quote=text, condition_quote='다진 후', action_quote='옮긴다',
            connector_quote='후', targets=[dict(item_ref='i3', quote='공통')], related_item_refs=[], reference_quotes=[], unresolved_reason='')], unresolved_reason='')
    edit_output(stored, output)
    def schema(r):
        r['units'][0]['schema']['properties']['step3'] = dict(type='object')
        r['units'][0]['schema']['required'].append('step3')
    mutate(stored, schema)
    body = query(stored)['answer']['answer']
    assert '출처: source v1 · 1단계' in body and '출처: source v2 · 1단계' in body


def test_saved_workbench_keeps_historical_answer_and_reports_current_restrictions_and_invalidations(stored, monkeypatch):
    service = stored[0]; result = query(stored)
    monkeypatch.setattr(business_use, 'restricted_sources', lambda *a:[dict(source_version_id='v1', state='blocked')])
    with service.repository.connect() as db:
        event = dict(event='business_correction', snapshot_id='snap', claim_ids=[], block_ids=['method'], requirement_ids=[])
        db.execute('INSERT INTO snapshot_events VALUES(?,?)', ('event', json.dumps(event)))
    detail = workbench.answers(service, 'stored_conditions', 'snap', result['run_id'])['detail']
    assert detail['answer'] == result['answer']
    assert detail['current_usage']['source_restrictions'][0]['state'] == 'blocked'
    assert detail['current_usage']['invalidations'] == [event]
