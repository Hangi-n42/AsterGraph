"""Synthetic contract declarations, not evidence of model selection or semantic support."""
from copy import deepcopy

import pytest

from app.knowledge import answer_links as links, business_run, business_use as use
from app.knowledge.business_models import BusinessQuery
from app.tests.unit.test_knowledge_answer_source_citations import source, QUOTE


def raw(**changes):
    return dict(dict(answer='q13 일반 설명. 다른 설명.', choice=None, citations=['q1'], limitations=['확인 불가'],
        source_citations=[dict(quote_id='sq_alpha', evidence_ref='b1', quote=QUOTE)],
        answer_links=[dict(target='answer', anchor='q13', claim_refs=[], quote_refs=['sq_alpha'])]), **changes)


def evaluate(monkeypatch, payload, contract=links.CONTRACT, views=None, review_context=None):
    views = views or [source()]
    model, refs = use.answer_references([dict(id='claim', text='제공 주장')], views, source_citation_contract=contract)
    run = dict(recipe=dict(options={}), query=dict(source_citation_contract=contract), units=[])
    if review_context is not None:
        run['selected_review_context'] = deepcopy(review_context)
    seen = []
    def call(service, active, stage, messages, schema, **kwargs):
        seen.append(dict(messages=messages, schema=schema, refs=kwargs['reference_map']))
        active['units'].append(dict(status='succeeded', response=dict(parsed=deepcopy(payload))))
        return active['units'][-1]['response']
    monkeypatch.setattr(business_run, 'call', call)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    context = dict(context=[dict(id='claim')], source_evidence=views)
    if review_context is not None:
        from app.knowledge.selected_review_answer import answer_context
        context.update(answer_context(review_context, ['claim'], contract))
    instruction = '기존 안내' + use.source_citations_instruction(contract)
    preview = business_run.json_request(run, 'business_qa', instruction, context, model, reference_map=refs)
    output = business_run.json_call(None, run, 'business_qa', instruction, context, model, reference_map=refs)
    assert seen == [dict(messages=preview['messages'], schema=preview['schema'], refs=preview['reference_map'])]
    assert run['units'][0]['response']['parsed'] == payload
    if output is not None:
        use.record_answer_source_citations(run, output, views, views)
        links.record(run, output, ['claim'])
        assert '_answer_link_metadata' not in output
    return output, run, preview


def bounded_review():
    return dict(required_claim_ids=['claim'], snapshot_id='s', review_run_id='r', final_review_unit_id='f',
        source_review_unit_id='b', review_fingerprint='rf', snapshot_fingerprint='sf',
        findings={'item': dict(findings=[dict(status='undetermined', statement='비교 전제로 확정 불가',
            reason='속성 일치만 확인함', source_result_ids=['observation']), dict(status='confirmed')])},
        source_observations=[dict(target_id='observation', represented_content='합성 비교 전제',
            evidence=[dict(source_version_id='v', parse_run_id='p', block_id='b', start_char=0, end_char=2, quote='전제')],
            expression_bindings=[dict(claim_id='claim', field='statement', quote='합성', span=[0, 2], claim_version='cv')],
            condition_references=[], condition_state='not_applicable')])


def test_bounded_judgment_keeps_review_premises_separate_from_direct_source_support(monkeypatch):
    reviewed = bounded_review(); before = deepcopy(reviewed)
    declaration = dict(target='limitations', anchor='확인 불가', claim_refs=[], quote_refs=[], review_refs=['rv_item_1'])
    payload = raw(answer_links=[declaration])
    _, run, packet = evaluate(monkeypatch, payload, links.REVIEW_CONTRACT, review_context=reviewed)
    record = run['answer_links']
    assert record['status'] == 'recorded' and record['links'][0]['status'] == 'resolved'
    assert record['links'][0]['declaration'] == declaration
    scope = record['review_scopes']['rv_item_1']
    assert scope['status'] == 'undetermined' and scope['semantic_support'] == 'not_assessed'
    assert scope['snapshot_id'] == 's' and scope['scope'] == 'selected_source_observations_only'
    assert scope['premises'][0]['evidence'] == reviewed['source_observations'][0]['evidence']
    prop = packet['schema']['properties']['answer_links']['items']['properties']
    assert prop['review_refs']['items']['enum'] == ['rv_item_1']
    assert 'rv_item_2' not in record['review_scopes']
    assert reviewed == before and run['units'][0]['response']['parsed'] == payload
    links.withhold(run)
    assert not run['answer_links'].get('review_scopes') and not run['answer_links']['links']


@pytest.mark.parametrize('fault', ['unknown', 'confirmed', 'mixed', 'missing', 'not_list', 'missing_premise', 'undelivered'])
def test_invalid_review_links_never_become_source_support(monkeypatch, fault):
    reviewed = bounded_review()
    declaration = dict(target='limitations', anchor='확인 불가', claim_refs=[], quote_refs=[], review_refs=['rv_item_1'])
    if fault in {'unknown', 'confirmed'}: declaration['review_refs'] = ['rv_absent' if fault == 'unknown' else 'rv_item_2']
    elif fault == 'mixed': declaration['quote_refs'] = ['sq_alpha']
    elif fault == 'missing': declaration['review_refs'] = []
    elif fault == 'not_list': declaration['review_refs'] = 'rv_item_1'
    elif fault == 'missing_premise': reviewed['source_observations'] = []
    else:
        from app.knowledge.selected_review_answer import review_scopes
        assert review_scopes(reviewed, []) == {}
        return
    _, run, _ = evaluate(monkeypatch, raw(answer_links=[declaration]), links.REVIEW_CONTRACT, review_context=reviewed)
    assert run['answer_links']['links'][0]['status'] == 'unresolved'


@pytest.mark.parametrize('contract', [links.REVIEW_CONTRACT, links.SEGMENT_CONTRACT])
def test_experimental_review_links_require_explicit_selection_and_a_bound_review(contract):
    kwargs = dict(question='합성', snapshot_id='s', selected_review=dict(run_id='r', unit_id='u'))
    query, _ = use.resolve_query_defaults(BusinessQuery(**kwargs), 'graph')
    assert query.source_citation_contract == links.CONTRACT
    experimental, _ = use.resolve_query_defaults(BusinessQuery(**kwargs, source_citation_contract=contract), 'graph')
    assert experimental.source_citation_contract == contract
    old, _ = use.resolve_query_defaults(BusinessQuery(**kwargs, source_citation_contract=links.CONTRACT), 'graph')
    assert old.source_citation_contract == links.CONTRACT
    with pytest.raises(ValueError, match='selected_review'):
        BusinessQuery(question='합성', snapshot_id='s', source_citation_contract=contract)


def segments():
    fact = dict(text='상품의 부위는 **등심**입니다.', claim_refs=['q1'], quote_refs=['sq_alpha'], review_refs=[])
    limit = dict(text='이 부위 비교만으로 적합성은 확정할 수 없습니다.', claim_refs=[], quote_refs=[], review_refs=['rv_item_1'])
    return dict(answer=[fact, deepcopy(fact), limit], limitations=[deepcopy(limit), deepcopy(limit)],
        choice=None, citations=['q1'], source_citations=raw()['source_citations'])


def test_text_is_generated_once_and_repeated_segments_keep_their_exact_locations(monkeypatch):
    payload = segments(); before = deepcopy(payload)
    output, run, packet = evaluate(monkeypatch, payload, links.SEGMENT_CONTRACT, review_context=bounded_review())
    assert output['answer'] == '\n\n'.join(p['text'] for p in payload['answer'])
    assert output['limitations'] == [p['text'] for p in payload['limitations']]
    assert payload == before == run['units'][0]['response']['parsed']
    assert '**등심**' in output['answer'] and 'answer_links' not in packet['schema']['properties']
    assert set(packet['schema']['properties']['answer']['items']['properties']) == {'text', 'claim_refs', 'quote_refs', 'review_refs'}
    record = run['answer_links']
    assert record['status'] == 'recorded' and record['duplicates_removed'] == 0
    assert len(record['links']) == 5 and record['claims_without_resolved_links'] == []
    assert record['links'][0]['location'] != record['links'][1]['location']
    assert record['links'][3]['location']['limitation_index'] == 0
    assert record['links'][4]['location']['limitation_index'] == 1
    for entry in record['links']:
        loc = entry['location']; text = output['answer'] if loc['target'] == 'answer' else output['limitations'][loc['limitation_index']]
        assert text[loc['start_char']:loc['end_char']] == entry['declaration']['anchor']
    assert record['semantic_support'] == 'not_assessed'


def test_old_markdown_copy_error_remains_rejected_and_raw_untouched(monkeypatch):
    payload = raw(answer='상품 부위는 **등심**입니다.', answer_links=[dict(target='answer',
        anchor='상품 부위는 등심입니다.', claim_refs=['q1'], quote_refs=['sq_alpha'])])
    _, run, _ = evaluate(monkeypatch, payload)
    assert run['answer_links']['links'][0]['errors'] == ['anchor_absent_or_non_unique']
    assert run['units'][0]['response']['parsed'] == payload


@pytest.mark.parametrize('fault', ['copied_anchor', 'empty', 'wrong_shape', 'extra_location'])
def test_segments_reject_invalid_shapes_instead_of_repairing_them(fault):
    payload = segments()
    if fault == 'copied_anchor': payload['answer_links'] = []
    elif fault == 'empty': payload['answer'] = []
    elif fault == 'wrong_shape': payload['answer'] = 'string from old contract'
    else: payload['answer'][0]['start_char'] = 0
    before = deepcopy(payload)
    with pytest.raises(ValueError): links.restore(payload, {}, contract=links.SEGMENT_CONTRACT)
    assert payload == before


@pytest.mark.parametrize('fault,error', [
    (dict(claim_refs=['unknown']), 'claim_not_provided_and_globally_cited'),
    (dict(quote_refs=['sq_missing']), 'quote_ref_unresolved'),
    (dict(quote_refs=[]), 'missing_quote_refs'),
    (dict(review_refs=['rv_item_1']), 'review_scope_is_not_source_quote_support'),
    (dict(quote_refs=[], review_refs=['rv_unknown']), 'review_ref_unresolved'),
])
def test_segment_rendering_does_not_relax_evidence_checks(monkeypatch, fault, error):
    payload = segments(); payload['answer'][0].update(fault)
    _, run, _ = evaluate(monkeypatch, payload, links.SEGMENT_CONTRACT, review_context=bounded_review())
    assert error in run['answer_links']['links'][0]['errors']
    assert run['answer_links']['links'][1]['status'] == 'resolved'


def test_changed_text_cannot_keep_a_segment_location():
    output, meta = links.restore(segments(), {}, contract=links.SEGMENT_CONTRACT)
    output['answer'] = output['answer'].replace('**등심**', '다른 값')
    output['_answer_link_metadata'] = meta
    run = dict(query=dict(source_citation_contract=links.SEGMENT_CONTRACT))
    links.record(run, output, [])
    assert 'segment_text_changed' in run['answer_links']['links'][0]['errors']


def test_new_schema_is_only_opt_in_and_literals_survive_id_restoration(monkeypatch):
    output, run, packet = evaluate(monkeypatch, raw())
    assert output == dict(answer='q13 일반 설명. 다른 설명.', choice=None, citations=['claim'], limitations=['확인 불가'])
    entry = run['answer_links']['links'][0]
    assert entry['status'] == 'resolved' and entry['declaration']['anchor'] == 'q13'
    assert entry['location'] == dict(target='answer', start_char=0, end_char=3)
    assert run['answer_links']['claims_without_resolved_links'] == ['claim']
    assert run['answer_links']['semantic_support'] == 'not_assessed'
    assert 'answer_links' in packet['schema']['required']
    assert packet['schema']['properties']['answer_links']['items']['properties']['claim_refs']['items']['const'] == 'q1'
    restored, _ = links.restore(dict(answer='q1', limitations=['b1'], citations=['q1'],
        source_citations=[dict(evidence_ref='b1', quote='b1', quote_id='sq_q1')],
        answer_links=[dict(target='answer', anchor='q1', claim_refs=['q1'], quote_refs=['sq_q1'])]), {'q1':'claim','b1':'block'})
    assert restored['answer'] == 'q1' and restored['limitations'] == ['b1']
    assert restored['source_citations'] == [dict(evidence_ref='block', quote='b1')]
    for contract in [None, 'provided_source_quotes_v1']:
        payload=raw(); payload.pop('answer_links')
        if contract is None: payload.pop('source_citations')
        _, old, packet = evaluate(monkeypatch, payload, contract)
        assert 'answer_links' not in packet['schema']['properties'] and 'answer_links' not in old
        assert links.PROMPT not in packet['messages'][0]['content']


def test_missing_empty_and_bad_metadata_are_separate_from_answer_failure(monkeypatch):
    missing = raw(); missing.pop('answer_links')
    _, run, _ = evaluate(monkeypatch, missing)
    assert run['answer_links']['status'] == 'not_recorded'
    _, run, _ = evaluate(monkeypatch, raw(answer_links=[]))
    assert run['answer_links']['status'] == 'recorded' and run['answer_links']['links'] == []
    assert run['answer_links']['claims_without_resolved_links'] == ['claim']
    for value in [None, {}, 'bad', 1]:
        output, run, _ = evaluate(monkeypatch, raw(answer_links=value))
        assert output and run['answer_links']['status'] == 'unresolved'
    for fault in [dict(answer=''), dict(citations=['unknown']), dict(citations=['q1','q1']),
                  dict(source_citations=[dict(quote_id='sq_a', evidence_ref='b1', quote=42)])]:
        output, run, _ = evaluate(monkeypatch, raw(**fault))
        assert output is None and run['units'][0]['status'] == 'failed'


@pytest.mark.parametrize('payload', [None, [], 'not an object', 12])
def test_valid_json_with_wrong_base_shape_fails_normally(monkeypatch, payload):
    output, run, _ = evaluate(monkeypatch, payload)
    assert output is None and run['units'][0]['status'] == 'failed'


def test_dedup_preserves_every_local_id_but_collision_stays_ambiguous(monkeypatch):
    item = raw()['source_citations'][0]
    many = [item, dict(item, quote_id='sq_beta'), dict(item, quote_id='sq_bad'), dict(item, quote_id='sq_bad')]
    entries = [dict(target='answer', anchor='q13', claim_refs=['q1'], quote_refs=['sq_beta','sq_alpha']),
               dict(target='answer', anchor='다른 설명', claim_refs=[], quote_refs=['sq_bad'])]
    output, run, _ = evaluate(monkeypatch, raw(source_citations=many, answer_links=entries))
    assert output['citations'] == ['claim']
    record = run['answer_source_citations']
    assert len(record['citations']) == 1 and record['duplicates_removed'] == 3
    assert record['citations'][0]['quote_ids'] == ['sq_alpha','sq_beta','sq_bad']
    assert run['answer_links']['quote_lookup']['sq_bad']['error'] == 'duplicate_quote_id'
    assert [v['status'] for v in run['answer_links']['links']] == ['resolved','unresolved']
    assert run['answer_links']['claims_without_resolved_links'] == []


@pytest.mark.parametrize('fault,error', [
    (dict(anchor='없음'), 'anchor_absent_or_non_unique'),
    (dict(anchor='설명'), 'anchor_absent_or_non_unique'),
    (dict(anchor=''), 'invalid_anchor'), (dict(target=[]), 'invalid_anchor'),
    (dict(claim_refs=['unknown']), 'claim_not_provided_and_globally_cited'),
    (dict(claim_refs=[1]), 'invalid_claim_refs'), (dict(quote_refs=[]), 'missing_quote_refs'),
    (dict(quote_refs=['b1']), 'quote_ref_unresolved'), (dict(quote_refs=[{}]), 'invalid_quote_refs'),
    (dict(extra='ignored?'), 'invalid_link_fields'),
])
def test_partial_errors_never_drop_valid_neighbor(monkeypatch, fault, error):
    valid = raw()['answer_links'][0]
    output, run, _ = evaluate(monkeypatch, raw(answer_links=[dict(valid, **fault),valid]))
    assert output and run['answer_links']['status'] == 'unresolved'
    assert error in run['answer_links']['links'][0]['errors']
    assert run['answer_links']['links'][1]['status'] == 'resolved'


def test_overlapping_occurrences_and_limitations_are_not_first_match(monkeypatch):
    for body in [dict(answer='aaa', limitations=[]), dict(answer='body', limitations=['aa','aa'])]:
        link=dict(target='answer' if not body['limitations'] else 'limitations', anchor='aa', claim_refs=[], quote_refs=['sq_alpha'])
        _, run, _ = evaluate(monkeypatch, raw(**body, answer_links=[link]))
        assert run['answer_links']['links'][0]['errors'] == ['anchor_absent_or_non_unique']
    item=dict(target='limitations',anchor='불가',claim_refs=[],quote_refs=['sq_alpha'])
    _, run, _=evaluate(monkeypatch,raw(answer_links=[item]))
    assert run['answer_links']['links'][0]['location'] == dict(target='limitations',limitation_index=0,start_char=3,end_char=5)


def test_source_address_and_bad_local_id_only_affect_referencing_links(monkeypatch):
    item=raw()['source_citations'][0]
    for quote in [dict(item,evidence_ref='missing'),dict(item,quote_id=1),dict(item,quote_id=None)]:
        output,run,_=evaluate(monkeypatch,raw(source_citations=[quote]))
        assert output and run['answer_links']['links'][0]['status']=='unresolved'
    undeclared=raw(citations=[], answer_links=[dict(raw()['answer_links'][0],claim_refs=['q1'])])
    output,run,_=evaluate(monkeypatch,undeclared)
    assert output and run['answer_links']['links'][0]['status']=='unresolved'


def test_quote_reuse_overlapping_anchors_duplicates_and_semantic_boundary(monkeypatch):
    # A structurally legal unrelated claim still needs independent human meaning review.
    first=dict(target='answer',anchor='q13 일반 설명',claim_refs=['q1'],quote_refs=['sq_alpha'])
    second=dict(first,anchor='일반 설명',claim_refs=[])
    _,run,_=evaluate(monkeypatch,raw(answer_links=[first,second,first]))
    assert run['answer_links']['status']=='recorded' and len(run['answer_links']['links'])==2
    assert run['answer_links']['duplicates_removed']==1 and run['answer_links']['semantic_support']=='not_assessed'
    links.withhold(run)
    public=run['answer_links']
    assert public['status']=='needs_review' and not any(public[k] for k in ['links','quote_lookup','quote_declarations','claims_without_resolved_links'])
    assert run['units'][0]['response']['parsed']['answer_links'][0]['anchor']=='q13 일반 설명'


@pytest.mark.parametrize('contract',[links.CONTRACT,'provided_source_quotes_v1'])
def test_only_snapshot_synthesis_accepts_explicit_contract(contract):
    BusinessQuery(question='q',snapshot_id='s',source_citation_contract=contract)
    for args in [dict(source_run_id='r'),dict(snapshot_id='s',answer_mode='items')]:
        with pytest.raises(ValueError): BusinessQuery(question='q',source_citation_contract=contract,**args)


def test_many_claims_and_quotes_are_sets_not_cartesian_semantic_pairs():
    output=dict(answer='같은 구절', citations=['second','first','unlinked'], limitations=[],
        _answer_link_metadata=dict(recorded=True,quote_ids=['sq_a','sq_b'],quote_lookup={
            'sq_a':dict(status='resolved',citation_index=0),'sq_b':dict(status='resolved',citation_index=1)},
            links=[dict(target='answer',anchor='같은 구절',claim_refs=['first','second'],quote_refs=['sq_b','sq_a'])]))
    run=dict(query=dict(source_citation_contract=links.CONTRACT))
    links.record(run,output,['first','second','unlinked'])
    record=run['answer_links']
    assert record['status']=='recorded' and record['semantic_support']=='not_assessed'
    assert record['claims_without_resolved_links']==['unlinked'] and len(record['links'])==1
    assert output['citations']==['second','first','unlinked']
    assert set(record['links'][0])=={'declaration','status','errors','location'}


@pytest.mark.parametrize('contract,blocked',[(None,False),('provided_source_quotes_v1',False),(links.CONTRACT,False),(links.CONTRACT,True)])
def test_api_query_json_call_save_get_and_workbench_gate(tmp_path,monkeypatch,contract,blocked):
    import json
    from uuid import uuid4
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core.config import settings
    from app.api.routers import knowledge
    from app.knowledge import graph_retrieval
    from app.knowledge.service import KnowledgeService
    from app.generation.model_client import ModelClient
    from app.generation import model_input_budget
    service=KnowledgeService(tmp_path/'knowledge.db')
    block=source()
    claim=dict(id='claim',chunk_id='b',role='event_entity',raw=dict(Event='합성 계약 검사용',Entity=[]),source_version_ids=['v'],
        evidence=business_run.exact_evidence([dict(block_id='b',quote=QUOTE)],[block]))
    origin=dict(id='origin',kind='business',status='succeeded',units=[],requirements=[],claims=[claim],blocks=[block],
        recipe=dict(options={}),model_identity={})
    snapshot=dict(id='s',kind='source_graph',run_id='origin',source_versions={'v':{}},blocks=[block],claims=[claim],concepts=[],requirements=[],assessments={})
    with service.repository.connect() as db:
        db.execute('INSERT INTO sources VALUES(?,?,?,?)',('source','test','source',json.dumps(dict(id='source',title='합성 계약 자료'))))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)',('v','source','hash',json.dumps(dict(id='v',source_id='source'))))
        for table,value in [('runs',origin),('snapshots',snapshot)]:
            db.execute(f'INSERT INTO {table} VALUES(?,?)',(value['id'],json.dumps(value)))
    blocked_now=[]
    def forbidden(*a,**k):pytest.fail('No model, native count, retrieval, embedding or background execution allowed')
    monkeypatch.setattr(ModelClient,'generate',forbidden)
    monkeypatch.setattr(model_input_budget,'count',forbidden)
    monkeypatch.setattr(service.executor,'submit',forbidden)
    monkeypatch.setattr(graph_retrieval,'embed',forbidden)
    monkeypatch.setattr(use,'restricted_sources',lambda *a:blocked_now)
    def retrieve(_s,run,*a,**k):
        run['graph_retrieval']=dict(contract='synthetic_fixed_hit_no_search')
        return [dict(block_id='claim',file_id='v',score=None)]
    monkeypatch.setattr(graph_retrieval,'retrieve',retrieve)
    def call(_s,run,stage,messages,schema,**kwargs):
        payload=dict(answer='명시한 합성 구절',choice=None,citations=['q1'],limitations=[])
        if contract:payload['source_citations']=[dict(evidence_ref='b1',quote=QUOTE)]
        if contract==links.CONTRACT:
            payload['source_citations'][0]['quote_id']='sq_fixture'
            payload['answer_links']=[dict(target='answer',anchor=payload['answer'],claim_refs=[],quote_refs=['sq_fixture'])]
        run['units'].append(dict(id=uuid4().hex,stage=stage,status='succeeded',error=None,messages=messages,schema=schema,
            reference_map=kwargs['reference_map'],response=dict(parsed=deepcopy(payload))))
        if blocked:blocked_now.append(dict(source_version_id='v',state='restricted'))
        return run['units'][-1]['response']
    monkeypatch.setattr(business_run,'call',call)
    monkeypatch.setattr(settings,'KNOWLEDGE_ENABLED',True)
    app=FastAPI();app.include_router(knowledge.router,prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    try:
        with TestClient(app) as client:
            response=client.post('/api/v1/knowledge/business/search',json=dict(snapshot_id='s',question='합성 계약 확인',
                candidate_contract=None,evidence_union=None,source_citation_contract=contract))
            assert response.status_code==200,response.text
            reply=response.json()['data'];rid=reply['run_id']
            stored=client.get('/api/v1/knowledge/runs/'+rid).json()['data']
            detail_reply=client.get('/api/v1/knowledge/workbench/answers',params=dict(kind='source_graph',scope_id='s',answer_id=rid))
            assert detail_reply.status_code==200,detail_reply.text
            detail=detail_reply.json()['data']['detail']
            assert stored['metrics']['llm_calls']==0
            if blocked:
                assert reply['answer'] is None and detail['answer']=={}
                assert reply['status']=='needs_review' and detail['source_citations']['citations']==[]
                for record in [reply['answer_links'],stored['answer_links'],detail['answer_links']]:
                    assert record['status']=='needs_review' and not any(record[k] for k in ['links','quote_lookup','quote_declarations','claims_without_resolved_links'])
                assert stored['units'][0]['response']['parsed']['answer_links'][0]['anchor']=='명시한 합성 구절'
            else:
                assert reply['answer']==stored['answer']==detail['answer']
                assert reply['answer']['citations']==['claim']
                if contract==links.CONTRACT:
                    assert reply['answer_links']==stored['answer_links']==detail['answer_links']
                    assert detail['answer_links']['links'][0]['status']=='resolved'
                else:assert 'answer_links' not in reply and 'answer_links' not in stored and 'answer_links' not in detail
            with service.repository.connect() as db:
                assert service.repository.get(db,'runs','origin')==origin
                assert service.repository.get(db,'snapshots','s')==snapshot
    finally:service.shutdown()
