"""Explicit source scope must not become global review or an address-validity filter."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_review as review, business_run
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments


@pytest.fixture(autouse=True)
def scope_only_tokenizer(monkeypatch):
    # These tests check source boundaries, not Korean morphology or search quality.
    from app.retrieval import tokenization
    monkeypatch.setattr(tokenization, '_tokenize_korean',
        lambda texts: [[text[i:i + 2] for i in range(len(text) - 1)] for text in texts])


def add_background(run):
    block = dict(deepcopy(run['blocks'][0]), id='outside', source_version_id='v2', source_id='outside')
    chunk = autoschema.chunks([block], 49152, 4096)[0]
    claim = autoschema.graph_record(chunk, 'entity_relation', dict(Head='외부', Relation='기록', Tail='항목'), 0)
    run['blocks'].append(block)
    run['chunks'].append(chunk)
    run['claims'].append(claim)
    run['sources'] = dict(v=dict(source_id='s'), v2=dict(source_id='outside'))
    return claim


@pytest.mark.parametrize('ownership', ['version', 'chunk', 'evidence_version', 'evidence_block', 'repair_view'])
def test_unresolved_address_candidate_retains_stored_source_ownership(ownership):
    run = local_run(); add_background(run)
    claim = run['claims'][0]
    chunk_id = claim['chunk_id']
    claim.update(source_version_ids=[], evidence=[], chunk_id='unresolved')
    claim['interpretation'] = dict(errors=['unresolved address'])
    if ownership == 'version':
        claim['source_version_ids'] = ['v']
    elif ownership == 'chunk':
        claim['chunk_id'] = chunk_id
    elif ownership == 'evidence_version':
        claim['evidence'] = [dict(source_version_id='v', block_id='unknown', quote='unresolved')]
    elif ownership == 'evidence_block':
        claim['evidence'] = [dict(block_id='body', quote='unresolved')]
    else:
        run['capacity_repair_views'] = dict(view=dict(source_version_id='v'))
        claim['chunk_id'] = 'view'
    original = deepcopy(run)
    assert claim in review.candidate_pool(run, dict(source_ids=['s']))
    assert run['claims'][-1] not in review.candidate_pool(run, dict(source_ids=['s']))
    assert run == original


def test_cross_source_candidate_keeps_other_source_evidence_and_context():
    run = local_run(); background = add_background(run)
    claim = run['claims'][0]
    claim['source_version_ids'] = ['v', 'v2']
    claim['evidence'] = business_run.exact_evidence([
        dict(block_id=b['id'], quote=b['text']) for b in run['blocks']], run['blocks'])
    original = deepcopy(run)
    selected = review.candidate_pool(run, dict(source_ids=['s']))
    assert claim in selected and background not in selected
    _, payload, _ = review.candidate_request(run, [claim])
    assert {b['source_version_id'] for b in payload['blocks']} == {'v', 'v2'}
    assert run == original


def test_empty_source_scope_keeps_legacy_pool_and_hash():
    run = local_run(); add_background(run)
    run['claims'][0]['superseded_by'] = ['replacement']
    assert review.candidate_pool(run, dict(source_ids=[])) == run['claims'][1:]
    assert review.pool_hash(run, dict(source_ids=[])) == review.pool_hash(run)
    assert review.pool_hash(run) == autoschema.identifier('claim_pool', run['claims'])


def test_scoped_fingerprints_ignore_background_but_bind_owned_content():
    run = local_run(); background = add_background(run)
    requirement = dict(id='r', revision=1, source_ids=['s'])
    source = dict(meanings=[meaning('m')])
    scope = dict(claim_ids=[c['id'] for c in run['claims'][:2]], pool_hash=review.pool_hash(run, requirement))
    def values():
        return (review.pool_hash(run, requirement), review.public_scope_fingerprint(run, requirement, source),
                business_run.assessment_fingerprint(run, requirement, source, scope))
    before, global_before = values(), review.pool_hash(run)
    background['statement'] += ' 변경'
    assert values() == before and review.pool_hash(run) != global_before
    run['claims'][0]['conditions'] = ['변경된 조건']
    assert all(after != old for after, old in zip(values(), before))


def test_assess_uses_same_pool_before_any_review_call(monkeypatch):
    run = local_run(); add_background(run)
    run['recipe']['review_contract'] = review.SOURCE_APPLICATION_CONTRACT
    run['claims'][0]['evidence'] = []
    requirement = dict(id='r', source_ids=['s'])
    class ReachedBoundary(Exception):
        pass
    def inspect(_service, _run, claims):
        assert claims == run['claims'][:2]
        raise ReachedBoundary
    monkeypatch.setattr(review, 'review_candidate_pool', inspect)
    with pytest.raises(ReachedBoundary):
        business_run.assess(None, run, requirement)


def test_public_scope_candidates_reviews_and_versions_share_source_scope(monkeypatch):
    from app.tests.unit.test_knowledge_business_public_scope import setup, mock_scope
    run, requirement, source, cid = setup(monkeypatch)
    add_background(run)
    requirement['source_ids'] = ['s']
    # Keep setup's completed reviews for both owned candidates and the outside one.
    captured = []
    mock_scope(monkeypatch, run, cid, captured=captured)
    result = review.public_requirement_scope(None, run, requirement, source)
    assert {c['id'] for c in captured[0]['candidates']} == {c['id'] for c in run['claims'][:2]}
    assert {r['claim_id'] for r in captured[0]['candidate_source_reviews']} == {c['id'] for c in run['claims'][:2]}
    assert set(result['public_scope']['candidate_versions']) == {c['id'] for c in run['claims'][:2]}
    assert result['public_scope']['public_requirement']['source_ids'] == ['s']


def test_representation_missing_pool_checks_every_scoped_candidate_only(monkeypatch):
    from app.knowledge.source_index import FrozenIndex
    run = local_run(); background = add_background(run)
    requirement = dict(id='r', revision=1, source_ids=['s'])
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[])
    first = run['claims'][0]['id']
    monkeypatch.setattr(FrozenIndex, 'search', lambda *a: [dict(block_id=first)])
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    batches = []
    def answer(_service, _run, stage, instruction, context, schema):
        run['units'].append(dict(id=str(len(run['units']))))
        if context['mode'] == 'requirement_join':
            return None
        batches.append([c['id'] for c in context['claims']])
        return judgments(['m'], status='missing')
    monkeypatch.setattr(business_run, 'json_call', answer)
    _, scope = review.represent(None, run, requirement, source, [])
    expected = {c['id'] for c in run['claims'][:2]}
    assert {cid for batch in batches for cid in batch} == expected
    assert background['id'] not in scope['candidate_inventory_ids']
    assert set(scope['candidate_inventory_ids']) == expected and scope['inventory_count'] == 2
    assert scope['pool_hash'] == review.pool_hash(run, requirement)
