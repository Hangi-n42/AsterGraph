from copy import deepcopy
import json

import pytest

from app.knowledge import autoschema,business_run,business_html_rows,graph_retrieval
from app.knowledge.business_models import HtmlLiteralRowsRequest
from app.knowledge.schemas import RunRequest,SourceRegistration
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business import finish


HTML='''<div id="source"><h1>분류표</h1><table>
<tr><th data-native-col="0">테마</th><th data-native-col="1">분야</th><th data-native-col="2">품목명</th><th data-native-col="3">분류코드</th><th data-native-col="4">업종명</th></tr>
<tr><td data-native-col="0" rowspan="2">정보통신</td><td data-native-col="1" rowspan="2">능동형 컴퓨팅</td><td data-native-col="2" rowspan="2">퍼베이시브 컴퓨팅</td><td data-native-col="3">58221</td><td data-native-col="4">시스템 소프트웨어 개발 및 공급업</td></tr>
<tr><td data-native-col="3">58222</td><td data-native-col="4">응용 소프트웨어 개발 및 공급업</td></tr>
</table></div>'''


@pytest.fixture
def source(tmp_path,monkeypatch):
    class NoModel:
        def __init__(self,*args):pytest.fail('Literal rows must not construct a model client')
    monkeypatch.setattr(business_run,'ModelClient',NoModel)
    service=KnowledgeService(tmp_path/'knowledge.db')
    registered=service.register('table.html',HTML.encode(),SourceRegistration(title='표',publisher='기관',namespace='test',selected_scope={'selector':'#source'}))
    vid=registered['source_version_id']
    parsed=finish(service,service.start(RunRequest(source_version_ids=[vid]))['run_id'])
    blocks=service.blocks(registered['source_id'],vid)['items']
    parent=dict(id='parent',kind='business',status='partial',blocks=blocks,claims=[],concepts=[],graph=dict(nodes=[],edges=[]),
        requirements=[],assessments=[],repairs=[],units=[],input_version_ids=[vid],chunks=[],sources={},model_identity={},
        recipe=dict(options=dict(context_tokens=49152,review_tokens=4096)),metrics=dict(llm_calls=0),started_at=None,finished_at=None)
    with service.repository.connect() as db:db.execute('INSERT INTO runs VALUES(?,?)',(parent['id'],json.dumps(parent)))
    ids=[b['id'] for b in blocks if b['locator'].get('row') in [1,2] and b['locator'].get('column')==3]
    assert len(ids)==2 and parsed['status']=='succeeded'
    try:yield service,parent,ids
    finally:service.shutdown()


def test_product_store_keeps_merged_owner_and_each_field_source_and_graph_passage(source):
    service,parent,ids=source;before=deepcopy(parent)
    result=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id='parent',block_ids=ids))
    run=service.run(result['run_id'])
    assert result['stored_rows']==2 and result['model_calls']==0 and not result['rejections']
    assert [c['raw']['fields']['분류코드'] for c in run['claims']]==['58221','58222']
    assert all(c['construction_method']==business_html_rows.METHOD and c['review_status']=='unreviewed' for c in run['claims'])
    assert all(business_run.exact_direct_row(c,run['blocks']) is None for c in run['claims'])
    claim=run['claims'][1]
    assert claim['field_sources']['품목명']['value']['locator']['row']==1
    assert claim['literal_source']['row']==2
    graph,edges,passages,_=graph_retrieval.build(dict(run,source_versions={}), 'full')
    code_node=next(n for n,d in graph.nodes(data=True) if d.get('field')=='분류코드' and d['value']=='58222')
    refs=graph.nodes[code_node]['evidence']
    own=claim['field_sources']['분류코드']['value']['block_id']
    sibling=claim['field_sources']['업종명']['value']['block_id']
    assert own in {r['block_id'] for r in refs} and sibling not in {r['block_id'] for r in refs}
    assert {passages[n]['evidence']['block_id'] for n in graph.successors(code_node)}=={r['block_id'] for r in refs}
    assert not autoschema.concept_targets(run['graph'])
    with service.repository.connect() as db:assert service.repository.get(db,'runs','parent')==before


def test_duplicate_selection_and_ambiguous_cell_are_not_stored(source):
    service,parent,ids=source
    with pytest.raises(ValueError,match='중복'):business_html_rows.prepare(service,parent,[ids[0],ids[0]])
    changed=deepcopy(parent);b=deepcopy(next(b for b in changed['blocks'] if b['id']==ids[0]));b['id']='duplicate';changed['blocks'].append(b)
    claims,rejections=business_html_rows.prepare(service,changed,[ids[0]])
    assert not claims and rejections[0]['reason']=='cell_owner_not_unique'


@pytest.mark.parametrize('change',['text','span','hash'])
def test_source_text_geometry_and_raw_hash_mismatch_are_rejected(source,change):
    service,parent,ids=source;changed=deepcopy(parent)
    if change=='hash':
        with service.repository.connect() as db:version=service.repository.get(db,'versions',parent['input_version_ids'][0])
        service.raw_path(version).write_bytes(HTML.encode()+b'changed')
    else:
        block=next(b for b in changed['blocks'] if b['id']==ids[0])
        if change=='text':block['text']='58229'
        else:block['locator']['merged_span']['rows']=2
    claims,rejections=business_html_rows.prepare(service,changed,ids)
    assert rejections
    assert len(claims)==(1 if change=='text' else 0)


def test_unrecognized_side_by_side_lists_are_not_paired(source):
    service,parent,ids=source;changed=deepcopy(parent)
    header=next(b for b in changed['blocks'] if b['locator'].get('row')==0 and b['locator'].get('column')==0)
    header['text']='독립 목록'
    claims,rejections=business_html_rows.prepare(service,changed,ids)
    assert not claims and rejections


def test_same_row_reuses_claim_and_conflicting_value_is_rejected(source):
    service,parent,ids=source
    first=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id='parent',block_ids=ids))
    second=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=first['run_id'],block_ids=ids))
    assert second['stored_rows']==0 and second['reused_rows']==2
    run=service.run(second['run_id']);assert len(run['claims'])==2
    run['claims'][0]['raw']['fields']['업종명']='충돌 값'
    with service.repository.connect() as db:service.repository.save(db,'runs',run)
    third=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=run['id'],block_ids=ids))
    assert third['stored_rows']==0 and third['reused_rows']==1
    assert third['rejections'][0]['reason']=='existing_row_content_conflict'
    assert service.run(third['run_id'])['claims'][0]['raw']['fields']['업종명']=='충돌 값'


def test_existing_review_status_graph_annotations_and_concept_connections_survive(source):
    service,parent,ids=source
    b=next(b for b in parent['blocks'] if b['id']==ids[0])
    claim=autoschema.graph_record(dict(id='existing',source_version_id=b['source_version_id'],blocks=[b]),
        'entity_relation',dict(Head='기관',Relation='연결',Tail='분류'),0)
    claim['review_status']='accepted';parent['claims']=[claim];parent['graph']=autoschema.graph(parent['claims'])
    parent['graph']['nodes'][0]['review_note']='보존 메모'
    parent['concepts']=[dict(target=deepcopy(parent['graph']['nodes'][0]),concepts=['기존 개념'],status='accepted')]
    with service.repository.connect() as db:service.repository.save(db,'runs',parent)
    before=deepcopy(parent)
    result=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id='parent',block_ids=ids))
    run=service.run(result['run_id'])
    assert run['claims'][0]==before['claims'][0] and run['concepts']==before['concepts']
    assert run['graph']['nodes'][:len(before['graph']['nodes'])]==before['graph']['nodes']
    graph,edges,_,_=graph_retrieval.build(dict(run,source_versions={}), 'full')
    assert any(e['relation']=='has_concept' and graph.nodes[e['tail']]['label']=='기존 개념' for e in edges)


def test_full_source_segments_overlap_only_their_own_field_cells(source,monkeypatch):
    from app.knowledge import source_segments
    service,parent,ids=source
    result=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id='parent',block_ids=ids))
    run=service.run(result['run_id']);run['include_unlinked_blocks']=True
    real_split=source_segments.split
    def split(block):
        if block['id']==ids[1]:return [dict(span=[0,2],shared_spans=[]),dict(span=[2,5],shared_spans=[])]
        return real_split(block)
    monkeypatch.setattr(source_segments,'split',split)
    graph,_,passages,_=graph_retrieval.build(dict(run,source_versions={}), 'full')
    code=next(n for n,d in graph.nodes(data=True) if d.get('field')=='분류코드' and d['value']=='58222')
    own=[passages[n]['evidence'] for n in graph.successors(code) if passages[n]['evidence']['block_id']==ids[1]]
    assert {(r['start_char'],r['end_char']) for r in own}=={(0,2),(2,5)}
    sibling=run['claims'][1]['field_sources']['업종명']['value']['block_id']
    assert sibling not in {passages[n]['evidence']['block_id'] for n in graph.successors(code)}


def test_same_values_at_distinct_rows_and_versions_do_not_merge(source):
    service,parent,ids=source
    result=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id='parent',block_ids=ids))
    first=service.run(result['run_id'])['claims']
    assert first[0]['id']!=first[1]['id']
    graph=autoschema.graph(first)
    assert len([n for n in graph['nodes'] if n.get('field')=='품목명'])==2
    registered=service.register('table.html',HTML.encode(),SourceRegistration(title='다른 출처',publisher='다른 기관',namespace='other',selected_scope={'selector':'#source'}))
    parsed=finish(service,service.start(RunRequest(source_version_ids=[registered['source_version_id']]))['run_id'])
    blocks=service.blocks(registered['source_id'],registered['source_version_id'])['items']
    other=dict(parent,id='other-parent',blocks=blocks,input_version_ids=[registered['source_version_id']])
    selected=[b['id'] for b in blocks if b['locator'].get('row') in [1,2] and b['locator'].get('column')==3]
    second,rejections=business_html_rows.prepare(service,other,selected)
    assert parsed['status']=='succeeded' and not rejections
    assert not {c['id'] for c in first}&{c['id'] for c in second}
    assert first[0]['field_sources']['품목명']['value']['source_version_id']!=second[0]['field_sources']['품목명']['value']['source_version_id']
