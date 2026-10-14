"""Relation generation boundaries preserve sources, whole claims and edge attribution."""
from copy import deepcopy

from app.knowledge import autoschema, business_concepts, business_run, graph_retrieval
from app.tests.unit.test_knowledge_concept_source_units import pool


def parent():
    chunks, claims, _ = pool()
    for claim in claims:
        claim['raw']['Relation'] = '접수'
    return dict(chunks=list(chunks.values()), claims=claims, graph=autoschema.graph(claims),
                recipe=dict(options=dict(context_tokens=49152, concept_tokens=512, neighbor_mode='plain')))


def relations(run):
    return [t for t in autoschema.concept_targets(run['graph']) if t['kind'] == 'relation']


def same_source():
    run = parent()
    run['claims'][1]['chunk_id'] = run['claims'][0]['chunk_id']
    run['graph'] = autoschema.graph(run['claims'])
    return run


def test_same_relation_name_in_distinct_sources_keeps_separate_targets_and_scopes():
    run = parent(); before = deepcopy(run)
    targets = relations(run)
    assert len(targets) == 2 and len({t['id'] for t in targets}) == 2
    assert [t['claim_ids'] for t in targets] == [[c['id']] for c in run['claims']]
    items = business_concepts.prepare(run, targets, 'plain')
    assert [i['selection']['mandatory_chunk_ids'] for i in items] == [['one'], ['two']]
    assert '필수 조건' in items[0]['messages'][-1]['content']
    assert '무관 문맥' not in items[0]['messages'][-1]['content']
    assert run == before


def test_repeated_participation_edges_count_each_claim_once_and_keep_every_edge():
    run = parent()
    chunk = run['chunks'][0]
    claim = autoschema.graph_record(chunk, 'event_entity', dict(Event='접수', Entity=['기관', '신청']), 0)
    run['claims'] = [claim]; run['graph'] = autoschema.graph(run['claims'])
    before = deepcopy(run['graph'])
    target = relations(run)[0]
    assert target['label'] == 'participation' and target['claim_ids'] == [claim['id']]
    assert len(run['graph']['edges']) == 2 and run['graph'] == before


def test_overflow_splits_at_whole_claims_with_exact_source_and_scope_preservation():
    run = same_source(); target = relations(run)[0]; before = deepcopy(run)
    single = [dict(target, claim_ids=[cid]) for cid in target['claim_ids']]
    sizes = [business_run.request_tokens(i['messages'], None, 512)
             for i in business_concepts.prepare(run, single, 'plain')]
    run['recipe']['options']['context_tokens'] = max(sizes)
    parts = business_concepts.prepare(run, [target], 'plain')
    assert len(parts) == 2
    assert [cid for i in parts for cid in i['target']['claim_ids']] == target['claim_ids']
    assert len({i['target']['id'] for i in parts}) == 2
    for item in parts:
        assert item['target']['partition_of'] == target['id']
        assert item['selection']['mandatory_chunk_ids'] == ['one']
        assert business_run.request_tokens(item['messages'], None, 512) <= max(sizes)
        assert '필수 조건' in item['messages'][-1]['content']
        assert item['selection']['relation_input_partition']['original_claim_ids'] == target['claim_ids']
    assert run['claims'] == before['claims'] and run['graph'] == before['graph']
    assert run['chunks'] == before['chunks']


def test_single_claim_overflow_is_left_for_product_preflight_and_is_not_truncated():
    run = parent(); target = relations(run)[0]
    expected = business_concepts.prepare(run, [target], 'plain')[0]
    run['recipe']['options']['context_tokens'] = 1
    assert business_concepts.prepare(run, [target], 'plain') == [expected]


def test_split_targets_are_not_regenerated_by_refresh_and_match_only_their_edges(monkeypatch):
    run = same_source(); target = relations(run)[0]
    single = business_concepts.prepare(run, [dict(target, claim_ids=[cid]) for cid in target['claim_ids']], 'plain')
    run['recipe']['options']['context_tokens'] = max(business_run.request_tokens(i['messages'], None, 512) for i in single)
    run.update(concepts=[], units=[])
    calls = []
    def call(service, current, stage, messages, **kwargs):
        calls.append((stage, messages)); current['units'].append(dict(id=str(len(calls))))
        return dict(text='개념' + str(len(calls)))
    monkeypatch.setattr(business_run, 'call', call)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    changed = {c['id'] for c in run['claims']}
    business_concepts.refresh_changed(None, run, changed)
    assert sum(stage == 'concept_relation' for stage, _ in calls) == 2
    first_calls = len(calls)
    business_concepts.refresh_changed(None, run, changed)
    assert len(calls) == first_calls
    run['blocks'] = [b for chunk in run['chunks'] for b in chunk['blocks']]
    graph, edges, _, _ = graph_retrieval.build(run, 'full')
    by_claim = {c['target']['claim_ids'][0]: c['concepts'] for c in run['concepts'] if c['target']['kind'] == 'relation'}
    for edge in edges:
        if edge['relation'] != '접수':
            continue
        assert graph.edges[edge['head'], edge['tail'], edge['id']]['concepts'] == by_claim[edge['claim_id']]
        assert not any(label in edge['text'] for labels in by_claim.values() for label in labels)


def test_legacy_edges_without_source_owner_stay_with_their_own_claims():
    run = parent()
    for edge in run['graph']['edges']:
        edge.pop('source_chunk_id')
    assert [t['claim_ids'] for t in relations(run)] == [[c['id']] for c in run['claims']]
