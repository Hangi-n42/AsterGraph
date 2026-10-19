from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from app.knowledge import graph_retrieval as gr


def edge(eid, claim=None, relation='fact'):
    return dict(id=eid, claim_id=claim, relation=relation)


def test_max_source_rank_not_quote_count_and_role_edges_share_source_rank():
    edges = [edge('e0', 'c'), edge('e1', 'c'), edge('e2', 'c', 'has_concept'), edge('e3', 'other')]
    scores = np.array([.8, .7, 1., .6])
    passages = {'p1': dict(claim_ids=['c']), 'p2': dict(claim_ids=['c'])}
    lexical = [dict(block_id='p1', score=2), dict(block_id='p2', score=1)]
    before = deepcopy((edges, scores, passages, lexical))
    _, trace = gr.source_edge_candidates(edges, scores, passages, lexical)
    rows = trace['edge_scores']
    assert rows['e0']['source_contribution'] == rows['e1']['source_contribution'] == 1/61
    assert rows['e0']['source_rank'] == rows['e1']['source_rank'] == 1
    assert len(rows['e0']['source_passages']) == 2
    assert rows['e0']['score'] == pytest.approx(1/62+1/61)
    assert rows['e2']['source_contribution'] == rows['e3']['source_contribution'] == 0
    assert edges == before[0] and passages == before[2] and lexical == before[3]
    np.testing.assert_array_equal(scores, before[1])


def test_exact_claim_join_does_not_match_same_surface_label():
    _, trace = gr.source_edge_candidates([edge('same label', 'c1'), edge('other same label', 'c2')],
        np.array([1., 0.]), {'p': dict(claim_ids=['c1'])}, [dict(block_id='p', score=1)])
    assert trace['edge_scores']['same label']['source_rank'] == 1
    assert trace['edge_scores']['other same label']['source_rank'] is None


def test_nonpositive_source_has_no_contribution():
    _, trace = gr.source_edge_candidates([edge('e', 'c')], np.array([1.]),
        {'p': dict(claim_ids=['c'])}, [dict(block_id='p', score=0), dict(block_id='p', score=-1)])
    assert trace['edge_scores']['e']['source_contribution'] == 0


def test_full_source_and_dense_ranks_no_channel_top30_cut():
    edges = [edge(f'e{i:02}', f'c{i}') for i in range(40)]
    passages = {f'p{i}': dict(claim_ids=['c39'] if i == 34 else []) for i in range(40)}
    lexical = [dict(block_id=f'p{i}', score=40-i) for i in range(40)]
    indices, trace = gr.source_edge_candidates(edges, np.arange(40., 0., -1.), passages, lexical)
    assert len(indices) == 30 and len(trace['ranked_edge_ids']) == 40
    assert trace['edge_scores']['e39']['dense_rank'] == 40
    assert trace['edge_scores']['e39']['source_rank'] == 35
    assert indices[0] == 39


def test_equal_total_score_uses_original_dense_rank():
    edges = [edge('z', 'c0'), edge('a', 'c1')]
    passages = {'p1': dict(claim_ids=['c1']), 'p2': dict(claim_ids=['c0'])}
    indices, trace = gr.source_edge_candidates(edges, np.array([1., 0.]), passages,
        [dict(block_id='p1', score=2), dict(block_id='p2', score=1)])
    assert trace['edge_scores']['z']['score'] == trace['edge_scores']['a']['score']
    assert indices == [0, 1]


def test_no_source_keeps_original_tie_and_cap():
    edges = list(reversed([edge(f'e{i:02}') for i in range(40)]))
    indices, _ = gr.source_edge_candidates(edges, np.ones(40), {}, [])
    assert [edges[i]['id'] for i in indices] == [f'e{i:02}' for i in range(30)]


def test_opt_in_rejects_other_retrieval_before_build(monkeypatch):
    monkeypatch.setattr(gr, 'build', lambda *a: pytest.fail('must stop before build'))
    with pytest.raises(ValueError):
        gr.retrieve(None, {}, {}, SimpleNamespace(retrieval='dense'), source_passage_candidates=True)
