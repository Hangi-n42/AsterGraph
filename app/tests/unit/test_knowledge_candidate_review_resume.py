"""Exact cached own judgments retain one-to-one input provenance for cached R."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.knowledge import business_review as review,business_run
from app.tests.unit.test_knowledge_public_bounded_flow import public_run,boundary_only


class SavedRuns:
    def __init__(self):self.runs={}
    @contextmanager
    def connect(self):yield None
    def get(self,_db,kind,key):
        assert kind=='runs'
        return deepcopy(self.runs[key])


def own_review(monkeypatch,service,run,*,donor=None,unit_id='original-unit',changed_output=False):
    claim=run['claims'][0]
    output=dict(checks=[dict(claim_id=claim['id'],claim_support='supported',error_fields=[],error_evidence=[],
        evidence=business_run.exact_evidence([dict(block_id='body',quote=run['blocks'][0]['text'])],run['blocks']),
        reason='원 응답 그대로' if not changed_output else '달라진 응답')],preservation_checks=[])
    def cached_json(_service,current,stage,instruction,context,schema,**kwargs):
        built=business_run.json_request(current,stage,instruction,context,schema)
        options=current['recipe']['options']
        cfg=dict(model=current['recipe']['models']['review'],generation=current['recipe']['generation'],
            identity=current['model_identity'],temperature=0,timeout=options['timeout'])
        limits=dict(max_tokens=options['review_tokens'],context_tokens=options['context_tokens'],think=options['think'])
        unit=dict(id=unit_id,stage=stage,status='succeeded',error=None,**built,
            request_configuration=cfg,requested_limits=limits,executed_limits=deepcopy(limits),
            response=dict(request_id='original-unit',failure_kind=None),restored_evidence_output=deepcopy(output))
        if donor:unit['reused_from']=dict(run_id=donor['id'],unit_id=donor['units'][-1]['id'],original_status='succeeded')
        current['units'].append(unit)
        return deepcopy(output)
    monkeypatch.setattr(business_run,'json_call',cached_json)
    return review.review_candidates(service,run,[claim])


def prepared(monkeypatch):
    parent,_=public_run();parent.update(id='parent',units=[])
    repo=SavedRuns();service=SimpleNamespace(repository=repo)
    original=own_review(monkeypatch,service,parent)
    repo.runs[parent['id']]=deepcopy(parent)
    child=deepcopy(parent);child.update(id='child',units=[],candidate_reviews=[])
    return service,parent,child,original


def test_exact_reuse_keeps_current_ids_and_original_R_input_reference(monkeypatch):
    service,parent,child,original=prepared(monkeypatch)
    receipt=own_review(monkeypatch,service,child,donor=parent,unit_id='new-unit')
    assert receipt['id']!=original['id'] and receipt['unit_id']=='new-unit'
    assert receipt['reused_judgment']==dict(run_id='parent',receipt_id=original['id'],unit_id='original-unit')
    assert receipt['output']==original['output'] and receipt['checks']==original['checks']
    direct=review.current_candidate_reviews(child);cid=child['claims'][0]['id']
    assert direct[cid]['receipt_id']==receipt['id'] and direct[cid]['unit_id']=='new-unit'
    expected=review.candidate_review_inputs(parent,review.current_candidate_reviews(parent),{cid})
    assert review.candidate_review_inputs(child,direct,{cid})==expected


@pytest.mark.parametrize('fault',['evidence_map','settings','output','cancelled','duplicate_receipt'])
def test_mismatched_or_ambiguous_origin_is_not_used(monkeypatch,fault):
    service,parent,child,original=prepared(monkeypatch)
    donor=service.repository.runs['parent']
    if fault=='evidence_map':donor['units'][0]['evidence_reference_map']={}
    if fault=='settings':donor['units'][0]['request_configuration']['identity']={'review':'different'}
    if fault=='output':donor['candidate_reviews'][0]['output']['checks'][0]['reason']='변경'
    if fault=='cancelled':donor['units'][0].update(status='failed',error='cancelled',response=dict(request_id='original-unit',failure_kind='cancelled'))
    if fault=='duplicate_receipt':donor['candidate_reviews'].append(deepcopy(donor['candidate_reviews'][0]))
    receipt=own_review(monkeypatch,service,child,donor=parent,unit_id='new-unit')
    assert 'reused_judgment' not in receipt
    direct=review.current_candidate_reviews(child);cid=child['claims'][0]['id']
    row=review.candidate_review_inputs(child,direct,{cid})[0]
    assert row['receipt_id']==receipt['id'] and row['unit_id']=='new-unit'


def test_repeated_resume_preserves_original_reference_without_rewriting_new_receipts(monkeypatch):
    service,parent,child,original=prepared(monkeypatch)
    first=own_review(monkeypatch,service,child,donor=parent,unit_id='child-unit')
    service.repository.runs['child']=deepcopy(child)
    second=deepcopy(child);second.update(id='second',units=[],candidate_reviews=[])
    receipt=own_review(monkeypatch,service,second,donor=child,unit_id='second-unit')
    assert receipt['id'] not in {first['id'],original['id']}
    assert receipt['reused_judgment']==dict(run_id='parent',receipt_id=original['id'],unit_id='original-unit')
    cid=second['claims'][0]['id']
    assert review.candidate_review_inputs(second,review.current_candidate_reviews(second),{cid})==review.candidate_review_inputs(parent,review.current_candidate_reviews(parent),{cid})


def test_changed_revalidated_output_cannot_inherit_origin(monkeypatch):
    service,parent,child,original=prepared(monkeypatch)
    receipt=own_review(monkeypatch,service,child,donor=parent,unit_id='new-unit',changed_output=True)
    assert 'reused_judgment' not in receipt


@pytest.mark.parametrize('change',['source','conditions','challenge'])
def test_changed_request_keeps_current_reference_and_exact_cache_boundary(monkeypatch,change):
    service,parent,child,original=prepared(monkeypatch)
    if change=='source':child['blocks'][0]['text']+=' 추가 원문'
    if change=='conditions':child['claims'][0]['conditions']=['새 조건']
    if change=='challenge':child['candidate_challenges']=[dict(meaning_key='m',
        claim_ids=[child['claims'][0]['id']],fields=['raw.Relation'],evidence=[],reason='새 이의')]
    receipt=own_review(monkeypatch,service,child,donor=parent,unit_id='new-unit')
    assert 'reused_judgment' not in receipt
