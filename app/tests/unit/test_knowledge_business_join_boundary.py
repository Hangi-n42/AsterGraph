"""Synthesis record errors must not rewrite source facts or certify a join."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.knowledge import business_review as review, business_run
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments
from app.tests.unit.test_knowledge_business_separated_review import synthesis


@pytest.mark.parametrize('fault', ['echo', 'null', 'changed', 'unknown', 'duplicate', 'check'])
def test_outside_scope_synthesis_stays_rejected_without_source_reassessment(monkeypatch, fault):
    compact = judgments(['m', 'other'], ids=['claim'])
    before = deepcopy(compact)
    response = synthesis()
    response['dependencies'] = [dict(meaning_key='m', premise_keys=[])]
    if fault == 'null':
        response['dependencies'][0]['premise_keys'] = None
    elif fault == 'changed':
        response['dependencies'][0]['premise_keys'] = ['other']
    elif fault == 'unknown':
        response['dependencies'][0]['meaning_key'] = 'undeclared'
    elif fault == 'duplicate':
        response['dependencies'] *= 2
    elif fault == 'check':
        response.update(dependencies=[], checks=[deepcopy(compact['checks'][0])])
    result, joined, _, errors = review.retain_synthesis(compact, response, set(), set(), [])
    assert errors and not joined and not result['satisfied'] and not result['conjunctions_satisfied']
    assert compact == before and all(result[k] == before[k] for k in ['checks', 'dependencies'])
    assert all(c['source_reassessment_needed'] is False for c in result['meaning_challenges'])
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **kw: pytest.fail('structural error rejudged source'))
    run = dict(recipe=dict(review_contract=review.SOURCE_APPLICATION_CONTRACT))
    assert review.reassess_source(None, run, {}, dict(source=dict(meanings=[meaning('m'), meaning('other')])),
                                 result['meaning_challenges']) is None


def test_evidenced_model_source_challenge_keeps_its_reassessment_path(monkeypatch):
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    original = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='unknown',
                    gaps=[], conjunctions=[], meaning_gaps=[], meaning_conjunctions=[], findings=[])
    challenge = dict(meaning_key='m', claim_ids=[], fields=['conditions'], evidence=meaning('m')['evidence'],
                     reason='원문의 적용 조건을 다시 확인')
    response = synthesis(); response['meaning_challenges'] = [challenge]
    result, _, _, _ = review.retain_synthesis(judgments(['m']), response, set(), set(), run['blocks'])
    assert result['meaning_challenges'] == [challenge]
    calls = []
    def stop_at_dispatch(*args, **kwargs):
        calls.append(args[2])
        run['units'].append(dict(id='source-dispatch'))
        return None
    monkeypatch.setattr(business_run, 'json_call', stop_at_dispatch)
    assert review.reassess_source(None, run, run['requirements'][0], dict(source=original),
                                 result['meaning_challenges']) is None
    assert calls == ['source_reassessment'] and original['meanings'] == [meaning('m')]


@pytest.mark.parametrize('premises', [[], None])
def test_only_empty_join_scope_limits_revision_lists_without_forcing_verdict(monkeypatch, premises):
    run = local_run(); run['recipe']['review_contract'] = review.CONTRACT
    source = dict(meanings=[meaning('m', required_for_requirement=True)], review_contract=review.CONTRACT,
        examined_block_ids=['body'], completeness='unknown', gaps=[], conjunctions=[], findings=[], source_batches=[])
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    seen = []
    def answer(service, current, stage, instruction, context, schema):
        current['units'].append(dict(id=str(len(seen)))); seen.append(context['mode'])
        if context['mode'] != 'requirement_join':
            result = judgments(['m'], ids=[run['claims'][0]['id']])
            result['dependencies'][0]['premise_keys'] = premises
            return result
        spec = schema.model_json_schema()['properties']
        assert context['review_meaning_keys'] == ([] if premises == [] else ['m'])
        for field in ['checks', 'dependencies']:
            assert (spec[field].get('maxItems') == 0) == (premises == [])
        result = synthesis(); result.update(satisfied=False, conjunctions_satisfied=False)
        assert schema.model_validate(result).satisfied is False
        echo = deepcopy(result); echo['dependencies'] = [dict(meaning_key='m', premise_keys=[])]
        if premises == []:
            with pytest.raises(ValidationError):
                schema.model_validate(echo)
            changed = deepcopy(result); changed['checks'] = [dict(meaning_key='m')]
            with pytest.raises(ValidationError):
                schema.model_validate(changed)
        else:
            schema.model_validate(echo)
        return result
    monkeypatch.setattr(business_run, 'json_call', answer)
    result, _ = review.represent(None, run, run['requirements'][0], source, [])
    assert seen == ['meaning_batch', 'requirement_join'] and result['satisfied'] is False
