"""Real parser/DOM and product entrypoint tests; generation is a local stub."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_concepts, business_run
from app.knowledge.business_models import ConceptRunRequest
from app.knowledge.schemas import RunRequest, SourceRegistration
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business import finish
from app.tests.unit.test_knowledge_concept_source_map_entrypoints import pool, store

HTML = '''<article id="source"><section><h1>Fixture appendix</h1><p>Fixture classification</p><table>
<tr><td>테마</td><td>분야</td><td>품목명</td><td>분류코드</td><td>업종명</td></tr>
<tr><td rowspan="6">category</td><td rowspan="6">field</td><td rowspan="3">itemA</td><td>codeA</td><td>activityA</td></tr>
<tr><td>codeB</td><td>activityB</td></tr><tr><td>codeC</td><td>activityC</td></tr>
<tr><td>otherD</td><td>codeD</td><td>activityD</td></tr>
<tr><td>otherE</td><td>codeE</td><td>activityE</td></tr>
<tr><td>otherF</td><td>codeF</td><td>activityF</td></tr>
</table><ul><li>Fixture note: classification needs a separate inspection.</li></ul></section></article>'''


@pytest.fixture
def factory(tmp_path, monkeypatch):
    services = []
    requests = []
    class Stub:
        def __init__(self, *args): pass
        def execution_identity(self, model, temperature, **limits):
            return dict(engine='ollama', engine_version='fixture-only', model_digest='a'*64,
                precision=dict(weights='fixture'), sampling=dict(contract='ollama-request-and-model-defaults-v1',
                    request_options=dict(temperature=temperature,num_predict=limits['max_tokens'],num_ctx=limits['context_tokens']),
                    think=limits['think'],model_parameters='fixture',model_configuration_sha256='b'*64))
        async def generate(self, request, cancelled=None):
            assert request.stage in {'concept_entity','concept_relation'}
            requests.append(request)
            return dict(request_id=request.request_id,text='검색 개념',done=True,done_reason='stop',failure_kind=None,elapsed_s=0)
    monkeypatch.setattr(business_run, 'ModelClient', Stub)
    monkeypatch.setattr('app.knowledge.business_use.publish',lambda *args:dict(id='fixture-change'))
    def make(html=HTML):
        service=KnowledgeService(tmp_path/f'{len(services)}.db');services.append(service)
        registration=service.register(f'fixture{len(services)}.html',html.encode(),SourceRegistration(
            title='fixture',publisher='fixture',namespace='test',selected_scope={'selector':'#source'}))
        vid=registration['source_version_id']
        parsed=finish(service,service.start(RunRequest(source_version_ids=[vid]))['run_id'])
        blocks=service.blocks(registration['source_id'],vid)['items']
        parent=pool(vid);parent['id']='parent'+str(len(services));parent['blocks']=blocks
        included=[b for b in blocks if b['text'] not in {'codeA','activityA'} and 'Fixture note:' not in b['text']]
        chunk=dict(id='fixture-owner',source_version_id=vid,blocks=deepcopy(included))
        claim=autoschema.graph_record(chunk,'entity_relation',dict(Head='itemA',Relation='classifies',Tail='activityB'),0)
        claim['evidence']=[dict(block_id=b['id'],source_version_id=vid,parse_run_id=parsed['id'],start_char=0,
            end_char=len(b['text']),quote=b['text']) for b in blocks if b['text'] in {'itemA','activityB'}]
        parent.update(chunks=[chunk],claims=[claim],graph=autoschema.graph([claim]))
        store(service,parent)
        return service,parent,requests
    try:yield make
    finally:
        for service in services:service.shutdown()


def request(parent, mode='verified_table_rows_v1'):
    target=next(n for n in parent['graph']['nodes'] if n['label']=='itemA')
    return ConceptRunRequest(parent_run_id=parent['id'],target_ids=[target['id']],neighbor_mode='plain',concept_source_context=mode)


def test_default_is_unchanged_and_opt_in_completes_item_rows_and_note(factory):
    service,parent,requests=factory();before=deepcopy(parent)
    _,baseline=business_concepts.plan(service,request(parent,'whole'))
    _,selected=business_concepts.plan(service,request(parent))
    a,b=baseline[0],selected[0];trace=b['selection']['source_context']
    assert 'source_context' not in a['selection'] and trace['status']=='selected'
    marker='\n\n개념화 대상과 연결 문맥:\n'
    assert a['messages'][1]['content'].partition(marker)[2]==b['messages'][1]['content'].partition(marker)[2]
    assert b['target']==a['target'] and b['selection']['selected_edge_ids']==a['selection']['selected_edge_ids']
    assert trace['item_rows']==[1,2,3] and len(trace['added'])==3 and len(trace['excluded'])==9
    assert all(word in b['messages'][1]['content'] for word in ['codeA','activityA','Fixture note:'])
    assert all(word not in b['messages'][1]['content'] for word in ['otherD','otherE','otherF'])
    refs=b['selection']['source_reference_map'];assert len(refs)==17
    assert len({(r['source_version_id'],r['block_id'],str(r['span'])) for r in refs.values()})==17
    assert {r['alias'] for r in trace['selected_references']}==set(refs)
    assert parent==before and not requests
    with service.repository.connect() as db:assert service.repository.get(db,'runs',parent['id'])==before


def test_selector_does_not_depend_on_target_id_or_label(factory):
    service,parent,_=factory()
    target=deepcopy(parent['graph']['nodes'][0]);target['id']='another-target';target['label']='unrelated display label'
    item=business_concepts.prepare(parent,[target],'plain',service=service,source_context='verified_table_rows_v1')[0]
    assert item['selection']['source_context']['status']=='selected' and len(item['selection']['source_reference_map'])==17


@pytest.mark.parametrize('fault',['hash','span','partial_scope','incomplete_parse'])
def test_unverified_source_retains_original_messages_with_explicit_reason(factory,fault):
    service,parent,_=factory();_,baseline=business_concepts.plan(service,request(parent,'whole'))
    with service.repository.connect() as db:
        version=service.repository.get(db,'versions',parent['input_version_ids'][0])
        if fault=='incomplete_parse':
            parse=service.repository.get(db,'runs',version['latest_parse_run_id']);parse['units'][0]['status']='failed';service.repository.save(db,'runs',parse)
    if fault=='hash':service.raw_path(version).write_bytes(b'changed')
    if fault=='span':parent['blocks'][0]['locator']['heading_level']=6
    if fault=='partial_scope':parent['blocks']=[b for b in parent['blocks'] if 'Fixture note:' not in b['text']]
    if fault in {'span','partial_scope'}:
        with service.repository.connect() as db:service.repository.save(db,'runs',parent)
    _,selected=business_concepts.plan(service,request(parent))
    assert selected[0]['messages']==baseline[0]['messages']
    trace=selected[0]['selection']['source_context'];assert trace['status']=='retained' and trace['unresolved']


@pytest.mark.parametrize('html',[
    HTML.replace('<table>','<ul><li><table>').replace('</table>','</table></li></ul>'),
    HTML.replace('</section>','<table><tr><td>second</td></tr></table></section>'),
    HTML.replace('Fixture note: classification needs a separate inspection.','Fixture note: 별표99를 참조한다.'),
])
def test_nested_multiple_or_unresolved_reference_scope_is_not_pruned(factory,html):
    service,parent,_=factory(html);_,selected=business_concepts.plan(service,request(parent))
    trace=selected[0]['selection']['source_context'];assert trace['status']=='retained' and trace['unresolved']
    _,baseline=business_concepts.plan(service,request(parent,'whole'));assert baseline[0]['messages']==selected[0]['messages']


def test_actual_selected_neighbor_evidence_cannot_be_excluded(factory):
    service,parent,_=factory();target=next(n for n in parent['graph']['nodes'] if n['label']=='itemA')
    other=deepcopy(parent['claims'][0]);other['id']='neighbor-claim'
    block=next(b for b in parent['blocks'] if b['text']=='activityD');other['evidence']=[dict(block_id=block['id'],
        source_version_id=block['source_version_id'],parse_run_id=block['parse_run_id'],start_char=0,end_char=len(block['text']),quote=block['text'])]
    parent['claims'].append(other)
    edge=deepcopy(parent['graph']['edges'][0]);edge.update(id='selected-neighbor',claim_id=other['id']);parent['graph']['edges'].append(edge)
    item=business_concepts.prepare(parent,[target],'plain',service=service,source_context='verified_table_rows_v1')[0]
    trace=item['selection']['source_context'];assert 'neighbor-claim' in trace['claim_ids']
    assert trace['status']=='retained' and trace['unresolved']==['ambiguous_or_multiple_item_groups']


@pytest.mark.parametrize('entry',['start','refresh','execute'])
def test_real_product_entrypoints_use_planned_context_and_keep_states(factory,entry):
    service,parent,requests=factory();before=deepcopy(parent)
    parent['recipe']['options']['concept_source_context']='verified_table_rows_v1'
    if entry=='start':
        result=business_concepts.start(service,request(parent))
        with service.repository.connect() as db:assert service.repository.get(db,'runs',parent['id'])==before
    else:
        parent['source_projection']=dict(stop_new_requests_at='2099-01-01T00:00:00+00:00',blocks_without_selected_extraction_target=[],unattempted_extraction=[])
        with service.repository.connect() as db:service.repository.save(db,'runs',parent)
        if entry=='refresh':
            business_concepts.refresh_changed(service,parent,{c['id'] for c in parent['claims']});result=parent
        else:
            business_run.execute(service,parent['id'])
            with service.repository.connect() as db:result=service.repository.get(db,'runs',parent['id'])
            assert result['status']=='succeeded',result.get('error')
    assert requests and all(r.stage in {'concept_entity','concept_relation'} for r in requests)
    chosen=next(c for c in result['concepts'] if c['target']['label']=='itemA')
    assert chosen['selection']['source_context']['status']=='selected'
    actual=next(r for r in requests if r.request_id==chosen['request_id'])
    assert 'Fixture note:' in actual.messages[1]['content'] and 'codeA' in actual.messages[1]['content']
    assert chosen['status']=='unreviewed' and chosen['approved_is_a'] is False
    assert chosen['target']['claim_ids']==parent['graph']['nodes'][0]['claim_ids']
    assert result.get('concept_bindings')


def test_same_geometry_with_other_header_roles_keeps_original_scope(factory):
    service,parent,_=factory(HTML.replace('품목명','비용').replace('분류코드','금액'))
    _,baseline=business_concepts.plan(service,request(parent,'whole'))
    _,selected=business_concepts.plan(service,request(parent))
    trace=selected[0]['selection']['source_context']
    assert trace['status']=='retained' and trace['unresolved']==['unsupported_classification_headers']
    assert selected[0]['messages']==baseline[0]['messages']


@pytest.mark.parametrize('override,expected',[(None,'verified_table_rows_v1'),('whole','whole')])
def test_resume_inherits_context_policy_unless_explicitly_overridden(factory,monkeypatch,override,expected):
    from app.knowledge.business_models import BusinessRunRequest
    service,parent,requests=factory()
    parent['recipe']['options']['concept_source_context']='verified_table_rows_v1'
    with service.repository.connect() as db:
        version=service.repository.get(db,'versions',parent['input_version_ids'][0])
        for block in parent['blocks']:block['source_id']=version['source_id']
        service.repository.save(db,'runs',parent)
    monkeypatch.setattr(service.executor,'submit',lambda *args:None)
    monkeypatch.setattr(business_run.ModelClient,'identities',lambda *args:deepcopy(parent['model_identity']),raising=False)
    result=business_run.start(service,BusinessRunRequest(source_version_ids=parent['input_version_ids'],
        resume_run_id=parent['id'],concept_source_context=override))
    with service.repository.connect() as db:
        child=service.repository.get(db,'runs',result['run_id'])
        assert service.repository.get(db,'runs',parent['id'])==parent
    assert child['recipe']['options']['concept_source_context']==expected and not requests
