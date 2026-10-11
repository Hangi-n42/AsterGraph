"""Only identical model-selected Event sentences can retain duplicate literal addresses."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema
from app.tests.unit.test_knowledge_business_scope import block, scope_for


def literal_case():
    event = '기관은 신청을 접수한다.'
    blocks = [block('body', event, 'section:1 > p:1'), block('second', event, 'section:2 > p:1')]
    chunk = autoschema.chunks(blocks, 49152, 4096)[0]
    refs = [dict(block_id=alias, quote=event) for alias in chunk['source_reference_map']]
    scope = scope_for(chunk, event)
    scope['evidence'] = deepcopy(refs)
    scope['meanings'][0]['evidence'] = deepcopy(refs)
    scope['meanings'][0]['participants'] = [dict(field='Entity', entity_index=i, evidence=deepcopy(refs)) for i in range(2)]
    return chunk, dict(Event=event, Entity=['기관','신청']), scope


@pytest.mark.parametrize('different_version', [False, True])
def test_identical_selected_sentences_keep_all_literal_addresses_and_raw_scope(different_version):
    chunk, raw, scope = literal_case()
    claim = autoschema.graph_record(chunk, 'event_entity', raw, 0, scope=scope)
    record = claim['interpretation']
    assert not record['errors'] and record['raw'] == scope
    assert record['semantic_status'] == 'unverified'
    assert len(record['address_restorations']) == 3
    assert {(m['field'],m['entity_index']) for m in record['mentions']} == {('Event',None),('Entity',0),('Entity',1)}
    for mention in record['mentions']:
        assert mention['address_status'] == 'resolved'
        assert {r['block_id'] for r in mention['evidence']} == {'body','second'}
        assert all(r['quote']==mention['value'] and r['source_version_id']=='v' for r in mention['evidence'])
    other_chunk = deepcopy(chunk)
    other_chunk['id'] = 'other-parent-chunk'
    for b in other_chunk['blocks']:
        for ref in other_chunk['source_reference_map'].values():
            if ref['block_id'] == b['id']: ref['block_id'] = 'other-' + b['id']
        b['id'] = 'other-' + b['id']
        if different_version: b['source_version_id'] = 'other-version'
        b['locator']['element_path'] = 'other-parent/' + b['locator']['element_path']
    other = autoschema.graph_record(other_chunk,'event_entity',raw,0,scope=scope)
    graph = autoschema.graph([claim,other])
    assert len(graph['nodes'])==6 and len(graph['edges'])==4
    assert graph['interpretations'][claim['id']]['mentions'] == record['mentions']


@pytest.mark.parametrize('fault',['different_sentence','same_name_only','within_quote_duplicate','different_condition','foreign_version','outside_selected_meaning'])
def test_nonidentical_or_ambiguous_event_evidence_stays_unresolved(fault):
    chunk,raw,scope = literal_case()
    if fault == 'foreign_version':
        chunk['blocks'][1]['source_version_id']='other'
    elif fault == 'outside_selected_meaning':
        for i in range(2):
            added = dict(deepcopy(chunk['blocks'][i]), id='outside'+str(i))
            chunk['blocks'].append(added)
            chunk['source_reference_map']['outside'+str(i)] = dict(block_id=added['id'], span=added.get('span'))
        for participant in scope['meanings'][0]['participants']:
            participant['evidence'] = [dict(block_id='outside'+str(i),quote=raw['Event']) for i in range(2)]
    elif fault == 'within_quote_duplicate':
        raw['Event']='기관은 신청을 접수하며 기관에 기록한다.'
        for b in chunk['blocks']: b['text']=raw['Event']
        for refs in [scope['evidence'],scope['meanings'][0]['evidence'],*[p['evidence'] for p in scope['meanings'][0]['participants']]]:
            for ref in refs: ref['quote']=raw['Event']
    else:
        text = '기관은 신청을 검토한다.' if fault=='different_sentence' else '기관 신청' if fault=='same_name_only' else '조건이 있으면 기관은 신청을 접수한다.'
        chunk['blocks'][1]['text']=text
        alias = next(k for k,v in chunk['source_reference_map'].items() if v['block_id']=='second')
        for refs in [scope['evidence'],scope['meanings'][0]['evidence'],*[p['evidence'] for p in scope['meanings'][0]['participants']]]:
            next(r for r in refs if r['block_id']==alias)['quote']=text
    record=autoschema.scope_record(scope,chunk,raw,'event_entity')
    assert record['errors'] and record['raw']==scope
    assert not record.get('address_restorations')
    assert any(m['address_status']=='unresolved' for m in record['mentions'])
