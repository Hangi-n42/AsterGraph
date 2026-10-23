"""Prepare a small own-source review, then execute exactly one review and stop."""
from copy import deepcopy
import json
from time import monotonic

from . import autoschema, business_review, business_run, business_use, concept_work, interpretation_edit
from .business_models import ScopedCandidateReviewRequest
from .business_rebuild import inherit_review_guard, validate_run
from .service import KnowledgeConflict, encode, utcnow


def basis(service, db, parent, request):
    if service.repository.get(db, 'runs', parent['id']) != parent:
        raise KnowledgeConflict('현재 부모 실행이 변경됐습니다.')
    if (parent.get('kind') != 'business' or parent['status'] not in {'partial', 'review_ready', 'succeeded'}
            or not parent.get('stored_pool') or parent['assessments'] or parent.get('candidate_review_scope')
            or parent.get('requirement_link', {}).get('usage') != 'review_draft_only'):
        raise ValueError('평가·승인이 없는 종료된 저장 검토초안이 필요합니다.')
    if concept_work.digest(parent) != request.expected_parent_fingerprint:
        raise KnowledgeConflict('검토한 부모 실행이 변경됐습니다.')
    validate_run(service, db, parent)
    if business_use.restricted_sources(db, parent['input_version_ids']):
        raise KnowledgeConflict('사용이 제한된 원문이 있습니다.')
    requirement = next((r for r in parent['requirements'] if r['id'] == request.requirement_id), None)
    current = service.repository.get(db, 'requirements', request.requirement_id)
    if (requirement is None or current['revision'] != request.expected_requirement_revision
            or requirement['revision'] != current['revision'] or current['status'] == 'needs_review'
            or business_review.preservation_requirement_version(requirement)
               != business_review.preservation_requirement_version(current)):
        raise KnowledgeConflict('현재 공개 요구 또는 revision이 변경됐습니다.')
    for vid in parent['input_version_ids']:
        version = service.repository.get(db, 'versions', vid)
        if version['sha256'] != parent['sources'][vid]['sha256'] or version['processing_status'] != 'parsed':
            raise KnowledgeConflict('원문 버전 또는 파싱 상태가 변경됐습니다.')
    for field, kind in [('claims', 'claims'), ('blocks', 'source'), ('graph', 'graph')]:
        if parent['stored_pool'][kind + '_hash'] != autoschema.identifier(kind, parent[field]):
            raise KnowledgeConflict('저장 후보·원문·그래프가 변경됐습니다.')
    pool = {c['id']: c for c in business_review.candidate_pool(parent, requirement)}
    if len(set(request.claim_ids)) != len(request.claim_ids) or not set(request.claim_ids) <= pool.keys():
        raise ValueError('중복되거나 공개 요구 출처 범위 밖인 후보입니다.')
    claims = [pool[cid] for cid in request.claim_ids]
    block_ids = set()
    for claim in claims:
        scope = claim.get('interpretation') or {}
        if (claim.get('extraction_error') or claim.get('superseded_by')
                or scope.get('contract') != autoschema.SCOPE_CONTRACT or not scope.get('meanings')
                or scope.get('errors') and not interpretation_edit.participant_errors_only(scope, claim, parent['blocks'])):
            raise ValueError('후보의 원문 주소 또는 추출 상태를 확인하세요.')
        groups = [claim.get('evidence', []), scope.get('evidence', [])]
        for meaning in scope['meanings']:
            groups.append(meaning.get('evidence', []))
            groups.extend(p.get('evidence', []) for p in meaning.get('participants', []))
        for refs in groups:
            if not refs:
                raise ValueError('후보·의미·참여자의 실제 원문 근거가 필요합니다.')
            exact = business_run.exact_evidence(refs, parent['blocks'])
            if any(e['source_version_id'] not in claim['source_version_ids'] for e in exact):
                raise ValueError('다른 후보 출처를 자기 원문으로 사용할 수 없습니다.')
            block_ids.update(e['block_id'] for e in exact)
    scope = dict(input_contract=business_review.SCOPED_CANDIDATE_INPUT, claim_ids=request.claim_ids,
        source_block_ids=[b['id'] for b in parent['blocks'] if b['id'] in block_ids])
    view = dict(parent, candidate_review_scope=scope)
    instruction, context, schema = business_review.candidate_request(view, claims,
        business_review.candidate_repair_context(view, set(request.claim_ids)))
    packet = business_run.json_request(view, 'candidate_source_review', instruction, context, schema)
    scope.update(packet=packet, input_fingerprint=concept_work.digest(dict(packet=packet, request=request.model_dump(),
        recipe=parent['recipe'], model_identity=parent['model_identity'])))
    return scope


def prepare(service, parent_id, request):
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        identifier = autoschema.identifier('scoped_candidate_review', [parent_id, request.idempotency_key])
        existing = db.execute('SELECT payload FROM runs WHERE id=?', (identifier,)).fetchone()
        if existing:
            child = json.loads(existing['payload'])
            if child['candidate_review_scope']['request'] != request.model_dump():
                raise KnowledgeConflict('같은 멱등 키에 다른 제한 검수 요청이 있습니다.')
            return dict(run_id=identifier, status=child['status'], duplicate_request=True)
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('기존 실행 종료 후 제한 검수를 준비하세요.')
        parent = service.repository.get(db, 'runs', parent_id)
        scope = basis(service, db, parent, request)
        child = deepcopy(parent)
        child.update(id=identifier, parent_run_id=parent_id, status='partial', started_at=None, finished_at=utcnow(),
            metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0),
            candidate_review_scope=dict(scope, request=request.model_dump(), phase='prepared', executed_unit_ids=[],
                authority='own_source_review_only; no_assessment_or_approval'))
        child.pop('changeset_id', None)
        inherit_review_guard(service, db, parent, child)
        db.execute('INSERT INTO runs VALUES(?,?)', (identifier, encode(child)))
    return dict(run_id=identifier, status='partial', duplicate_request=False,
                input_fingerprint=scope['input_fingerprint'])


def start(service, run_id, request):
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        run = service.repository.get(db, 'runs', run_id)
        scope = run.get('candidate_review_scope') or {}
        if scope.get('input_fingerprint') != request.expected_input_fingerprint:
            raise KnowledgeConflict('준비한 제한 검수 입력이 다릅니다.')
        if scope['phase'] != 'prepared':
            return dict(run_id=run_id, status=run['status'], duplicate_request=True)
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('기존 실행 종료 후 제한 검수를 실행하세요.')
        parent = service.repository.get(db, 'runs', run['parent_run_id'])
        frozen = basis(service, db, parent, ScopedCandidateReviewRequest(**scope['request']))
        if any(scope.get(k) != v for k, v in frozen.items()):
            raise KnowledgeConflict('준비 이후 제한 검수 입력이 변경됐습니다.')
        run.update(status='queued', started_at=None, finished_at=None)
        scope['phase'] = 'queued'
        service.repository.save(db, 'runs', run)
    try:
        service.executor.submit(execute, service, run_id)
    except Exception as exc:
        with service.lock, service.repository.connect() as db:
            run = service.repository.get(db, 'runs', run_id)
            run.update(status='failed', error=str(exc), finished_at=utcnow())
            run['candidate_review_scope']['phase'] = 'failed'
            service.repository.save(db, 'runs', run)
        raise
    return dict(run_id=run_id, status='queued', duplicate_request=False)


def execute(service, run_id):
    started = monotonic()
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', run_id)
        parent = service.repository.get(db, 'runs', run['parent_run_id'])
    scope = run['candidate_review_scope']
    unit_offset = len(run['units'])
    run.update(status='running', started_at=utcnow())
    business_run.save(service, run)
    try:
        if business_run.cancelled(service, run):
            return
        with service.repository.connect() as db:
            frozen = basis(service, db, parent, ScopedCandidateReviewRequest(**scope['request']))
        if (any(scope.get(k) != v for k, v in frozen.items())
                or any(run[k] != parent[k] for k in ('claims', 'blocks', 'sources', 'graph', 'concepts',
                    'recipe', 'model_identity', 'requirements', 'answer_items'))):
            raise KnowledgeConflict('준비 이후 부모·후보·원문·요구·설정이 변경됐습니다.')
        options = run['recipe']['options']
        identity = business_run.ModelClient(run['recipe']['generation']).identities(run['recipe']['models'],
            dict(draft=options['context_tokens'], review=max(options['context_tokens'],
                options.get('representation_context_tokens') or options['context_tokens'])))
        if identity != run['model_identity']:
            raise KnowledgeConflict('고정한 모델 식별자가 다릅니다.')
        claims = [next(c for c in run['claims'] if c['id'] == cid) for cid in scope['claim_ids']]
        repair_context = business_review.candidate_repair_context(run, set(scope['claim_ids']))
        instruction, context, schema = business_review.candidate_request(run, claims, repair_context)
        if business_run.json_request(run, 'candidate_source_review', instruction, context, schema) != scope['packet']:
            raise KnowledgeConflict('실제 단일 검수 요청이 준비한 입력과 다릅니다.')
        packet = scope['packet']
        scope['input_budget'] = business_run.request_budget(run, packet['messages'], packet['schema'],
            packet['max_tokens'] or options['review_tokens'])
        if (not scope['input_budget'].get('prompt_exact')
                or scope['input_budget']['estimate_tokens'] > options['context_tokens']):
            raise ValueError('정확한 입력 계수 또는 문맥 용량을 확인할 수 없습니다.')
        if business_run.cancelled(service, run):
            return
        before = len(run['units'])
        receipt = business_review.review_candidates(service, run, claims, repair_context=repair_context)
        units = run['units'][before:]
        scope['executed_unit_ids'] = [u['id'] for u in units]
        if len(units) != 1 or units[0]['stage'] != 'candidate_source_review' or receipt['errors']:
            raise ValueError('한 단계 제한 검수가 완료되지 않았습니다.')
        scope.update(phase='completed', receipt_id=receipt['id'])
        run['status'] = 'partial'
    except Exception as exc:
        scope['phase'] = 'failed'
        run.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        for unit in run['units'][unit_offset:]:
            if unit['status'] == 'running':
                unit.update(status='failed', error=run['error'], finished_at=utcnow())
        scope['executed_unit_ids'] = [u['id'] for u in run['units'][unit_offset:]]
    finally:
        run['finished_at'] = utcnow()
        run['metrics']['elapsed_s'] = monotonic() - started
        with service.lock, service.repository.connect() as db:
            if service.repository.get(db, 'runs', run_id)['status'] == 'cancel_requested':
                run['status'] = scope['phase'] = 'cancelled'
            service.repository.save(db, 'runs', run)
