"""Synthetic missing-participant evidence checks; no native model quality claims."""
from copy import deepcopy

import pytest

from app.knowledge import business_run as execution, business_selected_repair as repair
from app.knowledge import business_selected_repair_evidence as evidence
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_business_role_review import case
from app.tests.unit.test_knowledge_selected_repair import ready, proposal


def failed_proposal(case, monkeypatch):
    template = case[0]['blocks'][0]
    for bid, text, version in [('title', '제목: 조리', 'v1'), ('name', '음식명: 조리', 'v1'), ('other', '조리', 'v2')]:
        case[0]['blocks'].append(dict(template, id=bid, text=text, span=[0,len(text)], source_version_id=version))
    run, req, scope = ready(case, monkeypatch)
    run['request_reference_review']['block_ids'] = [b['id'] for b in run['blocks']]
    run['recipe'].update(models=dict(review='fixture'), generation='fixture'); run['model_identity'] = dict(fixture=True)
    raw = proposal(repair.packet(run, req, scope, run['blocks']))
    raw['patches'][0]['raw'] = dict(Event='조리에 돼지고기 120g을 사용한다.', Entity=['조리','돼지고기'])
    def generate(service, active, stage, instruction, context, schema):
        request = execution.json_request(active, stage, instruction, context, schema)
        value = schema.model_validate(raw).model_dump()
        opt = active['recipe']['options']; limits = dict(max_tokens=opt['review_tokens'], context_tokens=opt['context_tokens'], think=opt['think'])
        active['units'].append(dict(id='repair-unit',stage=stage,status='succeeded',
            **{k:request[k] for k in ('messages','schema','reference_map')},
            requested_limits=limits,executed_limits=limits,
            request_configuration=dict(model='fixture',generation='fixture',identity=active['model_identity'],temperature=0,timeout=opt['timeout']),
            response=dict(request_id='repair-unit',parsed=remap(value,request['reference_map'] or {}))))
        return deepcopy(value)
    monkeypatch.setattr(execution, 'json_call', generate)
    result = repair.recover(None, run, req, scope, run['blocks'])
    assert result['errors'] == [evidence.MISSING_PARTICIPANT] and not result['changes']
    return run, req, scope


def choices(context, occurrence='o2'):
    return dict(choices={key:dict(occurrence_id=occurrence,reason='합성 근거 선택') for key in context['tasks']})


def test_existing_proposition_stays_frozen_and_only_missing_evidence_is_selected(case, monkeypatch):
    run, req, scope = failed_proposal(case, monkeypatch); before = deepcopy(run['claims']); unit = deepcopy(run['units'][-1])
    context, gaps = evidence.packet(run, req, scope, run['blocks'])
    assert len(context['tasks']) == 1
    task = next(iter(context['tasks'].values()))
    assert task['entity'] == '조리' and list(task['occurrences']) == ['o1','o2']
    assert {o['reference']['block_id'] for o in task['occurrences'].values()} == {'title','name'}
    def generate(service, active, stage, prompt, packet, schema):
        assert stage == 'source_literal_participants' and packet == context
        active['units'].append(dict(id='evidence-unit',response=dict(request_id='evidence-unit')))
        return choices(packet)
    monkeypatch.setattr(execution,'json_call',generate)
    monkeypatch.setattr(repair.autoschema,'graph',lambda *a:dict(synthetic=True))
    result = execution.assess(None, run, req, phase='selected_repair_evidence')
    assert result['status'] == 'applied_awaiting_recheck' and len(result['changes']) == 1
    old = result['original_proposals']['patches'][0]; new = result['patches']['patches'][0]
    assert {k:v for k,v in old.items() if k!='evidence'} == {k:v for k,v in new.items() if k!='evidence'}
    assert new['evidence'][:-1] == old['evidence'] and new['evidence'][-1]['block_id'] == 'name'
    assert run['claims'][:len(before)] == before and run['units'][-2] == unit
    assert run['repairs'][-2]['status'] == 'unresolved'
    assert result['changes'][0]['after']['review_status'] == 'unreviewed'


@pytest.mark.parametrize('bad', ['null','outside','changed_event','changed_source','changed_request','changed_claim'])
def test_unknown_or_changed_basis_never_applies_new_claims(case, monkeypatch, bad):
    run, req, scope = failed_proposal(case, monkeypatch); before = deepcopy(run['claims'])
    if bad == 'changed_event': run['repairs'][-1]['patches']['patches'][0]['raw']['Event'] = '변경'
    elif bad == 'changed_source': run['blocks'][1]['text'] = '다른 문서'
    elif bad == 'changed_request': run['units'][-1]['messages'] = []
    elif bad == 'changed_claim': run['claims'][0]['statement'] = '변경'
    def generate(service, active, stage, prompt, context, schema):
        assert bad in {'null','outside'}
        return choices(context, None if bad=='null' else 'not-in-source')
    monkeypatch.setattr(execution,'json_call',generate)
    if bad in {'null','outside'}:
        result = evidence.complete(None,run,req,scope,run['blocks'])
        assert result['status']=='unresolved' and result['errors'] and not result['changes'] and run['claims']==before
    else:
        with pytest.raises(ValueError):evidence.complete(None,run,req,scope,run['blocks'])
