"""Server-created continuation of a completed source prefix; no public skip list."""
from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

from . import autoschema


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def completed_prefix(parent):
    from . import business_run
    if (parent.get('kind') != 'business' or parent['status'] not in {'failed', 'cancelled', 'partial'}
            or parent['requirements'] or parent['concepts'] or parent.get('stored_pool')
            or parent['recipe']['options']['repair']):
        raise ValueError('질문 없는 미완료 원문 추출 실행에서만 완료 기록을 이어갑니다.')
    stages = (*autoschema.ROLES, 'direct_definitions')
    complete = [u for u in parent['units'] if u['stage'] in stages and u.get('source_chunk_id')
                and u['status'] in {'succeeded', 'failed', 'partial'}
                and u.get('error') != 'cancelled' and (u.get('response') or {}).get('failure_kind') != 'cancelled']
    expected = [(c['id'], s) for c in parent['chunks'] for s in stages]
    keys = [(u['source_chunk_id'], u['stage']) for u in complete]
    if not complete or keys != expected[:len(keys)] or len(set(keys)) != len(keys):
        raise ValueError('완료 원문 역할은 저장된 실행 순서의 연속 구간이어야 합니다.')
    chunks = {c['id']: c for c in parent['chunks']}
    for unit in complete:
        chunk = chunks[unit['source_chunk_id']]
        if unit['stage'] in autoschema.ROLES:
            messages = business_run.extraction_messages(parent, chunk, unit['stage'])
            schema = autoschema.extraction_schema(unit['stage']); refs = chunk['source_reference_map']
        else:
            request = business_run.json_request(parent, 'direct_definitions',
                '원문의 명시적인 정의만 한국어로 추출한다. 없는 정의/상위유형은 만들지 않는다. term/definition과 정확 인용. '
                'context_only는 참고용이며 새 정의는 대상 구간에서만 만든다. 정의가 없으면 빈 배열.',
                dict(blocks=autoschema.source_packet(chunk['blocks'])), business_run.Definitions)
            messages, schema, refs = request['messages'], request['schema'], request['reference_map']
        cfg = unit['request_configuration']; limits = unit['executed_limits']
        model = parent['recipe']['models']['review' if unit['stage'] == 'direct_definitions' else 'draft']
        if (unit['messages'] != messages or unit['schema'] != schema or unit['reference_map'] != refs
                or cfg['model'] != model or cfg['identity'] != parent['model_identity']
                or cfg['generation'] != parent['recipe']['generation'] or cfg['temperature'] != 0
                or cfg['timeout'] != parent['recipe']['options']['timeout']
                or unit['requested_limits'] != limits
                or limits['context_tokens'] != parent['recipe']['options']['context_tokens']
                or limits['think'] != parent['recipe']['options']['think']
                or unit['status'] == 'succeeded' and (not unit.get('response') or unit['response'].get('failure_kind'))):
            raise ValueError('완료 역할의 원문·요청·설정·실행 결과가 저장 기록과 다릅니다.')
    return complete, keys


def prepare(service, parent_run_id):
    """Prepare only; the caller uses the existing product execute after reviewing the receipt."""
    from .service import KnowledgeConflict, encode
    with service.lock, service.repository.connect() as db:
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('다른 실행이 종료된 뒤 완료 기록을 이어갑니다.')
        parent = service.repository.get(db, 'runs', parent_run_id)
        complete, keys = completed_prefix(parent)
        run = deepcopy(parent)
        run.update(id=uuid4().hex, status='queued', units=deepcopy(complete), started_at=None, finished_at=None,
            parent_run_id=parent['id'], metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0),
            reuse_pool_parent_run_id=parent.get('reuse_pool_parent_run_id') or parent.get('parent_run_id'))
        run.pop('error', None)
        run['source_checkpoint'] = dict(parent_run_id=parent['id'], parent_sha256=digest(parent),
            completed_unit_ids=[u['id'] for u in complete], completed_source_roles=len(keys),
            preserved_status_counts={s:sum(u['status'] == s for u in complete) for s in ('succeeded', 'failed', 'partial')},
            preserved_claims_sha256=digest(parent['claims']),
            unfinished_units=deepcopy([u for u in parent['units'] if u not in complete]),
            prior_metrics=deepcopy(parent['metrics']), public_skip_list=False)
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    return dict(run_id=run['id'], status='queued', source_checkpoint=deepcopy(run['source_checkpoint']))


def validate(service, run):
    """Derive skip keys from the authoritative parent, never from caller-supplied roles."""
    checkpoint = run.get('source_checkpoint')
    if not checkpoint:
        return set()
    with service.repository.connect() as db:
        parent = service.repository.get(db, 'runs', checkpoint['parent_run_id'])
    if checkpoint['parent_sha256'] != digest(parent):
        raise ValueError('새 실행의 부모 저장 기록이 변경됐습니다.')
    complete, keys = completed_prefix(parent)
    if (checkpoint['completed_unit_ids'] != [u['id'] for u in complete]
            or run['units'] != complete or run['parent_run_id'] != parent['id']
            or run.get('reuse_pool_parent_run_id') != (parent.get('reuse_pool_parent_run_id') or parent.get('parent_run_id'))
            or any(run.get(k) != parent.get(k) for k in ('blocks', 'chunks', 'sources', 'recipe', 'model_identity',
                'claims', 'extraction_rejections', 'reusable_units', 'parent_recipe', 'parent_model_identity'))):
        raise ValueError('새 실행의 원문·설정·완료 기록·후보가 부모 기록과 다릅니다.')
    return set(keys)
