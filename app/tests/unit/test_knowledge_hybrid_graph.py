from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from app.knowledge import business_run, graph_retrieval as gr
from app.knowledge.business_models import BusinessQuery
from app.knowledge.discovery_profile import FrozenIndex
from app.tests.unit.test_knowledge_graph_retrieval import snapshot


@pytest.mark.parametrize('selection', ['selected', 'empty', 'no_edges', 'failure'])
def test_hybrid_graph_reuses_b_and_keeps_graph_fallback_explicit(monkeypatch, selection):
    s = snapshot()
    s['include_unlinked_blocks'] = True
    s['blocks'].append(dict(id='unlinked', source_version_id='v', text='미추출 원문'))
    if selection == 'no_edges':
        s.update(claims=[], concepts=[])
    before = deepcopy(s)
    passages = gr.build(s, 'full')[2]
    ids = list(passages)
    lexical = [dict(block_id=p, score=float(i)) for i, p in enumerate(reversed(ids))]
    monkeypatch.setattr(FrozenIndex, 'rank', lambda *_: lexical)
    monkeypatch.setattr(gr, 'embed', lambda texts, *, service=None: np.asarray([[1., .5] for _ in texts]))
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    calls = []

    def call(service, run, stage, instruction, context, schema, **kwargs):
        calls.append(stage)
        if selection == 'failure':
            return None
        return dict(selected_ids=[context['candidate_facts'][0]['id']] if selection == 'selected' else [])

    monkeypatch.setattr(business_run, 'json_call', call)
    service = SimpleNamespace()

    def retrieve(mode):
        run = dict(id=mode, answer_basis='source_passages_not_ontology_approval',
                   recipe=dict(options=dict(context_tokens=49152, review_tokens=4096)))
        hits = gr.retrieve(service, run, s, BusinessQuery(source_run_id='origin', question='원문', retrieval=mode))
        return hits, run['graph_retrieval']

    b, bt = retrieve('hybrid')
    assert not calls
    assert len(b) == len(ids) == 5  # Includes text without an extracted claim.
    if selection == 'failure':
        with pytest.raises(ValueError, match='관계 선택 모델 호출 실패'):
            retrieve('hybrid_graph')
        assert calls == ['graph_retrieval_filter']
        assert s == before
        return

    c, ct = retrieve('hybrid_graph')
    assert calls == ([] if selection == 'no_edges' else ['graph_retrieval_filter'])
    assert ct['contract'] == 'hybrid-graph-rrf-source-passages-v1'
    assert ct['hybrid'] == bt['hybrid']
    assert ct['hybrid_graph']['hybrid_ranking'] == [dict(block_id=h['block_id'], score=h['score']) for h in b]
    assert s == before and {h['block_id'] for h in c} == set(ids)
    if selection == 'selected':
        assert ct['hybrid_graph']['graph_used'] and ct['fallback'] is None
        # Independent arithmetic checks both stages, not the production fusion helper.
        b_scores = {}
        for rows in (lexical, bt['hybrid']['dense_ranking']):
            for i, row in enumerate(rows, 1):
                p = row['block_id']
                b_scores[p] = b_scores.get(p, 0) + 1 / (60 + i)
        assert [(h['block_id'], h['score']) for h in b] == sorted(b_scores.items(), key=lambda x: -x[1])
        scores = {}
        for rows in (ct['hybrid_graph']['hybrid_ranking'], ct['hybrid_graph']['graph_ranking']):
            for i, row in enumerate(rows, 1):
                p = row['block_id']
                scores[p] = scores.get(p, 0) + 1 / (60 + i)
        assert [(h['block_id'], h['score']) for h in c] == sorted(scores.items(), key=lambda x: -x[1])
        old, old_trace = retrieve('hipporag2')
        assert ct['hybrid_graph']['graph_ranking'] == [dict(block_id=h['block_id'], score=h['score']) for h in old]
        assert 'hybrid' not in old_trace
    else:
        assert not ct['hybrid_graph']['graph_used']
        assert ct['fallback'] == 'hybrid_passages' and ct['hybrid_graph']['graph_ranking'] == []
        assert [(h['block_id'], h['score']) for h in c] == [(h['block_id'], h['score']) for h in b]


def test_hybrid_graph_requires_source_run():
    with pytest.raises(ValueError, match='source_run_id'):
        BusinessQuery(snapshot_id='s', question='질문', retrieval='hybrid_graph')
