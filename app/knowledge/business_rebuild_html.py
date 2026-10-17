"""Opt-in local HTML source units; ambiguous structure never proves independence."""
from copy import deepcopy
from hashlib import sha256

from . import autoschema, concept_work, source_reader

POLICY = 'explicit_html_sections_v1'


def relative_path(node, root):
    parts = []
    while node is not root:
        if node.parent is None:
            raise ValueError('절 바깥 원문 위치입니다.')
        siblings = node.parent.find_all(node.name, recursive=False)
        parts.append(node.name + ':' + str(next(i for i, sibling in enumerate(siblings) if sibling is node)))
        node = node.parent
    return '/'.join(reversed(parts))


def profile(service, db, version_id, blocks):
    version = service.repository.get(db, 'versions', version_id)
    soup, parsed, reason = source_reader.load_html(service, db, version_id, version['latest_parse_run_id'])
    if reason != 'verified_raw_HTML_and_complete_parse_lineage':
        raise ValueError('절 단위 계획에는 원본과 완결한 HTML 파싱이 필요합니다: ' + reason)
    if {b['id'] for b in blocks} != {b['id'] for b in parsed}:
        raise ValueError('부분 원문에서 전역 단서가 없다고 판정할 수 없습니다.')
    scope = version.get('selected_scope') or {}
    if not isinstance(scope, dict):
        raise ValueError('절 판단에 지원하지 않는 원문 선택 계약입니다.')
    selector = scope.get('selector', 'body')
    roots = soup.select(selector)
    if len(roots) != 1:
        raise ValueError('절 판단의 선택 본문이 유일하지 않습니다.')
    root = roots[0]
    sections = root.find_all('section', recursive=False)
    if (not sections or any(not s.get('id') or len(soup.find_all(id=s['id'])) != 1
            or s.find('section') for s in sections)):
        raise ValueError('유일한 명시 절이 없는 평면·중첩·중복 구조는 지역 범위를 확정할 수 없습니다.')
    for section in sections:
        for link in section.find_all('a', href=True):
            href = link['href'].strip()
            targets = soup.find_all(id=href[1:]) if href.startswith('#') else []
            if len(targets) != 1 or not (targets[0] is section or section in targets[0].parents):
                raise ValueError('절 밖 또는 미확정 명시 참조는 이 지역 입력 계약에서 지원하지 않습니다.')
    units = {s['id']: dict(key=s['id'], block_ids=[], relative_blocks={},
        structure_sha256=sha256(str(s).encode()).hexdigest()) for s in sections}
    globals_, global_content = [], []
    recorded = {b['id']: b for b in parsed}
    for block in blocks:
        original = recorded[block['id']]
        if any(block.get(k) != original.get(k) for k in ('text', 'locator', 'parse_run_id')):
            raise ValueError('절 판단의 저장 원문이 파싱 기록과 다릅니다.')
        locator = block.get('locator', {})
        path = locator.get('element_path')
        nodes = soup.select(path) if path and '::text(' not in path else []
        if (len(nodes) != 1 or 'row' in locator or locator.get('attribute')
                or nodes[0].get_text('\n', strip=True) != block['text']):
            raise ValueError('절 본문의 물리 위치·문구를 유일하게 확인할 수 없습니다.')
        node = nodes[0]
        owners = [s for s in sections if node is s or s in node.parents]
        if not owners:
            globals_.append(block['id'])
            global_content.append(str(node))
            continue
        if len(owners) != 1:
            raise ValueError('주석의 부모 절 귀속이 미확정입니다.')
        owner = owners[0]; key = relative_path(node, owner)
        units[owner['id']]['block_ids'].append(block['id'])
        units[owner['id']]['relative_blocks'][key] = block['id']
    if any(not u['block_ids'] for u in units.values()):
        raise ValueError('빈 절의 적용 범위를 확정할 수 없습니다.')
    return dict(contract=POLICY, source_version_id=version_id, parse_run_id=version['latest_parse_run_id'],
        raw_sha256=version['sha256'], dates=deepcopy(version['dates']), units=units,
        global_context_block_ids=globals_, global_context_sha256=concept_work.digest(global_content),
        selection_rule='direct_unique_sections_are_targets; all_outside_source_is_read_as_context',
        scope='explicit_source_units; not_a_claim_of_general_HTML_semantic_scope')


def source_chunks(service, db, blocks, request):
    chunks, versions, chunk_units = [], {}, {}
    for vid in dict.fromkeys(b['source_version_id'] for b in blocks):
        group = [b for b in blocks if b['source_version_id'] == vid]
        info = profile(service, db, vid, group)
        versions[vid] = info
        order = {b['id']: i for i, b in enumerate(group)}
        by_id = {b['id']: b for b in group}
        globals_ = [dict(by_id[i], context_only=True) for i in info['global_context_block_ids']]
        for key, unit in info['units'].items():
            selected = [by_id[i] for i in unit['block_ids']]
            local = autoschema.chunks(selected, request.context_tokens, request.extraction_tokens, request.extraction_target_chars)
            unit['chunk_ids'] = []
            for chunk in local:
                views = sorted([*globals_, *chunk['blocks']], key=lambda b: (order[b['id']], b.get('span', [0])[0]))
                text = autoschema.source_text(views)
                if len(text.encode()) > (request.context_tokens-request.extraction_tokens-2500)*2:
                    raise ValueError('필수 전역 단서를 포함할 입력 용량이 없습니다.')
                chunk.update(id=autoschema.identifier('chunk', [POLICY, key,
                    [(b['id'], b.get('span'), b.get('context_only', False)) for b in views]]),
                    blocks=deepcopy(views), text=text,
                    source_reference_map={'b'+str(n+1): dict(block_id=b['id'], span=b.get('span')) for n,b in enumerate(views)})
                unit['chunk_ids'].append(chunk['id']); chunk_units[chunk['id']] = key
                chunks.append(chunk)
    return chunks, dict(contract=POLICY, versions=versions, chunk_units=chunk_units,
        generation_reuse=False, target_scope='explicit_sections', globals_are_context_only=True)


def unit_plan(service, db, parent, before, after, old, new):
    structure = parent.get('source_structure') or {}
    if structure.get('contract') != POLICY or parent['recipe']['options'].get('source_unit_policy') != POLICY:
        raise ValueError('전후에 같은 명시 절 입력 정책을 사용한 부모가 필요합니다.')
    a = profile(service, db, before, old)
    b = profile(service, db, after, new)
    saved = deepcopy(structure['versions'].get(before))
    if saved:
        for unit in saved['units'].values():
            unit.pop('chunk_ids', None)
    if saved != a:
        raise ValueError('부모의 절 입력 구조를 현재 원본으로 검증할 수 없습니다.')
    common = a['global_context_sha256'] == b['global_context_sha256'] and a['dates'] == b['dates']
    globals_map = dict(zip(a['global_context_block_ids'], b['global_context_block_ids'])) if common else {}
    result = []
    for key in sorted(a['units'].keys() | b['units'].keys()):
        x, y = a['units'].get(key), b['units'].get(key)
        same = bool(x and y and common and x['structure_sha256'] == y['structure_sha256']
                    and x['relative_blocks'].keys() == y['relative_blocks'].keys())
        stable = same
        errors = []
        # A failed/partial role cannot establish a complete reusable local result.
        if same:
            for cid in structure['versions'][before]['units'][key]['chunk_ids']:
                units = [u for u in parent['units'] if u.get('source_chunk_id') == cid]
                if any(len([u for u in units if u['stage'] == stage and u['status'] == 'succeeded'
                            and u.get('response', {}).get('done') is True
                            and u['response'].get('done_reason') in {'stop', 'eos', 'end_turn'}]) != 1
                       for stage in (*autoschema.ROLES, 'direct_definitions')):
                    same = False
                errors.extend(dict(claim_id=c['id'], extraction_error=c.get('extraction_error'),
                    scope_errors=c.get('interpretation', {}).get('errors', []))
                    for c in parent['claims'] if c['chunk_id'] == cid
                    and (c.get('extraction_error') or c.get('interpretation', {}).get('errors')))
                if errors:
                    same = False
        mapping = dict(globals_map)
        if same:
            mapping.update({bid: y['relative_blocks'][path] for path, bid in x['relative_blocks'].items()})
        result.append(dict(unit_key=key, before_block_ids=x['block_ids'] if x else [],
            after_block_ids=y['block_ids'] if y else [], block_bindings=mapping if same else {},
            action='add_source' if not x else 'remove_source' if not y else 'rebind_source' if same else
                'unresolved_source' if stable else 'rebuild_source',
            prior_input_errors=errors,
            reason='verified_same_explicit_unit_and_full_global_context' if same else
                'unchanged_input_has_incomplete_extraction_or_scope; no_automatic_retry' if stable else
                'new_or_changed_local_structure_or_global_context_or_incomplete_extraction'))
    return result


def project(value, mapping):
    """Project verified addresses only; callers still compare the entire rendered input."""
    import re
    if isinstance(value, dict):
        return {project(k, mapping): project(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [project(v, mapping) for v in value]
    if isinstance(value, str) and mapping:
        return re.sub('|'.join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)),
                      lambda m: mapping[m.group()], value)
    return value


def extraction_request(run, chunk, stage):
    from . import business_run
    if stage in autoschema.ROLES:
        return business_run.extraction_request(run, chunk, stage)
    return business_run.json_request(run, stage, business_run.DEFINITION_INSTRUCTION,
        dict(blocks=autoschema.source_packet(chunk['blocks'])), business_run.Definitions)


def bind_claims(service, db, parent, run, plan):
    from . import business_run
    mappings, receipts, proofs, carried = {}, [], [], []
    old_chunks = {c['id']: c for c in parent['chunks']}
    old_claims = {c['id']: c for c in parent['claims']}
    for action in plan['source_units']:
        if action['action'] != 'rebind_source':
            continue
        block_map = action['block_bindings']
        mappings.update(block_map)
        old_ids = parent['source_structure']['versions'][plan['request']['before_version_id']]['units'][action['unit_key']]['chunk_ids']
        for cid in old_ids:
            old = old_chunks[cid]
            matches = [c for c in run['chunks'] if len(c['blocks']) == len(old['blocks']) and all(
                block_map.get(x['id']) == y['id'] and x['text'] == y['text']
                and x.get('span') == y.get('span') and x.get('context_only', False) == y.get('context_only', False)
                for x, y in zip(old['blocks'], c['blocks']))]
            if len(matches) != 1:
                raise ValueError('절의 실제 물리 입력 구간이 일대일로 대응하지 않습니다.')
            new = matches[0]
            address_map = {**block_map, old['id']: new['id'],
                old['source_version_id']: new['source_version_id']}
            for x, y in zip(old['blocks'], new['blocks']):
                if x.get('parse_run_id') != y.get('parse_run_id'):
                    address_map[x['parse_run_id']] = y['parse_run_id']
            mappings.update(address_map)
            for stage in (*autoschema.ROLES, 'direct_definitions'):
                units = [u for u in parent['units'] if u.get('source_chunk_id') == cid and u['stage'] == stage
                         and u['status'] == 'succeeded']
                if len(units) != 1:
                    raise ValueError('절의 원래 실제 추출 응답이 유일하지 않습니다.')
                unit = units[0]
                options = run['recipe']['options']
                limits = dict(max_tokens=options['review_tokens' if stage == 'direct_definitions' else 'extraction_tokens'],
                              context_tokens=options['context_tokens'], think=options['think'])
                config = dict(model=run['recipe']['models']['review' if stage == 'direct_definitions' else 'draft'],
                    generation=run['recipe']['generation'], identity=run['model_identity'], temperature=0, timeout=options['timeout'])
                if (unit.get('request_configuration') != config
                        or unit.get('requested_limits') != unit.get('executed_limits') or unit.get('executed_limits') != limits):
                    raise ValueError('원래 절 추출 실행의 모델·입력 한도 계약을 확인할 수 없습니다.')
                old_request = extraction_request(parent, old, stage)
                new_request = extraction_request(run, new, stage)
                if any(unit.get(k) != old_request[k] for k in ('messages', 'schema', 'reference_map')):
                    raise ValueError('절의 원래 실제 추출 요청과 현재 재현 계약이 다릅니다.')
                if any(project(old_request[k], address_map) != new_request[k] for k in ('messages', 'schema', 'reference_map')):
                    raise ValueError('새 주소로 연결한 실제 추출 입력이 달라 지역 재추출이 필요합니다.')
                original, rebound = [], []
                if stage in autoschema.ROLES:
                    valid, rejected = autoschema.partition(unit['response']['parsed'], stage)
                    if rejected:
                        raise ValueError('불완전 추출 응답을 새 주소로 연결할 수 없습니다.')
                    for row in valid:
                        for chunk, dest, recipe in ((old, original, parent['recipe']), (new, rebound, run['recipe'])):
                            dest.append(autoschema.graph_record(chunk, stage, row['value'], row['index'],
                                scope=row['scope'], scope_required=True,
                                scope_contract=recipe.get('scope_contract', autoschema.SCOPE_CONTRACT)))
                else:
                    for n, definition in enumerate(unit['response']['parsed']['definitions']):
                        raw = dict(Head=definition['term'], Relation='정의', Tail=definition['definition'])
                        existing = old_claims.get(autoschema.identifier('claim', [old['id'], 'direct_definition', n, raw]))
                        if existing is None:
                            raise ValueError('정의 응답의 원래 저장 후보를 확인할 수 없습니다.')
                        original.append(dict(autoschema.graph_record(old, 'direct_definition', raw, n), evidence=deepcopy(existing['evidence'])))
                        rebound.append(dict(autoschema.graph_record(new, 'direct_definition', raw, n),
                            evidence=business_run.exact_evidence(project(existing['evidence'], address_map), new['blocks'])))
                role = 'direct_definition' if stage == 'direct_definitions' else stage
                stored = [c for c in parent['claims'] if c['chunk_id'] == cid and c['role'] == role]
                if {c['id'] for c in stored} != {c['id'] for c in original}:
                    raise ValueError('원래 응답과 저장 후보의 누락·중복 없는 대응이 필요합니다.')
                for x, y in zip(original, rebound):
                    if any(old_claims[x['id']].get(k) != v for k, v in x.items()
                           if k not in {'review_status', 'semantic_status'}):
                        raise ValueError('원래 추출 결과와 저장 후보가 달라 재연결할 수 없습니다.')
                    carried.append(y); mappings[x['id']] = y['id']
                    receipts.append(dict(before_claim_id=x['id'], after_claim_id=y['id'],
                        donor_run_id=parent['id'], stored_unit_id=unit['id'], approval_inherited=False))
                    for a, b in zip(x.get('interpretation', {}).get('meanings', []), y.get('interpretation', {}).get('meanings', [])):
                        mappings[a['id']] = b['id']
                proofs.append(dict(donor_run_id=parent['id'], stored_unit_id=unit['id'],
                    before_chunk_id=old['id'], after_chunk_id=new['id'], stage=stage,
                    stored_messages_sha256=concept_work.digest(unit['messages']),
                    projected_messages_sha256=concept_work.digest(new_request['messages'])))
    return carried, mappings, receipts, proofs
