"""Bound whole-target absence reuses server scope, never inferred partial meaning."""
from copy import deepcopy

import pytest

from app.knowledge import business_review as review
from app.tests.unit.test_knowledge_required_content import content_case,target_check
from app.tests.unit.test_knowledge_business_local_review import judgments


def missing_case():
    run,source,claims=content_case()
    target=review.requirement_content_target(source,source['meanings'][0])
    outputs=[]
    for index,text in enumerate(['이 후보 묶음에 부위·용도가 없다.','상품의 부위와 용도']):
        row=target_check(source,claims,status='missing')
        row.update(claim_ids=[],expression_quotes=[],represented_content='',missing_content=text,
            missing_evidence=deepcopy(target['evidence']))
        row=review.bind_requirement_check(row,target,claims,run['blocks'])
        assert row['content_scope_bound']
        output=judgments(['product'],status='partial',ids=[claims[0]['id']])
        output['checks'][0].update(represented_content='전체 의미의 정상 부분',missing_content='참고 잔여',missing_evidence=target['evidence'])
        output.update(requirement_checks=[row],source_checks=review.source_judgments(source,source['meanings']),review_unit_id='stored-'+str(index))
        outputs.append(output)
    return run,source,target,outputs


def test_same_valid_full_missing_scope_survives_different_model_wording_without_rewriting_history():
    _,source,target,outputs=missing_case();before=deepcopy(outputs)
    result=review.summarize_local(source['meanings'],outputs,source_owned=True,source=source)
    row=result['checks'][0]
    assert row['status']=='missing' and row['content_scope_bound']
    assert row['missing_content']==target['content'] and row['missing_evidence']==target['evidence']
    assert row['review_unit_ids']==['stored-0','stored-1'] and not row['claim_ids']
    assert result['whole_expression_checks'][0]['status']=='partial'
    assert outputs==before and not result['satisfied']


@pytest.mark.parametrize('fault',['scope','unbound','partial','unknown','claim','quote','represented','binding','error','reference_error','return_error','contract_error','blank','no_evidence'])
def test_invalid_or_non_whole_missing_is_not_filled_from_server_target(fault):
    run,source,target,outputs=missing_case();row=outputs[0]['requirement_checks'][0]
    if fault=='scope':row['requirement_scope_id']='other-scope'
    elif fault=='unbound':row['content_scope_bound']=False
    elif fault in {'partial','unknown'}:row['status']=fault
    elif fault=='claim':row['claim_ids']=[run['claims'][0]['id']]
    elif fault=='quote':row['expression_quotes']=[dict(claim_id=run['claims'][0]['id'],field='raw.Tail',quote='등심')]
    elif fault=='represented':row['represented_content']='정상 일부'
    elif fault=='binding':row['expression_bindings']=[dict(claim_id=run['claims'][0]['id'])]
    elif fault=='error':row['expression_errors']=['unverified']
    elif fault=='reference_error':row['expression_reference_errors']=['unverified']
    elif fault=='return_error':row['required_check_errors']=['unverified']
    elif fault=='contract_error':row['contract_errors']=[dict(reason='unverified')]
    elif fault=='blank':row['missing_content']=''
    else:row['missing_evidence']=[]
    before=deepcopy(outputs)
    result=review.summarize_local(source['meanings'],outputs,source_owned=True,source=source)
    # The untouched row prevents a full-target canonical absence, even if a legacy aggregate has another status.
    assert result['checks'][0].get('missing_content')!=target['content']
    assert outputs==before


def test_current_source_version_required_for_scope_reuse():
    _,source,target,outputs=missing_case();before=deepcopy(outputs)
    source['meanings'][0]['conditions']=['새 적용 조건']
    assert review.requirement_content_target(source,source['meanings'][0]) is None
    result=review.summarize_local(source['meanings'],outputs,source_owned=True,source=source)
    assert result['checks'][0]['status']=='unknown' and result['checks'][0].get('missing_content')!=target['content']
    assert outputs==before


def test_partial_rows_keep_their_actual_different_remainders():
    run,source,target,outputs=missing_case()
    for index,out in enumerate(outputs):
        row=target_check(source,run['claims'],status='partial')
        row.update(missing_content=['카레 용도','용도 상세'][index],missing_evidence=deepcopy(target['evidence']))
        out['requirement_checks']=[review.bind_requirement_check(row,target,run['claims'],run['blocks'])]
    before=deepcopy(outputs)
    result=review.summarize_local(source['meanings'],outputs,source_owned=True,source=source)
    assert result['checks'][0]['status']=='partial'
    assert [r['missing_content'] for r in result['checks'][0]['partial_contributions']]==['카레 용도','용도 상세']
    assert outputs==before
