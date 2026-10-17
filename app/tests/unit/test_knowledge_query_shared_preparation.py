from copy import deepcopy
from weakref import ref

import numpy as np
import pytest

from app.knowledge import autoschema, business_run, business_use, graph_retrieval as gr, source_reader
from app.knowledge.business_models import BusinessQuery
from app.knowledge.discovery_profile import FrozenIndex
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_graph_retrieval import snapshot


@pytest.fixture
def source_query(tmp_path, monkeypatch):
    source = snapshot()
    original = dict(id='origin', kind='business', status='succeeded', units=[], model_identity={},
        recipe=dict(options=dict(context_tokens=49152, review_tokens=4096)),
        sources=source['source_versions'], blocks=source['blocks'], claims=source['claims'], concepts=source['concepts'])
    service = KnowledgeService(tmp_path/'knowledge.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('origin', business_use.encode(original)))
    monkeypatch.setattr(gr, 'embed', lambda texts, *, service=None: np.asarray([[1., .5] for _ in texts]))
    monkeypatch.setattr(FrozenIndex, 'rank', lambda self, query, allowed: [
        dict(block_id=key, score=1.) for key in sorted(allowed)])
    def call(service, run, stage, instruction, context, schema, **kwargs):
        if stage == 'graph_retrieval_filter':
            return dict(selected_ids=[context['candidate_facts'][0]['id']])
        context = source_reader.restore_versions(context)
        return dict(answer='원문', choice=None, citations=[context['context'][0]['id']], limitations=[])
    monkeypatch.setattr(business_run, 'json_call', call)
    try:
        yield service, original
    finally:
        service.shutdown()


@pytest.mark.parametrize('retrieval', ['bm25', 'hybrid_graph'])
def test_source_query_builds_once_keeps_selected_contexts_independent_and_does_not_mutate(source_query, monkeypatch, retrieval):
    service, original = source_query
    build, chunks, source_context = gr.build, autoschema.chunks, gr.source_context
    built, bundles, graph_before, bundles_before, contexts = [], [], [], [], []
    def record_build(*args, **kwargs):
        result = build(*args, **kwargs)
        built.append(result)
        graph_before.append((deepcopy(dict(result[0].nodes(data=True))),
            deepcopy(list(result[0].edges(keys=True, data=True))), deepcopy(result[1:])))
        return result
    def record_chunks(*args, **kwargs):
        result = chunks(*args, **kwargs)
        bundles.append(result); bundles_before.append(deepcopy(result))
        return result
    def record_context(*args, **kwargs):
        result = source_context(*args, **kwargs)
        contexts.append(result)
        return result
    monkeypatch.setattr(gr, 'build', record_build)
    monkeypatch.setattr(autoschema, 'chunks', record_chunks)
    monkeypatch.setattr(gr, 'source_context', record_context)
    request = BusinessQuery(source_run_id='origin', question='원문', retrieval=retrieval, limit=2)
    for count in [1, 2]:
        result = business_use.query(service, request)
        assert result['status'] == 'answered'
        assert len(built) == count and len(bundles) == count
        assert len(contexts) == count * 3
        assert contexts[-1] is not contexts[-2] and contexts[-2] is not contexts[-3]
        graph, edges, passages, ignored = built[-1]
        nodes_before, edges_before, rest_before = graph_before[-1]
        assert dict(graph.nodes(data=True)) == nodes_before
        assert list(graph.edges(keys=True, data=True)) == edges_before
        assert (edges, passages, ignored) == rest_before
        assert bundles == bundles_before
        with service.repository.connect() as db:
            assert service.repository.get(db, 'runs', 'origin') == original
    assert built[0] is not built[1] and bundles[0] is not bundles[1]


@pytest.mark.parametrize('retrieval', ['bm25', 'hybrid_graph'])
def test_bundle_provider_is_released_before_qa_and_is_fresh_for_each_request(source_query, monkeypatch, retrieval):
    service, _ = source_query
    factory, call = gr.source_context_bundles, business_run.json_call
    providers = []
    def record_factory(*args):
        provider = factory(*args)
        providers.append(ref(provider))
        return provider
    def inspect_call(*args, **kwargs):
        if args[2] == 'business_qa':
            assert all(provider() is None for provider in providers)
        return call(*args, **kwargs)
    monkeypatch.setattr(gr, 'source_context_bundles', record_factory)
    monkeypatch.setattr(business_run, 'json_call', inspect_call)
    request = BusinessQuery(source_run_id='origin', question='원문', retrieval=retrieval, limit=2)
    for count in [1, 2]:
        assert business_use.query(service, request)['status'] == 'answered'
        assert len(providers) == count and all(provider() is None for provider in providers)


def test_changed_source_run_and_options_get_new_request_bundles(source_query, monkeypatch):
    service, original = source_query
    chunks, inputs = autoschema.chunks, []
    def record(blocks, context_tokens, output_tokens, **kwargs):
        inputs.append((deepcopy(blocks), context_tokens, output_tokens))
        return chunks(blocks, context_tokens, output_tokens, **kwargs)
    monkeypatch.setattr(autoschema, 'chunks', record)
    request = BusinessQuery(source_run_id='origin', question='원문', retrieval='hybrid_graph', limit=2)
    assert business_use.query(service, request)['status'] == 'answered'
    changed = deepcopy(original)
    changed['id'] = 'changed-origin'
    changed['sources']['v2'] = {}
    changed['blocks'].append(dict(id='new-block', source_version_id='v2', parse_run_id='p2', text='새 조건'))
    changed['recipe']['options'].update(context_tokens=8192, review_tokens=256)
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (changed['id'], business_use.encode(changed)))
    assert business_use.query(service, request.model_copy(update=dict(source_run_id=changed['id'])))['status'] == 'answered'
    assert len(inputs) == 2 and inputs[0][0] == original['blocks'] and inputs[1][0] == changed['blocks']
    assert inputs[0][1:] == (49152, 4096) and inputs[1][1:] == (8192, 256)
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', original['id']) == original


@pytest.mark.parametrize('failure', [False, True])
def test_bundle_provider_is_lazy_caches_empty_and_never_caches_failure(monkeypatch, failure):
    calls = []
    def chunks(*args, **kwargs):
        calls.append(args)
        if failure:
            raise ValueError('bundle failure')
        return []
    monkeypatch.setattr(autoschema, 'chunks', chunks)
    provider = gr.source_context_bundles([], dict(context_tokens=4096, review_tokens=256))
    assert not calls
    for _ in range(2):
        if failure:
            with pytest.raises(ValueError, match='bundle failure'):
                provider()
        else:
            assert provider() == []
    assert len(calls) == (2 if failure else 1)


def test_bundle_provider_keeps_capacity_validation_at_first_use():
    provider = gr.source_context_bundles([], dict(context_tokens=1000, review_tokens=4096))
    with pytest.raises(ValueError, match='No input capacity'):
        provider()


@pytest.mark.parametrize('context_tokens', [4096, 2800])
def test_shared_bundles_keep_per_selection_spans_locators_parents_and_continuations(context_tokens):
    blocks = [dict(id='head', text='조건', source_version_id='v1', parse_run_id='p1',
                   locator=dict(element_path='h1:nth-of-type(1)', heading_level=1)),
        dict(id='row-parent', text='기관', source_version_id='v1', parse_run_id='p1',
             locator=dict(element_path='table', row=1, column=0, merged_span=dict(rows=2, columns=1))),
        dict(id='row', text='다만 변경 제외', source_version_id='v1', parse_run_id='p1',
             locator=dict(element_path='table', row=2, column=1)),
        dict(id='parent', text='상위 조건', source_version_id='v1', parse_run_id='p1',
             locator=dict(element_path='ul:nth-of-type(1) > li:nth-of-type(1)::text(0)')),
        dict(id='body', text='조건과 예외 '*80, source_version_id='v1', parse_run_id='p1',
             locator=dict(element_path='ul:nth-of-type(1) > li:nth-of-type(1) > ul:nth-of-type(1) > li:nth-of-type(1)')),
        dict(id='body', text='다른 출처', source_version_id='v2', parse_run_id='p2', locator=dict(element_path=''))]
    options = dict(context_tokens=context_tokens, review_tokens=256)
    provider = gr.source_context_bundles(blocks, options)
    bundles = provider()
    before = deepcopy((blocks, bundles))
    for version, key in [('v1', 'row'), ('v1', 'body'), ('v2', 'body')]:
        block = next(b for b in blocks if b['id'] == key and b['source_version_id'] == version)
        selected = [dict(id='passage-'+version+'-'+key, text=block['text'], source_reference=dict(
            block_id=key, source_version_id=version, parse_run_id=block['parse_run_id'],
            start_char=0, end_char=len(block['text'])))]
        expected = gr.source_context(blocks, deepcopy(selected), options)
        actual = gr.source_context(blocks, selected, options, get_bundles=provider)
        assert actual == expected
        assert all(row['supports_context_ids'] == ['passage-'+version+'-'+key] for row in actual)
    assert (blocks, bundles) == before
    if context_tokens == 2800:
        assert any(block.get('continuation_bundle') for bundle in bundles for block in bundle['blocks'])


@pytest.mark.parametrize('context_tokens', [4096, 2800])
def test_parent_prefilter_matches_exhaustive_rules_for_empty_nested_table_and_other_source(monkeypatch, context_tokens):
    paths = ['', 'table', 'ul:nth-of-type(1) > li:nth-of-type(1)::text(0)',
        'ul:nth-of-type(1) > li:nth-of-type(1) > ul:nth-of-type(1) > li:nth-of-type(1) > p:nth-of-type(1)',
        'ul:nth-of-type(1) > li:nth-of-type(1) > span:nth-of-type(1)']
    blocks = [dict(id='b'+str(i), text='같은 이름' if i != 3 else '조건과 예외 '*80,
        source_version_id='v1', parse_run_id='p1', locator=dict(element_path=path))
        for i, path in enumerate(paths)]
    blocks[1]['locator'].update(row=0, column=0, merged_span=dict(rows=2, columns=1))
    blocks.append(dict(blocks[2], source_version_id='v2', parse_run_id='p2'))
    before = deepcopy(blocks)
    list_parents = autoschema.list_parents
    pools = []
    def record(block, candidates):
        pools.append((block['source_version_id'], len(candidates)))
        return list_parents(block, candidates)
    monkeypatch.setattr(autoschema, 'list_parents', record)
    actual = autoschema.chunks(blocks, context_tokens, 256, target_chars=1)
    assert pools == [('v1', 3)] * 5 + [('v2', 1)]
    groups = [blocks[:-1], blocks[-1:]]
    def exhaustive(block, candidates):
        group = next(group for group in groups if any(item is block for item in group))
        return list_parents(block, group)
    monkeypatch.setattr(autoschema, 'list_parents', exhaustive)
    expected = autoschema.chunks(blocks, context_tokens, 256, target_chars=1)
    assert actual == expected and blocks == before
    assert autoschema.chunks([], context_tokens, 256, target_chars=1) == []
    if context_tokens == 2800:
        assert any(block.get('continuation_bundle') for chunk in actual for block in chunk['blocks'])


def test_bundle_failure_keeps_retrieval_failure_trace_and_stored_state(source_query, monkeypatch):
    service, original = source_query
    def fail(*args, **kwargs):
        raise ValueError('No input capacity after instructions/schema/output reservation')
    monkeypatch.setattr(autoschema, 'chunks', fail)
    result = business_use.query(service, BusinessQuery(source_run_id='origin', question='원문', retrieval='hybrid_graph'))
    assert result['status'] == 'retrieval_failed' and 'No input capacity' in result['error']
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', result['run_id'])
        assert run['status'] == 'failed' and run['graph_retrieval']['contract']
        assert not run['units'] and service.repository.get(db, 'runs', 'origin') == original
