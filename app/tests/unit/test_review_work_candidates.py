"""Structural candidate contracts only; no model, embedding, PPR or answer evaluation."""
from copy import deepcopy
import json

import numpy as np
import pytest
from pydantic import ValidationError

from app.knowledge import autoschema, business_run, business_use, graph_retrieval as gr, review_work_candidates as work
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_graph_retrieval import snapshot


@pytest.fixture(autouse=True)
def no_model_or_ppr(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail('No embedding, model, index or PPR execution is allowed')
    from app.generation.model_client import ModelClient
    from app.knowledge.source_index import FrozenIndex
    import socket
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(ModelClient, 'generate', denied)
    monkeypatch.setattr(gr, 'embed', denied)
    monkeypatch.setattr(gr, 'encoder', denied)
    monkeypatch.setattr(gr, 'rank', denied)
    monkeypatch.setattr(gr.nx, 'pagerank', denied)
    monkeypatch.setattr(FrozenIndex, '__init__', denied)


def roles_fixture():
    """Two stored representations of a structural A→B relation, with literal addresses."""
    block = dict(id='b', source_version_id='v', parse_run_id='p', text='A B')
    def evidence(lo, hi):
        return dict(source_version_id='v', parse_run_id='p', block_id='b', start_char=lo,
                    end_char=hi, quote=block['text'][lo:hi], context_only=False, precision='exact_unverified_meaning')
    def mention(field, value, lo, hi, idx=None):
        return dict(field=field, entity_index=idx, value=value, evidence=[evidence(lo, hi)],
                    address_status='resolved', address_errors=[], meaning_refs=['m'])
    direct = [mention('Head', 'A', 0, 1), mention('Tail', 'B', 2, 3)]
    event = [mention('Event', 'A B', 0, 3), mention('Entity', 'A', 0, 1, 0), mention('Entity', 'B', 2, 3, 1)]
    def claim(cid, raw, participants):
        meaning = dict.fromkeys(work.MEANING_FIELDS)
        meaning.update(id='m', subject='A', action='r', object='B', evidence=[evidence(0, 3)],
                       participants=participants, address_errors=[])
        return dict(id=cid, raw=raw, source_version_ids=['v'], evidence=[evidence(0, 3)],
            conditions=[], exceptions=[], period=None, references=[], qualifier_status='unverified',
            review_status='accepted', semantic_status='unknown', interpretation=dict(contract='stored',
                semantic_status='unverified', target_status='addressed', errors=[], meanings=[meaning], mentions=participants))
    c1 = claim('c1', dict(Head='A', Relation='r', Tail='B'), direct)
    c2 = claim('c2', dict(Event='A B', Entity=['A', 'B']), event)
    nodes = {n: dict(label=label, kind=kind, claim_ids=['c1', 'c2'],
        identity_scope='source_version+exact_mention+kind+endpoint_text') for n, label, kind in
        [('a', 'A', 'entity'), ('b', 'B', 'entity'), ('event', 'A B', 'event')]}
    e1 = dict(id='e1', head='a', tail='b', head_label='A', tail_label='B', head_kind='entity',
              relation='r', claim_id='c1')
    e2 = [dict(id='e'+str(i), head='event', tail=n, head_label='A B', tail_label=label,
              head_kind='event', relation='participation', claim_id='c2') for i, n, label in [(2, 'a', 'A'), (3, 'b', 'B')]]
    return c1, c2, [e1], e2, nodes, {'b': block}


def test_exact_work_sharing_preserves_unknown_and_distinct_roles():
    c1, c2, e1, e2, nodes, blocks = roles_fixture()
    before = deepcopy((c1, c2, e1, e2, nodes, blocks))
    assert work.signature(c1, e1, nodes, blocks, 's') == work.signature(c2, e2, nodes, blocks, 's')
    assert (c1, c2, e1, e2, nodes, blocks) == before
    c2['conditions'] = ['different condition']
    assert work.signature(c1, e1, nodes, blocks, 's') != work.signature(c2, e2, nodes, blocks, 's')


@pytest.mark.parametrize('damage', ['missing', 'address', 'ambiguous', 'role'])
def test_uncertain_roles_and_addresses_cannot_share(damage):
    _, c, _, edges, nodes, blocks = roles_fixture()
    if damage == 'missing':
        del c['period']
    elif damage == 'address':
        c['interpretation']['mentions'][1]['evidence'][0]['quote'] = 'wrong'
    elif damage == 'role':
        c['interpretation']['mentions'][1]['entity_index'] = None
    else:
        nodes['a2'] = deepcopy(nodes['a'])
        edges.append(dict(edges[0], id='e4', tail='a2'))
    with pytest.raises(work.NotShareable):
        work.signature(c, edges, nodes, blocks, 's')


def test_r2_uses_best_exact_head_path_and_leaves_dense_scores_unchanged():
    c1, _, first, _, nodes, blocks = roles_fixture()
    c2 = deepcopy(c1)
    c2.update(id='c2', raw=dict(Head='A', Relation='other', Tail='B'))
    second = dict(first[0], id='e2', claim_id='c2', relation='other')
    edges = [first[0], second, dict(id='concept', head='a', tail='concept', relation='has_concept')]
    passages = {p: dict(evidence=c1['evidence'][0], claim_ids=['c1']) for p in ['p1', 'p2']}
    scores = np.array([.1, .2, .9])
    before = scores.copy()
    ranking = [dict(block_id=p, file_id='v', score=2-i) for i, p in enumerate(passages)]
    result = work.rank_edges(dict(claims=[c1, c2], blocks=list(blocks.values())), nodes, edges, passages, scores, ranking)
    row = result['edge_scores']['e2']
    assert row['J1_path_count'] == 2 and row['source_contribution'] == 1/61
    assert row['score'] == 1/62 + 1/61
    assert result['edge_scores']['concept']['source_contribution'] == 0
    np.testing.assert_array_equal(scores, before)
    c2['interpretation']['meanings'][0]['participants'][0]['address_status'] = 'unresolved'
    result = work.rank_edges(dict(claims=[c1, c2], blocks=list(blocks.values())), nodes, edges, passages, scores, ranking)
    assert result['edge_scores']['e2']['J1_path_count'] == 0


@pytest.mark.parametrize('change', [dict(source_run_id='origin', snapshot_id=None), dict(retrieval='dense'),
    dict(graph_variant='entity'), dict(graph_variant='entity_event'), dict(requirement_ids=['r'])])
def test_explicit_option_rejects_unsupported_scope(change):
    with pytest.raises(ValidationError):
        BusinessQuery(**dict(dict(snapshot_id='s', question='q', candidate_contract=work.CONTRACT), **change))


def test_document_context_explicitly_rejects_option():
    with pytest.raises(ValueError, match='graph context'):
        business_use.query(None, BusinessQuery(snapshot_id='s', question='q', candidate_contract=work.CONTRACT),
                           context_mode='document')


def test_individual_alias_restore_passes_original_dense_arrays_without_group_expansion(tmp_path, monkeypatch):
    from app.knowledge.source_index import FrozenIndex
    s = snapshot()
    s['claims'][2]['raw']['Entity'].append('신청')
    service = KnowledgeService(tmp_path/'knowledge.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(dict(
            id='origin', status='succeeded', units=[], graph=autoschema.graph(s['claims'])))))
    built = gr.build(s, 'full')
    edge_scores, passage_scores = np.linspace(.1, .9, len(built[1])), np.ones(len(built[2]))
    before = edge_scores.copy(), passage_scores.copy()
    monkeypatch.setattr(gr, 'query_scores', lambda *args: (edge_scores, passage_scores))
    monkeypatch.setattr(FrozenIndex, '__init__', lambda *args, **kwargs: None)
    monkeypatch.setattr(FrozenIndex, 'rank', lambda *args: [])
    selected = []
    def saved_response(service, run, stage, messages, schema, **kwargs):
        groups = json.loads(messages[1]['content'])['candidate_fact_groups']
        group = next(g for g in groups if len(g['members']) > 1)
        alias = group['members'][0]['id']
        selected.append(next(e for e, a in kwargs['reference_map'].items() if a == alias))
        return dict(parsed=dict(selected_ids=[alias]))
    monkeypatch.setattr(business_run, 'call', saved_response)
    class Boundary(Exception):
        pass
    def rank_boundary(graph, edges, passages, es, ps, ids, limit):
        assert es is edge_scores and ps is passage_scores
        assert ids == set(selected) and len(ids) == 1
        raise Boundary('Stopped before rank/PPR')
    monkeypatch.setattr(gr, 'rank', rank_boundary)
    run = dict(id='diagnostic', recipe=dict(options=dict(context_tokens=49152, review_tokens=8192)), units=[])
    try:
        with pytest.raises(Boundary):
            gr.retrieve(service, run, s, BusinessQuery(snapshot_id='s', question='q', candidate_contract=work.CONTRACT), built=built)
        assert run['graph_retrieval']['selected_edge_ids'] == selected
        np.testing.assert_array_equal(edge_scores, before[0])
        np.testing.assert_array_equal(passage_scores, before[1])
    finally:
        service.shutdown()


@pytest.mark.parametrize('contract', [None, work.CONTRACT])
def test_product_query_persists_preselector_request_and_preserves_baseline(tmp_path, monkeypatch, contract):
    from app.knowledge.source_index import FrozenIndex
    s = snapshot()
    service = KnowledgeService(tmp_path/'knowledge.db')
    original = dict(id='origin', status='succeeded', units=[], model_identity={},
        recipe=dict(options=dict(context_tokens=49152, review_tokens=8192)), graph=autoschema.graph(s['claims']))
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)', ('s', json.dumps(s)))
        db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(original)))
    captured = []
    class Boundary(Exception):
        pass
    def call(service, run, stage, messages, schema, **kwargs):
        assert stage == 'graph_retrieval_filter'
        captured.append(dict(messages=messages, schema=schema, **kwargs))
        raise Boundary('diagnostic stop before selector')
    monkeypatch.setattr(business_run, 'call', call)
    def scores(service, snapshot, edges, passages, *args):
        return np.ones(len(edges)), np.ones(len(passages))
    monkeypatch.setattr(gr, 'query_scores', scores)
    indexes = []
    monkeypatch.setattr(FrozenIndex, '__init__', lambda self, rows, **kwargs: indexes.append((rows, kwargs)))
    monkeypatch.setattr(FrozenIndex, 'rank', lambda *args: [])
    try:
        reply = business_use.query(service, BusinessQuery(snapshot_id='s', question='q', candidate_contract=contract))
        assert reply['status'] == 'retrieval_failed' and len(captured) == 1
        saved = service.run(reply['run_id'])
        trace = saved['graph_retrieval']
        payload = json.loads(captured[0]['messages'][1]['content'])
        assert bool(indexes) == bool(contract)
        assert ('candidate_fact_groups' in payload) == bool(contract)
        assert ('candidate_facts' in payload) == (contract is None)
        assert captured[0]['schema']['properties']['selected_ids']['maxItems'] <= 30
        aliases = captured[0]['reference_map']
        assert trace['candidate_edge_ids'] == list(aliases)
        if contract:
            assert all(b['original_claim'] in s['claims'] for b in trace['candidate_bindings'].values()
                       if b['original_claim'])
            assert all(not row['eligible_for_work_sharing'] for row in trace['work_eligibility'])
        with service.repository.connect() as db:
            assert service.repository.get(db, 'snapshots', 's') == s
            assert service.repository.get(db, 'runs', 'origin') == original
    finally:
        service.shutdown()
