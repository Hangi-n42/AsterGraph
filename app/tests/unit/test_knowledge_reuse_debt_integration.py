"""F1/F4-b storage and graph boundary only; synthetic fixtures, no native model."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_concepts, business_run, business_use, graph_retrieval
from app.knowledge.business_models import HtmlLiteralRowsRequest
from app.tests.unit.test_knowledge_concept_source_map_entrypoints import environment, pool
from app.tests.unit.test_knowledge_html_debt_rows import HTML, parent_source

PUBLISH = business_use.publish


@pytest.mark.parametrize('full_source', [False, True])
def test_literal_rows_preserve_exact_concept_work_and_field_source_boundaries(environment, monkeypatch, full_source):
    service, requests = environment
    monkeypatch.setattr(business_use, 'publish', PUBLISH)
    html = HTML.replace('</div>', '<p>기관은 신청을 접수한다.</p></div>')
    parent, selected = parent_source(service, html)
    paragraph = next(b for b in parent['blocks'] if b['text'] == '기관은 신청을 접수한다.')
    chunk = autoschema.chunks([paragraph], 49152, 8192)[0]
    claim = autoschema.graph_record(chunk, 'entity_relation', dict(Head='기관', Relation='접수', Tail='신청'), 0)
    config = pool(paragraph['source_version_id'])
    parent.update(chunks=[chunk], claims=[claim], graph=autoschema.graph([claim]),
                  recipe=config['recipe'], model_identity=config['model_identity'], metrics=config['metrics'])
    business_run.save(service, parent)
    target = next(t for t in autoschema.concept_targets(parent['graph']) if t['kind'] == 'entity')
    planned = business_concepts.prepare(parent, [target], 'plain')[0]
    concept = business_concepts.apply_selected_contract(service, parent, planned)
    assert len(requests) == 1 and concept['status'] == 'unreviewed'
    before = deepcopy(parent)

    result = service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=parent['id'], block_ids=selected))
    run = service.run(result['run_id'])
    assert result['stored_rows'] == 2 and result['model_calls'] == 0 and not result['rejections']
    for key in ('recipe', 'units', 'concepts', 'concept_work', 'concept_bindings', 'blocks', 'chunks'):
        assert run[key] == before[key]
    assert run['claims'][:1] == before['claims']
    assert autoschema.concept_targets(run['graph']) == autoschema.concept_targets(before['graph'])
    rebuilt = business_concepts.prepare(run, [target], 'plain')[0]
    assert rebuilt == planned
    reused = business_concepts.apply_selected_contract(service, run, rebuilt)
    assert reused == concept and len(requests) == 1
    assert run['units'] == before['units'] and run['concept_work'] == before['concept_work']
    assert run['concept_bindings'] == before['concept_bindings']
    assert reused['relation'] == 'has_concept' and reused['approved_is_a'] is False
    with service.repository.connect() as db:
        change = service.repository.get(db, 'changesets', result['changeset_id'])
        assert service.repository.get(db, 'runs', parent['id']) == before
    added = run['claims'][1:]
    assert not {c['id'] for c in added}.intersection(change['eligible_ids'])
    assert all(c['review_status'] == 'unreviewed' and c['semantic_status'] == 'unknown' for c in added)
    assert all(n['application_state'] == 'unresolved' for c in added for n in c['table_mapping']['common_notes'])
    graph, _, passages, ignored = graph_retrieval.build(dict(run, include_unlinked_blocks=full_source), 'full')
    assert not ignored
    assert any(n.get('kind') == 'concept' and n['label'] == '테스트 유형' for _, n in graph.nodes(data=True))
    hints = business_use.concept_hints(run)
    assert all(hints[cid] == ['테스트 유형'] for cid in target['claim_ids'])
    assert all(hints[c['id']] == [] for c in added)
    for row in added:
        for field in row['raw']['fields']:
            node = next(i for i, n in graph.nodes(data=True) if n.get('field') == field and row['id'] in n['claim_ids'])
            refs = {passages[i]['evidence']['block_id'] for i in graph.successors(node) if i in passages}
            own = row['field_sources'][field]
            assert {own['value']['block_id'], own['header']['block_id']} <= refs
            other_values = {value['value']['block_id'] for name, value in row['field_sources'].items() if name != field}
            assert not refs.intersection(other_values)
    stable = deepcopy(run)
    repeat = service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=run['id'], block_ids=selected))
    repeated = service.run(repeat['run_id'])
    assert repeat['stored_rows'] == 0 and repeat['reused_rows'] == 2 and len(requests) == 1
    for key in ('claims', 'graph', 'units', 'concepts', 'concept_work', 'concept_bindings'):
        assert repeated[key] == stable[key]
