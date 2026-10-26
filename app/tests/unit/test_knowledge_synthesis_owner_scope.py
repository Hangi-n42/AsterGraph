"""Generated synthesis owner limits preserve full context and consumer boundaries."""
from copy import deepcopy
from typing import get_args

import pytest
from pydantic import ValidationError

from app.knowledge import autoschema, business_review as review, business_run
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments
from app.tests.unit.test_knowledge_business_separated_review import synthesis


def join_contract(monkeypatch, *, empty=False, challenged=False, preservation=False, public=False):
    run = local_run()
    run['recipe']['review_contract'] = review.SOURCE_APPLICATION_CONTRACT
    run['input_version_ids'] = ['v']
    req = dict(run['requirements'][0], question='전체 질문', criterion='전체 의미 보존', target='이용자', situation='안내', period='')
    run['requirements'] = [req]
    source = dict(meanings=[meaning(k, required_for_requirement=True) for k in ('m', 'other', 'normal')],
        examined_block_ids=['body'], completeness='unknown', gaps=[], conjunctions=[], findings=[], source_batches=[],
        review_contract=review.SOURCE_APPLICATION_CONTRACT)
    if public:
        source['public_scope'] = dict(review_meaning_keys=['m', 'other', 'normal'], tasks=[], items=[], errors=[], followup=[],
            public_items=[dict(id='item')], input_contract=review.PUBLIC_SOURCE_INPUT_CONTRACT)
    if challenged:
        source['findings'] = [dict(id='qa', origin='qa', kind='unverified_expression_gap', text='미검증 관찰',
            meaning_keys=['m'], scope_meaning_keys=['m'], claim_ids=[], fields=[], unit_id='qa', provided_block_ids=['body'],
            requirement_version=review.preservation_requirement_version(req), candidate_pool_hash=review.pool_hash(run),
            source_fingerprint=review.preservation_source_version(run, ['v']),
            meaning_version=autoschema.identifier('meaning', source['meanings'][0]))]
    context = []
    if preservation:
        before, after = deepcopy(run['claims'])
        context = [dict(id='repair', targets=[dict(meaning_key='m', reason='기존 의미 보존')], preserve_meanings=[],
            changes=[dict(before=before, after=after, replacements=[], meaning_key='m')])]
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    monkeypatch.setattr(business_run, 'request_budget', lambda *a, **k: dict(estimate_tokens=0))
    monkeypatch.setattr(review, 'current_candidate_reviews', lambda r: {c['id']: dict(receipt_id='fixture', unit_id='fixture',
        check=dict(claim_support={c['id']: 'supported'}, incorrect_claim_ids=[], error_fields={})) for c in r['claims']})
    captured = {}
    class Inspected(Exception):
        pass
    def response(service, current, stage, instruction, packet, output_type):
        current['units'].append(dict(id='fixture' + str(len(current['units']))))
        if packet['mode'] == 'requirement_join':
            captured.update(run=current, packet=deepcopy(packet), output_type=output_type,
                request=business_run.json_request(current, stage, instruction, packet, output_type))
            raise Inspected
        out = judgments([m['key'] for m in packet['source']['meanings']], ids=[run['claims'][0]['id']])
        for row in out['checks']:
            if row['meaning_key'] == 'm' and not empty:
                row['status'] = 'partial'
        return dict(out, candidate_challenges=[])
    monkeypatch.setattr(business_run, 'json_call', response)
    with pytest.raises(Inspected):
        review.represent(None, run, req, source, context)
    return captured


def row_schema(schema, field):
    return schema['$defs'][schema['properties'][field]['items']['$ref'].split('/')[-1]]


@pytest.mark.parametrize('field', ['checks', 'dependencies'])
def test_actual_join_request_bounds_owners(monkeypatch, field):
    captured = join_contract(monkeypatch)
    request, packet = captured['request'], captured['packet']
    assert packet['review_meaning_keys'] == ['m']
    assert {m['key'] for m in packet['source']['meanings']} == {'m', 'other', 'normal'}
    assert {r['meaning_key'] for r in packet['local_judgments']['dependencies']} == {'m', 'other', 'normal'}
    assert row_schema(request['schema'], field)['properties']['meaning_key'].get('const') == 'm'
    assert '같은 값이어도 범위 밖 행은 반환하지 않는다' in request['messages'][0]['content']


def test_empty_scope_keeps_existing_zero_row_schema(monkeypatch):
    captured = join_contract(monkeypatch, empty=True)
    assert captured['packet']['review_meaning_keys'] == []
    for field in ('checks', 'dependencies'):
        assert captured['request']['schema']['properties'][field]['maxItems'] == 0


def test_owner_override_preserves_required_rows_remainders_and_other_dynamic_fields(monkeypatch):
    captured = join_contract(monkeypatch, challenged=True, preservation=True, public=True)
    schema = captured['request']['schema']
    assert schema['properties']['checks']['minItems'] == 1
    assert {'represented_content', 'missing_content', 'missing_evidence'} <= set(row_schema(schema, 'checks')['required'])
    assert schema['properties']['preservation_checks']['minItems'] == schema['properties']['preservation_checks']['maxItems'] == 1
    assert schema['properties']['public_item_checks']['minItems'] == schema['properties']['public_item_checks']['maxItems'] == 1
    assert set(row_schema(schema, 'public_item_checks')['properties']['meaning_keys']['items']['enum']) == {'m', 'other', 'normal'}
    assert captured['packet']['required_final_check_keys'] == ['m']
    with pytest.raises(ValidationError) as exc:
        captured['output_type'].model_validate(dict(synthesis(), candidate_challenges=[], public_item_checks=[]))
    assert any(e['loc'] == ('checks',) and e['type'] == 'too_short' for e in exc.value.errors())
    row_type = get_args(captured['output_type'].model_fields['checks'].annotation)[0]
    with pytest.raises(ValidationError) as exc:
        row_type.model_validate(dict(meaning_key='m', status='partial', claim_ids=[], reason='기존 부분',
            revision_basis='combined_expression', evidence=[]))
    assert {'represented_content', 'missing_content', 'missing_evidence'} <= {e['loc'][0] for e in exc.value.errors()}


@pytest.mark.parametrize('premises', [['other'], None, [], 'omitted'])
def test_dependency_endpoints_and_omitted_null_empty_remain_distinct(monkeypatch, premises):
    captured = join_contract(monkeypatch)
    compact = judgments(['m', 'other', 'normal'])
    compact['dependencies'][0]['premise_keys'] = ['normal']
    response = dict(synthesis(), candidate_challenges=[])
    response['checks'] = [dict(meaning_key='m',status='unknown',claim_ids=[],reason='최종 확인 불가',
        represented_content='',missing_content='',missing_evidence=[],revision_basis='new_evidence',
        evidence=[dict(block_id='body',quote=captured['run']['blocks'][0]['text'])])]
    if premises != 'omitted':
        response['dependencies'] = [dict(meaning_key='m', premise_keys=premises)]
    captured['output_type'].model_validate(response)
    response['checks'][0]['incorrect_claim_ids']=[]
    result, joined, _, errors = review.retain_synthesis(compact, response, {'m'}, set(), captured['run']['blocks'])
    accepted = premises is None or premises == 'omitted'
    assert joined == accepted and bool(errors) != accepted
    assert result['dependencies'][0]['premise_keys'] == (None if premises is None else ['normal'])
    assert result['dependencies'][1:] == compact['dependencies'][1:]


@pytest.mark.parametrize('fault', ['owner', 'endpoint', 'duplicate'])
def test_consumer_still_rejects_invalid_dependency_and_preserves_old_value(monkeypatch, fault):
    captured = join_contract(monkeypatch)
    compact = judgments(['m', 'other', 'normal'])
    response = dict(synthesis(), candidate_challenges=[])
    response['dependencies'] = [dict(meaning_key='outside' if fault == 'owner' else 'm',
        premise_keys=['outside'] if fault == 'endpoint' else [])]
    if fault == 'duplicate':
        response['dependencies'] *= 2
    if fault == 'owner':
        with pytest.raises(ValidationError):
            captured['output_type'].model_validate(response)
    result, joined, _, errors = review.retain_synthesis(compact, response, {'m'}, set(), captured['run']['blocks'])
    assert not joined and errors and result['dependencies'] == compact['dependencies']
