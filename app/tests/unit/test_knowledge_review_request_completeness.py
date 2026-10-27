"""Local request and return contracts, without model quality labels or generation."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app.knowledge import business_run as execution, business_review as review
from app.knowledge.business_models import ContributionReviewCheck
from app.knowledge.source_meanings import remap
from app.tests.unit.test_knowledge_expression_field_references import case, consume, wire
from app.tests.unit.test_knowledge_business_local_review import judgments, local_run, meaning


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
    from app.tests.unit.test_knowledge_application_evidence_references import case as legacy_case
    run,context=legacy_case()
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
