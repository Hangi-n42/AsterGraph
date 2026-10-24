"""Stored-consumer boundaries only; no new model or general semantic evaluation."""
from copy import deepcopy
from hashlib import sha256
import json
import re

import pytest
from pydantic import ValidationError

from app.knowledge import source_list_service as service_op, source_timing_consumer as timing
from app.knowledge.business_models import BusinessQuery
from app.tests.unit.test_knowledge_source_list_service import case, add_product


@pytest.fixture
def bound(case, monkeypatch):
    service,snapshot,payload,_=case
    add_product(case)
    text='1. 먼저 준비한다. 2. 1이 준비되면 공통과 소금을 사용한다. 3. 재료가 싱거우면 공통이나 소금으로 간을 한다.\n'
    block=next(b for b in snapshot['blocks'] if b['id']=='method');block['text']=text
    identity=dict(review=dict(name='fixture',digest='fixture'))
    recipe=dict(generation=dict(provider='fixture'),models=dict(review='fixture'),
                options=dict(review_tokens=8192,context_tokens=49152,think=False,timeout=1800))
    with service.repository.connect() as db:
        a=service.repository.get(db,'runs','conditions');a.update(query=dict(snapshot_id='snap'),model_identity=identity,recipe=recipe)
        original=json.loads(a['units'][0]['messages'][0]['content'])
        for row in original['context']:
            row['kind']='method' if row['id']=='method' else 'ingredient_list'
        original['context'][-1]['text']=text;original['context'][-1]['source_reference']['end_char']=len(text)
        a['units'][0]['messages'][0]['content']=json.dumps(original)
        service.repository.save(db,'runs',a)
        db.execute('UPDATE blocks SET payload=? WHERE id=?',(json.dumps(block),'method'))
        db.execute('UPDATE snapshots SET payload=? WHERE id=?',(json.dumps(snapshot),'snap'))
        ctx=deepcopy(original);ctx.update(method_prefixes=[],method_steps=[])
        starts=[m.start() for m in re.finditer(r'(?<!\S)[1-9]\d*\.\s',text)]
        for n,(start,end) in enumerate(zip(starts,[*starts[1:],len(text)]),1):
            ref=dict(source_version_id='v1',parse_run_id='parse',block_id='method',start_char=start,end_char=end,quote=text[start:end])
            ctx['method_steps'].append(dict(id='step'+str(n),method_ref='method',ordinal=n,text=ref['quote'],source_reference=ref))
        g=dict(kind='action_timing',quote='1이 준비되면 공통과 소금을 사용한다.',condition_quote='1이 준비되면',action_quote='사용한다.',
               connector_quote='',targets=[dict(item_ref='i1',quote='공통'),dict(item_ref='i2',quote='소금')],related_item_refs=[],reference_quotes=['1'],unresolved_reason='')
        output={s['id']:dict(groups=[deepcopy(g)] if s['ordinal']==2 else [],unresolved_reason='미검토') for s in ctx['method_steps']}
        instruction='supported fixture contract'
        monkeypatch.setattr(timing,'INSTRUCTION_SHA256',sha256(instruction.encode()).hexdigest())
        raw=json.dumps(output,ensure_ascii=False)
        unit=dict(id='timing_unit',stage='source_step_conditions',status='succeeded',reference_map={},
          requested_limits=dict(max_tokens=8192,context_tokens=49152,think=False),executed_limits=dict(max_tokens=8192,context_tokens=49152,think=False),
          request_configuration=dict(model='fixture',generation=recipe['generation'],identity=identity,timeout=1800),
          schema=dict(properties={s['id']:{} for s in ctx['method_steps']},required=[s['id'] for s in ctx['method_steps']]),
          messages=[dict(role='system',content=instruction),dict(role='user',content=json.dumps(ctx))],
          response=dict(text=raw,parsed=output,raw_response=dict(message=dict(content=raw)),failure_kind=None,
                        provider='fixture',model='fixture',stage='source_step_conditions',done=True,done_reason='stop'))
        run=dict(id='timing',kind='business_query',status='succeeded',snapshot_id='snap',query=dict(snapshot_id='snap'),
                 units=[unit],recipe=recipe,model_identity=identity,comparison_role=timing.PRODUCER,condition_validation=dict(record_integrity='valid'))
        db.execute('INSERT INTO runs VALUES(?,?)',('timing',json.dumps(run)))
    payload['list_comparison'].update(timing_run_id='timing',timing_unit_id='timing_unit')
    return case


def assemble(bound):
    service,snapshot,payload,_=bound
    with service.repository.connect() as db:
        return service_op.assemble(service,db,BusinessQuery.model_validate(payload),snapshot)


def mutate(bound,edit):
    service,_,_,_=bound
    with service.repository.connect() as db:
        run=service.repository.get(db,'runs','timing');edit(run);service.repository.save(db,'runs',run)


def output_edit(bound,edit):
    def change(run):
        response=run['units'][0]['response'];edit(response['parsed']);raw=json.dumps(response['parsed'],ensure_ascii=False)
        response.update(text=raw,raw_response=dict(message=dict(content=raw)))
    mutate(bound,change)


def context_edit(bound,edit):
    def change(run):
        unit=run['units'][0];ctx=json.loads(unit['messages'][1]['content']);edit(ctx);unit['messages'][1]['content']=json.dumps(ctx)
    mutate(bound,change)


def test_optional_timing_preserves_A_OR_and_all_existing_sections_and_citations(bound):
    _,_,payload,_=bound
    spec=payload['list_comparison'];spec.pop('timing_run_id');spec.pop('timing_unit_id');before=assemble(bound)
    assert 'timing_consumer' not in before
    spec.update(timing_run_id='timing',timing_unit_id='timing_unit');after=assemble(bound)
    assert after['condition_consumer']==before['condition_consumer']
    assert after['list_comparison']==before['list_comparison'] and after['product_facts']==before['product_facts']
    assert [s for s in after['answer']['sections'] if s['kind']!='stored_timing']==before['answer']['sections']
    assert all(after['source_reference_map'][k]==v for k,v in before['source_reference_map'].items())
    row=next(r for r in after['timing_consumer']['records'] if r['status']=='source_linked_stored_timing_record')
    assert row['evidence']['reference']['quote']=='1' and row['evidence']['reference_context']['quote']=='1이'
    assert row['evidence']['prior_number_context']['quote'].startswith('1. 먼저')
    section=next(s for s in after['answer']['sections'] if s['kind']=='stored_timing')
    assert section['original_run_id']=='timing' and section['original_unit_id']=='timing_unit' and '1이 준비되면' in section['text']
    assert section['semantic_status']=='unverified' and not row['human_approval']


@pytest.mark.parametrize('fault',['wrong_snapshot','wrong_kind','wrong_stage','contract','limits','empty_raw','mismatched_parsed','mismatched_wire',
    'duplicate_alias','duplicate_source_ref','changed_item_value','changed_item_span','changed_source','missing_step','overlapping_steps','wrong_parse','empty_output'])
def test_invalid_timing_is_local_and_keeps_A_answer(bound,fault):
    if fault=='wrong_snapshot':mutate(bound,lambda r:r.update(snapshot_id='stale'))
    elif fault=='wrong_kind':mutate(bound,lambda r:r.update(kind='business'))
    elif fault=='wrong_stage':mutate(bound,lambda r:r['units'][0].update(stage='other'))
    elif fault=='contract':mutate(bound,lambda r:r['units'][0]['messages'][0].update(content='changed instruction'))
    elif fault=='limits':mutate(bound,lambda r:r['units'][0]['executed_limits'].update(max_tokens=100))
    elif fault=='empty_raw':mutate(bound,lambda r:r['units'][0]['response'].update(text=''))
    elif fault=='mismatched_parsed':mutate(bound,lambda r:r['units'][0]['response'].update(parsed={}))
    elif fault=='mismatched_wire':mutate(bound,lambda r:r['units'][0]['response']['raw_response']['message'].update(content='{}'))
    elif fault=='duplicate_alias':mutate(bound,lambda r:r['units'][0].update(reference_map=dict(a='x',b='x')))
    elif fault=='duplicate_source_ref':context_edit(bound,lambda c:c['context'].append(deepcopy(c['context'][0])))
    elif fault=='changed_item_value':context_edit(bound,lambda c:c['sources'][0]['items'][0].update(name='changed'))
    elif fault=='changed_item_span':context_edit(bound,lambda c:c['sources'][0]['items'][0].update(name_span=[0,1]))
    elif fault=='changed_source':context_edit(bound,lambda c:c['sources'][0].update(source_version_id='v2'))
    elif fault=='missing_step':context_edit(bound,lambda c:c['method_steps'].pop(1))
    elif fault=='overlapping_steps':context_edit(bound,lambda c:c['method_steps'][1]['source_reference'].update(start_char=0))
    elif fault=='wrong_parse':context_edit(bound,lambda c:c['method_steps'][1]['source_reference'].update(parse_run_id='missing'))
    else:output_edit(bound,lambda x:x.clear())
    result=assemble(bound)
    assert not any(s['kind']=='stored_timing' for s in result['answer']['sections'])
    assert any(s['kind']=='stored_condition' for s in result['answer']['sections'])
    assert result['condition_consumer']['original_validation']['record_integrity']=='invalid'
    assert result['product_facts'][0]['storage']=='냉장 보관하고 개봉 후 밀봉한다.'
    assert result['timing_consumer']['status']=='unresolved' and result['timing_consumer']['errors']


@pytest.mark.parametrize('fault',['duplicate_target','mixed_source','wrong_literal_name','missing_span_text','duplicate_group','unsupported_kind',
                                 'compound_action','negative','reversed_action','all_step_scope'])
def test_ambiguous_or_unsupported_group_cannot_replace_normal_A(bound,fault):
    def edit(x):
        g=x['step2']['groups'][0]
        if fault=='duplicate_target':g['targets'].append(deepcopy(g['targets'][0]))
        elif fault=='mixed_source':g['targets'][0]['item_ref']='i3'
        elif fault=='wrong_literal_name':g['targets'][0]['quote']='공'
        elif fault=='missing_span_text':g['condition_quote']='없는 문구'
        elif fault=='duplicate_group':x['step2']['groups'].append(deepcopy(g))
        elif fault=='unsupported_kind':g['kind']='unqualified_action'
        elif fault=='compound_action':g['action_quote']='소금을 사용한다.'
        elif fault=='negative':g['condition_quote']='1이 준비되지 않으면'
        elif fault=='reversed_action':g.update(condition_quote='소금을 사용한다.',action_quote='1이 준비되면')
        else:g.update(quote='먼저 준비한다. 2. 1이 준비되면 공통과 소금을 사용한다.')
    output_edit(bound,edit);result=assemble(bound)
    assert not any(s['kind']=='stored_timing' for s in result['answer']['sections'])
    assert any(s['kind']=='stored_condition' for s in result['answer']['sections'])
    assert result['timing_consumer']['status']=='unresolved'


def test_bad_extra_timing_group_does_not_discard_a_valid_group(bound):
    output_edit(bound,lambda x:x['step2']['groups'].append(dict(x['step2']['groups'][0],quote='없는 시점')))
    result=assemble(bound);rows=result['timing_consumer']['records']
    assert len(rows)==2 and {r['status'] for r in rows}=={'unresolved','source_linked_stored_timing_record'}


def test_pair_is_required(bound):
    _,_,p,_=bound;del p['list_comparison']['timing_unit_id']
    with pytest.raises(ValidationError):BusinessQuery.model_validate(p)


@pytest.mark.parametrize('number,condition,names,action',[(1,'1이 준비되면',['원료갑','원료을'],'사용한다.'),(2,'2가 완료되면',['자재병','자재정'],'옮긴다.')])
def test_surface_contract_accepts_other_source_names_numbers_states_and_actions(number,condition,names,action):
    previous=f'{number}. 앞 단계 문맥. '
    quote=condition+' '+names[0]+'와 '+names[1]+'를 '+action
    current=f'{number+1}. '+quote+'\n';text=previous+current
    def ref(start,end):return dict(source_version_id='v',parse_run_id='p',block_id='b',start_char=start,end_char=end,quote=text[start:end])
    prior=dict(id='earlier',method_ref='m',ordinal=number,evidence=ref(0,len(previous)))
    step=dict(id='later',method_ref='m',ordinal=number+1,text=current,evidence=ref(len(previous),len(text)))
    class Sources:
        def exact(self,r):
            assert text[r['start_char']:r['end_char']]==r['quote'];return r
    group=dict(quote=quote,condition_quote=condition,action_quote=action,connector_quote='',related_item_refs=[],reference_quotes=[str(number)],
               targets=[dict(item_ref='a',quote=names[0]),dict(item_ref='b',quote=names[1])],unresolved_reason='')
    items={k:dict(source_version_id='v',name=n) for k,n in zip(['a','b'],names)}
    record=timing.bind(Sources(),step,group,items,dict(earlier=prior,later=step))
    assert record['status']=='source_linked_stored_timing_record' and record['semantic_status']=='unverified'


@pytest.mark.parametrize('field,value',[('response',None),('response',[]),('response','bad'),('raw_response',None),('raw_response',[]),
    ('raw_response','bad'),('message',None),('message',[]),('message','bad'),('text',None),('text',123),('messages',[None])])
def test_corrupt_stored_timing_types_keep_normal_A_and_product(bound,field,value):
    def edit(run):
        u=run['units'][0]
        if field in ['response','messages']:u[field]=value
        elif field=='message':u['response']['raw_response'][field]=value
        else:u['response'][field]=value
    mutate(bound,edit);result=assemble(bound)
    assert result['timing_consumer']['status']=='unresolved'
    assert any(s['kind']=='stored_condition' for s in result['answer']['sections'])
    assert result['product_facts'][0]['manufacturer']=='시험업체'


@pytest.mark.parametrize('predicate,tail',[('사용하는',' 것은 아니다.'),('사용한다','고 말했다.'),('사용한다','는 안내를 인용했다.')])
def test_truncated_quote_does_not_turn_following_denial_or_report_into_positive_timing(bound,predicate,tail):
    service,snapshot,_,_=bound
    old='사용한다.';new=predicate+tail
    # Change the registered parent and both actual stored contexts consistently.
    block=next(b for b in snapshot['blocks'] if b['id']=='method');block['text']=block['text'].replace(old,new)
    with service.repository.connect() as db:
        db.execute('UPDATE blocks SET payload=? WHERE id=?',(json.dumps(block),'method'))
        for rid in ['conditions','timing']:
            run=service.repository.get(db,'runs',rid);unit=run['units'][0]
            index=0 if rid=='conditions' else 1;ctx=json.loads(unit['messages'][index]['content'])
            ctx['context'][-1]['text']=block['text'];ctx['context'][-1]['source_reference']['end_char']=len(block['text'])
            if rid=='timing':
                delta=len(new)-len(old)
                for step in ctx['method_steps']:
                    if step['ordinal']==2:
                        step['text']=step['text'].replace(old,new);step['source_reference']['quote']=step['text'];step['source_reference']['end_char']+=delta
                    elif step['ordinal']==3:
                        step['source_reference']['start_char']+=delta;step['source_reference']['end_char']+=delta
                g=unit['response']['parsed']['step2']['groups'][0]
                g['quote']=g['quote'][:-len(old)]+predicate;g['action_quote']=predicate
                raw=json.dumps(unit['response']['parsed'],ensure_ascii=False);unit['response'].update(text=raw,raw_response=dict(message=dict(content=raw)))
            unit['messages'][index]['content']=json.dumps(ctx);service.repository.save(db,'runs',run)
    result=assemble(bound)
    assert not any(s['kind']=='stored_timing' for s in result['answer']['sections'])
    assert any(s['kind']=='stored_condition' for s in result['answer']['sections'])
    assert any(any(word in r.get('reason','') for word in ['후행','선두','지원']) for r in result['timing_consumer']['records'])
