"""Source-version rebuild plans; generation and approval keep their existing contracts."""
from copy import deepcopy
from hashlib import sha256
import json

from . import autoschema, business_run, concept_work, business_rebuild_html
from .service import KnowledgeConflict, encode, utcnow

VERSION = 'source-scoped-rebuild-v2'


def validate_views(views, blocks):
    for view in views:
        matches = [b for b in blocks if (b['source_version_id'], b.get('parse_run_id'), b['id'])
                   == (view['source_version_id'], view.get('parse_run_id'), view['id'])]
        if len(matches) != 1:
            raise ValueError('보존 문맥의 원문 주소 대응이 유일하지 않습니다.')
        block = matches[0]
        start, end = view.get('span', [0, len(view['text'])])
        offset = block.get('span', [0])[0]
        if (view.get('locator') != block.get('locator') or not 0 <= start-offset <= end-offset <= len(block['text'])
                or view['text'] != block['text'][start-offset:end-offset]):
            raise ValueError('보존 문맥의 구간·본문·위치가 현재 저장 원문과 다릅니다.')


def row_correspondence(before, after, key_fields):
    if not key_fields or len(set(key_fields)) != len(key_fields):
        raise ValueError('유일한 행 식별 열이 필요합니다.')
    def index(blocks):
        result = {}
        for block in blocks:
            fields = block.get('locator', {}).get('fields')
            # shortcut: XLSX needs verified header/unit/formula/style dependencies before partial rebinding.
            if block.get('locator', {}).get('format') == 'xlsx':
                raise ValueError('XLSX 머리글·단위·수식·서식 의존성이 미확정이므로 부분 재구축을 지원하지 않습니다.')
            if (block.get('locator', {}).get('format') != 'json' or not fields
                    or any(k not in fields for k in key_fields)
                    or block['text'] != json.dumps(fields, ensure_ascii=False)):
                raise ValueError('검증 가능한 정형 행과 식별 열이 필요합니다.')
            key = tuple(json.dumps(fields[k], ensure_ascii=False, sort_keys=True) for k in key_fields)
            if key in result:
                raise ValueError('중복 행 식별자는 첫 일치로 연결할 수 없습니다.')
            result[key] = block
        return result
    old, new = index(before), index(after)
    result = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        av = a['locator']['fields'] if a else {}
        bv = b['locator']['fields'] if b else {}
        fields = [k for k in sorted(av.keys() | bv.keys()) if k not in av or k not in bv
                  or concept_work.digest(av[k]) != concept_work.digest(bv[k])]
        result.append(dict(key=[json.loads(k) for k in key], before_block_id=a['id'] if a else None,
            after_block_id=b['id'] if b else None, changed_fields=fields,
            action='add_row' if not a else 'remove' if not b else 'rebuild_row' if fields else 'rebind_row',
            position_changed=bool(a and b and {k:v for k,v in a['locator'].items() if k != 'fields'}
                                  != {k:v for k,v in b['locator'].items() if k != 'fields'})))
    return result


def source_basis(service, db, version_id):
    version = service.repository.get(db, 'versions', version_id)
    if version['processing_status'] != 'parsed':
        raise ValueError('완료된 원문 파싱이 필요합니다.')
    parsed = service.repository.get(db, 'runs', version['latest_parse_run_id'])
    if parsed['status'] != 'succeeded':
        raise ValueError('부분·미완료 파싱은 행 부재를 확인할 수 없습니다.')
    blocks = service.parse_blocks(db, version['latest_parse_run_id'], version_id)
    raw = service.raw_path(version).read_bytes()
    if sha256(raw).hexdigest() != version['sha256']:
        raise ValueError('원본 파일의 해시가 저장 버전과 다릅니다.')
    return dict(version=deepcopy(version), blocks_sha256=concept_work.digest(blocks)), blocks


def requirement_scope(service, db, source_id, before_version_id, selected_ids):
    from .business_changes import stored_dependencies
    registered = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM requirements')]
    dependencies, blocks = stored_dependencies(service, registered)
    before_blocks = {b['id'] for b in blocks if b['source_version_id'] == before_version_id}
    direct = {d['requirement_id'] for d in dependencies if before_blocks.intersection(d.get('source_block_ids', []))}
    candidates = [r for r in registered if r['id'] in {*selected_ids, *direct}
                  or not r.get('source_ids') or source_id in r['source_ids']]
    identifiers = {r['id'] for r in candidates}
    return candidates, dict(candidate_ids=[r['id'] for r in candidates], direct_dependency_ids=sorted(direct),
        unselected_review_ids=sorted(identifiers-set(selected_ids)),
        stored_dependencies=[d for d in dependencies if d['requirement_id'] in identifiers],
        source_dependencies=[deepcopy(b) for b in blocks if b['id'] in before_blocks],
        selection_rule='actual_stored_source_dependencies_or_declared_source_or_unspecified_scope_or_explicit_request',
        status='conservative_review_candidates; not_semantic_impact_or_independence_judgment',
        automatic_meaning_impact=False,
        out_of_declared_source_scope_ids=[r['id'] for r in registered if r['id'] not in identifiers])


def plan(service, request):
    with service.lock, service.repository.connect() as db:
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('기존 실행 종료 후 부분 재구축을 계획하세요.')
        parent = service.repository.get(db, 'runs', request.parent_run_id)
        if parent.get('kind') != 'business' or parent['status'] in {'queued', 'running', 'cancel_requested'}:
            raise ValueError('종료된 업무 지식 실행이 필요합니다.')
        if request.before_version_id not in parent['input_version_ids'] or request.after_version_id in parent['input_version_ids']:
            raise ValueError('부모의 이전 원문을 새 버전 하나로 교체하세요.')
        before, old = source_basis(service, db, request.before_version_id)
        after, new = source_basis(service, db, request.after_version_id)
        if before['version']['source_id'] != after['version']['source_id']:
            raise ValueError('같은 출처의 전후 버전이 필요합니다.')
        previous = [b for b in parent['blocks'] if b['source_version_id'] == request.before_version_id]
        # A subset cannot establish absence of rows outside its recorded scope.
        if {b['id'] for b in previous} != {b['id'] for b in old} or any(
                any(b.get(k) != next(p for p in old if p['id'] == b['id']).get(k)
                    for k in ('text', 'locator', 'parse_run_id')) for b in previous):
            raise ValueError('부분 원문 부모의 미확인 범위를 전체 행으로 연결할 수 없습니다.')
        source_units = []
        if request.key_fields:
            rows = row_correspondence(old, new, request.key_fields)
            by_old = {r['before_block_id']: r for r in rows if r['before_block_id']}
            actions, represented = [], set()
            for claim in parent['claims']:
                reads = {v for v in claim['source_version_ids']} | {e['source_version_id'] for e in claim.get('evidence', [])}
                if request.before_version_id not in reads:
                    actions.append(dict(claim_id=claim['id'], action='preserve',
                        reason='claim_and_evidence_use_unchanged_source_versions'))
                    continue
                ref = business_run.exact_direct_row(claim, parent['blocks'])
                if not ref or ref['block_id'] not in by_old:
                    raise ValueError('정형 행 외 변경 근거는 지역 재추출 계획이 필요합니다.')
                row = by_old[ref['block_id']]
                represented.add(ref['block_id'])
                actions.append(dict(row, claim_id=claim['id'], reason='verified_parser_row; no_generation_or_approval_reuse'))
            if represented != {b['id'] for b in old}:
                raise ValueError('기존 정형 행의 누락·중복 없는 저장 대응이 필요합니다.')
            if len([a for a in actions if a['action'] != 'preserve']) != len(represented):
                raise ValueError('동일 행의 중복 주장은 자동 병합할 수 없습니다.')
            actions.extend(dict(r, claim_id=None, reason='new_source_row') for r in rows if r['action'] == 'add_row')
        else:
            source_units = business_rebuild_html.unit_plan(service, db, parent,
                request.before_version_id, request.after_version_id, old, new)
            rows, actions = [], []
            by_unit = {u['unit_key']: u for u in source_units}
            for claim in parent['claims']:
                reads = set(claim['source_version_ids']) | {e['source_version_id'] for e in claim.get('evidence', [])}
                if request.before_version_id not in reads:
                    actions.append(dict(claim_id=claim['id'], action='preserve',
                        reason='claim_and_evidence_use_unchanged_source_versions'))
                    continue
                key = parent['source_structure']['chunk_units'].get(claim['chunk_id'])
                if key not in by_unit or reads != {request.before_version_id}:
                    raise ValueError('변경 절 후보의 실제 입력 범위가 미확정입니다.')
                unit = by_unit[key]
                actions.append(dict(claim_id=claim['id'], action=unit['action'], unit_key=key,
                    reason=unit['reason']))
        for rid in request.requirement_ids:
            service.repository.get(db, 'requirements', rid)
        requirements, discovery = requirement_scope(service, db, before['version']['source_id'],
            request.before_version_id, request.requirement_ids)
        snapshot = service.repository.get(db, 'snapshots', request.base_snapshot_id) if request.base_snapshot_id else None
        if snapshot and (snapshot.get('kind') != 'source_graph' or request.before_version_id not in snapshot['source_versions']):
            raise ValueError('이전 원문을 포함한 명시적 사용 스냅샷이 필요합니다.')
        basis = dict(parent_run_id=parent['id'], parent_sha256=concept_work.digest(parent),
            before=before, after=after, requirements=[dict(id=r['id'], revision=r['revision'],
                assessment=deepcopy(r.get('current_assessment'))) for r in requirements],
            unchanged_sources=[source_basis(service, db, vid)[0] for vid in parent['input_version_ids']
                               if vid != request.before_version_id],
            snapshot_id=request.base_snapshot_id, snapshot_sha256=concept_work.digest(snapshot) if snapshot else None)
        identifier = autoschema.identifier('source_rebuild', [VERSION, request.model_dump(), basis])
        existing = db.execute('SELECT payload FROM runs WHERE id=?', (identifier,)).fetchone()
        if existing:
            return json.loads(existing['payload'])
        run = dict(id=identifier, kind='business_rebuild_plan', contract=VERSION, status='planned',
            request=request.model_dump(), basis=basis, actions=actions, rows=rows, source_units=source_units,
            requirement_discovery=discovery, units=[],
            input_version_ids=[request.before_version_id, request.after_version_id],
            dates=dict(before=before['version']['dates'], after=after['version']['dates']),
            date_change_is_input_change=before['version']['dates'] != after['version']['dates'],
            approval_inherited=False, generation_reused=False, created_at=utcnow(),
            metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0))
        db.execute('INSERT INTO runs VALUES(?,?)', (identifier, encode(run)))
        return run


def validate(service, db, plan, *, run_id=None):
    basis = plan['basis']
    if (plan['contract'] not in {VERSION, 'source-scoped-rebuild-v1'}
            or plan['contract'] == 'source-scoped-rebuild-v1' and plan.get('source_units')):
        raise KnowledgeConflict('절 단위 완결·실패 보존 정책이 변경됐습니다. 새 계획이 필요합니다.')
    if concept_work.digest(service.repository.get(db, 'runs', basis['parent_run_id'])) != basis['parent_sha256']:
        raise KnowledgeConflict('부분 재구축 계획의 부모 판단이 변경됐습니다.')
    for key in ('before', 'after'):
        current, _ = source_basis(service, db, basis[key]['version']['id'])
        if current != basis[key]:
            raise KnowledgeConflict('부분 재구축 계획의 원문·파싱 버전이 변경됐습니다.')
    for expected in basis['unchanged_sources']:
        current, _ = source_basis(service, db, expected['version']['id'])
        if current != expected:
            raise KnowledgeConflict('보존한 문맥 원문·파싱 버전이 변경됐습니다.')
    for expected in basis['requirements']:
        current = service.repository.get(db, 'requirements', expected['id'])
        pointer = current.get('current_assessment')
        own_runs = {*plan.get('execution_run_ids', []), *plan.get('review_run_ids', []), *([run_id] if run_id else [])}
        if current['revision'] != expected['revision'] or (pointer != expected['assessment']
                and (not pointer or pointer['run_id'] not in own_runs)):
            raise KnowledgeConflict('부분 재구축 계획의 요구 또는 판단이 변경됐습니다.')
    if basis['snapshot_id'] and concept_work.digest(service.repository.get(db, 'snapshots', basis['snapshot_id'])) != basis['snapshot_sha256']:
        raise KnowledgeConflict('부분 재구축 계획의 기준 스냅샷이 변경됐습니다.')


def fingerprint(plan):
    return concept_work.digest({k: plan[k] for k in ('contract', 'basis', 'request', 'actions', 'rows',
        *[key for key in ('source_units', 'requirement_discovery') if key in plan])})


def extraction_donor(service, db, parent, claim, cache):
    stage = 'direct_definitions' if claim['role'] == 'direct_definition' else claim['role']
    units = [u for u in parent['units'] if u.get('source_chunk_id') == claim['chunk_id']
             and u['stage'] == stage and u.get('status') == 'succeeded' and u.get('messages')]
    if len(units) == 1:
        return parent['id'], units[0]
    guard = parent.get('source_rebuild_guard')
    if guard:
        identifier = guard['construction_run_id']
        if identifier not in cache:
            cache[identifier] = service.repository.get(db, 'runs', identifier)
        construction = cache[identifier]
        if not construction.get('source_rebuild') or [c for c in construction['claims'] if c['id'] == claim['id']] != [claim]:
            raise ValueError('저장풀의 원래 부분 재구축 후보 계보를 확인할 수 없습니다.')
        return extraction_donor(service, db, construction, claim, cache)
    receipt = parent.get('source_rebuild') or {}
    proofs = [p for p in receipt.get('preserved_extraction_inputs', []) if p['claim_id'] == claim['id']]
    if len(proofs) != 1:
        raise ValueError('보존 후보의 과거 실제 입력 범위가 미확정입니다. 지역 재검토가 필요합니다.')
    proof = proofs[0]
    donor_id = proof.get('donor_run_id') or receipt['parent_run_id']
    if donor_id not in cache:
        cache[donor_id] = service.repository.get(db, 'runs', donor_id)
    donor = cache[donor_id]
    matches = [u for u in donor['units'] if u['id'] == proof['stored_unit_id']]
    old_claims = [c for c in donor['claims'] if c['id'] == claim['id']]
    if (len(matches) != 1 or old_claims != [claim]
            or matches[0].get('source_chunk_id') != claim['chunk_id']
            or matches[0]['stage'] != stage or matches[0]['status'] != 'succeeded'
            or concept_work.digest(matches[0]['messages']) != proof['stored_messages_sha256']
            or concept_work.digest(matches[0].get('schema')) != proof['stored_schema_sha256']
            or matches[0].get('reference_map') != proof['stored_reference_map']):
        raise ValueError('보존 후보의 원래 요청·주장·연결 계보가 변경됐습니다.')
    return donor_id, matches[0]


def prepare_run(service, db, run, request):
    plan = service.repository.get(db, 'runs', request.source_rebuild_plan_id)
    if plan.get('kind') != 'business_rebuild_plan':
        raise ValueError('부분 재구축 계획을 선택하세요.')
    validate(service, db, plan)
    prior_ids = plan.get('execution_run_ids', [])
    prior = service.repository.get(db, 'runs', prior_ids[-1]) if prior_ids else None
    def options(value):
        return {k: v for k, v in value['recipe']['options'].items() if k != 'resume_run_id'}
    if prior and not request.resume_run_id:
        if options(run) != options(prior):
            raise KnowledgeConflict('같은 계획의 실행 요청이 달라졌습니다.')
        return dict(run_id=prior['id'], status=prior['status'], duplicate_request=True)
    if request.reuse_run_id or request.reassess_run_id or request.block_ids or request.target_parse_run_ids:
        raise ValueError('부분 재구축은 서버 계획의 전체 문맥과 처리 단위를 사용합니다.')
    parent = service.repository.get(db, 'runs', plan['basis']['parent_run_id'])
    run['parent_recipe'] = deepcopy(parent['recipe'])
    run['parent_model_identity'] = deepcopy(parent.get('model_identity'))
    run['reuse_pool_parent_run_id'] = parent['id']
    run['reusable_units'] = [deepcopy(u) for u in parent['units'] if u['stage'].startswith('concept_')
                             and concept_work.complete(u)]
    expected_versions = [plan['request']['after_version_id'] if v == plan['request']['before_version_id'] else v
                         for v in parent['input_version_ids']]
    if (run['input_version_ids'] != expected_versions
            or request.requirement_ids != plan['request']['requirement_ids']):
        raise ValueError('부분 재구축 계획의 원문·요구 범위를 사용하세요.')
    if request.resume_run_id:
        if not prior or prior['id'] != request.resume_run_id or prior['status'] not in {'failed', 'cancelled', 'partial'}:
            raise ValueError('같은 계획의 마지막 미완료 실행에서만 재개하세요.')
        if (options(prior) != options(run) or prior['model_identity'] != run['model_identity']
                or any(prior['recipe'][k] != run['recipe'][k] for k in ('generation', 'models', 'version', 'scope_contract', 'review_contract'))):
            raise ValueError('부분 재개는 같은 모델·판단 계약에서만 가능합니다.')
        for key in ('claims', 'concepts', 'units', 'source_rebuild', 'concept_work', 'concept_bindings', 'source_concept_bindings'):
            if key in prior:
                run[key] = deepcopy(prior[key])
        failed = [u for u in run['units'] if u['status'] in {'failed', 'partial', 'cancelled'}]
        run['units'] = [u for u in run['units'] if u not in failed]
        run['source_rebuild'].setdefault('prior_failures', []).append(dict(run_id=prior['id'],
            unit_ids=[u['id'] for u in failed], metrics=deepcopy(prior['metrics']), error=prior.get('error')))
        run['source_rebuild']['resumed_from_run_id'] = prior['id']
    else:
        claims = {c['id']: c for c in parent['claims']}
        unchanged = set(parent['input_version_ids']) - {plan['request']['before_version_id']}
        run['chunks'] = [deepcopy(c) for vid in run['input_version_ids']
            for c in (parent['chunks'] if vid in unchanged else run['chunks']) if c['source_version_id'] == vid]
        run['claims'] = [deepcopy(claims[a['claim_id']]) for a in plan['actions'] if a['action'] == 'preserve']
        rows = {b['id']: (chunk, index, b) for chunk in run['chunks'] for index, b in enumerate(chunk['blocks'])
                if not b.get('context_only') and b.get('locator', {}).get('fields')}
        carried, bindings, preserved_inputs, donors = [], [], [], {parent['id']: parent}
        source_map, source_bindings, source_inputs = {}, [], []
        if plan.get('source_units'):
            if request.source_unit_policy != business_rebuild_html.POLICY:
                raise ValueError('전후에 같은 명시 절 입력 정책이 필요합니다.')
            if (parent['model_identity'] != run['model_identity'] or any(parent['recipe'].get(k) != run['recipe'].get(k)
                    for k in ('version', 'scope_contract', 'generation', 'models')) or any(
                    parent['recipe']['options'].get(k) != run['recipe']['options'].get(k)
                    for k in ('context_tokens', 'extraction_tokens', 'extraction_target_chars', 'review_tokens', 'think', 'timeout'))):
                raise ValueError('절 결과 재연결은 같은 추출 모델·입력 계약에서만 가능합니다.')
            carried, source_map, source_bindings, source_inputs = business_rebuild_html.bind_claims(service, db, parent, run, plan)
        for action in plan['actions']:
            if action['action'] == 'preserve':
                claim = deepcopy(claims[action['claim_id']])
                old_chunk = next(c for c in parent['chunks'] if c['id'] == claim['chunk_id'])
                validate_views(old_chunk['blocks'], run['blocks'])
                new_chunk = next((c for c in run['chunks'] if c['id'] == claim['chunk_id']), None)
                stage = 'direct_definitions' if claim['role'] == 'direct_definition' else claim['role']
                before_request = business_rebuild_html.extraction_request(parent, old_chunk, stage)
                before_input = before_request['messages']
                if not new_chunk or before_request != business_rebuild_html.extraction_request(run, new_chunk, stage):
                    raise ValueError('보존 후보의 실제 추출 문맥이 달라 지역 재추출이 필요합니다.')
                donor_id, unit = extraction_donor(service, db, parent, claim, donors)
                verified = (all(unit.get(k) == before_request[k] for k in ('messages', 'schema', 'reference_map'))
                    if stage == 'direct_definitions' else any(old_chunk['text'] in m.get('content', '')
                        for m in unit['messages'] if isinstance(m.get('content'), str)))
                if not verified:
                    raise ValueError('보존 후보의 과거 실제 입력 범위가 미확정입니다. 지역 재검토가 필요합니다.')
                carried.append(claim)
                preserved_inputs.append(dict(claim_id=claim['id'], chunk_id=old_chunk['id'],
                    donor_run_id=donor_id,
                    stored_unit_id=unit['id'], stored_source_chunk_id=unit['source_chunk_id'],
                    stored_messages_sha256=concept_work.digest(unit['messages']),
                    stored_schema_sha256=concept_work.digest(unit.get('schema')),
                    stored_reference_map=deepcopy(unit.get('reference_map')),
                    current_regeneration_sha256=concept_work.digest(before_input),
                    stored_request_matches_current_contract=unit['messages'] == before_input
                        and unit.get('schema') == before_request['schema'],
                    source_block_ids=[b['id'] for b in old_chunk['blocks']],
                    source_views=[dict(block_id=b['id'], source_version_id=b['source_version_id'],
                        parse_run_id=b.get('parse_run_id'), span=b.get('span', [0, len(b['text'])]),
                        locator=deepcopy(b.get('locator')), text_sha256=sha256(b['text'].encode()).hexdigest())
                        for b in old_chunk['blocks']],
                    scope='stored_request_contains_unchanged_source_chunk; not_generation_contract_reuse'))
            elif action['action'] == 'rebind_row':
                chunk, index, block = rows[action['after_block_id']]
                claim = business_run.direct_tabular_row(chunk, block, index)
                carried.append(claim)
                bindings.append(dict(before_claim_id=action['claim_id'], after_claim_id=claim['id'],
                    before_block_id=action['before_block_id'], after_block_id=block['id'],
                    dates=deepcopy(plan['dates']), method='verified_new_version_row_binding', approval_inherited=False))
        run['claims'] = carried
        targets = {a['after_block_id'] for a in plan['actions'] if a['action'] in {'rebuild_row', 'add_row'}}
        targets.update(bid for unit in plan.get('source_units', [])
            if unit['action'] in {'add_source', 'rebuild_source'} for bid in unit['after_block_ids'])
        extraction_chunks = [c['id'] for c in run['chunks'] if targets.intersection(
            b['id'] for b in c['blocks'] if not b.get('context_only'))]
        run['parent_run_id'] = parent['id']
        run['source_rebuild'] = dict(plan_id=plan['id'], plan_fingerprint=fingerprint(plan),
            parent_run_id=parent['id'], extraction_chunk_ids=extraction_chunks,
            target_block_ids=sorted(targets), preserved_claim_ids=[a['claim_id'] for a in plan['actions'] if a['action'] == 'preserve'],
            preserved_extraction_inputs=preserved_inputs, row_bindings=bindings,
            source_address_map=source_map, source_claim_bindings=source_bindings, source_extraction_inputs=source_inputs,
            unresolved_source_units=[deepcopy(u) for u in plan.get('source_units', []) if u['action'] == 'unresolved_source'],
            removed_claim_ids=[a['claim_id'] for a in plan['actions'] if a['action'] in {'remove', 'remove_source'}],
            replaced_claim_ids=[a['claim_id'] for a in plan['actions'] if a['action'] in {'rebuild_row', 'rebuild_source'}],
            approval_inherited=False, completed_extraction=[], context_scope='full_stored_source; extraction_subset_only')
        run['units'].append(dict(id=autoschema.identifier('source_rebind', plan['id']), stage='source_row_rebind',
            status='succeeded', model_called=False, bindings=deepcopy(bindings), finished_at=utcnow()))
    run['graph'] = autoschema.graph(run['claims'], run['blocks'])
    plan.setdefault('execution_run_ids', []).append(run['id'])
    service.repository.save(db, 'runs', plan)


def validate_run(service, db, run):
    receipt = run.get('source_rebuild') or run.get('source_rebuild_guard')
    if not receipt:
        return
    plan = service.repository.get(db, 'runs', receipt['plan_id'])
    if receipt['plan_fingerprint'] != fingerprint(plan):
        raise KnowledgeConflict('부분 재구축 계획의 판단 단위가 변경됐습니다.')
    validate(service, db, plan, run_id=run['id'])


def inherit_review_guard(service, db, parent, run):
    receipt = parent.get('source_rebuild') or parent.get('source_rebuild_guard')
    if not receipt:
        return
    validate_run(service, db, parent)
    run['source_rebuild_guard'] = dict(plan_id=receipt['plan_id'], plan_fingerprint=receipt['plan_fingerprint'],
        construction_run_id=receipt.get('construction_run_id', parent['id']), parent_review_run_id=parent['id'],
        scope='basis_only; no_extraction_completion_or_approval_inherited')
    plan = service.repository.get(db, 'runs', receipt['plan_id'])
    plan.setdefault('review_run_ids', []).append(run['id'])
    service.repository.save(db, 'runs', plan)


def completed(service, run):
    with service.repository.connect() as db:
        validate_run(service, db, run)
    records = {(v['chunk_id'], v['stage']) for v in run['source_rebuild']['completed_extraction']}
    successful = {(u.get('source_chunk_id'), u['stage']) for u in run['units'] if u['status'] == 'succeeded'}
    if not records <= successful:
        raise ValueError('완료한 재구축 단위의 성공 기록을 확인할 수 없습니다.')
    return records


def record_completion(run, chunk_id, stage):
    if 'source_rebuild' in run:
        records = run['source_rebuild']['completed_extraction']
        item = dict(chunk_id=chunk_id, stage=stage)
        if item not in records:
            records.append(item)


def snapshot_invalidations(db, snapshot):
    result = []
    for row in db.execute("SELECT payload FROM runs WHERE json_extract(payload, '$.kind')='business_rebuild_plan'"):
        plan = json.loads(row['payload'])
        before = plan['request']['before_version_id']
        if before not in snapshot['source_versions']:
            continue
        changed = [a for a in plan['actions'] if a['action'] in {'rebuild_row', 'remove', 'rebuild_source', 'remove_source'}]
        blocks = {a['before_block_id'] for a in changed if a.get('before_block_id')}
        blocks.update(bid for unit in plan.get('source_units', [])
            if unit['action'] in {'rebuild_source', 'remove_source', 'unresolved_source'} for bid in unit['before_block_ids'])
        result.append(dict(event='business_source_rebuild_pending', snapshot_id=snapshot['id'],
            run_ids=[plan['id']], before_version_id=before, after_version_id=plan['request']['after_version_id'],
            reason='new_source_change_not_applied_to_this_snapshot',
            claim_ids=[c['id'] for c in snapshot['claims'] if any(e['source_version_id'] == before
                and e['block_id'] in blocks for e in c.get('evidence', []))], block_ids=sorted(blocks),
            requirement_ids=plan.get('requirement_discovery', {}).get('candidate_ids', plan['request']['requirement_ids']),
            impact_status='conservative_pending_review; not_confirmed_affected', approval_inherited=False))
    return result
