"""Continuation reuses bound preservation; invalid locations affect only their target."""
from copy import deepcopy

import pytest

from app.knowledge import business_edit, business_review as review, business_run, business_use
from app.knowledge.business_models import RequirementSynthesisCheck
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments
from app.tests.unit.test_knowledge_business_scope import block


def preserved_parent():
    parent = local_run()
    parent['claims'] = [dict(id=f'c{i}', raw=dict(Event=f'원문 {i}'), source_version_ids=[f'v{i}']) for i in range(3)]
    parent['blocks'] = [dict(block(f'b{i}', f'원문 {i}'), source_version_id=f'v{i}', source_id='s') for i in range(3)]
    source = dict(meanings=[dict(meaning(f'm{i}'), evidence=[dict(block_id=f'b{i}', quote=f'원문 {i}',
        source_version_id=f'v{i}')]) for i in range(3)])
    for m in source['meanings']:
        m['evidence'] = business_run.exact_evidence(m['evidence'], parent['blocks'])
    check = [dict(target_id=f'c{i}', status='preserved', before_normal_meanings=[f'm{i}'],
        after_locations=[f'c{i}'], reason='저장 정상 의미 보존') for i in range(3)]
    assessment = dict(id='a', requirement_id='r', revision=1, source=source,
        representation=dict(preservation_checks=check, meaning_challenges=[]))
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(parent, parent['requirements'][0], source)
    parent['assessments'] = [assessment]
    current = deepcopy(parent)
    current['assessments'] = []
    return parent, current, source


def test_latest_preservation_without_an_edit_receipt_reuses_all_three_targets():
    parent, current, source = preserved_parent()
    assert current['repairs'] == []
    current['preservation_reuses'] = business_edit.preservation_reuses(parent, current)
    assert {r['check']['target_id'] for r in current['preservation_reuses']} == {'c0', 'c1', 'c2'}
    assert len(review.valid_preservation_reuses(current, current['requirements'][0], source['meanings'])) == 3


@pytest.mark.parametrize('mode', ['resume_run_id', 'reassess_run_id'])
def test_product_start_saves_latest_preservation_without_mutating_parent(tmp_path, monkeypatch, mode):
    from app.knowledge.business_models import BusinessRunRequest
    from app.knowledge.service import KnowledgeService, encode
    parent, _, _ = preserved_parent()
    parent.update(id='parent', kind='business', status='partial', input_version_ids=['v0', 'v1', 'v2'],
        model_identity={}, graph=dict(nodes=[], edges=[]), concepts=[], stored_pool=dict(parent_run_id='origin'))
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)', (parent['id'], encode(parent)))
            db.execute('INSERT INTO sources VALUES(?,?,?,?)', ('s', 'fixture', None, encode(dict(id='s', title='자료'))))
            db.execute('INSERT INTO requirements VALUES(?,?)', ('r', encode(parent['requirements'][0])))
            for i in range(3):
                version = dict(id=f'v{i}', source_id='s', processing_status='parsed', latest_parse_run_id='p',
                    filename='source.txt', sha256=f'hash{i}', dates={})
                db.execute('INSERT INTO versions VALUES(?,?,?,?)', (version['id'], 's', version['sha256'], encode(version)))
        monkeypatch.setattr(service.executor, 'submit', lambda *a: None)
        monkeypatch.setattr(service, 'parse_blocks', lambda db, pid, vid: deepcopy(
            [b for b in parent['blocks'] if b['source_version_id'] == vid]))
        monkeypatch.setattr(business_run.ModelClient, 'identities', lambda *a: {})
        request = BusinessRunRequest(source_version_ids=parent['input_version_ids'], requirement_ids=['r'],
            **{mode: 'parent'})
        child = service.run(business_run.start(service, request)['run_id'])
        assert {r['check']['target_id'] for r in child['preservation_reuses']} == {'c0', 'c1', 'c2'}
        assert child['claims'] == parent['claims'] and child['assessments'] == []
        with service.repository.connect() as db:
            assert service.repository.get(db, 'runs', 'parent') == parent
        assert business_use.snapshots(service)['items'] == []
    finally:
        service.shutdown()


@pytest.mark.parametrize('change', ['claim', 'meaning', 'source', 'superseded', 'legacy', 'contradiction'])
def test_only_related_preservation_is_invalidated(change):
    parent, current, source = preserved_parent()
    if change == 'claim':
        current['claims'][0]['raw']['Event'] = '수정된 주장'
    elif change == 'meaning':
        source = deepcopy(source)
        source['meanings'][0]['conditions'] = ['새 조건']
    elif change == 'source':
        current['blocks'][0]['text'] = '다른 원문'
    elif change == 'superseded':
        current['claims'][0]['superseded_by'] = ['replacement']
    elif change == 'legacy':
        parent['assessments'][0]['representation']['preservation_checks'][0]['after_locations'] = ['c0.raw.Event']
    else:
        current['candidate_challenges'] = [dict(claim_ids=['c0'], fields=['raw.Event'])]
    current['preservation_reuses'] = business_edit.preservation_reuses(parent, current)
    valid = review.valid_preservation_reuses(current, current['requirements'][0], source['meanings'])
    assert {r['check']['target_id'] for r in valid} == {'c1', 'c2'}


@pytest.mark.parametrize('field,value', [('revision', 2), ('question', '바뀐 공개 질문')])
def test_requirement_change_cannot_reuse_older_preservation(field, value):
    parent, current, _ = preserved_parent()
    current['requirements'][0][field] = value
    assert not business_edit.preservation_reuses(parent, current)


def test_stale_parent_fingerprint_cannot_create_reuse():
    parent, current, _ = preserved_parent()
    parent['assessments'][0]['input_fingerprint'] = 'stale'
    assert not business_edit.preservation_reuses(parent, current)


def test_new_preservation_schema_selects_only_provided_active_ids():
    run = local_run()
    claims = [dict(id='active'), dict(id='superseded', superseded_by=['active'])]
    context = dict(claims=claims, repair_context=[dict(changes=[])])
    schema = business_run.json_request(run, 'requirement_representation', '보존 대조', context,
        RequirementSynthesisCheck)['schema']
    located = next(v for v in schema['$defs'].values() if 'after_locations' in v.get('properties', {}))
    assert located['properties']['after_locations']['items']['const'] == 'active'


def test_invalid_preservation_does_not_block_an_unrelated_eligible_claim():
    run = dict(claims=[dict(id='fixed'), dict(id='normal')], repairs=[], requirements=[dict(id='r')], assessments=[])
    source = dict(meanings=[dict(key='m', source_status='supported', availability='provided', evidence=['source'])])
    assessment = dict(requirement_id='r', source=source, errors=[], representation=dict(
        checks=[dict(meaning_key='m', status='represented', claim_ids=['fixed', 'normal'])], source_challenges=[],
        preservation_checks=[dict(target_id='fixed', status='preserved', before_normal_meanings=['m'],
            after_locations=['fixed.raw.Event'])]))
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source)
    run['assessments'] = [assessment]
    eligible, blocked = business_use.eligibility(run)
    assert eligible == {'normal'} and blocked['fixed'] == ['normal_meaning_preservation_conflict']


def test_fresh_assessment_marks_only_invalid_preservation_unknown(monkeypatch):
    from app.knowledge import business_store
    run = local_run()
    run.update(id='run', metrics={}, source_corrections=[])
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[])
    result = judgments(['m'], ids=[run['claims'][0]['id']])
    result['preservation_checks'] = [dict(target_id=c['id'], status='preserved', before_normal_meanings=['m'],
        after_locations=[c['id']] if i else [c['id']+'.raw.Event'], reason='보존') for i,c in enumerate(run['claims'])]
    monkeypatch.setattr(review, 'represent', lambda *a, **k: (deepcopy(result), dict(batches=[], failures=[])))
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_store, 'save_assessment', lambda *a: None)
    assessment = business_run.assess(None, run, run['requirements'][0], source=source)
    assert [p['status'] for p in assessment['representation']['preservation_checks']] == ['unknown', 'preserved']
    assert assessment['representation']['preservation_checks'][0]['after_locations'] == []
    assert assessment['status'] != 'satisfied'


def test_new_challenge_after_context_selection_keeps_preservation_incomplete(monkeypatch):
    from app.knowledge import business_store
    parent, run, source = preserved_parent()
    run.update(id='run', metrics={}, source_corrections=[], prior_repairs=[dict(id='repair', requirement_id='r', targets=[],
        preserve_meanings=[], changes=[dict(before=c, after=c, meaning_key=f'm{i}')
            for i,c in enumerate(run['claims'])])])
    source = deepcopy(source)
    source.update(examined_block_ids=[b['id'] for b in run['blocks']], completeness='complete', gaps=[], conjunctions=[])
    run['preservation_reuses'] = business_edit.preservation_reuses(parent, run)
    result = judgments(['m0', 'm1', 'm2'], ids=['c0', 'c1', 'c2'])
    result['meaning_challenges'] = [dict(meaning_key='m0', claim_ids=['c0'], fields=['raw.Event'],
        evidence=source['meanings'][0]['evidence'], reason='새 원문 모순')]
    def represent(*args, **kwargs):
        assert args[4] == []
        return deepcopy(result), dict(batches=[], failures=[])
    monkeypatch.setattr(review, 'represent', represent)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_store, 'save_assessment', lambda *a: None)
    assessment = business_run.assess(None, run, run['requirements'][0], source=source)
    states = {p['target_id']:p['status'] for p in assessment['representation']['preservation_checks']}
    assert states == {'c0':'unknown', 'c1':'preserved', 'c2':'preserved'}
    assert not assessment['preservation_complete'] and assessment['status'] != 'satisfied'
    assert [v['before']['id'] for r in review.repair_context(run,run['requirements'][0],source['meanings'])
        for v in r['changes']] == ['c0']
