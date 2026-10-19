from copy import deepcopy
import json

import numpy as np
import pytest
from pydantic import ValidationError

from app.knowledge import business_run, business_use, graph_retrieval as gr
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService


def inputs():
    snapshot = dict(claims=[dict(id=f'c{i}', review_status='accepted') for i in range(5)])
    edges = [dict(id='e3', claim_id='c3', relation='재료'),
             dict(id='role3', claim_id='c3', relation='참여자'),
             dict(id='e4', claim_id='c4', relation='재료'),
             dict(id='concept', claim_id='c2', relation='has_concept'),
             dict(id='stale', claim_id='not-in-snapshot', relation='재료')]
    passages = {f'p{i}': dict(claim_ids=[f'c{i}'], evidence=dict(source_version_id=f'v{i}'))
                for i in range(5)}
    ranked = [(pid, 1. / (i + 1)) for i, pid in enumerate(passages)]
    baseline = [dict(block_id=f'c{i}', file_id=f'v{i}', score=score,
                     passage_id=pid, selection_reason='hipporag2') for i, (pid, score) in enumerate(ranked[:2])]
    return snapshot, edges, passages, ranked, baseline


def test_union_preserves_entire_baseline_and_adds_all_facts_in_original_order():
    s, edges, passages, ranked, baseline = inputs()
    before = deepcopy((s, edges, passages, ranked, baseline))
    hits, trace = gr.selected_claim_union(s, edges, passages, ranked,
        ['e4', 'role3', 'e3', 'concept', 'stale', 'unknown'], baseline, 2, 'hipporag2')
    assert hits[:2] == baseline and [h['block_id'] for h in hits] == ['c0', 'c1', 'c3', 'c4']
    assert trace['baseline_limit'] == 2 and trace['returned_claim_count'] == 4
    assert trace['additional_claim_ids'] == ['c3', 'c4']
    assert hits[2]['selection_reason'] == 'hipporag2'
    assert (s, edges, passages, ranked, baseline) == before


def test_only_claim_id_is_deduplicated_and_other_scope_in_same_passage_remains():
    s, edges, passages, ranked, baseline = inputs()
    passages['p0']['claim_ids'].append('c3')
    s['claims'][0]['raw'] = s['claims'][3]['raw'] = dict(Head='동일 표현', Relation='조건', Tail='다른 범위')
    hits, trace = gr.selected_claim_union(s, edges, passages, ranked, ['e3', 'role3'], baseline, 2, 'hipporag2')
    assert [h['block_id'] for h in hits] == ['c0', 'c1', 'c3']
    assert hits[-1]['passage_id'] == 'p0' and trace['additional_claim_ids'] == ['c3']


def test_unaccepted_or_unranked_claim_never_added_and_empty_additions_keep_baseline():
    s, edges, passages, ranked, baseline = inputs()
    s['claims'][3]['review_status'] = 'needs_review'
    hits, trace = gr.selected_claim_union(s, edges, passages, ranked[:-1], ['e3', 'e4'], baseline, 2, 'hipporag2')
    assert hits == baseline and not trace['additional_claim_ids']


@pytest.mark.parametrize('fields', [dict(retrieval='dense'), dict(retrieval='bm25'),
    dict(snapshot_id=None, source_run_id='r'), dict(requirement_ids=['r']),
    dict(answer_mode='source_quotes')])
def test_experiment_rejects_paths_outside_reviewed_snapshot_synthesis(fields):
    values = dict(snapshot_id='s', question='질문', evidence_union='selected_factual_claims_v1')
    values.update(fields)
    with pytest.raises(ValidationError):
        BusinessQuery(**values)


def test_default_keeps_old_limit_contract_and_union_is_explicit():
    request = BusinessQuery(snapshot_id='s', question='질문')
    assert request.evidence_union is None and request.limit == 12
    assert BusinessQuery(**dict(request.model_dump(), evidence_union='selected_factual_claims_v1')).limit == 12


def test_shared_query_keeps_complete_union_when_budget_guard_blocks(tmp_path, monkeypatch):
    claims = [dict(id=f'c{i}', chunk_id=f'ch{i}', role='entity_relation',
        raw=dict(Head='대상', Relation='조건', Tail=f'조건{i}'), statement=f'조건{i}',
        source_version_ids=['v'], review_status='accepted',
        evidence=[dict(block_id=f'b{i}', source_version_id='v', parse_run_id='p',
                       start_char=0, end_char=3, quote=f'조건{i}')]) for i in range(5)]
    s = dict(id='s', kind='source_graph', run_id='origin', claims=claims, concepts=[],
             source_versions={'v': {}}, requirements=[], assessments={},
             blocks=[dict(id=f'b{i}', source_version_id='v', text=f'조건{i}') for i in range(5)])
    _, edges, passages, _ = gr.build(s, 'full')
    selected = [e['id'] for e in edges if e['claim_id'] in {'c3', 'c4'}]
    recipe = dict(generation={'provider': 'ollama'}, models={'review': 'mock', 'draft': 'mock'},
        options=dict(context_tokens=49152, review_tokens=8192, think=False, timeout=2))
    service = KnowledgeService(tmp_path/'knowledge.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)', ('s', json.dumps(s)))
        db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(dict(
            id='origin', status='succeeded', units=[], model_identity={}, recipe=recipe))))
    monkeypatch.setattr(gr, 'embed', lambda texts, *, service=None: np.asarray([[1., .5] for _ in texts]))
    monkeypatch.setattr(gr, 'rank', lambda *args: ([(pid, 1.) for pid in passages], {}))
    original = business_run.json_call
    def call(service, run, stage, instruction, context, schema, **kwargs):
        if stage == 'graph_retrieval_filter':
            return dict(selected_ids=selected)
        assert len(context['context']) == 4
        return original(service, run, stage, instruction, context, schema, **kwargs)
    monkeypatch.setattr(business_run, 'json_call', call)
    monkeypatch.setattr(business_run, 'request_budget', lambda *args, **kwargs: dict(estimate_tokens=49153))
    monkeypatch.setattr(business_run.ModelClient, 'generate', lambda *a, **k: pytest.fail('oversized union must not dispatch'))
    try:
        result = business_use.query(service, BusinessQuery(snapshot_id='s', question='질문', limit=2,
            evidence_union='selected_factual_claims_v1'))
        assert [h['block_id'] for h in result['retrieval']] == ['c0', 'c1', 'c3', 'c4']
        run = service.run(result['run_id'])
        assert run['units'][-1]['error'] == 'input_capacity' and run['metrics']['llm_calls'] == 0
        assert run['execution_boundary']['evidence_union']['baseline_limit'] == 2
    finally:
        service.shutdown()
