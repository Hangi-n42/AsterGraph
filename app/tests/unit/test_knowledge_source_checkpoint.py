"""A genuine stored source-applicability result survives cancellation or failed R."""
from copy import deepcopy

import pytest

from app.knowledge import business_review as review, business_run
from app.knowledge.source_index import FrozenIndex
from app.tests.unit.test_knowledge_public_bounded_flow import public_run
from app.tests.unit.test_knowledge_business_local_review import meaning


def source_checkpoint(monkeypatch):
    run, requirement = public_run()
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='partial', gaps=[],
        meaning_gaps=[], meaning_conjunctions=[], conjunctions=[], findings=[], source_batches=[])
    source['meanings'][0]['evidence'] = business_run.exact_evidence(source['meanings'][0]['evidence'], run['blocks'])
    monkeypatch.setattr(FrozenIndex, 'search', lambda index, query, ids, limit=6:
        [dict(block_id=k) for k in ('m', 'body') if k in ids])
    monkeypatch.setattr(review, 'review_candidate_pool', lambda *a, **kw: pytest.fail('No pending candidate review before source selection'))
    def application(service, current, stage, instruction, context, schema):
        assert stage == 'requirement_application' and 'candidates' not in context
        output = schema.model_validate(dict(items=[dict(item_id='question', meaning_keys=['m'],
            source_state='available', read_block_ids=['body'], gap='', reason='Synthetic source-only fixture')],
            meaning_challenges=[])).model_dump()
        current['units'].append(dict(id='source-selection', status='succeeded', error=None,
            restored_evidence_output=deepcopy(output)))
        return output
    monkeypatch.setattr(business_run, 'json_call', application)
    source = review.public_requirement_scope(None, run, requirement, source)
    assert review.public_scope_valid(run, requirement, source)
    snapshots = []
    monkeypatch.setattr(business_run, 'save', lambda service, current: snapshots.append(deepcopy(current)))
    saved = []
    monkeypatch.setattr(business_run.business_store, 'save_assessment',
        lambda service, current, req, assessment: saved.append(deepcopy(assessment)))
    return run, requirement, source, snapshots, saved


def test_cancel_after_source_preserves_unknown_assessment_without_calling_R(monkeypatch):
    run, requirement, source, snapshots, saved = source_checkpoint(monkeypatch)
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: True)
    monkeypatch.setattr(review, 'represent', lambda *a, **kw: pytest.fail('R must not start after cancellation'))
    assessment = business_run.assess(None, run, requirement, source=source)
    assert assessment['status'] == 'unknown' and assessment['representation'] is None
    assert assessment['input_fingerprint'] == business_run.assessment_fingerprint(run, requirement, assessment['source'])
    assert assessment['source']['public_scope']['expression_review_pending']
    assert run['assessments'] == [assessment] and saved == [assessment]
    assert snapshots[-1]['assessments'] == [assessment]
    assert business_run.requirement_completion(assessment, claims=run['claims'])['status'] != 'satisfied'


def test_failed_R_does_not_discard_completed_current_source_work(monkeypatch):
    run, requirement, source, snapshots, saved = source_checkpoint(monkeypatch)
    monkeypatch.setattr(review, 'repair_context', lambda *a: [])
    monkeypatch.setattr(review, 'valid_preservation_reuses', lambda *a, **kw: [])
    def fail_R(*a, **kw):
        assert saved and snapshots[-1]['assessments'][0]['representation'] is None
        raise RuntimeError('Synthetic R boundary failure')
    monkeypatch.setattr(review, 'represent', fail_R)
    with pytest.raises(RuntimeError, match='R boundary'):
        business_run.assess(None, run, requirement, source=source)
    assert len(run['assessments']) == 1 and run['assessments'][0] == saved[0]
    assert saved[0]['status'] == 'unknown' and saved[0]['representation'] is None
    assert review.public_scope_valid(run, requirement, saved[0]['source'])
    assert saved[0]['source']['meanings'] == source['meanings']
