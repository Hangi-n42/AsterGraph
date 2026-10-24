"""Whole Markdown documents, with verified stored producers rather than block independence."""
from copy import deepcopy
from collections import Counter

from . import autoschema, business_run, concept_work
from .source_meanings import remap

POLICY = 'whole_source_v1'
STAGES = (*autoschema.ROLES, 'direct_definitions',
          'capacity_repair_event_entity', 'capacity_dependency_event_relation')


def verify_claims(original, replayed):
    if len(original) != len(replayed):
        raise ValueError('생산 응답의 후보 수가 다릅니다.')
    differences = {}
    for stored, current in zip(original, replayed):
        left, right = deepcopy(stored), deepcopy(current)
        a = left.get('interpretation', {}).get('errors', [])
        b = right.get('interpretation', {}).get('errors', [])
        if a != b:
            # autoschema's missing endpoint diagnostics iterate a set; no semantic field is reordered.
            if (not isinstance(a, list) or not isinstance(b, list)
                    or not all(isinstance(x, str) for x in [*a, *b]) or Counter(a) != Counter(b)):
                raise ValueError('생산 후보의 오류 상태가 다릅니다.')
            left['interpretation']['errors'] = right['interpretation']['errors'] = []
            differences[stored['id']] = dict(original_errors=a, replay_errors=b,
                original_sha256=concept_work.digest(stored), replay_sha256=concept_work.digest(current),
                reason='autoschema missing endpoint set iteration; diagnostic reasons only')
        if left != right:
            raise ValueError('원시 응답으로 검증한 후보 원형이 저장 결과와 다릅니다.')
    return differences


def inventory(service, db, parent, seen=None):
    seen = set() if seen is None else seen
    if parent['id'] in seen:
        raise ValueError('원문 생산 실행 계보가 순환합니다.')
    seen.add(parent['id'])
    donors = {}
    def load(identifier):
        run = service.repository.get(db, 'runs', identifier)
        donors[identifier] = concept_work.digest(run)
        return run
    cursor = load(parent['id'])
    while not any(u['stage'] in STAGES for u in cursor['units']):
        if not cursor.get('parent_run_id') or cursor['parent_run_id'] in seen:
            raise ValueError('저장 후보의 실제 추출 생산자를 확인할 수 없습니다.')
        previous = load(cursor['parent_run_id'])
        if any(cursor[k] != previous[k] for k in ('claims', 'blocks', 'chunks', 'sources')):
            raise ValueError('재검수 부모의 후보·원문 원형이 생산 실행과 다릅니다.')
        seen.add(previous['id'])
        cursor = previous
    replay = deepcopy(cursor)
    replay['claims'] = []
    proofs, failures = {}, []
    receipt = cursor.get('source_rebuild') or {}
    if receipt:
        if receipt.get('whole_source_policy') != POLICY:
            raise ValueError('다른 부분 재구축 정책의 생산 계보는 별도 검증이 필요합니다.')
        prior = load(receipt['parent_run_id'])
        _, old, old_donors, old_failures = inventory(service, db, prior, seen)
        donors.update(old_donors)
        failures.extend(old_failures)
        by_id = {c['id']: c for c in prior['claims']}
        current = {c['id']: c for c in cursor['claims']}
        for cid in receipt['preserved_claim_ids']:
            if current.get(cid) != by_id.get(cid) or cid not in old:
                raise ValueError('이전 문서의 보존 후보 원형을 확인할 수 없습니다.')
            replay['claims'].append(deepcopy(by_id[cid]))
            proofs[cid] = deepcopy(old[cid])
    chunks = {c['id']: c for c in cursor['chunks']}
    for stored in cursor['units']:
        unit = deepcopy(stored)
        stage = unit['stage']
        if stage not in STAGES:
            continue
        if unit['status'] not in {'succeeded', 'partial'} or not unit.get('response') or unit['response'].get('failure_kind'):
            failures.append(dict(run_id=cursor['id'], unit_id=unit['id'], stage=stage,
                status=unit['status'], error=unit.get('error')))
            continue
        response = unit['response']
        if (response.get('done') is not True or response.get('done_reason') not in {'stop', 'eos', 'end_turn'}
                or unit.get('requested_limits') != unit.get('executed_limits')):
            raise ValueError('저장 추출의 정상 종료·실행 한도를 확인할 수 없습니다.')
        config = unit.get('request_configuration') or {}
        model = cursor['recipe']['models']['review' if stage == 'direct_definitions' else 'draft']
        if (config.get('model') != model or config.get('identity') != cursor['model_identity']
                or config.get('generation') != cursor['recipe']['generation'] or config.get('temperature') != 0):
            raise ValueError('생산 실행의 실제 모델·설정이 다릅니다.')
        if unit['status'] == 'partial':
            failures.append(dict(run_id=cursor['id'], unit_id=unit['id'], stage=stage,
                status=unit['status'], error=unit.get('error')))
        chunk = chunks[unit['source_chunk_id']]
        if unit.get('reused_from'):
            origin = unit['reused_from']
            source = load(origin['run_id'])
            matches = [u for u in source['units'] if u['id'] == origin['unit_id']]
            if len(matches) != 1 or any(unit.get(k) != matches[0].get(k)
                    for k in ('messages', 'schema', 'reference_map', 'response')):
                raise ValueError('정확 재사용의 원래 응답·입력이 다릅니다.')
        offset = len(replay['claims'])
        if stage == 'direct_definitions':
            expected = business_run.json_request(replay, stage, business_run.DEFINITION_INSTRUCTION,
                dict(blocks=autoschema.source_packet(chunk['blocks'])), business_run.Definitions)
            if any(unit.get(k) != expected[k] for k in ('messages', 'schema', 'reference_map')):
                raise ValueError('저장 명시 정의의 실제 입력이 다릅니다.')
            reverse = {v:k for k,v in (unit.get('reference_map') or {}).items()}
            parsed = unit.get('restored_evidence_output') or business_run.remap_expression_keys(remap(response['parsed'], reverse), reverse)
            business_run.store_definitions(replay, chunk, parsed)
        else:
            role = stage.replace('capacity_repair_', '').replace('capacity_dependency_', '')
            view = cursor.get('capacity_repair_views', {}).get(unit.get('repair_view_id'), chunk)
            if (unit['messages'] != business_run.extraction_messages(replay, view, role)
                    or unit['schema'] != autoschema.extraction_schema(role)
                    or unit['reference_map'] != view['source_reference_map']):
                raise ValueError('저장 추출의 실제 원문·선행 후보 입력이 다릅니다.')
            origin = unit.get('capacity_repair_origin')
            if origin:
                source = load(origin['run_id'])
                failed = next((u for u in source['units'] if u['id'] == origin['unit_id']), {})
                if (failed.get('status') != 'failed' or failed.get('error') != 'truncated'
                        or failed.get('messages') != unit['messages'] or failed.get('schema') != unit['schema']
                        or view['blocks'] != chunk['blocks']):
                    raise ValueError('용량 복구의 실패 원형·전체 문서 입력이 다릅니다.')
            origin = unit.get('dependency_refresh_origin')
            if origin:
                source = load(origin['run_id'])
                previous = next((u for u in source['units'] if u['id'] == origin['unit_id']), {})
                upstream = {u['id'] for u in cursor['units'] if u['stage'] == 'capacity_repair_event_entity'
                            and u['status'] == 'succeeded' and 'materialized_claim_ids' in u}
                if (previous.get('status') != 'succeeded' or previous.get('messages') == unit['messages']
                        or not origin.get('repaired_upstream_unit_ids')
                        or not set(origin['repaired_upstream_unit_ids']) <= upstream):
                    raise ValueError('선행 복구 뒤 관계 입력 변경의 계보가 다릅니다.')
            business_run.store_extraction(replay, view, role, response, unit)
        added = replay['claims'][offset:]
        if 'materialized_claim_ids' in stored and stored['materialized_claim_ids'] != [c['id'] for c in added]:
            raise ValueError('복구 응답과 실제 저장 후보의 연결이 다릅니다.')
        for claim in added:
            proofs[claim['id']] = dict(claim_id=claim['id'], chunk_id=chunk['id'], donor_run_id=cursor['id'],
                stored_unit_id=stored['id'], stored_stage=stage, stored_source_chunk_id=stored['source_chunk_id'],
                stored_messages_sha256=concept_work.digest(stored['messages']),
                stored_schema_sha256=concept_work.digest(stored.get('schema')),
                stored_reference_map=deepcopy(stored.get('reference_map')),
                stored_claim_sha256=concept_work.digest(claim), source_views=deepcopy(chunk['blocks']),
                scope='verified_frozen_producer; no_new_generation_or_approval')
    differences = verify_claims(cursor['claims'], replay['claims'])
    if parent['claims'] != cursor['claims']:
        raise ValueError('원시 응답으로 검증한 후보 원형이 저장 결과와 다릅니다.')
    for claim in cursor['claims']:
        proof = proofs[claim['id']]
        proof['replay_claim_sha256'] = proof['stored_claim_sha256']
        proof['stored_claim_sha256'] = concept_work.digest(claim)
        if claim['id'] in differences:
            proof['diagnostic_order_only'] = differences[claim['id']]
    return cursor, proofs, donors, failures


def unit_plan(parent, before, after, old, new):
    if not new:
        raise ValueError('빈 문서 전체 삭제는 이 재구축 정책에서 지원하지 않습니다.')
    if parent['recipe']['options'].get('source_unit_policy', 'whole') != 'whole':
        raise ValueError('문서 전체 정책으로 읽은 부모가 필요합니다.')
    if any(b.get('locator', {}).get('format') != 'md' for b in [*old, *new]):
        raise ValueError('문서 전체 재구축은 Markdown에서만 지원합니다.')
    for claim in parent['claims']:
        reads = set(claim['source_version_ids']) | {e['source_version_id'] for e in claim.get('evidence', [])}
        if before in reads and reads != {before}:
            raise ValueError('변경 문서 밖의 교차 근거는 추가 재구축 범위가 필요합니다.')
    return [dict(unit_key=POLICY, action='rebuild_source', before_block_ids=[b['id'] for b in old],
        after_block_ids=[b['id'] for b in new], reason='whole_document_changed; no_block_independence_assumed')]
