"""An admitted QA observation needs one final contribution decision, with stable source work retained."""
from copy import deepcopy
import pytest
from app.knowledge import business_review as review, business_run
from app.tests.unit.test_knowledge_business_feedback import bound
from app.tests.unit.test_knowledge_business_local_review import judgments
from app.tests.unit.test_knowledge_business_separated_review import synthesis


@pytest.mark.parametrize('fault',['missing','duplicate','wrong_key','no_evidence','duplicate_location'])
def test_required_final_check_failure_keeps_history_but_leaves_observation_open(bound,fault):
    parent,qa,basis,snapshot=bound
    compact=judgments(['m','normal'],ids=[parent['claims'][0]['id']]);before=deepcopy(compact)
    row=dict(deepcopy(compact['checks'][0]),revision_basis='rechecked_unchanged',evidence=parent['assessments'][0]['source']['meanings'][0]['evidence'])
    response=synthesis();response['checks']=[row]
    if fault=='missing':response['checks']=[]
    elif fault=='duplicate':response['checks']=[row,deepcopy(row)]
    elif fault=='wrong_key':row['meaning_key']='outside'
    elif fault=='no_evidence':row['evidence']=[]
    else:row['claim_ids']*=2
    result,joined,valid,errors=review.retain_synthesis(compact,response,{'m'},set(row['claim_ids']),parent['blocks'],required_check_keys={'m'})
    assert not joined and errors and 'm' not in valid['checks']
    assert result['checks']==before['checks'] and compact==before
    resolution=review.qa_check_resolutions([dict(id='qa',meaning_keys=['m'])],result,valid['checks'])[0]
    assert resolution['status']=='unresolved'
    assert any(c.get('source_reassessment_needed') is False for c in result['meaning_challenges'])


def test_unchanged_final_check_accepts_reordered_locations_and_cannot_hide_a_change(bound):
    parent,*_=bound;ids=[c['id'] for c in parent['claims']]
    compact=judgments(['m','normal'],ids=ids);response=synthesis()
    row=dict(deepcopy(compact['checks'][0]),claim_ids=ids[::-1],revision_basis='rechecked_unchanged',
        evidence=parent['assessments'][0]['source']['meanings'][0]['evidence'])
    response['checks']=[row]
    result,joined,valid,errors=review.retain_synthesis(compact,response,{'m'},set(ids),parent['blocks'],required_check_keys={'m'})
    assert joined and not errors and result['checks'][1]==compact['checks'][1]
    assert review.qa_check_resolutions([dict(id='qa',meaning_keys=['m'])],result,valid['checks'])[0]['reason']==row['reason']
    row['status']='partial'
    assert not review.retain_synthesis(compact,response,{'m'},set(ids),parent['blocks'],required_check_keys={'m'})[1]


@pytest.mark.parametrize('status',['partial','missing','unknown'])
def test_final_check_is_the_single_basis_of_observation_disposition(bound,status):
    parent,*_=bound;cid=parent['claims'][0]['id'];compact=judgments(['m','normal'],ids=[cid])
    row=dict(deepcopy(compact['checks'][0]),status=status,revision_basis='prior_misreading',reason='최종 판단',
        represented_content='실제 부분',missing_content='잔여',missing_evidence=parent['assessments'][0]['source']['meanings'][0]['evidence'],
        evidence=parent['assessments'][0]['source']['meanings'][0]['evidence'])
    response=synthesis();response['checks']=[row]
    result,joined,valid,errors=review.retain_synthesis(compact,response,{'m'},{cid},parent['blocks'],required_check_keys={'m'})
    resolution=review.qa_check_resolutions([dict(id='qa',meaning_keys=['m'])],result,valid['checks'])[0]
    assert joined and not errors and result['checks'][0]['status']==status
    assert resolution['status']==('unresolved' if status=='unknown' else 'resolved')
    assert all(resolution[k]==row[k] for k in ['claim_ids','reason','evidence'])
    assert result['checks'][1]==compact['checks'][1]


@pytest.fixture
def source_receipt(bound):
    parent,*_=bound;a=parent['assessments'][0];s=a['source'];q=parent['requirements'][0]
    f=dict(id='source-f',origin='source',kind='local_not_found',meaning_keys=['unresolved:other'],
        scope_meaning_keys=['m'],claim_ids=[],fields=[],provided_block_ids=['body'],unit_id='source',text='국소 미발견')
    row=dict(finding_id=f['id'],status='not_required',meaning_keys=['m'],claim_ids=[parent['claims'][0]['id']],fields=[],
        evidence=deepcopy(s['meanings'][0]['evidence']),reason='다른 실제 구간에서 제공됨')
    s['findings']=[f];s['finding_resolutions']=[row]
    a['review_scope']=dict(claim_ids=[c['id'] for c in parent['claims']],join_unit_id='join')
    a['input_fingerprint']=business_run.assessment_fingerprint(parent,q,s,a['review_scope'])
    parent['units']=[dict(id='join',status='succeeded',error=None,restored_evidence_output=dict(finding_resolutions=[deepcopy(row)]))]
    return parent,q,deepcopy(s),f,row


@pytest.mark.parametrize('fault',['none','block','question','meaning','candidate','finding','raw','challenge'])
def test_source_inspection_reuse_checks_versions_and_actual_receipt(source_receipt,fault):
    parent,q,s,f,row=source_receipt;challenges=[]
    if fault=='block':parent['blocks'][0]['text']+='변경'
    elif fault=='question':q['question']+='변경'
    elif fault=='meaning':s['meanings'][0]['statement']+='변경'
    elif fault=='candidate':parent['claims'][0]['raw']['Tail']='변경'
    elif fault=='finding':f['text']+='변경'
    elif fault=='raw':parent['units'][0]['restored_evidence_output']['finding_resolutions']=[]
    elif fault=='challenge':challenges=[dict(meaning_key='m',fields=['statement'],evidence=row['evidence'])]
    refs=review.reusable_source_resolutions(parent,q,s,[f],challenges)
    assert bool(refs)==(fault=='none')
    if refs:
        assert refs[0]['resolution']==row and refs[0]['authority']=='unchanged_source_inspection_not_expression_completeness'
        assert 'checks' not in refs[0]


def test_sent_final_check_schema_requires_all_remainder_fields(bound):
    from pydantic import Field, ValidationError, create_model
    from app.knowledge.business_models import ChallengedContributionRevision, ContributionSynthesisCheck
    parent,*_=bound
    output=create_model('RequiredFinalContributionTest',__base__=ContributionSynthesisCheck,
        checks=(list[ChallengedContributionRevision],Field(min_length=1)))
    packet=dict(blocks=parent['blocks'],claims=parent['claims'])
    schema=business_run.json_request(parent,'requirement_representation','최종 판정',packet,output)['schema']
    ref=schema['properties']['checks']['items']['$ref'].split('/')[-1]
    assert {'represented_content','missing_content','missing_evidence'} <= set(schema['$defs'][ref]['required'])
    row=dict(meaning_key='m',status='partial',claim_ids=[],reason='설명만 있음',revision_basis='combined_expression',evidence=[])
    with pytest.raises(ValidationError):ChallengedContributionRevision.model_validate(row)


@pytest.mark.parametrize('field',['represented_content','missing_content','missing_evidence'])
def test_partial_final_row_without_a_remainder_cannot_close_qa(bound,field):
    parent,*_=bound;cid=parent['claims'][0]['id'];compact=judgments(['m'],ids=[cid]);response=synthesis()
    evidence=parent['assessments'][0]['source']['meanings'][0]['evidence']
    row=dict(deepcopy(compact['checks'][0]),status='partial',revision_basis='combined_expression',evidence=evidence,
        represented_content='실제 부분',missing_content='잔여',missing_evidence=evidence)
    row[field]=[] if field=='missing_evidence' else ''
    response['checks']=[row]
    result,joined,valid,errors=review.retain_synthesis(compact,response,{'m'},{cid},parent['blocks'],required_check_keys={'m'})
    assert not joined and 'm' not in valid['checks']
    assert review.qa_check_resolutions([dict(id='qa',meaning_keys=['m'])],result,valid['checks'])[0]['status']=='unresolved'


def test_verified_source_resolution_keeps_its_original_candidate_address(source_receipt):
    parent,q,source,f,row=source_receipt
    retained=review.reusable_source_resolutions(parent,q,source,[f]);assert len(retained)==1
    def resolve(candidate_row):
        s=deepcopy(source);result=judgments(['m']);result.update(source_completeness='partial',
            unselected_source_required=False,finding_resolutions=[deepcopy(candidate_row)])
        review.resolve_findings(s,result,[f],parent['blocks'],[],joined=True,resolution_keys={'m'},expression_keys={'m'},
            retained_source_resolutions=[r['resolution'] for r in retained])
        return s['finding_resolutions'][0]
    assert resolve(row)==row  # No current join claim is supplied; the exact old row has a validated receipt.
    changed=dict(deepcopy(row),reason='새 출력으로 바뀜')
    assert resolve(changed)['status']=='unresolved'
    changed=dict(deepcopy(row),claim_ids=['new-unprovided'])
    assert resolve(changed)['status']=='unresolved'


@pytest.mark.parametrize('fault',['none','unknown','missing_final'])
def test_multi_observation_uses_each_final_row_and_blocks_only_pending_keys(bound,fault):
    parent,*_=bound;source=parent['assessments'][0]['source'];cid=parent['claims'][0]['id']
    source['meanings']=[dict(deepcopy(source['meanings'][0]),key=k) for k in ['normal','gap','pending']]
    source['public_scope']['review_meaning_keys']=['normal','gap','pending']
    finding=dict(id='qa',origin='qa',meaning_keys=['normal','gap','pending'],claim_ids=[],fields=[],text='미검증 묶음')
    result=judgments(['normal','gap','pending'],ids=[cid])
    result.update(source_completeness='partial',unselected_source_required=False,finding_resolutions=[])
    evidence=source['meanings'][0]['evidence']
    for c in result['checks']:c['evidence']=evidence
    result['checks'][1].update(status='missing',claim_ids=[])
    explicit={'normal','gap','pending'}
    if fault=='unknown':result['checks'][2]['status']='unknown'
    elif fault=='missing_final':explicit.remove('pending')
    row=review.qa_check_resolutions([finding],result,explicit)[0]
    assert row['meaning_keys']==(['normal','gap','pending'] if fault=='none' else ['pending'])
    assert row['status']==('resolved' if fault=='none' else 'unresolved')
    result['finding_resolutions']=[row]
    review.resolve_findings(source,result,[finding],parent['blocks'],parent['claims'],joined=True,
        resolution_keys={'normal','gap','pending'},expression_keys=explicit)
    assert {c['meaning_key'] for c in result['meaning_challenges']}==(set() if fault=='none' else {'pending'})
    assert result['checks'][0]['status']=='represented' and result['checks'][1]['status']=='missing'


def test_multi_observation_reaches_final_actions_without_blocking_independent_facts(monkeypatch):
    from app.knowledge import autoschema
    from app.tests.unit.test_knowledge_business_missing_recovery import fixture
    run,req,source=fixture(monkeypatch);run['input_version_ids']=['v']
    source['meanings'].append(dict(deepcopy(source['meanings'][0]),key='pending'))
    keys=['part','other','pending'];source['public_scope']['review_meaning_keys']=keys
    source['findings']=[dict(id='qa',origin='qa',kind='unverified_expression_gap',meaning_keys=keys,
        scope_meaning_keys=keys,claim_ids=[],fields=[],text='미검증 관찰',unit_id='qa',provided_block_ids=['body'],
        requirement_version=review.preservation_requirement_version(req),
        source_fingerprint=review.preservation_source_version(run,['v']),
        candidate_pool_hash=review.pool_hash(run),meaning_versions={m['key']:autoschema.identifier('meaning',m) for m in source['meanings']})]
    before=deepcopy(run['claims']);packets=[]
    def response(s,current,stage,instruction,packet,schema):
        packets.append(deepcopy(packet));current['units'].append(dict(id='unit'+str(len(packets))))
        refs=[dict(block_id='body',quote=run['blocks'][0]['text'])]
        rows=[dict(meaning_key=k,status=status,claim_ids=[before[0]['id']] if status=='represented' else [],
            reason='현재 대조',represented_content='기존 정상' if status=='represented' else '',
            missing_content='원문 누락' if status=='missing' else '',missing_evidence=refs if status=='missing' else [])
            for k,status in zip(keys,['represented','missing','unknown'])]
        out=dict(checks=rows,dependencies=[dict(meaning_key=k,premise_keys=[]) for k in keys],
            source_challenges=[],meaning_challenges=[],candidate_challenges=[],preservation_checks=[])
        if packet['mode']=='requirement_join':
            assert packet['required_final_check_keys']==sorted(keys)
            assert len(packet['qa_expression_observations'])==1
            for row in rows:row.update(revision_basis='rechecked_unchanged',evidence=refs)
            out.update(satisfied=False,conjunctions_satisfied=True,reason='부분 처리',
                source_completeness='complete',unselected_source_required=False,finding_resolutions=[])
        return schema.model_validate(out).model_dump()
    monkeypatch.setattr(business_run,'json_call',response)
    assessment=business_run.assess(None,run,req,source=source,focus_meaning_keys=keys)
    actions={a['meaning_key']:a['action'] for a in assessment['actions']}
    assert {k:actions[k] for k in keys}==dict(part='maintain',other='recover',pending='hold')
    assert assessment['blocked_meaning_keys']==['pending'] and not assessment['global_blocks']
    assert assessment['review_scope']['required_final_check_keys']==sorted(keys)
    assert run['claims']==before and assessment['source']['meanings']==source['meanings']
