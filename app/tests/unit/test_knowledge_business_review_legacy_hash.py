from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_review as review, business_run
from app.tests.unit.test_knowledge_business_preservation_fields import actual_change


@pytest.fixture
def legacy_receipt():
    run, context, _ = actual_change()
    claim = run['claims'][0]
    claim['interpretation'] = dict(contract=autoschema.SCOPE_CONTRACT, meanings=[dict(subject='현장 답사 희망자')],
        address_restorations=[dict(kind='literal_event_endpoint', evidence=deepcopy(claim['evidence']))])
    run.update(repairs=context, model_identity={'review': {'digest': 'fixed'}}, candidate_reviews=[])
    run['recipe'].update(generation={}, models={'review': 'local-review'})
    context = review.candidate_repair_context(run, {claim['id']})
    instruction, payload, schema = review.candidate_request(run, [claim], context)
    old_value = business_run.compact_claim(claim)
    old_value['interpretation']['address_restorations'] = deepcopy(claim['interpretation']['address_restorations'])
    payload['preservation_views'][0]['after_versions'][claim['id']] = autoschema.identifier('claim', old_value)
    packet = business_run.json_request(run, 'candidate_source_review', instruction, payload, schema)
    options = run['recipe']['options']
    limits = dict(max_tokens=options['review_tokens'], context_tokens=options['context_tokens'], think=options['think'])
    config = dict(model='local-review', generation={}, identity=run['model_identity'], temperature=0, timeout=options['timeout'])
    output = dict(checks=[], preservation_checks=[])
    run['units'] = [dict(packet, id='unit', status='succeeded', error=None, restored_evidence_output=deepcopy(output),
                         request_configuration=config, requested_limits=deepcopy(limits), executed_limits=deepcopy(limits))]
    run['candidate_reviews'] = [dict(id='receipt', unit_id='unit', review_contract=run['recipe']['review_contract'],
        claim_ids=[claim['id']], errors=[], output=output, checks=[dict(claim_ids=[claim['id']],
        claim_support={claim['id']: 'supported'}, incorrect_claim_ids=[], error_fields={})])]
    return run


def test_legacy_hash_reuses_only_the_complete_reconstructed_request(legacy_receipt):
    before = deepcopy(legacy_receipt)
    assert legacy_receipt['claims'][0]['id'] in review.current_candidate_reviews(legacy_receipt)
    assert legacy_receipt == before


@pytest.mark.parametrize('fault', ['meaning', 'condition', 'ledger', 'source', 'address', 'model', 'prompt', 'schema', 'limits', 'output', 'hash'])
def test_legacy_compatibility_never_ignores_other_changes(legacy_receipt, fault):
    run = legacy_receipt; claim = run['claims'][0]; unit = run['units'][0]
    if fault == 'meaning': claim['interpretation']['meanings'][0]['subject'] = '다른 대상'
    elif fault == 'condition': claim['conditions'].append('다른 조건')
    elif fault == 'ledger': claim['interpretation']['address_restorations'][0]['kind'] = 'changed'
    elif fault == 'source': run['blocks'][0]['text'] += '\n다른 문맥'
    elif fault == 'address': run['blocks'][0]['parse_run_id'] = 'other-parse'
    elif fault == 'model': unit['request_configuration']['model'] = 'other-model'
    elif fault == 'prompt': unit['messages'][0]['content'] += 'changed'
    elif fault == 'schema': unit['schema']['title'] = 'OtherContract'
    elif fault == 'limits': unit['executed_limits']['max_tokens'] += 1
    elif fault == 'output': unit['restored_evidence_output']['checks'] = ['changed']
    else:
        import json
        value = json.loads(unit['messages'][-1]['content'])
        key = next(iter(value['preservation_views'][0]['after_versions']))
        value['preservation_views'][0]['after_versions'][key] = 'arbitrary-version'
        unit['messages'][-1]['content'] = json.dumps(value, ensure_ascii=False)
    assert not review.current_candidate_reviews(run)
