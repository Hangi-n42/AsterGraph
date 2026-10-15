"""Reconceptualize selected entities from a fixed stored extraction pool."""
from copy import deepcopy
import json
from time import monotonic
from uuid import uuid4

from . import autoschema, business_run, concept_work
from .service import KnowledgeConflict, encode, utcnow


def plan(service, request):
    with service.repository.connect() as db:
        parent = service.repository.get(db, 'runs', request.parent_run_id)
    if parent.get('kind') != 'business' or parent['status'] in {'queued', 'running', 'cancel_requested'}:
        raise ValueError('종료된 업무 지식 실행의 추출 풀을 선택하세요.')
    targets = {t['id']: t for t in autoschema.concept_targets(parent['graph']) if t['kind'] == 'entity'}
    if not set(request.target_ids) <= targets.keys():
        raise ValueError('현재 그래프의 개체 대상만 선택하세요.')
    return parent, prepare(parent, [targets[i] for i in dict.fromkeys(request.target_ids)], request.neighbor_mode)


def prepare(parent, targets, mode):
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
        messages, selection = autoschema.concept_messages(target, parent['graph'], chunks, mode)
        estimate = business_run.request_tokens(messages, None, options['concept_tokens'])
        if target['kind'] != 'relation' or len(target['claim_ids']) < 2 or estimate <= options['context_tokens']:
            planned.append(dict(target=target, messages=messages, selection=selection))
            continue
        # Split at whole-claim boundaries; never truncate the required source or Scope.
        groups, pending = [], []
        for claim_id in target['claim_ids']:
            trial = dict(target, claim_ids=pending + [claim_id])
            trial_messages, _ = autoschema.concept_messages(trial, parent['graph'], chunks, mode)
            if pending and business_run.request_tokens(trial_messages, None, options['concept_tokens']) > options['context_tokens']:
                groups.append(pending)
                pending = []
            pending.append(claim_id)
        groups.append(pending)
        for index, claim_ids in enumerate(groups):
            part = dict(target, id=autoschema.identifier('relation', [target['id'], claim_ids]),
                        claim_ids=claim_ids, partition_of=target['id'])
            messages, selection = autoschema.concept_messages(part, parent['graph'], chunks, mode)
            selection['relation_input_partition'] = dict(original_target_id=target['id'],
                original_claim_ids=list(target['claim_ids']), original_estimated_tokens=estimate,
                context_tokens=options['context_tokens'], index=index, parts=len(groups))
            planned.append(dict(target=part, messages=messages, selection=selection))
    for item in planned:
        item['work_input'] = concept_work.prepare(parent, item)
    return planned


def refresh_changed(service, run, changed_ids):
    options = run['recipe']['options']
    targets = [t for t in autoschema.concept_targets(run['graph']) if changed_ids.intersection(t['claim_ids'])]
    planned = prepare(run, targets, options['neighbor_mode'])
    for item in planned:
        if business_run.cancelled(service, run):
            return
        apply_selected_contract(service, run, item, refreshed=True)



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
        if service.closed or any(json.loads(r['payload'])['status'] in {'queued', 'running', 'cancel_requested'}
                                 for r in db.execute('SELECT payload FROM runs')):
            raise KnowledgeConflict('기존 실행 종료 후 개념화를 시작하세요.')
        recipe = deepcopy(parent['recipe']); recipe['options']['neighbor_mode'] = request.neighbor_mode
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
