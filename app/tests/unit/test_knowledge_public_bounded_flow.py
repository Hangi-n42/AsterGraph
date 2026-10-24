"""Bound public inputs without converting search omissions into semantic verdicts."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_review as review, business_run
from app.knowledge.source_index import FrozenIndex
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments


@pytest.fixture(autouse=True)
def boundary_only(monkeypatch):
    from app.retrieval.pipeline.stages import bm25_retriever
    # Deliberately not a morphology/retrieval-quality test.
    monkeypatch.setattr(bm25_retriever, '_tokenize_korean',
        lambda texts: [[text[i:i + 2] for i in range(len(text) - 1)] for text in texts])
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)


def public_run():
    run = local_run()
    run['recipe'].update(review_contract=review.SOURCE_APPLICATION_CONTRACT,
        models=dict(review='review', draft='draft'), generation=dict(provider='ollama'))
    run.update(id='run', model_identity=dict(review='digest'), metrics=dict(llm_calls=0, model_total_s=0))
    requirement = dict(id='r', revision=1, question='신청 조건은?', criterion='원문 조건',
        target='이용자', situation='안내', period='', source_ids=[])
    run['requirements'] = [requirement]
    run['answer_items'] = [dict(id='question', requirement_id='r', requirement_revision=1,
        field='question', request_quote='신청 조건')]
    return run, requirement


@pytest.mark.parametrize('public', [True, False])
def test_source_precedes_public_selection_while_nonpublic_keeps_legacy_review_order(monkeypatch, public):
    run, requirement = public_run()
    if not public:
        run['answer_items'] = []
    calls = []
    def source(*a, **kw):
        calls.append('source')
        return dict(meanings=[], examined_block_ids=[])
    def scope(*a):
        calls.append('public_selection')
        raise RuntimeError('boundary')
    def representation(*a, **kw):
        calls.append('representation')
        raise RuntimeError('boundary')
    monkeypatch.setattr(review, 'source', source)
    monkeypatch.setattr(review, 'needs_source_read', lambda *a: False)
    monkeypatch.setattr(review, 'review_candidate_pool', lambda *a, **kw: calls.append('own_review'))
    monkeypatch.setattr(review, 'public_requirement_scope', scope)
    monkeypatch.setattr(review, 'repair_context', lambda *a: [])
    monkeypatch.setattr(review, 'valid_preservation_reuses', lambda *a, **kw: [])
    monkeypatch.setattr(review, 'represent', representation)
    monkeypatch.setattr(business_run, 'apply_source_corrections', lambda r, q, s: s)
    with pytest.raises(RuntimeError, match='boundary'):
        business_run.assess(None, run, requirement)
    assert calls == (['source', 'public_selection'] if public else ['own_review', 'source', 'representation'])


def test_public_subset_keeps_premises_cross_source_fields_and_full_unread_inventory(monkeypatch):
    run, requirement = public_run()
    base = run['blocks'][0]
    for identifier, version, text in [('condition', 'v2', '접수 조건과 예외를 유지한다.'),
                                      ('outside', 'v3', '다른 업무의 별도 자료다.')]:
        b = dict(deepcopy(base), id=identifier, source_id=version, source_version_id=version, text=text)
        chunk = autoschema.chunks([b], 49152, 4096)[0]
        run['blocks'].append(b); run['chunks'].append(chunk)
        run['claims'].append(autoschema.graph_record(chunk, 'entity_relation',
            dict(Head=identifier, Relation='기록', Tail=text), 0))
    first = run['claims'][0]
    first['source_version_ids'].append('v2')
    first.update(conditions=['정상 조건'], exceptions=['정상 예외'], period='원문 기간', references=['문서간 참조'])
    first['evidence'] = business_run.exact_evidence([
        dict(block_id=b['id'], quote=b['text']) for b in run['blocks'][:2]], run['blocks'])
    unresolved = deepcopy(first)
    unresolved.update(id='unresolved', evidence=[dict(block_id='unknown', quote='미확정 주소')])
    run['claims'].append(unresolved)
    source = dict(meanings=[meaning('answer'), meaning('premise'), meaning('other')])
    source['meanings'][0]['premise_keys'] = ['premise']
    source['meanings'][1]['evidence'] = [dict(block_id='condition', quote=run['blocks'][1]['text'])]
    source['meanings'][2]['evidence'] = [dict(block_id='outside', quote=run['blocks'][2]['text'])]
    original = deepcopy((run['claims'], source))
    def search(_index, _query, ids, limit=6):
        return [dict(block_id=k) for k in ('answer', 'body') if k in ids]
    monkeypatch.setattr(FrozenIndex, 'search', search)
    own_batches, packets = [], []
    def own(_s, _r, claims, **kw):
        own_batches.append(deepcopy(claims))
    monkeypatch.setattr(review, 'review_candidate_pool', own)
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda r: {c['id']: dict(receipt_id='own', unit_id='own',
        check=dict(claim_support={c['id']: 'supported'}, incorrect_claim_ids=[], error_fields={}, evidence=[]))
        for c in r['claims'][:3]})
    def application(_s, current, stage, instruction, packet, schema):
        packets.append(deepcopy(packet))
        assert '미제공·주소 미일치 후보는 부재·오류·승인이 아니며' in instruction
        row = dict(task_id=packet['public_tasks'][0]['id'], meaning_keys=['answer'], candidate_ids=[],
            source_state='available', expression_state='not_found', read_block_ids=[], gap='', reason='후속 전체 탐색')
        output = schema.model_validate(dict(items=[row], meaning_challenges=[])).model_dump()
        current['units'].append(dict(id='application', status='succeeded', error=None, restored_evidence_output=output))
        return output
    monkeypatch.setattr(business_run, 'json_call', application)
    result = review.public_requirement_scope(None, run, requirement, source)
    packet, scope = packets[0], result['public_scope']
    assert {m['key'] for m in packet['source_facts']} == {'answer', 'premise'}
    expected = {c['id'] for c in run['claims'][:3]}
    assert {c['id'] for c in own_batches[0]} == expected
    assert {c['id'] for c in packet['candidates']} == expected
    supplied = next(c for c in packet['candidates'] if c['id'] == first['id'])
    assert all(supplied[k] == first[k] for k in ('raw', 'conditions', 'exceptions', 'period', 'references'))
    assert own_batches[0][0]['evidence'] == first['evidence']
    _, own_packet, _ = review.candidate_request(run, [first])
    assert {b['source_version_id'] for b in own_packet['blocks']} == {'v', 'v2'}
    assert set(scope['candidate_versions']) == {c['id'] for c in run['claims']}
    assert set(scope['provided_candidate_versions']) == expected
    assert {r['id'] for r in packet['candidate_inventory'] if not r['provided']} == {run['claims'][3]['id'], 'unresolved'}
    assert packet['source_inventory'][0]['id'] == 'outside' and 'text' not in packet['source_inventory'][0]
    assert scope['followup'][0]['action'] == 'check_candidate_pool'
    assert scope['review_meaning_keys'] == ['answer', 'premise']
    assert (run['claims'], source) == original
    assert review.public_scope_valid(run, requirement, result)
    old = deepcopy(result); old['public_scope'].pop('input_contract')
    assert not review.public_scope_valid(run, requirement, old)
    run['claims'][-1]['conditions'].append('미제공 후보 변경')
    assert not review.public_scope_valid(run, requirement, result)


def failed_unit(run, request):
    options = run['recipe']['options']
    return dict(id='failed', stage='candidate_source_review', status='failed', error='input_capacity',
        **deepcopy({k: request[k] for k in ('messages', 'schema', 'reference_map', 'evidence_reference_map')}),
        request_configuration=dict(model='review', generation=deepcopy(run['recipe']['generation']),
            identity=deepcopy(run['model_identity']), temperature=0, timeout=options['timeout']),
        requested_limits=dict(max_tokens=options['review_tokens'], context_tokens=options['context_tokens'], think=options['think']))


@pytest.mark.parametrize('storage', ['units', 'reusable_units', 'inspection_units'])
def test_identical_failed_review_is_pending_without_new_call_or_approval(monkeypatch, storage):
    run, requirement = public_run()
    args = review.candidate_request(run, run['claims'])
    request = business_run.json_request(run, 'candidate_source_review', *args)
    unit = failed_unit(run, request); run.setdefault(storage, []).append(unit)
    before = deepcopy(unit)
    monkeypatch.setattr(review, 'review_candidates', lambda *a, **kw: pytest.fail('repeated failed request'))
    review.review_candidate_pool(None, run, run['claims'], requirement=requirement)
    review.review_candidate_pool(None, run, run['claims'], requirement=requirement)
    assert run[storage][0] == before and not review.current_candidate_reviews(run)
    assert len(run['candidate_review_deferrals']) == 1
    assert run['candidate_review_deferrals'][0]['status'] == 'pending'
    assert len(run['units']) == (1 if storage == 'units' else 0)
    assert review.inherited_inspection_units(run) == [unit]


@pytest.mark.parametrize('change', ['claim', 'source', 'model', 'timeout', 'budget', 'executed_limits', 'nonpublic'])
def test_changed_request_or_nonpublic_path_is_not_blocked_by_public_failure_guard(monkeypatch, change):
    run, requirement = public_run()
    request = business_run.json_request(run, 'candidate_source_review', *review.candidate_request(run, run['claims']))
    run['units'].append(failed_unit(run, request))
    if change == 'claim': run['claims'][0]['conditions'].append('새 조건')
    elif change == 'source': run['blocks'][0]['text'] += ' 실제 원문 변경.'
    elif change == 'model': run['model_identity']['review'] = 'new_digest'
    elif change == 'timeout': run['recipe']['options']['timeout'] += 1
    elif change == 'budget': run['recipe']['options']['review_tokens'] += 1
    elif change == 'executed_limits':
        run['units'][0]['executed_limits'] = dict(run['units'][0]['requested_limits'], max_tokens=1)
    else: run['answer_items'] = []
    calls = []
    monkeypatch.setattr(review, 'review_candidates', lambda *a, **kw: calls.append(True))
    review.review_candidate_pool(None, run, run['claims'], requirement=requirement)
    assert calls == [True] and not run.get('candidate_review_deferrals')


def test_successful_review_is_reused_for_subsets_without_new_request(monkeypatch):
    from app.tests.unit.test_knowledge_business_responsibilities import setup_direct_receipt
    run, receipt = setup_direct_receipt(monkeypatch, states=('supported', 'supported'))
    monkeypatch.setattr(review, 'review_candidates', lambda *a, **kw: pytest.fail('successful receipt repeated'))
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **kw: pytest.fail('new model request'))
    review.review_candidate_pool(None, run, run['claims'][:1])
    assert set(review.current_candidate_reviews(run)) == set(receipt['claim_ids'])


@pytest.mark.parametrize('stage', ['candidate_source_review', 'requirement_representation'])
@pytest.mark.parametrize('case', ['exact', 'public_changed_timeout', 'nonpublic_changed_timeout'])
def test_public_parent_response_reuse_requires_exact_execution_settings(monkeypatch, stage, case):
    run, _ = public_run()
    options = run['recipe']['options']
    budget = options['review_tokens']
    messages, schema = [dict(role='user', content='same input')], {}
    limits = dict(max_tokens=budget, context_tokens=options['context_tokens'], think=options['think'])
    donor = dict(id='parent-unit', stage=stage, status='succeeded', error=None,
        messages=messages, schema=schema, reference_map=None,
        request_configuration=dict(model='review', generation=deepcopy(run['recipe']['generation']),
            identity=deepcopy(run['model_identity']), temperature=0, timeout=options['timeout']),
        requested_limits=deepcopy(limits), executed_limits=deepcopy(limits),
        response=dict(request_id='parent-unit', failure_kind=None, elapsed_s=0, parsed={}))
    run.update(parent_recipe=deepcopy(run['recipe']), parent_model_identity=deepcopy(run['model_identity']),
        parent_run_id='parent', reusable_units=[donor])
    if case != 'exact': options['timeout'] += 1
    if case == 'nonpublic_changed_timeout': run['answer_items'] = []
    calls = []
    class FakeClient:
        def __init__(self, config): pass
        async def generate(self, request, cancelled):
            calls.append(request)
            return dict(request_id='fresh', failure_kind=None, elapsed_s=0, parsed={})
    monkeypatch.setattr(business_run, 'ModelClient', FakeClient)
    business_run.call(None, run, stage, messages, schema, review=True)
    if case == 'public_changed_timeout':
        assert len(calls) == 1 and not run['units'][-1].get('reused_from')
    else:
        assert not calls and run['units'][-1]['reused_from']['unit_id'] == 'parent-unit'


@pytest.mark.parametrize('ranked_all', [True, False])
def test_r_rechecks_capacity_and_reviews_new_remaining_batches(monkeypatch, ranked_all):
    run, requirement = public_run()
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete',
        gaps=[], conjunctions=[], public_scope=dict(review_meaning_keys=['m'], tasks=[], items=[], errors=[], followup=[],
            unit_id='scope', public_requirement={k:v for k,v in requirement.items() if k != 'source_ids'}))
    direct, review_counts, dispatched = {}, {}, []
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda r: deepcopy(direct))
    monkeypatch.setattr(FrozenIndex, 'search', lambda _i, _q, ids, limit=6:
        [dict(block_id=c) for c in (sorted(ids) if ranked_all else sorted(ids)[:1])])
    def own(_s, _r, claims, **kw):
        for c in claims:
            cid = c['id']
            if cid not in direct:
                review_counts[cid] = review_counts.get(cid, 0) + 1
                direct[cid] = dict(receipt_id=cid, unit_id='own', check=dict(claim_support={cid:'supported'},
                    incorrect_claim_ids=[], error_fields={}, error_evidence=[], reason='정상 조건을 포함한 검수 설명'))
    monkeypatch.setattr(review, 'review_candidate_pool', own)
    real_request = business_run.json_request
    def capacity(messages, schema, max_tokens):
        import json
        packet = json.loads(messages[-1]['content'])
        added = packet.get('whole_candidate_judgments', [])
        return 50000 if len(packet.get('claims', [])) > 1 and added else 10000
    monkeypatch.setattr(business_run, 'request_tokens', capacity)
    def answer(_s, current, stage, instruction, packet, schema):
        current['units'].append(dict(id='r'+str(len(current['units']))))
        if packet['mode'] == 'requirement_join': return None
        request = real_request(current, stage, instruction, packet, schema)
        assert capacity(request['messages'], request['schema'], 4096) <= 49152
        assert len(packet['claims']) == 1 and packet['whole_candidate_judgments']
        dispatched.append(deepcopy(packet))
        return judgments(['m'], status='missing')
    monkeypatch.setattr(business_run, 'json_call', answer)
    _, scope = review.represent(None, run, requirement, source, [])
    ids = {c['id'] for c in run['claims']}
    assert {c['id'] for p in dispatched for c in p['claims']} == ids
    assert review_counts == {cid:1 for cid in ids}
    assert set(scope['candidate_inventory_ids']) == ids


@pytest.mark.parametrize('entrypoint', ['feedback', 'participant'])
@pytest.mark.parametrize('public', [True, False])
@pytest.mark.parametrize('replacement', [True, False])
def test_repair_entrypoints_do_not_restore_full_public_pre_review(monkeypatch, entrypoint, public, replacement):
    from contextlib import contextmanager
    from threading import RLock
    from types import SimpleNamespace
    from app.knowledge import business_feedback as feedback, business_participant_resume as participant, business_use
    run, requirement = public_run()
    run['id'] = 'child'; run['parent_run_id'] = 'parent'; run['recipe']['options']['repair'] = True
    if not public: run['answer_items'] = []
    assessment = dict(id='a', requirement_id='r', source=dict(meanings=[meaning('m')]),
        representation=dict(checks=[dict(meaning_key='m')]), status='partial')
    run['assessments'] = [assessment]
    parent = deepcopy(run); parent['id'] = 'parent'
    receipt = dict(repair_id='repair', requirement_id='r', assessment_id='a', proposals={})
    run['participant_resumption'] = receipt
    run['answer_gap_recheck'] = dict(findings=[dict(id='gap', requirement_id='r', meaning_keys=['m'])])
    class Repository:
        @contextmanager
        def connect(self): yield None
        def get(self, db, table, identifier): return parent if identifier == 'parent' else run
        def save(self, *args): pass
    service = SimpleNamespace(repository=Repository(), lock=RLock())
    class FakeClient:
        def __init__(self, config): pass
        def identities(self, *args): return deepcopy(run['model_identity'])
    monkeypatch.setattr(business_run, 'ModelClient', FakeClient)
    monkeypatch.setattr(participant, 'plan', lambda *a: deepcopy(receipt))
    events, direct = [], {}
    def repair(_s, current, req, original, **kw):
        added = dict(deepcopy(current['claims'][0]), id='new')
        if replacement: current['claims'][0]['superseded_by'] = ['new']
        current['claims'].append(added); current['repairs'].append(dict(id='repair'))
        events.append(('repair',))
        return True
    def own(_s, current, claims, **kw):
        events.append(('own', [c['id'] for c in claims]))
        direct.update({c['id']:dict(check=dict(claim_support={c['id']:'supported'},
            incorrect_claim_ids=[], error_fields={})) for c in claims})
    def assess(_s, current, req, **kw):
        events.append(('assess', kw['phase']))
        return dict(id='after'+str(len(events)), source=deepcopy(assessment['source']), status='partial')
    monkeypatch.setattr(business_run, 'repair', repair)
    monkeypatch.setattr(review, 'review_candidate_pool', own)
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda r: deepcopy(direct))
    monkeypatch.setattr(business_run, 'assess', assess)
    monkeypatch.setattr(business_run, 'reassess_challenges', lambda s, r, q, a, **kw: a)
    monkeypatch.setattr(business_run, 'refresh_repaired_graph', lambda *a: None)
    monkeypatch.setattr(business_use, 'publish', lambda *a: dict(id='changeset'))
    (feedback if entrypoint == 'feedback' else participant).execute(service, 'child')
    assert run['status'] == 'partial' and not run.get('error')
    reviewed = [e[1] for e in events if e[0] == 'own']
    if public:
        assert reviewed == ([] if entrypoint == 'feedback' else [['new']])
        assert any(e[0] == 'assess' and e[1].startswith('after_') for e in events)
    else:
        assert reviewed == [[c['id'] for c in review.candidate_pool(run, requirement)]]
    assert run['claims'][-1]['id'] == 'new'
