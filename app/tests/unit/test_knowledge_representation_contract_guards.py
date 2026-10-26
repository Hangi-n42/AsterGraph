from copy import deepcopy

import pytest

from app.knowledge import business_review as review, business_run, business_use
from app.tests.unit.test_knowledge_business_local_review import judgments, local_run, meaning
from app.tests.unit.test_knowledge_business_separated_review import synthesis


def source_case():
    return dict(meanings=[meaning('answer', required_for_requirement=True),
                          meaning('other', required_for_requirement=False)],
                review_contract=review.CONTRACT, processing_scope=dict(requested_meaning_keys=['answer', 'other']))


def contradictory_check(cid='bad'):
    return dict(meaning_key='answer', status='represented', claim_ids=[cid], incorrect_claim_ids=[],
                reason='전체 표현이라고 했지만 누락도 명시', represented_content='기관은 접수한다.',
                missing_content='추가 서류를 확인한다.', missing_evidence=meaning('answer')['evidence'])


def test_local_source_dependency_rewrite_is_quarantined_without_changing_input():
    source = source_case(); output = judgments(['answer', 'other'])
    output['source_checks'][1]['required_for_requirement'] = False
    output['dependencies'][0]['premise_keys'] = ['other']
    before = deepcopy(output)
    compact = review.summarize_local(source['meanings'], [output], source_owned=True)
    assert output == before
    assert compact['dependencies'][0]['premise_keys'] == []
    assert compact['meaning_challenges'][0]['source_reassessment_needed'] is False
    assessment = dict(source=source, representation=compact, errors=[], issues=[])
    assert review.requirement_states(source, compact)['answer'] is True
    assert review.blocked(assessment)[0] == {'answer'}


@pytest.mark.parametrize('premises', [[], ['other'], None])
def test_g_cannot_rewrite_known_source_dependency_but_null_is_uncertainty(premises):
    compact = judgments(['answer', 'other'])
    compact['dependencies'][0]['premise_keys'] = ['other']
    response = synthesis(); response['dependencies'] = [dict(meaning_key='answer', premise_keys=premises)]
    result, joined, _, errors = review.retain_synthesis(compact, response, {'answer'}, set(), [])
    assert joined == (premises in (['other'], None))
    assert bool(errors) == (premises == [])
    assert result['dependencies'][0]['premise_keys'] == (premises if joined else ['other'])


def test_old_saved_dependency_cannot_expand_question_or_poison_independent_fact():
    source = source_case(); output = judgments(['answer', 'other'])
    output['source_checks'][1]['required_for_requirement'] = False
    output['dependencies'][0]['premise_keys'] = ['other']
    assessment = dict(source=source, representation=output, errors=[], issues=[])
    assert review.requirement_states(source, output) == {'answer': True, 'other': False}
    assert review.dependency_rows(assessment)[0]['premise_keys'] == []
    assert review.affected(assessment, {'other'}) == {'other'}


def test_represented_remainder_survives_summary_as_unknown_with_raw_label():
    output = judgments(['answer']); output['checks'] = [contradictory_check()]
    before = deepcopy(output)
    row = review.summarize_local([meaning('answer')], [output])['checks'][0]
    assert output == before and row['status'] == 'unknown'
    assert row['missing_content'] == before['checks'][0]['missing_content']
    assert row['missing_evidence'] == before['checks'][0]['missing_evidence']
    assert row['contract_errors'][0]['check'] == before['checks'][0]
    again = judgments(['answer']); again['checks'] = [row]
    repeated = review.summarize_local([meaning('answer')], [again])['checks'][0]
    assert repeated['missing_content'] == row['missing_content'] and repeated['missing_evidence'] == row['missing_evidence']


@pytest.mark.parametrize('cid', ['bad', 'good'])
def test_bad_local_contribution_does_not_discard_independent_complete_candidate(cid):
    bad = judgments(['answer']); bad['checks'] = [contradictory_check(cid)]
    good = judgments(['answer'], ids=['good'])
    row = review.summarize_local([meaning('answer')], [bad, good])['checks'][0]
    assert row['status'] == 'represented' and row['claim_ids'] == ['good']
    assert row['contract_errors'][0]['check']['claim_ids'] == [cid]


def test_same_candidate_keeps_valid_contribution_when_g_adds_contradictory_sibling(monkeypatch):
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    cid = run['claims'][0]['id']; source = dict(meanings=[meaning('answer')], review_contract=review.CONTRACT)
    compact = judgments(['answer'], ids=[cid]); compact['checks'][0]['claim_support'] = {cid:'supported'}
    response = synthesis(); response['checks'] = [dict(contradictory_check(cid),
        revision_basis='prior_misreading', evidence=meaning('answer')['evidence'])]
    result, joined, _, errors = review.retain_synthesis(compact, response, {'answer'}, {cid}, run['blocks'])
    assert not joined and errors and result['checks'][0]['status'] == 'represented'
    assessment = dict(requirement_id='r', source=source, representation=result, errors=[], issues=[])
    assert review.blocked(assessment) == (set(), [])
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(run, run['requirements'][0], source)
    run['assessments'] = [assessment]
    eligible, blocked = business_use.eligibility(run)
    assert cid in eligible and cid not in blocked


def test_grounded_source_partial_reassessment_can_update_a_real_dependency(monkeypatch):
    from app.tests.unit.test_knowledge_business_reassessment_scope import setup_source, partial_call
    run, req, source = setup_source(); before = deepcopy(source)
    proposed = deepcopy(source); proposed['meanings'][0]['premise_keys'] = ['normal']
    partial_call(monkeypatch, run, proposed, [])
    challenge = dict(meaning_key='m', fields=['premise_keys'], evidence=source['meanings'][0]['evidence'], reason='합성 원문 전제 재판정')
    updated = review.reassess_source(None, run, req, dict(source=source), [challenge])
    assert source == before and updated['meanings'][0]['premise_keys'] == ['normal']
    assert updated['meanings'][1] == before['meanings'][1]
    output = judgments(['m','normal']); output['dependencies'][0]['premise_keys'] = ['normal']
    compact = review.summarize_local(updated['meanings'], [output], source_owned=True)
    assert compact['dependencies'][0]['premise_keys'] == ['normal'] and not compact['meaning_challenges']
    assert review.affected(dict(source=updated, representation=compact), {'normal'}) == {'m','normal'}


@pytest.mark.parametrize('premises', ['omitted', None, [], ['other']])
def test_unknown_source_premise_stays_unknown_until_source_reassessment(premises):
    source = source_case(); source['meanings'][0]['premise_keys'] = None
    output = judgments(['answer','other']); output['dependencies'] = [] if premises == 'omitted' else [dict(meaning_key='answer',premise_keys=premises)]
    compact = review.summarize_local(source['meanings'], [output], source_owned=True)
    assert compact['dependencies'][0]['premise_keys'] is None
    assert bool(compact['meaning_challenges']) == (premises not in ('omitted', None))
    assert review.requirement_states(source,compact)['answer'] is True
    assert 'answer' in review.blocked(dict(source=source,representation=compact,errors=[],issues=[]))[0]


@pytest.mark.parametrize('missing_content,missing_evidence', [('누락',[]),('',meaning('answer')['evidence'])])
def test_either_remainder_field_blocks_old_saved_completion_and_repair(missing_content,missing_evidence):
    from app.tests.unit.test_knowledge_requirement_remainder_contract import completion_case
    a = completion_case(); a['representation']['checks'][0].update(
        missing_content=missing_content, missing_evidence=missing_evidence)
    assert business_run.requirement_completion(a)['status']=='partial'
    run=local_run();run['recipe']['review_contract']=review.CONTRACT
    a['actions']=[dict(meaning_key='answer',action='recover',claim_ids=[],reason='미검증 보강')]
    assert business_run.repair(None,run,run['requirements'][0],a) is False


def test_g_represented_remainder_retains_original_compact_and_contract_evidence():
    compact = judgments(['answer'], status='missing')
    response = synthesis(); response['checks'] = [dict(contradictory_check('normal'),
        revision_basis='prior_misreading', evidence=meaning('answer')['evidence'])]
    result, joined, _, errors = review.retain_synthesis(compact, response, {'answer'}, {'normal'}, local_run()['blocks'])
    assert not joined and any(e['reason'] == 'represented_with_explicit_remainder' for e in errors)
    assert result['checks'][0]['status'] == 'unknown'
    assert result['checks'][0]['contract_errors'][0]['check'] == response['checks'][0]
