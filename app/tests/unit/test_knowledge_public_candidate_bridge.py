from copy import deepcopy

import pytest

from app.knowledge import business_review, business_run
from app.tests.unit.test_knowledge_business_local_review import local_run


def test_public_evidence_selection_uses_verified_version_and_intersecting_span():
    block = dict(id='body', source_version_id='v', parse_run_id='p', text='앞 조건. 뒤 예외.')
    def claim(identifier, quote, version='v'):
        return dict(id=identifier, source_version_ids=[version], evidence=[dict(block_id='body', quote=quote)])
    first = claim('first', '앞 조건.')
    rest = claim('rest', '뒤 예외.')
    wrong_version = claim('foreign', '앞 조건.', 'other')
    run = dict(blocks=[block])
    source = dict(meanings=[dict(evidence=[dict(block_id='body', quote='앞 조건.')])])
    assert business_review.public_evidence_candidates(run, source, [first, rest, wrong_version]) == [first]
    source['meanings'][0]['evidence'][0]['quote'] = '없는 인용'
    assert business_review.public_evidence_candidates(run, source, [first, rest]) == []


@pytest.mark.parametrize('public', [False, True])
def test_assess_connects_own_source_review_only_for_explicit_public_request(monkeypatch, public):
    run = local_run(); run['recipe']['review_contract'] = business_review.CONTRACT
    requirement = dict(id='r', revision=1, question='신청 접수는?', criterion='원문 조건',
        target='기관', situation='안내', period='', source_ids=[])
    if public:
        run['answer_items'] = [dict(id='question', requirement_id='r', requirement_revision=1,
            field='question', request_quote=requirement['question'])]
    source = dict(meanings=[dict(key='m', evidence=[dict(block_id='body', quote=run['blocks'][0]['text'])])],
                  examined_block_ids=['body'])
    calls = []
    monkeypatch.setattr(business_run, 'apply_source_corrections', lambda r, q, s: deepcopy(s))
    monkeypatch.setattr(business_review, 'review_candidate_pool', lambda s, r, claims: calls.append([c['id'] for c in claims]))
    def stopped(*args, **kwargs):
        raise RuntimeError('stopped after observing the bridge')
    if public:
        monkeypatch.setattr(business_review, 'public_requirement_scope', stopped)
    else:
        # Stop before unrelated source validation; the public branch must not run.
        source['meanings'] = []
        monkeypatch.setattr(business_review, 'repair_context', lambda *args: [])
        monkeypatch.setattr(business_review, 'valid_preservation_reuses', lambda *args, **kwargs: [])
        monkeypatch.setattr(business_review, 'represent', stopped)
    with pytest.raises(RuntimeError, match='observing the bridge'):
        business_run.assess(None, run, requirement, source=source)
    expected = [[c['id'] for c in run['claims']]] if public else []
    assert calls == expected


def test_partial_requirement_does_not_imply_own_source_failure_or_approval(monkeypatch):
    from app.knowledge import business_use
    from app.tests.unit.test_knowledge_business_responsibilities import setup_direct_receipt
    run, _ = setup_direct_receipt(monkeypatch, states=('supported', 'supported'))
    run['assessments'] = [dict(requirement_id='r', status='partial',
        source=dict(public_scope=dict(tasks=[])), representation=None)]
    ids = {c['id'] for c in run['claims']}
    assert business_use.eligibility(run)[0] == ids
    # A stale/failed receipt is never replaced by the public selection verdict.
    run['claims'][0]['raw']['Relation'] = '변경된 후보'
    assert run['claims'][0]['id'] not in business_use.eligibility(run)[0]
