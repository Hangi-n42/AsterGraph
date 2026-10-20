"""Synthetic contract tests; no model calls or recipe-quality claims."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.knowledge import business_run, business_use, source_list_service as operation
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService
from app.knowledge.source_list_comparison import parse_field


@pytest.fixture
def case(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    blocks, fields, context, sources, parse_units = [], [], [], [], []
    for version, text in [('v1', '재료: 공통 1g, 소금 2g\n'), ('v2', '재료: 공통 2g, 다른 3g\n')]:
        bid = 'b' + version
        block = dict(id=bid, source_version_id=version, parse_run_id='parse', text=text, locator={}, order=0)
        blocks.append(block)
        ref = dict(source_version_id=version, parse_run_id='parse', block_id=bid,
                   start_char=4, end_char=len(text.rstrip()), quote=text[4:].rstrip())
        fields.append(dict(ref, field_label='재료'))
        context.append(dict(id=bid, text=text, source_reference=dict(ref, start_char=0, end_char=len(text))))
        items = []
        for item in parse_field(ref, [block])['items']:
            row = dict(id='i' + str(sum(len(s['items']) for s in sources) + len(items) + 1), source_ref=bid)
            for role in ('entry', 'name', 'quantity'):
                row[role + '_span'] = [item[role]['start_char'], item[role]['end_char']]
                if role != 'entry': row[role] = item[role]['quote']
            items.append(row)
        sources.append(dict(source_version_id=version, items=items))
        parse_units.append(dict(id=version + ':text', source_version_id=version, status='succeeded', spec=None))
    method = '1. 재료가 싱거우면 공통이나 소금으로 간을 한다.\n'
    blocks.append(dict(id='method', source_version_id='v1', parse_run_id='parse', text=method, locator={}, order=1))
    context.append(dict(id='method', text=method, source_reference=dict(source_version_id='v1', parse_run_id='parse',
        block_id='method', start_char=0, end_char=len(method))))
    q = dict(kind='use_condition', evidence_ref='method', quote='재료가 싱거우면', condition_quote='재료가 싱거우면',
             action_quote='공통이나 소금으로 간을 한다', connector_quote='이나', related_item_refs=['i2'])
    rows = [dict(item_ref='i1', status='explicit_qualification', qualifications=[q]),
            dict(item_ref='i2', status='explicit_qualification', qualifications=[dict(q, related_item_refs=['i1'])]),
            *[dict(item_ref=i, status='not_stated', qualifications=[]) for i in ('i3', 'i4')]]
    unit = dict(id='unit', stage='source_list_conditions', status='succeeded', reference_map={},
        messages=[dict(role='user', content=json.dumps(dict(sources=sources, context=context), ensure_ascii=False))],
        response=dict(text=json.dumps(dict(items=rows), ensure_ascii=False), parsed=dict(items=rows), failure_kind=None))
    prior = dict(id='conditions', kind='business_query', status='partial', snapshot_id='snap', units=[unit],
                 condition_validation=dict(record_integrity='invalid'))
    snapshot = dict(id='snap', kind='source_graph', run_id='origin', source_versions={'v1': {}, 'v2': {}},
                    blocks=blocks, claims=[dict(id='c')], requirements=[], assessments={}, concepts=[])
    with service.repository.connect() as db:
        for version in ('v1', 'v2'):
            source = dict(id='s'+version, title='source '+version)
            db.execute('INSERT INTO sources VALUES(?,?,?,?)', (source['id'], 'test', version, json.dumps(source)))
            value = dict(id=version, source_id=source['id'], latest_parse_run_id='parse')
            db.execute('INSERT INTO versions VALUES(?,?,?,?)', (version, source['id'], version, json.dumps(value)))
        for run in [dict(id='parse', kind='parse', input_version_ids=['v1','v2'], units=parse_units, status='succeeded'),
                    dict(id='origin', kind='business', status='succeeded', units=[], recipe={}, model_identity={}), prior]:
            db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], json.dumps(run)))
        for b in blocks:
            db.execute('INSERT INTO blocks VALUES(?,?,?,?,?,?)',
                       (b['id'], b['source_version_id'], 'parse', b['source_version_id']+':text', b['order'], json.dumps(b)))
        db.execute('INSERT INTO snapshots VALUES(?,?)', ('snap', json.dumps(snapshot)))
    def forbidden(*a, **kw): pytest.fail('Explicit operation must not execute generation or retrieval')
    from app.generation.model_client import ModelClient
    from app.knowledge import graph_retrieval
    from app.knowledge.source_index import FrozenIndex
    for owner, attr in [(business_run,'call'), (business_run,'json_call'), (ModelClient,'generate'),
                        (ModelClient,'identities'), (graph_retrieval,'retrieve'), (graph_retrieval,'embed'),
                        (FrozenIndex,'__init__')]:
        monkeypatch.setattr(owner, attr, forbidden)
    payload = dict(question='표시 제목', snapshot_id='snap', answer_mode='source_list_comparison', retrieval='explicit_sources',
        list_comparison=dict(contract='quantity-line-fields-v1', fields=fields,
                             condition_run_id='conditions', condition_unit_id='unit'))
    yield service, snapshot, payload, prior
    service.executor.shutdown(wait=False)


def assemble(case):
    service, snapshot, payload, _ = case
    with service.repository.connect() as db:
        return operation.assemble(service, db, BusinessQuery.model_validate(payload), snapshot)


def rewrite_prior(case, edit):
    service, _, _, _ = case
    with service.repository.connect() as db:
        value = service.repository.get(db, 'runs', 'conditions')
        edit(value['units'][0])
        service.repository.save(db, 'runs', value)


def edit_output(case, edit):
    def change(unit):
        edit(unit['response']['parsed']['items'][0]['qualifications'][0])
        unit['response']['text'] = json.dumps(unit['response']['parsed'], ensure_ascii=False)
    rewrite_prior(case, change)


def test_public_api_stores_and_reads_exact_map_preserving_invalid_and_question_independence(case, monkeypatch):
    from app.api.routers import knowledge as api
    from app.knowledge import autoschema
    service, _, payload, prior = case
    monkeypatch.setattr(api.settings, 'KNOWLEDGE_ENABLED', True)
    monkeypatch.setattr(autoschema, 'graph', lambda *a: dict(nodes=[], edges=[]))
    app = FastAPI(); app.include_router(api.router, prefix='/api/v1')
    app.dependency_overrides[api.get_knowledge_service] = lambda: service
    client = TestClient(app)
    response = client.post('/api/v1/knowledge/business/search', json=payload)
    assert response.status_code == 200, response.text
    data = response.json()['data']; rid = data['run_id']
    assert data['status'] == 'partial' and not data['qa_model_called']
    assert [r['name'] for r in data['list_comparison']['comparison']['common']] == ['공통']
    assert data['condition_consumer']['original_validation']['record_integrity'] == 'invalid'
    saved = client.get('/api/v1/knowledge/runs/' + rid).json()['data']
    assert saved['units'] == [] and saved['metrics']['llm_calls'] == 0
    assert saved['source_reference_map'] == data['source_reference_map']
    detail = client.get('/api/v1/knowledge/workbench/answers', params=dict(kind='source_graph', scope_id='snap', answer_id=rid)).json()['data']['detail']
    assert detail['answer'] == saved['answer']
    refs = {r['id']: {k:e for k,e in r['evidence'][0].items() if k in operation.ADDRESS} for r in detail['evidence']}
    assert refs == saved['source_reference_map']
    assert service.run('conditions')['condition_validation'] == prior['condition_validation']
    payload['question'] = '전혀 다른 제목과 임의의 상품명'
    second = client.post('/api/v1/knowledge/business/search', json=payload).json()['data']
    assert second['answer'] == data['answer'] and second['source_reference_map'] == data['source_reference_map']


@pytest.mark.parametrize('fault', ['partial', 'span', 'parse', 'unregistered', 'cross_version'])
def test_wrong_or_partial_field_rejected_without_active_run_leak(case, fault):
    service, _, payload, _ = case
    ref = payload['list_comparison']['fields'][0]
    if fault == 'partial': ref.update(end_char=9, quote='공통 1g')
    elif fault == 'span': ref['start_char'] += 1
    elif fault == 'parse': ref['parse_run_id'] = 'missing'
    elif fault == 'unregistered': ref['block_id'] = 'unknown'
    else: ref['source_version_id'] = 'v2'
    with pytest.raises((ValueError, KeyError)):
        business_use.query(service, BusinessQuery.model_validate(payload))
    with service.repository.connect() as db:
        assert not service.repository.has_active_runs(db)
        failed = [json.loads(r[0]) for r in db.execute("SELECT payload FROM runs WHERE id NOT IN ('parse','origin','conditions')")]
        assert len(failed) == 1 and failed[0]['status'] == 'failed' and failed[0]['answer'] is None


@pytest.mark.parametrize('fault', ['different_sentence', 'other_subject', 'negative', 'duplicate', 'wrong_subject', 'nonadjacent', 'cross_source'])
def test_condition_fragments_do_not_pass_only_because_they_share_a_parent(case, fault):
    service, snapshot, _, _ = case
    if fault == 'wrong_subject': edit_output(case, lambda q: q.update(action_quote='소금으로 간을 한다'))
    elif fault == 'cross_source': edit_output(case, lambda q: q.update(related_item_refs=['i3']))
    else:
        block = next(b for b in snapshot['blocks'] if b['id'] == 'method')
        if fault == 'different_sentence': text = block['text'].replace('면 ', '면. ')
        elif fault == 'other_subject': text = block['text'].replace('공통이나', '설탕은 공통이나')
        elif fault == 'negative': text = block['text'].replace('한다.', '한다는 뜻이 아니다.')
        elif fault == 'duplicate': text = block['text'] + block['text']
        else: text = block['text'].replace('면 ', '면 먼저 볶고 ')
        block['text'] = text
        with service.repository.connect() as db:
            db.execute('UPDATE blocks SET payload=? WHERE id=?', (json.dumps(block), 'method'))
        def change(unit):
            value = json.loads(unit['messages'][0]['content'])
            value['context'][-1]['text'] = text
            value['context'][-1]['source_reference']['end_char'] = len(text)
            unit['messages'][0]['content'] = json.dumps(value)
        rewrite_prior(case, change)
    result = assemble(case)
    assert result['condition_consumer']['records'][0]['status'] == 'unresolved'
    assert result['condition_consumer']['records'][0]['errors']
    assert result['list_comparison']['comparison']['status'] == 'ready'


def test_missing_offsets_only_bind_unique_occurrence(case):
    service, snapshot, _, _ = case
    with service.repository.connect() as db:
        sources = operation.Sources(service, db, snapshot)
        ref = dict(source_version_id='v1', parse_run_id='parse', block_id='bv1', quote='공통')
        assert sources.exact(ref)['start_char'] == 4
        with pytest.raises(ValueError): sources.exact(dict(ref, quote=' '))
        with pytest.raises(ValueError): sources.exact(dict(ref, start_char=4))


@pytest.mark.parametrize('at_save', [False, True])
def test_source_restrictions_block_at_entry_and_save(case, monkeypatch, at_save):
    service, _, payload, _ = case
    calls = []
    def restrictions(*a):
        calls.append(1)
        return [dict(source_version_id='v1', state='blocked')] if len(calls) > int(at_save) else []
    monkeypatch.setattr(business_use, 'restricted_sources', restrictions)
    result = business_use.query(service, BusinessQuery.model_validate(payload))
    assert result['status'] == 'needs_review' and result['answer'] is None
    with service.repository.connect() as db: assert not service.repository.has_active_runs(db)


@pytest.mark.parametrize('mutation', ['revision', 'cancel', 'invalidation'])
def test_save_rechecks_revision_cancel_and_invalidation(case, monkeypatch, mutation):
    service, snapshot, payload, _ = case
    snapshot['requirements'] = [dict(id='r', revision=1, status='ready')]
    with service.repository.connect() as db:
        db.execute('UPDATE snapshots SET payload=? WHERE id=?', (json.dumps(snapshot), 'snap'))
        db.execute('INSERT INTO requirements VALUES(?,?)', ('r', json.dumps(snapshot['requirements'][0])))
    original = operation.assemble
    def change(*args):
        result = original(*args)
        with service.repository.connect() as db:
            if mutation == 'revision':
                service.repository.save(db, 'requirements', dict(id='r', revision=2, status='ready'))
            elif mutation == 'cancel':
                row = db.execute("SELECT id FROM runs WHERE json_extract(payload,'$.status')='running'").fetchone()
                run = service.repository.get(db, 'runs', row['id']); run['status'] = 'cancel_requested'
                service.repository.save(db, 'runs', run)
            else:
                event = dict(event='business_correction', snapshot_id='snap', claim_ids=[], block_ids=['method'], requirement_ids=[])
                db.execute('INSERT INTO snapshot_events VALUES(?,?)', ('event', json.dumps(event)))
        return result
    monkeypatch.setattr(operation, 'assemble', change)
    result = business_use.query(service, BusinessQuery.model_validate(payload))
    assert result['status'] == ('cancelled' if mutation == 'cancel' else 'needs_review') and result['answer'] is None
    with service.repository.connect() as db: assert not service.repository.has_active_runs(db)


def test_mode_cannot_silently_select_or_reuse_other_contracts(case):
    _, _, payload, _ = case
    for edits in [dict(retrieval='hipporag2'), dict(answer_mode='synthesis'), dict(requirement_ids=['r']), dict(choices=['a'])]:
        with pytest.raises(ValidationError): BusinessQuery.model_validate(dict(payload, **edits))


def add_product(case):
    service, snapshot, payload, _ = case
    texts = [('name','제품명: 시험제품\n'), ('type','식품 유형: 공통\n'),
             ('role','영업소 정보 1 / 영업소 구분: 제조원\n'), ('company','영업소 정보 1 / 업체명: 시험업체\n'),
             ('storage','보관방법 / 보관·취급방법: 냉장 보관하고 개봉 후 밀봉한다.\n')]
    new = [dict(id=bid, source_version_id='vp', parse_run_id='parse', text=text, order=i, locator={})
           for i,(bid,text) in enumerate(texts)]
    def ref(bid, quote):
        block = next(b for b in new if b['id']==bid); start=block['text'].index(quote)
        return dict(source_version_id='vp', parse_run_id='parse', block_id=bid,
                    start_char=start, end_char=start+len(quote), quote=quote)
    claims = [dict(id='type_claim', source_version_ids=['vp'], raw=dict(Head='시험제품', Relation='식품 유형은', Tail='공통'),
                   evidence=[ref('type','식품 유형: 공통')]),
              dict(id='maker_claim', source_version_ids=['vp'], raw=dict(Head='시험업체', Relation='제조원이다', Tail='시험제품'),
                   evidence=[ref('role','영업소 구분: 제조원'), ref('company','업체명: 시험업체')]),
              dict(id='storage_claim', source_version_ids=['vp'], raw=dict(Entity=['시험제품'], Event='저장 해석'),
                   evidence=[ref('storage','냉장 보관하고 개봉 후 밀봉한다.')])]
    snapshot['source_versions']['vp']={};snapshot['blocks'].extend(new);snapshot['claims'].extend(claims)
    payload['list_comparison']['products']=[dict(type_claim_id='type_claim', manufacturer_claim_id='maker_claim', storage_claim_id='storage_claim')]
    with service.repository.connect() as db:
        db.execute('INSERT INTO sources VALUES(?,?,?,?)', ('sp','test','vp',json.dumps(dict(id='sp',title='시험제품'))))
        db.execute('INSERT INTO versions VALUES(?,?,?,?)', ('vp','sp','vp',json.dumps(dict(id='vp',source_id='sp',latest_parse_run_id='parse'))))
        run=service.repository.get(db,'runs','parse');run['input_version_ids'].append('vp')
        run['units'].append(dict(id='vp:text',source_version_id='vp',status='succeeded',spec=None));service.repository.save(db,'runs',run)
        for b in new: db.execute('INSERT INTO blocks VALUES(?,?,?,?,?,?)',(b['id'],'vp','parse','vp:text',b['order'],json.dumps(b)))
    return claims


def test_product_uses_registered_name_type_role_and_complete_storage_field(case):
    add_product(case)
    result=assemble(case);product=result['product_facts'][0]
    assert product['name']=='시험제품' and product['manufacturer']=='시험업체'
    assert product['storage']=='냉장 보관하고 개봉 후 밀봉한다.'
    section=next(s for s in result['answer']['sections'] if s['kind']=='product')
    assert section['claim_ids']==product['claim_ids'] and '개봉 후 밀봉한다' in section['text']
    assert set(result['answer']['citations'])=={c for s in result['answer']['sections'] for c in s['citations']}
    assert set(result['answer']['citations']) < set(result['source_reference_map'])


@pytest.mark.parametrize('fault',['cross_version','wrong_type','wrong_product','partial_storage','wrong_role','different_group','offsetless_ambiguous'])
def test_product_facts_reject_wrong_subject_role_source_and_ambiguous_or_partial_refs(case,fault):
    claims=add_product(case);service,snapshot,_,_=case
    if fault=='cross_version': claims[1]['source_version_ids']=['v1']
    elif fault=='wrong_type': claims[0]['raw']['Tail']='다른유형'
    elif fault=='wrong_product': claims[1]['raw']['Tail']='다른제품'
    elif fault=='partial_storage':
        ref=claims[2]['evidence'][0];ref['quote']='냉장 보관';ref['end_char']=ref['start_char']+len(ref['quote'])
    else:
        bid='role' if fault=='wrong_role' else 'company'
        block=next(b for b in snapshot['blocks'] if b['id']==bid)
        if fault=='wrong_role': block['text']=block['text'].replace('제조원','수입원')
        elif fault=='different_group': block['text']=block['text'].replace('정보 1','정보 2')
        else:
            ref=claims[1]['evidence'][1];ref.pop('start_char');ref.pop('end_char')
            block['text']+=block['text']
        with service.repository.connect() as db:
            db.execute('UPDATE blocks SET payload=? WHERE id=?',(json.dumps(block),bid))
    with pytest.raises(ValueError): assemble(case)


def test_saved_native_or_provided_item_mismatch_is_not_consumed(case):
    rewrite_prior(case, lambda unit: unit['response'].update(text='{}'))
    with pytest.raises(ValueError): assemble(case)


def test_related_does_not_require_subject_self_inclusion(case):
    before=assemble(case)['condition_consumer']['records'][0]
    assert before['status']=='source_linked_stored_model_record'
    assert before['qualifications'][0]['subject_item_ref']=='i1'
    assert before['qualifications'][0]['related_item_refs']==['i2']
    edit_output(case, lambda q: q.update(related_item_refs=['i1','i2']))
    assert assemble(case)['condition_consumer']['records'][0]['status']=='source_linked_stored_model_record'
