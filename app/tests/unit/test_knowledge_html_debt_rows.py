from copy import deepcopy
import json

import pytest

from app.knowledge import autoschema,business_html_rows,business_run,graph_retrieval
from app.knowledge.business_models import HtmlLiteralRowsRequest
from app.knowledge.schemas import RunRequest,SourceRegistration
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business import finish


# Structural fixture from D01; passing it is not a semantic quality result.
HTML='''<div id="source"><section><h1>&lt;별표 2&gt;</h1><p>업종별 융자제한 부채비율</p><ul>
<li>*업종별 산업분류코드 중 하위코드 항목이 있을 경우 우선적용
<table><tr><th data-native-col="0" rowspan="2">번호</th><th data-native-col="1" rowspan="2">업종(KSIC-10)</th><th data-native-col="2" rowspan="2">평균부채<br>비율(%)</th><th data-native-col="3" rowspan="2">제한부채<br>비율(%)</th><th data-native-col="4"></th></tr>
<tr><th data-native-col="4">사업전환<br>융자</th></tr>
<tr><td data-native-col="0">19</td><td data-native-col="1">C25(금속가공제품(기계 및 가구 제외))</td><td data-native-col="2">154.0</td><td data-native-col="3">462.1</td><td data-native-col="4">924.1</td></tr>
<tr><td data-native-col="0">20</td><td data-native-col="1">C26(전자부품, 컴퓨터, 영상, 음향 및 통신장비)</td><td data-native-col="2">115.2</td><td data-native-col="3">345.7</td><td data-native-col="4">691.4</td></tr></table></li>
<li>* 제한부채비율은 최소 200%, 최대 500% 이내</li>
<li>* 한국은행 기업경영분석에 의한 최근 3개년 가중평균 부채비율</li>
</ul></section></div>'''


def parent_source(service,html=HTML):
    registered=service.register('debt.html',html.encode(),SourceRegistration(
        title='표 구조 검사',publisher='검사',namespace='test',selected_scope={'selector':'#source'}))
    parsed=finish(service,service.start(RunRequest(source_version_ids=[registered['source_version_id']]))['run_id'])
    assert parsed['status']=='succeeded'
    blocks=service.blocks(registered['source_id'],registered['source_version_id'])['items']
    parent=dict(id=registered['source_version_id'],kind='business',status='partial',blocks=blocks,claims=[],concepts=[],
        graph=dict(nodes=[],edges=[]),requirements=[],assessments=[],repairs=[],units=[],
        input_version_ids=[registered['source_version_id']],chunks=[],sources={},model_identity={},
        recipe=dict(options=dict(context_tokens=49152,review_tokens=4096)),metrics=dict(llm_calls=0),started_at=None,finished_at=None)
    with service.repository.connect() as db:db.execute('INSERT INTO runs VALUES(?,?)',(parent['id'],json.dumps(parent)))
    ids=[b['id'] for b in blocks if b['locator'].get('row') in [2,3] and b['locator'].get('column')==1]
    assert len(ids)==2
    return parent,ids


@pytest.fixture
def source(tmp_path,monkeypatch):
    class NoModel:
        def __init__(self,*args):pytest.fail('Literal rows must not construct a model client')
    monkeypatch.setattr(business_run,'ModelClient',NoModel)
    service=KnowledgeService(tmp_path/'knowledge.db')
    try:yield service,*parent_source(service)
    finally:service.shutdown()


@pytest.mark.parametrize('full_source',[False,True])
def test_store_preserves_literals_units_uncertainty_and_field_addresses(source,full_source):
    service,parent,ids=source;before=deepcopy(parent)
    result=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=parent['id'],block_ids=ids))
    run=service.run(result['run_id'])
    assert result['stored_rows']==2 and result['model_calls']==0 and not result['rejections'],result
    claim=run['claims'][0];mapping=claim['table_mapping'];fields=claim['raw']['fields']
    assert list(fields.values())==['19','C25(금속가공제품(기계 및 가구 제외))','154.0','462.1','924.1']
    assert mapping['units']['평균부채\n비율(%)']['state']=='explicit_in_header'
    assert mapping['units']['제한부채\n비율(%)']['symbol']=='%'
    assert mapping['units']['사업전환\n융자']['state']=='unresolved'
    assert mapping['units']['사업전환\n융자']['symbol'] is None
    assert mapping['empty_header']['text']=='' and mapping['empty_header']['block_id'] is None
    assert len(mapping['common_notes'])==3 and all(n['application_state']=='unresolved' for n in mapping['common_notes'])
    assert claim['literal_source']['row_key']=={'번호':'19','업종(KSIC-10)':fields['업종(KSIC-10)']}
    assert claim['review_status']=='unreviewed' and claim['semantic_status']=='unknown'
    assert business_run.exact_direct_row(claim,run['blocks']) is None
    assert not autoschema.concept_targets(run['graph'])
    graph,_,passages,_=graph_retrieval.build(dict(run,source_versions={},include_unlinked_blocks=full_source),'full')
    node=next(n for n,v in graph.nodes(data=True) if v.get('field')=='평균부채\n비율(%)' and v['value']=='154.0')
    refs={passages[n]['evidence']['block_id'] for n in graph.successors(node)}
    assert claim['field_sources']['평균부채\n비율(%)']['value']['block_id'] in refs
    assert claim['field_sources']['제한부채\n비율(%)']['value']['block_id'] not in refs
    assert {n['evidence']['block_id'] for n in mapping['common_notes']}<=refs
    with service.repository.connect() as db:assert service.repository.get(db,'runs',parent['id'])==before


def test_repeat_requires_same_mapping_not_only_same_values(source):
    service,parent,ids=source
    first=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=parent['id'],block_ids=ids))
    run=service.run(first['run_id']);before=deepcopy(run['claims'])
    repeat=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=run['id'],block_ids=ids))
    assert repeat['stored_rows']==0 and repeat['reused_rows']==2
    assert service.run(repeat['run_id'])['claims']==before
    run['claims'][0]['table_mapping']['units']['사업전환\n융자']['symbol']='%'
    with service.repository.connect() as db:service.repository.save(db,'runs',run)
    conflict=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=run['id'],block_ids=ids))
    assert conflict['stored_rows']==0 and conflict['reused_rows']==1
    assert conflict['rejections'][0]['reason']=='existing_row_content_conflict'


@pytest.mark.parametrize('old,new',[
    ('업종(KSIC-10)','업종(KSIC-11)'),
    ('평균부채<br>비율(%)','평균부채<br>비율(배)'),
    ('최대 500%','최대 600%'),
    ('rowspan="2">번호','rowspan="1">번호'),
    ('<th data-native-col="4"></th>','<th data-native-col="4">단위(%)</th>'),
])
def test_changed_header_unit_note_or_geometry_is_not_reused(source,old,new):
    service,parent,ids=source
    first=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=parent['id'],block_ids=ids))
    changed,selected=parent_source(service,HTML.replace(old,new))
    changed['claims']=service.run(first['run_id'])['claims']
    with service.repository.connect() as db:service.repository.save(db,'runs',changed)
    result=service.store_business_html_rows(HtmlLiteralRowsRequest(parent_run_id=changed['id'],block_ids=selected))
    assert result['stored_rows']==0 and result['reused_rows']==0 and result['rejections']
    assert service.run(result['run_id'])['claims']==changed['claims']


def test_note_must_match_registered_parse_not_only_parent_payload(source):
    service,parent,ids=source;changed=deepcopy(parent)
    note=next(b for b in changed['blocks'] if '최대 500%' in b['text'])
    note['locator']['block_order']+=1
    claims,rejections=business_html_rows.prepare(service,changed,ids)
    assert not claims and rejections
