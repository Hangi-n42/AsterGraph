"""Reconceptualize selected entities from a fixed stored extraction pool."""
from copy import deepcopy
from time import monotonic
from uuid import uuid4

from . import autoschema, business_run, concept_work
from .service import KnowledgeConflict, encode, utcnow


def plan(service, request):
    with service.repository.connect() as db:
        parent = service.repository.get(db, 'runs', request.parent_run_id)
    if parent.get('kind') != 'business' or parent['status'] in {'queued', 'running', 'cancel_requested'}:
        raise ValueError('종료된 업무 지식 실행의 추출 풀을 선택하세요.')
    targets = {t['id']: t for t in autoschema.concept_targets(parent['graph'])
               if request.include_events_and_relations or t['kind'] == 'entity'}
    if not set(request.target_ids) <= targets.keys():
        raise ValueError('현재 그래프와 선택한 종류의 대상만 선택하세요.')
    return parent, prepare(parent, [targets[i] for i in dict.fromkeys(request.target_ids)], request.neighbor_mode,
        service=service, source_context=request.concept_source_context)


def source_preservation(service, parent_run_id, *, request=None):
    """Retain old source knowledge; never call it a current-runtime cache hit."""
    from . import business_rebuild, business_rebuild_source
    with service.lock, service.repository.connect() as db:
        if request:
            db.execute('BEGIN IMMEDIATE')
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('기존 실행 종료 후 저장 개념을 연결하세요.')
        parent = service.repository.get(db, 'runs', parent_run_id)
        receipt = parent.get('source_rebuild') or {}
        if parent.get('kind') != 'business' or receipt.get('whole_source_policy') != 'whole_source_v1':
            raise ValueError('종료된 문서 전체 재구축 실행이 필요합니다.')
        business_rebuild.validate_run(service, db, parent)
        business_rebuild_source.inventory(service, db, parent)
        if autoschema.graph(parent['claims'], parent['blocks']) != parent['graph']:
            raise KnowledgeConflict('추출 후보와 저장 그래프가 다릅니다.')
        if parent['recipe']['options'].get('concept_source_context', 'whole') != 'whole':
            raise ValueError('이 보존 경로는 전체 원문 문맥 정책만 지원합니다.')
        fingerprint = concept_work.digest(parent)
        if request and request.expected_parent_fingerprint != fingerprint:
            raise KnowledgeConflict('검토한 추출 기준이 변경됐습니다.')
        plan_record = service.repository.get(db, 'runs', receipt['plan_id'])
        donor = service.repository.get(db, 'runs', plan_record['construction_run_id'])
        units = {u['id']: u for u in donor['units']}
        chunks = business_run.source_chunks(parent)
        retained, pending, proofs, bindings, works = [], [], [], [], {}
        for target in autoschema.concept_targets(parent['graph']):
            messages, selection = autoschema.concept_messages(target, parent['graph'], chunks,
                parent['recipe']['options']['neighbor_mode'])
            item = dict(target=target, messages=messages, selection=selection)
            item['work_input'] = concept_work.prepare(parent, item)
            matches = [c for c in donor['concepts'] if c['target'] == target]
            if len(matches) != 1:
                partitioned = any(c['target'].get('partition_of') == target['id'] for c in donor['concepts'])
                pending.append(dict(target=target, reason='stored_partition_requires_prepare' if partitioned else 'new_or_changed_target'))
                continue
            concept = matches[0]
            unit = units.get(concept.get('request_id'), {})
            original = unit.get('concept_work_input') or {}
            expected = deepcopy(item['work_input']); expected.pop('runtime')
            old_input = deepcopy(original); old_input.pop('runtime', None)
            connected = [b for b in donor.get('concept_bindings', []) if b['concept_id'] == concept['id']]
            work = donor.get('concept_work', {}).get(concept.get('work_id'), {})
            valid = (concept.get('status') == 'unreviewed' and not concept.get('discarded')
                and not concept.get('superseded_by') and concept.get('relation') == 'has_concept'
                and concept.get('approved_is_a') is False and concept_work.complete(unit)
                and not concept_work.unknown_fields(original)
                and unit.get('requested_limits') == unit.get('executed_limits') == original.get('requested_limits')
                and not selection.get('relation_input_partition')
                and unit.get('stage') == 'concept_' + target['kind'] and expected == old_input
                and unit.get('messages') == messages and unit.get('schema') is None
                and unit.get('reference_map') == selection['source_reference_map']
                and concept['selection'] == selection and concept_work.same_input(unit, concept, item)
                and concept['concepts'] == autoschema.concepts(unit['response']['text'])
                and len(connected) == 1 and work.get('status') == 'complete'
                and work.get('input') == original and work.get('fingerprint') == concept_work.digest(original)
                and unit.get('concept_work_id') == concept.get('work_id'))
            if valid:
                binding = connected[0]
                valid = (binding.get('target') == target and binding.get('target_id') == target['id']
                    and binding.get('request_id') == unit['id'] and binding.get('work_id') == concept['work_id']
                    and binding.get('source_reference_map') == selection['source_reference_map']
                    and binding.get('status') == 'unreviewed' and binding.get('relation') == 'has_concept'
                    and binding.get('approved_is_a') is False)
            if not valid:
                pending.append(dict(target=target, reason='stored_producer_or_actual_input_not_verified'))
                continue
            concept_work.validate_request(original, unit)
            retained.append(deepcopy(concept)); bindings.append(deepcopy(binding))
            works[work['id']] = deepcopy(work)
            proofs.append(dict(target_id=target['id'], concept_id=concept['id'], donor_run_id=donor['id'],
                unit_id=unit['id'], work_id=work['id'], original_unit_sha256=concept_work.digest(unit),
                original_concept_sha256=concept_work.digest(concept), original_binding_sha256=concept_work.digest(binding),
                source_input_fingerprint=concept_work.source_input_fingerprint(item),
                original_runtime=deepcopy(original['runtime']), new_work_connected=False,
                reason='execution_contract_unknown_or_changed; existing_result_retained'))
        result = dict(parent_run_id=parent['id'], parent_fingerprint=fingerprint, donor_run_id=donor['id'],
            retained_targets=len(retained), pending_targets=len(pending), retained_target_ids=[p['target_id'] for p in proofs],
            pending=pending, current_runtime_exact_cache=False, actual_human_approval=False,
            supported_source_context='whole; verified existing unpartitioned results only',
            pending_plan='use existing prepare with current policy/budget; target count is not a call cap')
        if not request:
            return result
        if service.closed:
            raise KnowledgeConflict('서비스 종료로 저장 개념 연결을 중단했습니다.')
        identifier = autoschema.identifier('source_concept_retention', [fingerprint, concept_work.digest(donor), proofs])
        existing = db.execute('SELECT payload FROM runs WHERE id=?', (identifier,)).fetchone()
        if existing:
            return dict(result, run_id=identifier, status='partial', duplicate_request=True)
        run = deepcopy(parent)
        run.pop('source_rebuild', None); run.pop('changeset_id', None)
        run.update(id=identifier, status='partial', parent_run_id=parent['id'], concepts=retained,
            units=[deepcopy(units[p['unit_id']]) for p in proofs], concept_work=works, concept_bindings=bindings,
            concept_link_checks=deepcopy(proofs), started_at=utcnow(), finished_at=utcnow(),
            metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0),
            source_concept_retention=dict(result, proofs=proofs, approval_inherited=False),
            stored_pool=dict(parent_run_id=parent['id'], claims_hash=autoschema.identifier('claims', parent['claims']),
                source_hash=autoschema.identifier('source', parent['blocks']), graph_hash=autoschema.identifier('graph', parent['graph']),
                construction_recipe=deepcopy(parent['recipe']), construction_model_identity=deepcopy(parent['model_identity']),
                assessment_inherited=False, approval_inherited=False),
            conceptualization_scope='old_runtime_results_retained; changed_targets_pending')
        run['source_concept_retention'].update(inherited_failures=deepcopy(receipt.get('inherited_failures', [])),
            completed_extraction=deepcopy(receipt.get('completed_extraction', [])))
        business_rebuild.inherit_review_guard(service, db, parent, run)
        db.execute('INSERT INTO runs VALUES(?,?)', (identifier, encode(run)))
        return dict(result, run_id=identifier, status=run['status'], duplicate_request=False)


def prepare(parent, targets, mode, *, service=None, source_context=None):
    policy = source_context or parent['recipe']['options'].get('concept_source_context') or 'whole'
    context = None
    if policy != 'whole' and targets:
        from .concept_source_context import Context, VERSION
        if policy != VERSION:
            raise ValueError('지원하지 않는 개념화 원문 문맥 계약입니다.')
        context = Context(service, parent)
    chunks = business_run.source_chunks(parent)
    for claim in parent['claims']:
        if claim['chunk_id'] not in chunks:
            ids = {e['block_id'] for e in claim['evidence']}
            blocks = [b for b in parent['blocks'] if b['id'] in ids]
            if not blocks:
                raise ValueError('교정된 대상의 원문 위치를 확인할 수 없습니다.')
            chunks[claim['chunk_id']] = dict(id=claim['chunk_id'], blocks=blocks, text=autoschema.source_text(blocks),
                                           source_version_id=blocks[0]['source_version_id'])
    planned = []
    options = parent['recipe']['options']
    for target in targets:
        messages, selection = autoschema.concept_messages(target, parent['graph'], chunks, mode, source_context=context)
        estimate = business_run.request_budget(parent, messages, None, options['concept_tokens'], review=False)['estimate_tokens']
        if target['kind'] != 'relation' or len(target['claim_ids']) < 2 or estimate <= options['context_tokens']:
            planned.append(dict(target=target, messages=messages, selection=selection))
            continue
        # Split at whole-claim boundaries; never truncate the required source or Scope.
        groups, pending = [], []
        for claim_id in target['claim_ids']:
            trial = dict(target, claim_ids=pending + [claim_id])
            trial_messages, _ = autoschema.concept_messages(trial, parent['graph'], chunks, mode, source_context=context)
            if pending and business_run.request_budget(parent, trial_messages, None, options['concept_tokens'], review=False)['estimate_tokens'] > options['context_tokens']:
                groups.append(pending)
                pending = []
            pending.append(claim_id)
        groups.append(pending)
        for index, claim_ids in enumerate(groups):
            part = dict(target, id=autoschema.identifier('relation', [target['id'], claim_ids]),
                        claim_ids=claim_ids, partition_of=target['id'])
            messages, selection = autoschema.concept_messages(part, parent['graph'], chunks, mode, source_context=context)
            selection['relation_input_partition'] = dict(original_target_id=target['id'],
                original_claim_ids=list(target['claim_ids']), original_estimated_tokens=estimate,
                context_tokens=options['context_tokens'], index=index, parts=len(groups))
            planned.append(dict(target=part, messages=messages, selection=selection))
    for item in planned:
        item['work_input'] = concept_work.prepare(parent, item)
    return planned


def refresh_changed(service, run, changed_ids):
    options = run['recipe']['options']
    targets = autoschema.concept_targets(run['graph'])
    planned = prepare(run, targets, options['neighbor_mode'], service=service)
    live = {(i['target']['kind'], i['target']['id']) for i in planned}
    previous = {(c['target']['kind'], c['target']['id']) for c in run['concepts']
                if c['status'] in {'unreviewed', 'accepted'}}
    previous_groups = {(c['target']['kind'], c['target'].get('partition_of', c['target']['id'])) for c in run['concepts']
                       if c['status'] in {'unreviewed', 'accepted'}}
    def stale(concept, reason):
        concept.update(previous_status=concept['status'], status='needs_review', stale_reason=reason)
        for binding in [*run.get('concept_bindings', []), *run.get('source_concept_bindings', [])]:
            if binding['concept_id'] == concept['id']:
                binding.update(previous_status=binding['status'], status='needs_review')
    for concept in run['concepts']:
        if concept['status'] in {'unreviewed', 'accepted'} and (concept['target']['kind'], concept['target']['id']) not in live:
            stale(concept, 'concept_target_removed')
    for item in planned:
        prior = [c for c in run['concepts'] if c['target']['id'] == item['target']['id']
                 and c['target']['kind'] == item['target']['kind'] and c['status'] in {'unreviewed', 'accepted'}]
        units = {u['id']: u for u in run['units']}
        target = item['target']
        regrouped = ((target['kind'], target['id']) not in previous
                     and (target['kind'], target.get('partition_of', target['id'])) in previous_groups)
        if not regrouped and not changed_ids.intersection(target['claim_ids']) and not any(
                not concept_work.same_input(units.get(c.get('request_id'), {}), c, item) for c in prior):
            continue
        if business_run.cancelled(service, run):
            return
        for concept in prior:
            if concept['target'] != item['target']:
                stale(concept, 'concept_target_input_changed')
        apply_selected_contract(service, run, item, refreshed=True)
    business_run.save(service, run)



def apply_selected_contract(service, run, item, *, refreshed=False):
    if run['recipe'].get('concept_work_contract') == concept_work.VERSION:
        return apply(service, run, item, refreshed=refreshed)
    # Existing runs keep their recorded contract; reading old results does not opt in.
    if refreshed and any(c['status'] in {'unreviewed','accepted'} and c['target'] == item['target'] for c in run['concepts']):
        return
    response = business_run.call(service, run, 'concept_' + item['target']['kind'], item['messages'],
        max_tokens=run['recipe']['options']['concept_tokens'], reference_map=item['selection']['source_reference_map'])
    result = dict(id=uuid4().hex, target=item['target'], selection=item['selection'],
        concepts=autoschema.concepts(response['text']) if response else [], status='unreviewed' if response else 'failed',
        relation='has_concept', approved_is_a=False, request_id=run['units'][-1]['id'])
    if refreshed: result['refreshed_after_claim_change'] = True
    run['concepts'].append(result)
    business_run.save(service, run)
    return result


def observe_execution(run, expected):
    client = business_run.ModelClient(run['recipe']['generation'])
    observe = getattr(client, 'execution_identity', None)
    expected['runtime'] = observe(run['recipe']['models']['draft'], 0,
        max_tokens=expected['requested_limits']['max_tokens'], context_tokens=expected['requested_limits']['context_tokens'],
        think=expected['requested_limits']['think']) if observe else None
    current_digest = (expected.get('runtime') or {}).get('model_digest')
    declared_identity = run['model_identity'].get('draft')
    declared_digest = declared_identity.get('digest') if isinstance(declared_identity, dict) else None
    if current_digest and declared_digest and current_digest != declared_digest:
        raise KnowledgeConflict('고정한 개념화 모델 digest가 변경됐습니다.')

def apply(service, run, item, *, refreshed=False):
    expected = deepcopy(item['work_input'])
    observe_execution(run, expected)
    for concept in run['concepts']:
        if concept['target'] != item['target'] or concept['status'] not in {'unreviewed','accepted'}:
            continue
        unit = next((u for u in run['units'] if u['id'] == concept.get('request_id')), None)
        if unit and concept_work.reusable(service, run, unit, expected, run['id']):
            # Repair a missing binding after a response/concept save interruption.
            bind(run, item, unit, concept)
            business_run.save(service, run)
            return concept
        if unit and concept_work.same_input(unit, concept, item):
            checks = run.setdefault('concept_link_checks', [])
            check = dict(target_id=item['target']['id'], concept_id=concept.get('id'),
                reason='execution_contract_unknown_or_changed; existing_result_retained',
                unknown_contract_fields=concept_work.unknown_fields(expected) +
                    ['donor.' + k for k in concept_work.unknown_fields(unit.get('concept_work_input'))], new_work_connected=False)
            if check not in checks: checks.append(check)
            business_run.save(service, run)
            return concept
        concept.update(previous_status=concept['status'], status='needs_review', stale_reason='concept_input_changed')
        for binding in run.get('concept_bindings', []):
            if binding['concept_id'] == concept.get('id'):
                binding.update(previous_status=binding['status'], status='needs_review')
    response = business_run.call(service, run, expected['stage'], item['messages'],
        max_tokens=run['recipe']['options']['concept_tokens'], reference_map=item['selection']['source_reference_map'],
        concept_work_input=expected)
    unit = run['units'][-1]
    valid = response is not None and concept_work.complete(unit)
    if response is not None and not valid:
        unit.update(status='failed', error='incomplete_concept_response')
    concept = dict(id=uuid4().hex, target=deepcopy(item['target']), selection=deepcopy(item['selection']),
        concepts=autoschema.concepts(response['text']) if valid else [], status='unreviewed' if valid else 'failed',
        relation='has_concept', approved_is_a=False, request_id=unit['id'])
    if refreshed: concept['refreshed_after_claim_change'] = True
    run['concepts'].append(concept)
    bind(run, item, unit, concept)
    business_run.save(service, run)
    return concept


def record_work(run, unit):
    donor = unit.get('reused_from') or dict(run_id=run['id'], unit_id=unit['id'])
    work_id = unit.get('concept_work_id') or autoschema.identifier('concept_work', [donor['run_id'], donor['unit_id']])
    unit['concept_work_id'] = work_id
    expected = deepcopy(unit.get('concept_work_input'))
    works = run.setdefault('concept_work', {})
    works.setdefault(work_id, dict(id=work_id, input=expected, fingerprint=concept_work.digest(expected),
        unknown_contract_fields=concept_work.unknown_fields(expected),
        raw_request_unit_id=unit['id'], response_unit_id=unit['id'], donor=deepcopy(unit.get('reused_from')),
        status='complete' if concept_work.complete(unit) else unit.get('status', 'failed')))
    return work_id


def bind(run, item, unit, concept):
    work_id = record_work(run, unit)
    binding = dict(target_id=item['target']['id'], target=deepcopy(item['target']), work_id=work_id,
        concept_id=concept['id'], request_id=unit['id'], source_reference_map=deepcopy(item['selection']['source_reference_map']),
        status=concept['status'], relation='has_concept', approved_is_a=False)
    bindings = run.setdefault('concept_bindings', [])
    if not any(b['concept_id'] == concept['id'] and b['work_id'] == work_id for b in bindings):
        bindings.append(binding)
    concept['work_id'] = work_id
    concept['source_input_fingerprint'] = concept_work.source_input_fingerprint(item)



def start(service, request):
    parent, planned = plan(service, request)
    donor = parent
    if request.donor_run_id:
        with service.repository.connect() as db:
            donor = service.repository.get(db, 'runs', request.donor_run_id)
        if (donor.get('kind') not in {'business','business_concept'} or donor['status'] in {'queued','running','cancel_requested'}
                or donor['input_version_ids'] != parent['input_version_ids']
                or donor.get('kind') == 'business_concept' and donor.get('parent_run_id') != parent['id']):
            raise ValueError('동일 원문 범위의 종료된 명시적 donor 실행이 필요합니다.')
    donor_inputs = []
    for item in planned:
        donor_inputs.append((item['messages'], item['selection']['source_reference_map']))
    with service.lock, service.repository.connect() as db:
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('기존 실행 종료 후 개념화를 시작하세요.')
        recipe = deepcopy(parent['recipe']); recipe['options']['neighbor_mode'] = request.neighbor_mode
        recipe['options']['concept_source_context'] = request.concept_source_context or recipe['options'].get('concept_source_context') or 'whole'
        recipe['concept_work_contract'] = concept_work.VERSION
        run = dict(id=uuid4().hex, kind='business_concept', status='running', parent_run_id=parent['id'],
            input_version_ids=parent['input_version_ids'], recipe=recipe, model_identity=parent['model_identity'],
            graph_fingerprint=autoschema.identifier('graph', parent['graph']), planned=planned, concepts=[], units=[],
            parent_recipe=deepcopy(donor['recipe']), parent_model_identity=deepcopy(donor['model_identity']),
            reuse_pool_parent_run_id=donor['id'],
            reusable_units=[deepcopy(u) for u in donor['units'] if any(u.get('messages') == messages
                and u.get('reference_map') == reference_map for messages,reference_map in donor_inputs)],
            started_at=utcnow(), finished_at=None, metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0))
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    begin = monotonic()
    try:
        for item in planned:
            if business_run.cancelled(service, run): break
            apply_selected_contract(service, run, item)
        run['status'] = 'succeeded' if len(run['concepts']) == len(planned) and all(c['status'] != 'failed' for c in run['concepts']) else 'partial'
    except Exception as exc:
        run.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    finally:
        if business_run.cancelled(service, run): run['status'] = 'cancelled'
        run.update(finished_at=utcnow()); run['metrics']['elapsed_s'] = monotonic() - begin
        with service.lock, service.repository.connect() as db:
            service.repository.save(db, 'runs', run)
    return run
