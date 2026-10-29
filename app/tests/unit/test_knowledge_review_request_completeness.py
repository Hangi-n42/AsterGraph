"""Local request and return contracts, without model quality labels or generation."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app.knowledge import business_run as execution, business_review as review
from app.knowledge.business_models import ContributionReviewCheck
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_required_content import content_case, target_check
from app.tests.unit.test_knowledge_business_local_review import judgments, local_run, meaning


def case():
    run, source, claims = content_case()
    target = review.requirement_content_target(source,source['meanings'][0])
    context = dict(blocks=run['blocks'],claims=[execution.compact_claim(c) for c in claims],
        source=source,required_content_targets=[target])
    row = target_check(source,claims)
    output = dict(checks=[deepcopy(row)],requirement_checks=[row],source_challenges=[],
        meaning_challenges=[],dependencies=[],candidate_challenges=[])
    return run,source,context,output


def wire(run,context,output,output_type=ContributionReviewCheck):
    request=execution.json_request(run,'requirement_representation','고정',context,output_type)
    return execution.remap_expression_keys(remap(output,request['reference_map'] or {}),request['reference_map'] or {}),request


def consume(monkeypatch,run,context,output,output_type=ContributionReviewCheck):
    def saved(*args,**kwargs):
        run['units'].append(dict(id='synthetic',status='succeeded',error=None,response=dict(parsed=deepcopy(output))))
        return dict(parsed=deepcopy(output))
    monkeypatch.setattr(execution,'call',saved)
    monkeypatch.setattr(execution,'save',lambda *args:None)
    return execution.json_call(None,run,'requirement_representation','고정',context,output_type)


def two_targets():
    run, source, context, output = case()
    target = dict(context['required_content_targets'][0],meaning_key='sibling',scope_id='synthetic-sibling-scope')
    context['required_content_targets'].append(target)
    output['requirement_checks'].append(dict(deepcopy(output['requirement_checks'][0]),
        meaning_key=target['meaning_key'],requirement_scope_id=target['scope_id']))
    output, _ = wire(run,context,output)
    output['checks'] = [deepcopy(output['requirement_checks'][0])]
    return run, source, context, output


@pytest.mark.parametrize('mutation',['absent','empty','partial','duplicate','scope','scope_collision','swapped','outside','empty_reason'])
def test_completeness_violation_preserves_whole_and_normal_siblings(monkeypatch,mutation):
    run, source, context, output = two_targets()
    normal = deepcopy(output['requirement_checks'][1]);whole = deepcopy(output['checks'])
    if mutation == 'absent':output.pop('requirement_checks')
    elif mutation == 'empty':output['requirement_checks']=[]
    elif mutation == 'partial':output['requirement_checks']=output['requirement_checks'][1:]
    elif mutation == 'duplicate':output['requirement_checks'].insert(0,deepcopy(output['requirement_checks'][0]))
    elif mutation == 'scope':output['requirement_checks'][0]['requirement_scope_id']='wrong'
    elif mutation == 'scope_collision':output['requirement_checks'][0]['requirement_scope_id']=normal['requirement_scope_id']
    elif mutation == 'swapped':
        output['requirement_checks'][0]['requirement_scope_id'],output['requirement_checks'][1]['requirement_scope_id'] = (
            output['requirement_checks'][1]['requirement_scope_id'],output['requirement_checks'][0]['requirement_scope_id'])
    elif mutation == 'outside':output['requirement_checks'][0]['meaning_key']='outside'
    else:output['requirement_checks'][0]['reason']=' '
    result=consume(monkeypatch,run,context,output)
    validation=result['required_review_validation']
    assert not validation['complete'] and run['units'][-1]['error']=='required_review_incomplete'
    assert result['checks'][0]['status']==whole[0]['status']
    if mutation not in {'absent','empty','swapped'}:
        sibling=next(r for r in result['requirement_checks'] if r['meaning_key']=='sibling')
        assert sibling['status']==normal['status'] and not sibling['required_check_errors']
        assert review.bind_requirement_check(sibling,context['required_content_targets'][1],run['claims'],run['blocks'])['content_scope_bound']
    for row in result['requirement_checks']:
        if row['required_check_errors']:
            assert row['status']=='unknown'
            bound=review.bind_requirement_check(row,next((t for t in context['required_content_targets'] if t['meaning_key']==row['meaning_key']),None),run['claims'],run['blocks'])
            assert bound['status']=='unknown' and not bound['content_scope_bound']
    if mutation in {'absent','empty','partial'}:assert 'product' in validation['missing']
    if mutation=='duplicate':assert 'product' in validation['invalid'] and not validation['missing']


def test_conditional_schema_requires_exact_count_and_allowed_ids_but_legacy_model_does_not():
    run, _, context, output=two_targets()
    request=execution.json_request(run,'requirement_representation','검수',context,ContributionReviewCheck)
    schema=request['schema'];field=schema['properties']['requirement_checks']
    assert 'requirement_checks' in schema['required'] and field['minItems']==field['maxItems']==2
    assert 'requirement_checks' not in ContributionReviewCheck.model_json_schema()['required']
    typed=execution.required_review_type(ContributionReviewCheck,request['required_review_targets'])
    # The wire's ID references are restored before the original output schema consumes them.
    for rows in [[],output['requirement_checks'][:1],output['requirement_checks']*2]:
        with pytest.raises(ValidationError):typed.model_validate(dict(output,requirement_checks=rows))
    row=schema['$defs'][field['items']['$ref'].split('/')[-1]]
    assert set(row['properties']['meaning_key']['enum'])==set(remap(list(request['required_review_targets']),request['reference_map']))
    assert set(row['properties']['requirement_scope_id']['enum'])==set(request['required_review_targets'].values())


def test_explicit_unknown_is_a_complete_return_but_never_semantic_completion(monkeypatch):
    run, source, context, output=case()
    row=output['requirement_checks'][0]
    row.update(status='unknown',claim_ids=[],expression_quotes=[],represented_content='',reason='확인 불가')
    output['checks']=[deepcopy(row)]
    result=consume(monkeypatch,run,context,output)
    assert result['required_review_validation']['complete']
    row=result['requirement_checks'][0]
    result['requirement_checks']=[review.bind_requirement_check(row,context['required_content_targets'][0],run['claims'],run['blocks'])]
    question=review.question_representation(source,result)
    assert question['checks'][0]['status']=='unknown'
    result['source_checks']=review.source_judgments(source,source['meanings'])
    summary=review.summarize_local(source['meanings'],[result],source_owned=True,source=source)
    assert summary['checks'][0]['status']=='unknown' and not summary.get('satisfied')


@pytest.mark.parametrize('targets',[None,[]])
def test_unscoped_request_is_byte_equivalent_when_new_contract_is_disabled(monkeypatch,targets):
    run, _, context, _=case()
    if targets is None:context.pop('required_content_targets')
    else:context['required_content_targets']=targets
    actual=execution.json_request(run,'requirement_representation','고정',context,ContributionReviewCheck)
    monkeypatch.setattr(execution,'required_review_targets',lambda *args:None)
    legacy=execution.json_request(run,'requirement_representation','고정',context,ContributionReviewCheck)
    assert actual==legacy and 'required_review_targets' not in actual


def test_product_caller_and_evaluation_use_same_builder(monkeypatch):
    run=local_run();source=dict(meanings=[meaning('m')],examined_block_ids=['body'],completeness='complete',gaps=[],conjunctions=[])
    requirement=run['requirements'][0];seen=[];original=review.local_review_inputs
    def builder(*args,**kwargs):
        built=original(*args,**kwargs);seen.append(built);return built
    def answer(service,active,stage,instruction,packet,schema):
        active['units'].append(dict(id=str(len(active['units']))))
        if packet['mode']=='meaning_batch':
            claims=[next(c for c in run['claims'] if c['id']==p['id']) for p in packet['claims']]
            assert instruction==seen[0][0] and packet==seen[0][1](claims,source['meanings'])
            independent=original(run,requirement,source,[])
            assert independent[0]==instruction and independent[1](claims,source['meanings'])==packet
            actual=execution.json_request(run,stage,instruction,packet,schema)
            expected=execution.json_request(run,stage,independent[0],independent[1](claims,source['meanings']),schema)
            assert actual==expected
        return judgments(['m'],ids=[c['id'] for c in run['claims']])
    monkeypatch.setattr(review,'local_review_inputs',builder)
    monkeypatch.setattr(execution,'json_call',answer)
    monkeypatch.setattr(execution,'cancelled',lambda *args:False)
    review.represent(None,run,requirement,source,[])
    assert len(seen)==1


def test_builder_uses_full_source_and_preserves_previous_meanings_and_qa_context():
    run,source,context,_=case();requirement=run['requirements'][0]
    source['findings']=[dict(id='qa',origin='qa',meaning_keys=['product'],candidate_binding_valid=False)]
    previous={'product':dict(source['meanings'][0],statement='이전 원문 의미')}
    instruction,packet=review.local_review_inputs(run,requirement,source,[],previous_meanings=previous)
    view=packet(run['claims'],source['meanings'])
    assert 'requirement_checks는 required_content_targets' in instruction
    assert 'expression_challenges는' in instruction
    assert view['source']['meanings']==[previous['product']]
    assert view['required_content_targets']==context['required_content_targets']
    assert view['expression_challenges']==source['findings']


def test_legacy_partial_targets_keep_the_original_request(monkeypatch):
    run,_,context,_=case()
    context['required_content_targets']=[dict(meaning_key='product',content='과거 불완전 대상')]
    actual=execution.json_request(run,'requirement_representation','고정',context,ContributionReviewCheck)
    assert execution.required_review_targets(context,ContributionReviewCheck) is None
    monkeypatch.setattr(execution,'required_review_targets',lambda *args:None)
    assert actual==execution.json_request(run,'requirement_representation','고정',context,ContributionReviewCheck)


def test_duplicate_server_target_is_rejected_before_generation():
    run,_,context,_=case()
    context['required_content_targets']*=2
    with pytest.raises(ValueError,match='required_review_targets'):
        execution.json_request(run,'requirement_representation','검수',context,ContributionReviewCheck)


@pytest.mark.parametrize('field',['required_content','evidence','content_evidence_bound','content_source_version'])
def test_product_builder_keeps_valid_target_when_another_application_is_unverified(field):
    run,source,_,_=case()
    other=deepcopy(source['meanings'][0]);other['key']='other'
    source['meanings'].append(other);source['public_scope']['review_meaning_keys'].append('other')
    other['requirement_applications'][0].pop(field)
    assert review.requirement_content_target(source,other) is None
    instruction,packet=review.local_review_inputs(run,run['requirements'][0],source,[])
    context=packet(run['claims'],source['meanings'])
    assert [t['meaning_key'] for t in context['required_content_targets']]==['product']
    request=execution.json_request(run,'requirement_representation',instruction,context,ContributionReviewCheck)
    assert list(request['required_review_targets'])==['product']
    assert 'requirement_checks' in request['schema']['required']


@pytest.mark.parametrize('mutation',['missing','duplicate','scope'])
def test_nonreference_path_records_diagnostics_and_keeps_normal_sibling(monkeypatch,mutation):
    from pydantic import BaseModel, Field
    from app.knowledge.business_models import RequiredContributionCheck, ContributionCheck
    class WithoutEvidenceViews(BaseModel):
        checks: list[ContributionCheck]
        requirement_checks: list[RequiredContributionCheck] = Field(default_factory=list)
    run,source,context,output=two_targets()
    # Restore wire aliases: this synthetic type is intentionally outside source-view subclasses.
    _,request=wire(run,context,{})
    reverse={v:k for k,v in (request['reference_map'] or {}).items()}
    output=execution.remap_expression_keys(remap(output,reverse),reverse)
    normal=deepcopy(output['requirement_checks'][1]);whole=deepcopy(output['checks'])
    if mutation=='missing':output['requirement_checks']=output['requirement_checks'][1:]
    elif mutation=='duplicate':output['requirement_checks'].insert(0,deepcopy(output['requirement_checks'][0]))
    else:output['requirement_checks'][0]['requirement_scope_id']='wrong'
    output,_=wire(run,context,output,WithoutEvidenceViews)
    before=deepcopy(output)
    result=consume(monkeypatch,run,context,output,WithoutEvidenceViews)
    assert result['required_review_validation']['complete'] is False
    assert run['units'][-1]['status']=='failed' and run['units'][-1]['error']=='required_review_incomplete'
    sibling=next(r for r in result['requirement_checks'] if r['meaning_key']=='sibling')
    assert sibling['status']==normal['status'] and sibling['required_check_errors']==[]
    assert result['checks']==whole
    assert output==before and run['units'][-1]['response']['parsed']==before
    assert run['units'][-1]['restored_evidence_output']==result


def test_nonreference_diagnostics_and_raw_survive_service_save_GET(monkeypatch,tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel,Field
    from app.api.routers import knowledge
    from app.knowledge.service import KnowledgeService
    from app.knowledge.business_models import RequiredContributionCheck,ContributionCheck
    class WithoutEvidenceViews(BaseModel):
        checks: list[ContributionCheck]
        requirement_checks: list[RequiredContributionCheck] = Field(default_factory=list)
    product_save=execution.save
    run,_,context,output=two_targets()
    _,request=wire(run,context,{})
    reverse={v:k for k,v in (request['reference_map'] or {}).items()}
    output=execution.remap_expression_keys(remap(output,reverse),reverse)
    output['requirement_checks'][0]['requirement_scope_id']='wrong'
    output,_=wire(run,context,output,WithoutEvidenceViews);before=deepcopy(output)
    result=consume(monkeypatch,run,context,output,WithoutEvidenceViews)
    run.update(id='required-return-synthetic',kind='business',status='partial',metrics={},analysis_units=[],result=result)
    service=KnowledgeService(tmp_path/'proof.db')
    with service.repository.connect() as db: db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],json.dumps(run,ensure_ascii=False)))
    product_save(service,run)
    app=FastAPI();app.include_router(knowledge.router)
    app.dependency_overrides[knowledge.get_knowledge_service]=lambda:service
    monkeypatch.setattr(knowledge.settings,'KNOWLEDGE_ENABLED',True)
    with TestClient(app) as client:
        response=client.get('/knowledge/runs/'+run['id']);assert response.status_code==200
        got=response.json()['data'];got.pop('counts');assert got==run
    assert got['units'][-1]['response']['parsed']==before
    assert got['result']['requirement_checks'][0]['required_check_errors']
    assert got['result']['requirement_checks'][1]['status']=='represented'
    service.shutdown()


def test_unrelated_nonreference_call_keeps_original_return_and_does_not_save(monkeypatch):
    from pydantic import BaseModel
    class UnrelatedOutput(BaseModel):
        value: str
    run=local_run();context=dict(note='기존 무계약 입력')
    with monkeypatch.context() as disabled:
        disabled.setattr(execution,'required_review_targets',lambda *args:None)
        prior=execution.json_request(run,'requirement_representation','고정',context,UnrelatedOutput)
    current=execution.json_request(run,'requirement_representation','고정',context,UnrelatedOutput)
    assert current==prior and current['evidence_reference_map'] is None
    def output(*args,**kwargs):
        run['units'].append(dict(id='legacy',status='succeeded',error=None))
        return dict(parsed=dict(value='기존 값'))
    monkeypatch.setattr(execution,'call',output)
    monkeypatch.setattr(execution,'save',lambda *args:pytest.fail('무계약 비참조 호출은 저장 동작 불변'))
    result=execution.json_call(None,run,'requirement_representation','고정',context,UnrelatedOutput)
    assert result==dict(value='기존 값')
    assert run['units'][-1]==dict(id='legacy',status='succeeded',error=None)
