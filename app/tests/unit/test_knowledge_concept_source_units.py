"""Concept source ownership and exact packet preservation boundaries."""
from copy import deepcopy
from app.knowledge import autoschema
from app.tests.unit.test_knowledge_business_scope import block, scope_for


def pool(*, context=False, version='v'):
    text = '기관은 신청과 서류를 처리한다.'
    body = block('body', text)
    chunks = {}
    claims = []
    for n, (name, relation, tail) in enumerate([('one', '접수', '신청'), ('two', '검토', '서류')]):
        b = deepcopy(body)
        if n:
            b['context_only'] = context
            b['source_version_id'] = version
        note = dict(block('note:' + name, '필수 조건' if n == 0 else '무관 문맥'), context_only=True)
        chunk = dict(id=name, source_version_id=b['source_version_id'], blocks=[b, note],
            source_reference_map={'b1': dict(block_id='body', span=None), 'b2': dict(block_id=note['id'], span=None)})
        chunks[name] = chunk
        scope = scope_for(chunk, text, tail=tail)
        if context and n:
            note['context_only'] = False
            scope['evidence'].append(dict(block_id='b2', quote=note['text']))
        claims.append(autoschema.graph_record(chunk, 'entity_relation', dict(Head='기관', Relation=relation, Tail=tail), n, scope=scope))
    return chunks, claims, autoschema.graph(claims)


def test_relation_uses_own_claim_source_and_keeps_required_note():
    chunks, claims, graph = pool()
    target = next(t for t in autoschema.concept_targets(graph) if t['kind'] == 'relation' and t['label'] == '접수')
    messages, selection = autoschema.concept_messages(target, graph, chunks)
    assert selection['mandatory_chunk_ids'] == ['one']
    assert '필수 조건' in messages[-1]['content'] and '무관 문맥' not in messages[-1]['content']
    assert graph['edges'][0]['source_chunk_id'] == claims[0]['chunk_id']


def test_shared_entity_keeps_both_claim_sources_and_deduplicates_identical_packet():
    chunks, _, graph = pool()
    target = next(n for n in graph['nodes'] if n['label'] == '기관')
    messages, selection = autoschema.concept_messages(target, graph, chunks)
    assert selection['mandatory_chunk_ids'] == ['one', 'two']
    assert len(selection['source_reference_map']) == 3
    assert len(selection['duplicate_source_packets']) == 1
    assert '필수 조건' in messages[-1]['content'] and '무관 문맥' in messages[-1]['content']


def test_different_context_status_or_source_version_packets_are_not_deduplicated():
    for context, version in [(True, 'v'), (False, 'other-version')]:
        chunks, _, graph = pool(context=context, version=version)
        target = dict(id='relation', kind='relation', label='접수', claim_ids=[e['claim_id'] for e in graph['edges']])
        _, selection = autoschema.concept_messages(target, graph, chunks)
        assert len(selection['source_reference_map']) == 4
        assert not selection['duplicate_source_packets']


def test_model_view_excludes_only_restore_ledger_and_keeps_meaning_errors():
    _, claims, _ = pool()
    record = claims[0]['interpretation']
    record['address_restorations'] = [dict(kind='test', evidence=deepcopy(record['evidence']))]
    record['errors'] = ['preserved diagnostic']
    before = deepcopy(record)
    model = autoschema.compact_interpretation(record)
    assert 'address_restorations' not in model and model['errors'] == before['errors']
    assert model['meanings'][0]['conditions'] == before['meanings'][0]['conditions']
    assert record == before
