"""Recheck stored, version-bound QA observations through the existing repair path."""
from copy import deepcopy
import json
from time import monotonic
from uuid import uuid4

from . import autoschema, business_review, business_run, business_use
from .service import KnowledgeConflict, encode, utcnow


def bind_gaps(parent, qa, basis, snapshot, task_ids):
    """Reuse task addresses, never infer an unnamed meaning from QA prose."""
    selection = qa.get('answer_meaning_selection') or {}
    units = [u for u in qa.get('units', []) if u.get('stage') == 'business_qa' and u.get('status') == 'succeeded'
             and not u.get('error') and (u.get('response') or {}).get('parsed') == selection.get('output')]
    if (parent.get('kind') != 'business' or qa.get('kind') != 'business_query' or qa.get('answer_status') != 'answered'
            or qa.get('answer_item_errors') or qa.get('query', {}).get('answer_mode') != 'reviewed_items'
            or len(units) != 1 or not selection.get('output') or len(task_ids) != len(set(task_ids))
            or qa.get('snapshot_id') != snapshot['id'] or qa['query'].get('snapshot_id') != snapshot['id']
            or snapshot.get('run_id') != basis['id']
            or qa.get('execution_boundary', {}).get('source_review_run_id') != basis['id']):
        raise ValueError('저장 QA 응답과 원래 검수 실행의 연결을 확인할 수 없습니다.')
    if (any(parent[k] != basis[k] for k in ('claims', 'blocks', 'input_version_ids', 'sources', 'answer_items'))
            or snapshot['blocks'] != basis['blocks'] or qa['answer_items'] != parent['answer_items']
            or qa['input_version_ids'] != parent['input_version_ids']):
        raise KnowledgeConflict('QA 이후 원문·후보·공개 항목 버전이 바뀌었습니다.')
    requirements = {r['id']: r for r in parent['requirements']}
    old_requirements = {r['id']: r for r in basis['requirements']}
    if (requirements.keys() != old_requirements.keys() or any(
            business_review.preservation_requirement_version(r) != business_review.preservation_requirement_version(old_requirements[rid])
            for rid, r in requirements.items())):
        raise KnowledgeConflict('QA 이후 공개 요구 버전이 바뀌었습니다.')
    tasks = {t['id']: t for r in requirements.values() for t in business_review.public_item_tasks(parent, r)}
    if not set(task_ids) <= tasks.keys():
        raise ValueError('현재 공개 작업 ID가 아닙니다.')
    latest = {a['requirement_id']: a for a in parent['assessments']}
    findings, deferred = [], []
    for tid in task_ids:
        task = tasks[tid]; rid = task['item']['requirement_id']; requirement = requirements[rid]
        work_item = dict(task['item'], id=tid, public_item_id=task['item']['id'], context=task['context'])
        rows = [r for r in selection['output']['items'] if r['item_id'] == tid]
        work = [r for r in qa.get('answer_work_records', []) if r['task_id'] == tid]
        if (qa['query']['question'] != requirement['question'] or qa.get('answer_work_items', []).count(work_item) != 1
                or len(rows) != 1 or len(work) != 1):
            raise KnowledgeConflict('QA 질문·대상·상황의 작업 연결이 일치하지 않습니다.')
        source = latest[rid]['source']; old_source = snapshot['assessments'][rid]['source']
        original_work = [r for r in old_source['public_scope']['items'] if r['task_id'] == tid]
        if (len(original_work) != 1 or work[0].get('original_unit_id') != old_source['public_scope']['unit_id']
                or any(work[0][k] != original_work[0][k] for k in ('meaning_keys', 'read_block_ids', 'candidate_ids'))):
            raise KnowledgeConflict('QA 작업의 저장된 원문 대응 기록이 일치하지 않습니다.')
        keys = work[0]['meaning_keys']
        meanings = [m for m in source['meanings'] if m['key'] in keys]
        old_meanings = [m for m in old_source['meanings'] if m['key'] in keys]
        if (meanings != old_meanings or not set(keys) <= set(source['public_scope']['review_meaning_keys'])
                or not set(work[0]['read_block_ids']) <= {b['id'] for b in parent['blocks']}):
            raise KnowledgeConflict('QA 작업의 원문 의미·주소 연결이 바뀌었습니다.')
        if len(set(keys)) != 1 or len(meanings) != 1 or not rows[0]['unconfirmed']:
            deferred.append(dict(task_id=tid, reason='gap_not_uniquely_bound_to_one_existing_meaning',
                                 original_output=deepcopy(rows[0]), original_work_record=deepcopy(work[0])))
            continue
        refs = business_run.exact_evidence(meanings[0]['evidence'], business_review.source_blocks(parent, requirement))
        if not refs or not {e['block_id'] for e in refs} <= set(work[0]['read_block_ids']):
            raise ValueError('기존 의미의 실제 원문 주소가 QA 작업 범위에 없습니다.')
        related = sorted({cid for selected in rows[0]['selected']
            for cid in selection['available'][selected['meaning_ref']]['claim_ids']})
        if not set(related) <= set(qa['provided_ids']) & {c['id'] for c in parent['claims']}:
            raise ValueError('QA가 실제 제공받은 후보 위치가 아닙니다.')
        for index, text in enumerate(rows[0]['unconfirmed']):
            findings.append(dict(id=autoschema.identifier('qa_gap', [qa['id'], tid, index]), origin='qa',
                kind='unverified_expression_gap', text=text, meaning_keys=list(keys), scope_meaning_keys=list(keys),
                claim_ids=[], fields=[], related_claim_ids=related, unit_id=units[0]['id'],
                provided_block_ids=sorted({e['block_id'] for e in refs}), evidence=refs,
                qa_run_id=qa['id'], snapshot_id=snapshot['id'], task=deepcopy(task), requirement_id=rid,
                requirement_version=business_review.preservation_requirement_version(requirement),
                meaning_version=autoschema.identifier('meaning', meanings[0]),
                source_fingerprint=business_review.preservation_source_version(parent, parent['input_version_ids']),
                candidate_pool_hash=business_review.pool_hash(parent),
                authority='unverified_QA_observation_not_source_truth_candidate_error_or_recovery_action'))
    return dict(qa_run_id=qa['id'], source_run_id=basis['id'], snapshot_id=snapshot['id'],
                task_ids=list(task_ids), findings=findings, deferred=deferred)


def start(service, run_id, request):
    with service.lock, service.repository.connect() as db:
        if service.closed or any(json.loads(r['payload'])['status'] in {'queued', 'running', 'cancel_requested'}
                                 for r in db.execute('SELECT payload FROM runs')):
            raise KnowledgeConflict('기존 실행 종료 후 재검수하세요.')
        parent = service.repository.get(db, 'runs', run_id)
        qa = service.repository.get(db, 'runs', request.qa_run_id)
        if qa.get('kind') != 'business_query' or not qa.get('snapshot_id'):
            raise ValueError('저장된 QA 실행 ID가 필요합니다.')
        snapshot = service.repository.get(db, 'snapshots', qa['snapshot_id'])
        basis = service.repository.get(db, 'runs', snapshot['run_id'])
        receipt = bind_gaps(parent, qa, basis, snapshot, request.task_ids)
        if business_use.restricted_sources(db, parent['input_version_ids']):
            raise KnowledgeConflict('사용이 제한된 원문이 있습니다.')
        current_requirements = {}
        for r in parent['requirements']:
            current = service.repository.get(db, 'requirements', r['id'])
            if (business_review.preservation_requirement_version(current) != business_review.preservation_requirement_version(r)
                    or current['status'] == 'needs_review'):
                raise KnowledgeConflict('현재 요구 검수 실행이 바뀌었습니다.')
            current_requirements[r['id']] = current
        # The original request can reuse its child; selecting that child is an explicit new recheck.
        for row in db.execute('SELECT payload FROM runs ORDER BY rowid DESC'):
            child = json.loads(row['payload'])
            if (child.get('parent_run_id') != parent['id'] or child['status'] not in {'succeeded', 'partial'}
                    or not child.get('finished_at') or child['recipe']['options']['repair'] != request.repair
                    or any(child[k] != parent[k] for k in ('blocks', 'input_version_ids', 'sources', 'answer_items'))
                    or any((child.get('answer_gap_recheck') or {}).get(k) != v for k, v in receipt.items())):
                continue
            latest = {a['requirement_id']: a for a in child['assessments']}
            if any((current.get('current_assessment') or {}).get('run_id') not in {parent['id'], child['id']}
                    or (current.get('current_assessment') or {}).get('assessment_id') != latest[r['id']]['id']
                    or (current.get('current_assessment') or {}).get('source_version_ids') != child['input_version_ids']
                    or latest[r['id']].get('input_fingerprint') != business_run.assessment_fingerprint(
                        child, r, latest[r['id']]['source'], latest[r['id']].get('review_scope'))
                    for r in child['requirements'] for current in [current_requirements[r['id']]]):
                continue
            if child.get('changeset_id'):
                change = service.repository.get(db, 'changesets', child['changeset_id'])
                if change['candidates'] != child['claims'] or change.get('invalidated_claim_ids'):
                    continue
            return dict(run_id=child['id'], status=child['status'], deferred=receipt['deferred'], reused=True)
        if any((r.get('current_assessment') or {}).get('run_id') != parent['id'] for r in current_requirements.values()):
            raise KnowledgeConflict('현재 요구 검수 실행이 바뀌었습니다.')
        run = deepcopy(parent)
        run.update(id=uuid4().hex, parent_run_id=parent['id'], status='queued' if receipt['findings'] else 'partial',
            started_at=None, finished_at=None if receipt['findings'] else utcnow(),
            metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0), answer_gap_recheck=receipt)
        run['recipe']['options']['repair'] = request.repair
        for key in ('changeset_id', 'error', 'continuation'):
            run.pop(key, None)
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    if receipt['findings']:
        service.executor.submit(execute, service, run['id'])
    return dict(run_id=run['id'], status=run['status'], deferred=receipt['deferred'])


def execute(service, run_id):
    started = monotonic()
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', run_id)
    run.update(status='running', started_at=utcnow()); business_run.save(service, run)
    try:
        options = run['recipe']['options']
        run['model_identity'] = business_run.ModelClient(run['recipe']['generation']).identities(
            run['recipe']['models'], dict(draft=options['context_tokens'],
                review=max(options['context_tokens'], options.get('representation_context_tokens') or options['context_tokens'])))
        receipt = run['answer_gap_recheck']; receipt['assessment_ids'] = []
        for requirement in run['requirements']:
            findings = [f for f in receipt['findings'] if f['requirement_id'] == requirement['id']]
            if not findings or business_run.cancelled(service, run):
                continue
            previous = next(a for a in reversed(run['assessments']) if a['requirement_id'] == requirement['id'])
            source = deepcopy(previous['source'])
            existing_ids = {f['id'] for f in source.setdefault('findings', [])}
            source['findings'].extend(deepcopy(f) for f in findings if f['id'] not in existing_ids)
            keys = sorted({k for f in findings for k in f['meaning_keys']})
            assessment = business_run.assess(service, run, requirement, source=source,
                phase='qa_gap_recheck', focus_meaning_keys=keys)
            receipt['assessment_ids'].append(assessment['id'])
            assessment = business_run.reassess_challenges(service, run, requirement, assessment, focus_meaning_keys=keys)
            if assessment['id'] != receipt['assessment_ids'][-1]:
                receipt['assessment_ids'].append(assessment['id'])
            if options['repair'] and not business_run.cancelled(service, run) and business_run.repair(service, run, requirement, assessment):
                business_review.review_candidate_pool(service, run, run['claims'])
                if business_run.cancelled(service, run):
                    break
                assessment = business_run.assess(service, run, requirement, source=assessment['source'],
                    phase='after_qa_gap_repair', focus_meaning_keys=keys)
                receipt['assessment_ids'].append(assessment['id'])
                assessment = business_run.reassess_challenges(service, run, requirement, assessment, focus_meaning_keys=keys)
                if assessment['id'] != receipt['assessment_ids'][-1]:
                    receipt['assessment_ids'].append(assessment['id'])
                run['repairs'][-1].update(recheck_assessment_id=assessment['id'], status='recheck_incomplete'
                    if assessment['status'] != 'satisfied' else 'rechecked')
        business_run.refresh_repaired_graph(service, run)
        if not business_run.cancelled(service, run):
            run['changeset_id'] = business_use.publish(service, run)['id']
            run['status'] = 'partial'
    except Exception as exc:
        run.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    finally:
        if business_run.cancelled(service, run):
            run['status'] = 'cancelled'
        run['finished_at'] = utcnow(); run['metrics']['elapsed_s'] = monotonic() - started
        with service.lock, service.repository.connect() as db:
            service.repository.save(db, 'runs', run)
