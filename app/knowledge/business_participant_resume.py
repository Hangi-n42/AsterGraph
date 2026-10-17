"""Resume only failed participant proposals from an unchanged stored product run."""
from copy import deepcopy
import json
from time import monotonic
from uuid import uuid4

from . import business_run, business_review, business_use
from .business_checkpoint import digest
from .service import KnowledgeConflict, encode, utcnow


def plan(service, parent, repair_id):
    if parent.get('kind') != 'business' or parent['status'] not in {'partial', 'review_ready'} or not parent.get('finished_at'):
        raise ValueError('완료된 업무 복구 실행이 필요합니다.')
    receipt = next((r for r in parent['repairs'] if r['id'] == repair_id), None)
    if receipt is None:
        raise ValueError('이 실행에 없는 복구 기록입니다.')
    requirement = next(r for r in parent['requirements'] if r['id'] == receipt['requirement_id'])
    original_assessment = next(a for a in parent['assessments'] if a['id'] == receipt['assessment_id'])
    latest = next(a for a in reversed(parent['assessments']) if a['requirement_id'] == requirement['id'])
    for assessment, claims in [(original_assessment, receipt['before']), (latest, parent['claims'])]:
        basis = dict(parent, claims=claims)
        if assessment['input_fingerprint'] != business_run.assessment_fingerprint(basis, requirement,
                assessment['source'], assessment.get('review_scope')) or business_review.blocked(assessment)[1]:
            raise ValueError('원복구·최신 누락 판정의 입력 버전 불일치')
    with service.repository.connect() as db:
        current = service.repository.get(db, 'requirements', requirement['id'])
        if (business_review.preservation_requirement_version(current) != business_review.preservation_requirement_version(requirement)
                or current['status'] == 'needs_review' or business_use.restricted_sources(db, parent['input_version_ids'])):
            raise KnowledgeConflict('현재 요구 또는 원문 사용 상태가 바뀌었습니다.')
    original = deepcopy(parent); original['claims'] = deepcopy(receipt['before'])
    matches = []
    for unit in parent['units']:
        if unit['stage'] != 'requirement_repair':
            continue
        try:
            output = business_run.repair(service, original, requirement, deepcopy(original_assessment), replay_unit=unit)
            if output == receipt['patches']:
                matches.append((unit, output))
        except ValueError:
            continue
    if len(matches) != 1:
        raise ValueError('동일 원요청·응답의 단일 복구 생성 기록을 확인할 수 없습니다.')
    unit, output = matches[0]
    changed = {c['meaning_key'] for c in receipt['changes']}
    recoverable = {a['meaning_key'] for a in latest['actions'] if a['action'] == 'recover' and not a['claim_ids']}
    patches = []
    for patch in output['patches']:
        if patch['meaning_key'] not in recoverable - changed or patch['target_id'] is not None or patch.get('role') != 'event_entity':
            continue
        try:
            business_run.recovered_statement_patch(patch, parent['blocks'])
        except ValueError:
            patches.append(patch)
    if not patches:
        raise ValueError('최신 누락 판정에 남은 참여자 주소 실패 제안이 없습니다.')
    return dict(parent_sha256=digest(parent), repair_id=repair_id, original_unit_id=unit['id'],
        original_request_sha256=digest({k:unit[k] for k in ('messages','schema','reference_map','request_configuration','executed_limits')}),
        original_response_sha256=digest(unit['response']), assessment_id=latest['id'],
        requirement_id=requirement['id'], proposals=dict(patches=patches, unresolved=[]),
        authority='stored_unverified_proposals; no_new_repair_generation; latest_missing_assessment')


def start(service, run_id, repair_id):
    with service.lock, service.repository.connect() as db:
        if service.closed:
            raise KnowledgeConflict('기존 실행 종료 후 실패 제안을 이어갑니다.')
        parent = service.repository.get(db, 'runs', run_id)
        for row in db.execute('SELECT payload FROM runs ORDER BY rowid DESC'):
            child = json.loads(row['payload'])
            previous = child.get('participant_resumption') or {}
            if (child.get('parent_run_id') == run_id and previous.get('repair_id') == repair_id
                    and previous.get('parent_sha256') == digest(parent)):
                return dict(run_id=child['id'], status=child['status'], participant_resumption=previous, reused=True)
        if service.repository.has_active_runs(db):
            raise KnowledgeConflict('기존 실행 종료 후 실패 제안을 이어갑니다.')
        continuation = plan(service, parent, repair_id)
        run = deepcopy(parent)
        run.update(id=uuid4().hex, parent_run_id=parent['id'], status='queued', started_at=None, finished_at=None,
            metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0), participant_resumption=continuation)
        for key in ('changeset_id', 'error'):
            run.pop(key, None)
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    service.executor.submit(execute, service, run['id'])
    return dict(run_id=run['id'], status='queued', participant_resumption=continuation)


def execute(service, run_id):
    started = monotonic()
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', run_id)
        parent = service.repository.get(db, 'runs', run['parent_run_id'])
    run.update(status='running', started_at=utcnow()); business_run.save(service, run)
    try:
        receipt = run['participant_resumption']
        if receipt != plan(service, parent, receipt['repair_id']) or any(run[k] != parent[k] for k in
                ('blocks', 'claims', 'requirements', 'recipe', 'model_identity', 'answer_items')):
            raise ValueError('실패 제안 재개 준비 이후 부모·원문·후보·설정 변경')
        options = run['recipe']['options']
        identity = business_run.ModelClient(run['recipe']['generation']).identities(run['recipe']['models'],
            dict(draft=options['context_tokens'], review=max(options['context_tokens'], options.get('representation_context_tokens') or options['context_tokens'])))
        if identity != run['model_identity']:
            raise ValueError('원제안 실행과 현재 모델 식별 불일치')
        requirement = next(r for r in run['requirements'] if r['id'] == receipt['requirement_id'])
        assessment = next(a for a in run['assessments'] if a['id'] == receipt['assessment_id'])
        if not business_run.cancelled(service, run) and business_run.repair(service, run, requirement, assessment, proposals=receipt['proposals']):
            business_review.review_candidate_pool(service, run, run['claims'])
            direct = business_review.current_candidate_reviews(run)
            added = {c['id'] for c in run['claims']} - {c['id'] for c in parent['claims']}
            supported = {cid for cid in added if cid in direct and direct[cid]['check']['claim_support'].get(cid) == 'supported'
                and not direct[cid]['check']['incorrect_claim_ids'] and not direct[cid]['check']['error_fields']}
            if supported and not business_run.cancelled(service, run):
                keys = [c['meaning_key'] for c in (assessment.get('representation') or {}).get('checks', [])]
                after = business_run.assess(service, run, requirement, source=assessment['source'],
                    phase='after_participant_resumption', focus_meaning_keys=keys or None)
                after = business_run.reassess_challenges(service, run, requirement, after, focus_meaning_keys=keys or None)
                run['repairs'][-1].update(recheck_assessment_id=after['id'], status='rechecked' if after['status'] == 'satisfied' else 'recheck_incomplete')
            business_run.refresh_repaired_graph(service, run)
            run['changeset_id'] = business_use.publish(service, run)['id']
        run['status'] = 'partial'
    except Exception as exc:
        run.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    finally:
        if business_run.cancelled(service, run):
            run['status'] = 'cancelled'
        run['finished_at'] = utcnow(); run['metrics']['elapsed_s'] = monotonic() - started
        business_run.save(service, run)
