"""F3 child reads over F4-b rows; synthetic fixtures and local client stubs only."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_concepts, business_run, business_use, graph_retrieval
from app.knowledge.business_models import ConceptRunRequest, HtmlLiteralRowsRequest
from app.tests.unit.test_knowledge_concept_source_map_entrypoints import environment, pool
from app.tests.unit.test_knowledge_html_debt_rows import HTML, parent_source

PUBLISH = business_use.publish


@pytest.fixture
def debt_view(environment, monkeypatch):
    service, requests = environment
    monkeypatch.setattr(business_use, 'publish', PUBLISH)
    parent, ids = parent_source(service, HTML.replace('</div>', '<p>기관은 신청을 접수한다.</p></div>'))
    block = next(b for b in parent['blocks'] if b['text'] == '기관은 신청을 접수한다.')
    chunk = autoschema.chunks([block], 49152, 8192)[0]
    claim = autoschema.graph_record(chunk, 'entity_relation', dict(Head='기관', Relation='접수', Tail='신청'), 0)
    config = pool(block['source_version_id'])
    parent.update(chunks=[chunk], claims=[claim], graph=autoschema.graph([claim]),
                  recipe=config['recipe'], model_identity=config['model_identity'], metrics=config['metrics'])
    targets = autoschema.concept_targets(parent['graph'])[:2]
    parent['concepts'] = [dict(id='old-' + t['id'], target=deepcopy(t), concepts=['기존 ' + t['label']],
        status='accepted', relation='has_concept', approved_is_a=False) for t in targets]
    business_run.save(service, parent)
    result = service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=parent['id'], block_ids=ids))
    with service.repository.connect() as db:
        parent = service.repository.get(db, 'runs', result['run_id'])
    child = business_concepts.start(service, ConceptRunRequest(parent_run_id=parent['id'],
        target_ids=[targets[0]['id']], neighbor_mode='plain'))
    assert child['status'] == 'succeeded' and child['recipe']['options']['concept_source_context'] == 'whole'
    return service, requests, parent, child


def test_completed_child_reads_over_stored_debt_graph_without_mutating_other_state(debt_view):
    service, requests, parent, child = debt_view
    before_parent, before_child = deepcopy(parent), deepcopy(child)
    graph_before, _, passages_before, _ = graph_retrieval.build(parent, 'full')
    with service.repository.connect() as db:
        view, provenance = business_use.concept_read_view(service, db, parent, child['id'])
        assert service.repository.get(db, 'runs', parent['id']) == before_parent
        assert service.repository.get(db, 'runs', child['id']) == before_child
    assert view == [parent['concepts'][1], child['concepts'][0]]
    assert provenance['parent_and_snapshot_persisted'] is False
    assert view[-1]['status'] == 'unreviewed' and view[-1]['approved_is_a'] is False
    graph_after, _, passages_after, _ = graph_retrieval.build(dict(parent, concepts=view), 'full')
    assert passages_after == passages_before
    for node, data in graph_before.nodes(data=True):
        if data.get('kind') in {'structured_row', 'field_value', 'passage'}:
            assert graph_after.nodes[node] == data
            assert set(graph_after.successors(node)) == set(graph_before.successors(node))
    assert parent == before_parent and child == before_child and len(requests) == 1


@pytest.mark.parametrize('fault', ['raw', 'field_evidence'])
def test_changed_parent_claim_or_debt_field_evidence_still_rejects_child(debt_view, fault):
    service, requests, parent, child = debt_view
    if fault == 'raw':
        parent['claims'][0]['raw']['Relation'] = '변경된 관계'
    else:
        row = parent['claims'][1]
        row['field_evidence'][next(iter(row['raw']['fields']))][0]['quote'] = '변경된 값'
    with service.repository.connect() as db:
        with pytest.raises(ValueError, match='동일 부모'):
            business_use.concept_read_view(service, db, parent, child['id'])
    assert len(requests) == 1


def test_debt_table_legacy_entity_target_keeps_whole_context_under_f3_opt_in(debt_view):
    service, requests, parent, _ = debt_view
    row = parent['claims'][1]
    values = [source['value'] for source in row['field_sources'].values()]
    blocks = [b for b in parent['blocks'] if b['id'] in {ref['block_id'] for ref in values}]
    chunk = dict(id='legacy-debt-event', source_version_id=blocks[0]['source_version_id'], blocks=blocks)
    raw = dict(Event=row['raw']['Event'], Entity=[row['raw']['fields']['업종(KSIC-10)']])
    legacy = autoschema.graph_record(chunk, 'event_entity', raw, 0)
    legacy['evidence'] = deepcopy(values)
    parent = dict(parent, claims=[legacy], chunks=[chunk], graph=autoschema.graph([legacy]))
    target = next(t for t in autoschema.concept_targets(parent['graph']) if t['kind'] == 'entity')
    whole = business_concepts.prepare(parent, [target], 'plain', service=service, source_context='whole')[0]
    selected = business_concepts.prepare(parent, [target], 'plain', service=service, source_context='verified_table_rows_v1')[0]
    assert selected['messages'] == whole['messages']
    assert selected['selection']['source_reference_map'] == whole['selection']['source_reference_map']
    assert selected['selection']['source_context']['status'] == 'retained'
    assert len(requests) == 1
