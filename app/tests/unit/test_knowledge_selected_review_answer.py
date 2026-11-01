"""Synthetic handoff and version guards; never evidence of model accuracy."""
from copy import deepcopy

import pytest

from app.knowledge import business_run as execution, business_use, business_selected_review as final
from app.knowledge import selected_review_answer as handoff
from app.knowledge.business_models import BusinessQuery
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_business_role_review import case
from app.tests.unit.test_knowledge_selected_business_review import prepared, output
from app.tests.unit.test_knowledge_evidence_preservation import data, fixture_service, no_network


def fixture(case, monkeypatch, contract=final.CONTRACT):
    run, requirement, scope = prepared(case, monkeypatch)
    context = final.packet(run, requirement, scope, run['blocks'], contract=contract)
    raw = output(context, 'sufficient_in_scope')
    result = final.consume(raw, context)
    result['review_unit_id'] = 'final-unit'
    run['selected_business_reviews'] = [result]
    packet = execution.json_request(run, 'requirement_representation', final.instruction(contract), context, final.output_type(context))
    run['units'].append(dict(id='final-unit', status='succeeded',
        **{k:packet[k] for k in ('messages', 'schema', 'reference_map')},
        response=dict(request_id='final-unit', parsed=remap(raw, packet['reference_map'] or {}))))
    snapshot = dict(id='snapshot', requirements=[deepcopy(requirement)], blocks=deepcopy(run['blocks']),
        source_versions=deepcopy(run['sources']), claims=[dict(deepcopy(c), review_status='accepted') for c in run['claims']])
    query = BusinessQuery(question=requirement['question'], snapshot_id='snapshot',
        selected_review=dict(run_id=run['id'], unit_id='final-unit'))
    return run, snapshot, query


@pytest.mark.parametrize('contract', [final.CONTRACT, final.RELATION_CONTRACT])
def test_exact_review_binds_only_existing_approved_claims_without_mutation(case, monkeypatch, contract):
    run, snapshot, query = fixture(case, monkeypatch, contract)
    before = deepcopy((run, snapshot))
    value = handoff.bind(run, snapshot, query)
    assert value['required_claim_ids'] == ['c1']
    assert value['findings'] == run['selected_business_reviews'][0]['model_output']['items']
    assert value['source_observations'][0]['consumer_status'] == 'partial'
    assert (run, snapshot) == before
    assert value['authority'] == 'diagnostic_model_review_not_source_fact_or_use_approval'


@pytest.mark.parametrize('change', ['question', 'revision', 'raw', 'conditions', 'source_version',
    'source_text', 'missing_claim', 'not_approved', 'final_output', 'final_request', 'final_result', 'source_result', 'contract'])
def test_incompatible_version_or_tampered_review_is_rejected(case, monkeypatch, change):
    run, snapshot, query = fixture(case, monkeypatch)
    if change == 'question': query.question += '다른 질문'
    elif change == 'revision': snapshot['requirements'][0]['revision'] += 1
    elif change == 'raw': snapshot['claims'][0]['raw']['Tail'] = '변경된 값'
    elif change == 'conditions': snapshot['claims'][0]['conditions'] = ['새 조건']
    elif change == 'source_version': snapshot['source_versions'] = {'v2': {}}
    elif change == 'source_text': snapshot['blocks'][0]['text'] += '수정'
    elif change == 'missing_claim': snapshot['claims'] = []
    elif change == 'not_approved': snapshot['claims'][0]['review_status'] = 'unreviewed'
    elif change == 'final_output': next(iter(run['units'][-1]['response']['parsed']['items'].values()))['reason'] = 'edited'
    elif change == 'final_request': run['units'][-1]['messages'] = []
    elif change == 'final_result': run['selected_business_reviews'][0]['overall'] = 'unknown'
    elif change == 'contract': run['selected_business_reviews'][0]['contract'] = final.RELATION_CONTRACT
    else: run['bound_source_comparisons'][-1]['checks'][0]['status'] = 'missing'
    with pytest.raises(ValueError): handoff.bind(run, snapshot, query)


def test_unretrieved_review_facts_are_not_forwarded_as_delivered_evidence():
    with pytest.raises(ValueError, match='not_delivered'):
        handoff.answer_context(dict(required_claim_ids=['c1']), [])


def reviewed_source(snapshot):
    block = dict(id='reviewed-title', source_version_id='v', parse_run_id='p', text='Named fixture item')
    snapshot['blocks'].append(block)
    ref = dict(block_id=block['id'], source_version_id='v', parse_run_id='p', start_char=0,
        end_char=len(block['text']), quote=block['text'], precision='exact')
    return dict(required_claim_ids=['c2'], source_observations=[dict(evidence=[ref],
        condition_references=[deepcopy(snapshot['claims'][2]['evidence'][0])],
        expression_bindings=[dict(claim_id='c2')])])


def test_review_source_row_is_citable_when_claim_attaches_another_row(monkeypatch):
    snapshot, original, candidates, baseline, run = data()
    reviewed = reviewed_source(snapshot)
    before = deepcopy((snapshot, reviewed))
    rows = business_use.graph_source_evidence(snapshot, run['recipe'], {'c2'}, [])
    views, order = business_use.source_evidence_views(rows, [])
    assert [v['id'] for v in views] == ['b2']
    rows = business_use.graph_source_evidence(snapshot, run['recipe'], {'c2'}, [], reviewed)
    views, _ = business_use.source_evidence_views(rows, order)
    assert [v['id'] for v in views] == ['b2', 'reviewed-title']
    assert views[0]['text'] == snapshot['blocks'][2]['text']
    assert views[1]['claim_references'][0]['claim_ids'] == ['c2']
    query = BusinessQuery(question='q', snapshot_id='s', source_citation_contract='provided_source_quote_links_v1')
    _, body, schema, references = business_use.graph_qa_input(snapshot, original, run['recipe'], query,
        candidates, [dict(block_id='c2')], order, reviewed)
    assert body['source_evidence'] == views and 'reviewed-title' in references
    assert 'reviewed-title' in str(schema.model_json_schema())
    assert (snapshot, reviewed) == before


@pytest.mark.parametrize('change', ['source_version_id', 'parse_run_id', 'start_char', 'missing_claim'])
def test_review_source_cannot_move_address_or_reference_undelivered_claim(change):
    snapshot, original, candidates, baseline, run = data()
    reviewed = reviewed_source(snapshot)
    if change == 'missing_claim':
        reviewed['source_observations'][0]['expression_bindings'][0]['claim_id'] = 'absent'
    else:
        reviewed['source_observations'][0]['evidence'][0][change] = 1 if change == 'start_char' else 'changed'
    with pytest.raises(ValueError):
        business_use.graph_source_evidence(snapshot, run['recipe'], {'c2'}, [], reviewed)


@pytest.mark.parametrize('change', [dict(retrieval='bm25'), dict(graph_variant='entity'), dict(evidence_union=None),
    dict(source_run_id='r', snapshot_id=None), dict(answer_mode='source_quotes')])
def test_unsupported_answer_paths_reject_selected_review(change):
    values = dict(question='q', snapshot_id='s', selected_review=dict(run_id='r', unit_id='u'))
    values.update(change)
    with pytest.raises(ValueError): BusinessQuery(**values)


def test_required_review_facts_and_preview_fingerprint_survive_capacity_assembly(monkeypatch):
    snapshot, original, candidates, baseline, run = data()
    context = dict(required_claim_ids=['c4'], authority='diagnostic_model_review_not_source_fact_or_use_approval')
    run['selected_review_context'] = context
    query = BusinessQuery(question='Fixture question', snapshot_id='s', evidence_union='ranked_preserved_claims_v2',
        selected_review=dict(run_id='r', unit_id='u'))
    monkeypatch.setattr(execution, 'request_budget', lambda *a: dict(estimate_tokens=1))
    hits = business_use.preserved_graph_hits(run, snapshot, original, query, candidates, baseline)
    assert 'c4' in run['evidence_assembly']['mandatory_claim_ids']
    assert run['evidence_assembly']['selected_review_required_claim_ids'] == ['c4']
    _, body, schema, refs = business_use.graph_qa_input(snapshot, original, run['recipe'], query, candidates,
        hits, run['source_reference_order'], context)
    packet = execution.json_request(run, 'business_qa',
        business_use.SYNTHESIS_PROMPT + business_use.REVIEWED_MEANINGS_PROMPT + handoff.INSTRUCTION,
        body, schema, reference_map=refs)
    assert packet['messages'][1]['content'] and body['selected_requirement_review'] == context
    assert run['evidence_assembly']['request_fingerprint'] == execution.autoschema.identifier('qa_input', packet)


def test_required_review_facts_are_not_dropped_on_capacity_failure(monkeypatch):
    snapshot, original, candidates, baseline, run = data()
    run['selected_review_context'] = dict(required_claim_ids=['c4'])
    run['recipe']['options']['context_tokens'] = 1
    monkeypatch.setattr(execution, 'request_budget', lambda *a: dict(estimate_tokens=2))
    query = BusinessQuery(question='q', snapshot_id='s', evidence_union='ranked_preserved_claims_v2')
    with pytest.raises(ValueError, match='mandatory_capacity'):
        business_use.preserved_graph_hits(run, snapshot, original, query, candidates, baseline)
    assert 'c4' in run['evidence_assembly']['steps'][0]['claim_ids']


@pytest.mark.parametrize('changed_during_call', [False, True])
def test_api_new_answer_persists_snapshot_review_and_holds_changed_input(tmp_path, monkeypatch, changed_during_call):
    service, client, wires = fixture_service(tmp_path, monkeypatch)
    calls = []
    context = dict(required_claim_ids=['c4'], snapshot_id='s', review_run_id='review', final_review_unit_id='u')
    def load(*a):
        calls.append(True)
        return dict(context, changed=True) if changed_during_call and len(calls)>1 else deepcopy(context)
    monkeypatch.setattr(handoff, 'load', load)
    try:
        with service.repository.connect() as db:
            before = [tuple(r) for r in db.execute('SELECT * FROM snapshots')]
        reply = client.post('/api/v1/knowledge/business/search', json=dict(question='Fixture question', snapshot_id='s',
            selected_review=dict(run_id='review',unit_id='u')))
        assert reply.status_code == 200, reply.text
        value = reply.json()['data']
        assert value['snapshot_id']=='s' and len(wires)==2
        assert value['status']==('needs_review' if changed_during_call else 'answered')
        saved = client.get('/api/v1/knowledge/runs/'+value['run_id']).json()['data']
        assert saved['selected_review_context']==context and saved['snapshot_id']=='s'
        assert saved['query']['selected_review']==dict(run_id='review',unit_id='u')
        assert saved['answer']==value['answer']
        if changed_during_call:
            assert value['answer'] is None and saved['answer_source_citations']['citations']==[]
        else:
            assert saved['answer_source_citations']['citations'] and saved['answer_links']
        with service.repository.connect() as db:
            assert [tuple(r) for r in db.execute('SELECT * FROM snapshots')]==before
            assert db.execute('SELECT count(*) FROM decisions').fetchone()[0]==0
    finally: service.shutdown()
