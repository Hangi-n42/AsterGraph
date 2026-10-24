"""Requirements persist across runs; assessment history lives in immutable run records."""
import json
from copy import deepcopy
from .service import KnowledgeConflict, encode, utcnow


def put_requirement(service, request):
    value = request.model_dump()
    expected = value.pop('expected_revision')
    with service.lock, service.repository.connect() as db:
        row = db.execute('SELECT payload FROM requirements WHERE id=?', (value['id'],)).fetchone()
        previous = json.loads(row['payload']) if row else None
        if expected != (previous['revision'] if previous else 0):
            raise KnowledgeConflict('Requirement revision changed')
        for source_id in value['source_ids']:
            service.repository.get(db, 'sources', source_id)
        value.update(revision=expected + 1, updated_at=utcnow(), current_assessment=None,
                     status='unassessed', history=deepcopy(previous.get('history', [])) if previous else [],
                     change_history=deepcopy(previous.get('change_history', [])) if previous else [])
        db.execute('INSERT INTO requirement_versions VALUES(?,?,?)', (value['id'], value['revision'], encode(value)))
        db.execute('INSERT INTO requirements VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                   (value['id'], encode(value)))
    return value


def requirements(service, identifier=None):
    with service.repository.connect() as db:
        values = [json.loads(row['payload']) for row in db.execute(
            'SELECT payload FROM requirements' + (' WHERE id=?' if identifier else ''),
            (identifier,) if identifier else ())]
        return dict(items=values)


def save_assessment(service, run, requirement, assessment):
    """Retain previous judgments/repair receipts; never rewrite a requirement to fit output."""
    with service.lock, service.repository.connect() as db:
        current = service.repository.get(db, 'requirements', requirement['id'])
        if current['revision'] != requirement['revision']:
            raise KnowledgeConflict('Requirement changed during assessment')
        ref = dict(run_id=run['id'], assessment_id=assessment['id'], revision=requirement['revision'],
                   source_version_ids=run['input_version_ids'], claim_ids=assessment.get('claim_ids', []),
                   status=assessment['status'], recorded_at=utcnow())
        current['history'].append(ref)
        current.update(current_assessment=ref, status=assessment['status'])
        service.repository.save(db, 'requirements', current)


def link_stored_requirement(service, parent_id, request):
    """Prepare the existing stored-pool review input without submitting evaluation."""
    from . import autoschema, business_review, business_use, concept_work
    from .business_models import BusinessRunRequest
    from .business_rebuild import inherit_review_guard, validate_run
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        identifier = autoschema.identifier('stored_requirement_link', [parent_id, request.idempotency_key])
        existing = db.execute('SELECT payload FROM runs WHERE id=?', (identifier,)).fetchone()
        if existing:
            child = json.loads(existing['payload'])
            if child['requirement_link']['request'] != request.model_dump():
                raise KnowledgeConflict('같은 멱등 키에 다른 요구 연결 요청이 있습니다.')
            return dict(run_id=identifier, changeset_id=child['changeset_id'], status='partial', duplicate_request=True)
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('기존 실행 종료 후 저장 후보의 요구를 연결하세요.')
        parent = service.repository.get(db, 'runs', parent_id)
        reference = service.repository.get(db, 'runs', request.reference_run_id)
        if (concept_work.digest(parent) != request.expected_parent_fingerprint
                or concept_work.digest(reference) != request.expected_reference_fingerprint):
            raise KnowledgeConflict('검토한 저장 후보 또는 과거 참조 실행이 변경됐습니다.')
        if (parent.get('kind') != 'business' or not parent.get('stored_pool')
                or parent['status'] in {'queued', 'running', 'cancel_requested'}
                or parent['requirements'] or parent['assessments'] or reference.get('kind') != 'business'):
            raise ValueError('요구·평가가 없는 종료된 저장 후보 풀과 과거 업무 요구 실행이 필요합니다.')
        validate_run(service, db, parent)
        if business_use.restricted_sources(db, parent['input_version_ids']):
            raise KnowledgeConflict('사용이 제한된 원문이 있습니다.')
        current = service.repository.get(db, 'requirements', request.requirement_id)
        previous = next((r for r in reference['requirements'] if r['id'] == current['id']), None)
        if (current['revision'] != request.expected_requirement_revision or previous is None
                or business_review.preservation_requirement_version(current)
                   != business_review.preservation_requirement_version(previous)):
            raise KnowledgeConflict('원래 공개 요구의 내용 또는 revision이 다릅니다.')
        if not set(current['source_ids']) <= {b['source_id'] for b in parent['blocks']}:
            raise ValueError('공개 요구가 지정한 출처가 저장 원문 범위에 없습니다.')
        for field, kind in [('claims', 'claims'), ('blocks', 'source'), ('graph', 'graph')]:
            if parent['stored_pool'][kind + '_hash'] != autoschema.identifier(kind, parent[field]):
                raise KnowledgeConflict('저장 후보 풀의 원문·주장·그래프가 변경됐습니다.')
        requirement = {k: deepcopy(current[k]) for k in ('id', 'revision', 'question_ids', 'question',
            'criterion', 'target', 'situation', 'period', 'source_ids', 'required')}
        public_items = [i for i in reference.get('answer_items', []) if i['requirement_id'] == current['id']]
        if not public_items:
            raise ValueError('과거 실행의 원래 공개 질문 항목이 필요합니다.')
        selection = BusinessRunRequest(source_version_ids=parent['input_version_ids'],
            requirement_ids=[current['id']], answer_items=public_items)
        child = deepcopy(parent)
        child.update(id=identifier, parent_run_id=parent_id, status='partial', started_at=utcnow(), finished_at=utcnow(),
            requirements=[requirement], assessments=[], metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0),
            answer_items=business_use.bind_answer_items(selection, [requirement]))
        child['recipe']['options'].update(requirement_ids=[current['id']], answer_items=deepcopy(child['answer_items']))
        child['stored_pool'].update(parent_run_id=parent_id, assessment_inherited=False, approval_inherited=False)
        child['requirement_link'] = dict(request=request.model_dump(), actor=request.actor, reason=request.reason,
            parent_fingerprint=request.expected_parent_fingerprint, reference_run_id=reference['id'],
            reference_fingerprint=request.expected_reference_fingerprint,
            historical_assessment_ids=[a['id'] for a in reference['assessments'] if a['requirement_id'] == current['id']],
            assessment_status='unassessed', usage='review_draft_only', model_work_submitted=False)
        child.pop('changeset_id', None)
        inherit_review_guard(service, db, parent, child)
        child['changeset_id'] = business_use.publish(service, child, connection=db)['id']
        db.execute('INSERT INTO runs VALUES(?,?)', (identifier, encode(child)))
    return dict(run_id=identifier, changeset_id=child['changeset_id'], status='partial', duplicate_request=False)
