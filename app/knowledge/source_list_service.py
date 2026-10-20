"""Explicit source-list operation. No retrieval, generation, or semantic approval.

The condition consumer only binds a complete Korean conditional seasoning choice
sentence. Other syntax remains unresolved; stored model omissions are not repaired.
"""
from copy import deepcopy
import json
import re
from time import monotonic

from . import autoschema, business_run, source_meanings
from .source_list_comparison import parse_field, compare_lists
from .service import utcnow

CONTRACT = 'stored-list-condition-addresses-v1'
ADDRESS = ('source_version_id', 'parse_run_id', 'block_id', 'start_char', 'end_char', 'quote')


class Sources:
    def __init__(self, service, db, snapshot):
        self.service, self.db = service, db
        self.blocks = {b['id']: b for b in snapshot['blocks']}
        self.versions = set(snapshot['source_versions'])
        self.parses = {}

    def exact(self, ref):
        if not all(k in ref for k in ADDRESS[:3]) or not ref.get('quote'):
            raise ValueError('출처 주소와 비어 있지 않은 인용이 필요합니다.')
        version, parse, bid = (ref[k] for k in ADDRESS[:3])
        if version not in self.versions or bid not in self.blocks:
            raise ValueError('현재 snapshot에서 사용할 수 없는 원문 주소입니다.')
        key = (version, parse)
        if key not in self.parses:
            registered = self.service.repository.get(self.db, 'versions', version)
            self.service.repository.get(self.db, 'sources', registered['source_id'])
            self.parses[key] = {b['id']: b for b in self.service.parse_blocks(self.db, parse, version)}
        block = self.parses[key].get(bid)
        if (not block or block['text'] != self.blocks[bid]['text']
                or self.blocks[bid]['source_version_id'] != version
                or self.blocks[bid]['parse_run_id'] != parse):
            raise ValueError('등록 원문과 snapshot의 주소가 일치하지 않습니다.')
        text, quote = block['text'], ref['quote']
        start, end = ref.get('start_char'), ref.get('end_char')
        if start is None and end is None:
            if len(list(re.finditer(re.escape(quote), text))) != 1:
                raise ValueError('위치 없는 인용이 부모 원문에서 유일하지 않습니다.')
            start, end = text.index(quote), text.index(quote) + len(quote)
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                or text[start:end] != quote):
            raise ValueError('원문 문자 위치와 인용이 일치하지 않습니다.')
        return dict(source_version_id=version, parse_run_id=parse, block_id=bid,
                    start_char=start, end_char=end, quote=quote, precision='exact')

    def field(self, field):
        ref = self.exact(field.model_dump())
        text = self.blocks[ref['block_id']]['text']
        prefix = field.field_label + ':'
        if not text.startswith(prefix) or '\n' in text.rstrip('\n'):
            raise ValueError('v1은 한 줄 label: value 필드만 지원합니다.')
        start = len(prefix) + len(text[len(prefix):]) - len(text[len(prefix):].lstrip())
        if (ref['start_char'], ref['end_char']) != (start, len(text.rstrip())):
            raise ValueError('목록 필드 값 전체를 정확히 지정해야 합니다.')
        return parse_field(ref, list(self.blocks.values()))


def fragment(sources, parent, quote):
    if not isinstance(quote, str) or not quote or len(list(re.finditer(re.escape(quote), parent['quote']))) != 1:
        raise ValueError('제공된 부모에서 조각이 유일하지 않습니다.')
    start = parent['start_char'] + parent['quote'].index(quote)
    return sources.exact(dict(parent, quote=quote, start_char=start, end_char=start + len(quote)))


def bind_choice(sources, parent, qualification, subject, related):
    """A surface/address contract, never a general entailment verifier."""
    if qualification.get('kind') != 'use_condition' or len(related) != 1:
        raise ValueError('지원 범위 밖의 조건 종류 또는 선택 항목 수입니다.')
    parts = {role: fragment(sources, parent, qualification.get(role + '_quote'))
             for role in ('action', 'condition', 'connector')}
    parts['quote'] = fragment(sources, parent, qualification.get('quote'))
    condition, action, connector = (parts[k] for k in ('condition', 'action', 'connector'))
    if connector['quote'] not in {'이나', '나', '또는', '혹은'}:
        raise ValueError('지원 범위 밖의 선택 연결어입니다.')
    if not condition['quote'].endswith('면'):
        raise ValueError('v1의 명시적 조건 어미가 없습니다.')
    if re.search(r'않|말[고아]|제외|금지|아니|대신|못|없', condition['quote'] + action['quote']):
        raise ValueError('부정·제외 구문은 별도 검토가 필요합니다.')
    a, b = subject['name'], related[0]['name']
    patterns = [re.escape(x) + r'\s*' + re.escape(connector['quote']) + r'\s*' + re.escape(y)
                + r'(?:으로|로)\s+간을 (?:한다|맞춘다)' for x, y in ((a, b), (b, a))]
    if a == b or not any(re.fullmatch(pattern, action['quote']) for pattern in patterns):
        raise ValueError('대상 두 이름과 선택·행위의 표면 연결을 확인할 수 없습니다.')
    if not (action['start_char'] <= connector['start_char'] < connector['end_char'] <= action['end_char']):
        raise ValueError('연결어가 행위 내부에 없습니다.')
    if not (condition['start_char'] <= parts['quote']['start_char'] < parts['quote']['end_char'] <= condition['end_char']):
        raise ValueError('기록된 quote가 조건 부분과 일치하지 않습니다.')
    text = sources.blocks[parent['block_id']]['text']
    start, end = condition['start_char'], action['end_char']
    gap = text[condition['end_char']:action['start_char']]
    if condition['end_char'] > action['start_char'] or not re.fullmatch(r'[\s,]+', gap):
        raise ValueError('조건과 행위가 인접하지 않습니다.')
    # Require the entire sentence: preceding subjects and trailing negation are
    # not silently discarded even when all fragments occur in the same block.
    before = re.split(r'[.!?]\s+|\n', text[:start])[-1].strip()
    after = re.split(r'[.!?](?:\s|$)|\n', text[end:], maxsplit=1)[0].strip()
    if before or after or re.search(r'[.!?]\s|\n', text[start:end]):
        raise ValueError('같은 완전 문장에 속한 조건·행위가 아닙니다.')
    return dict(status='source_linked_stored_model_record', kind=qualification['kind'],
                subject_item_ref=subject['id'], related_item_refs=[related[0]['id']],
                evidence=parts, semantic_status='unverified', human_approval=False)


def stored_conditions(service, db, sources, snapshot, spec, fields):
    prior = service.repository.get(db, 'runs', spec.condition_run_id)
    if (prior.get('snapshot_id') != snapshot['id'] or prior.get('status') in {'queued', 'running', 'cancel_requested'}):
        raise ValueError('같은 snapshot의 종료된 조건 실행이 필요합니다.')
    units = [u for u in prior['units'] if u['id'] == spec.condition_unit_id]
    if len(units) != 1 or units[0].get('stage') != 'source_list_conditions' or units[0]['status'] != 'succeeded':
        raise ValueError('성공한 저장 조건 응답 unit을 선택하세요.')
    unit = units[0]
    response = unit['response']
    if response.get('failure_kind') or json.loads(response['text']) != response['parsed']:
        raise ValueError('저장 원시 응답과 parsed 기록이 일치하지 않습니다.')
    mapping = unit.get('reference_map') or {}
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('저장 참조 별칭이 중복됩니다.')
    reverse = {alias: identifier for identifier, alias in mapping.items()}
    inputs = [json.loads(m['content']) for m in unit['messages'] if m.get('role') == 'user']
    if len(inputs) != 1:
        raise ValueError('단일 실제 제공 문맥이 필요합니다.')
    context = source_meanings.remap(inputs[0], reverse)
    output = source_meanings.remap(response['parsed'], reverse)
    views = {}
    for row in context['context']:
        if row['id'] in views:
            raise ValueError('제공 문맥 ID가 중복됩니다.')
        views[row['id']] = sources.exact(dict(row['source_reference'], quote=row['text']))
    items, by_version = {}, {f['field']['source_version_id']: f for f in fields}
    if len(by_version) != 2 or len(context['sources']) != 2:
        raise ValueError('서로 다른 두 원문 버전 목록이 필요합니다.')
    seen_versions = set()
    for source in context['sources']:
        version = source['source_version_id']
        if version not in by_version or version in seen_versions:
            raise ValueError('저장 목록 원문 버전이 요청과 다릅니다.')
        seen_versions.add(version)
        actual = by_version[version]
        rows = source['items']
        if len(rows) != len(actual['items']):
            raise ValueError('저장 목록 항목 수가 원문 계산과 다릅니다.')
        for row, item in zip(rows, actual['items']):
            parent = views.get(row['source_ref'])
            if not parent or parent['block_id'] != actual['field']['block_id'] or parent['source_version_id'] != version:
                raise ValueError('저장 목록 항목의 출처가 요청과 다릅니다.')
            if row['id'] in items:
                raise ValueError('저장 항목 ID가 중복됩니다.')
            for role in ('entry', 'name', 'quantity'):
                ref = item[role]
                if row[role + '_span'] != [ref['start_char'], ref['end_char']]:
                    raise ValueError('저장 목록 문자 위치가 원문 계산과 다릅니다.')
                if role != 'entry' and row[role] != ref['quote']:
                    raise ValueError('저장 목록 값이 원문 계산과 다릅니다.')
                if not parent['start_char'] <= ref['start_char'] < ref['end_char'] <= parent['end_char']:
                    raise ValueError('목록 항목이 실제 제공 범위를 벗어납니다.')
            items[row['id']] = dict(row, source_version_id=version)
    records = output.get('items', [])
    if len(records) != len(items) or {r['item_ref'] for r in records} != set(items):
        raise ValueError('조건 응답 항목이 중복되거나 누락되었습니다.')
    consumed = []
    for row in records:
        subject = items[row['item_ref']]
        result = dict(item_ref=subject['id'], source_version_id=subject['source_version_id'], name=subject['name'],
                      stored_status=row['status'], status='unresolved', qualifications=[], errors=[])
        for q in row.get('qualifications', []):
            try:
                refs = q.get('related_item_refs', [])
                # The original contract did not require the subject in related.
                if len(refs) != len(set(refs)) or any(r not in items for r in refs):
                    raise ValueError('선택 관련 항목 참조가 중복되거나 제공되지 않았습니다.')
                related = [items[r] for r in refs if r != subject['id']]
                parent = views.get(q.get('evidence_ref'))
                if (row['status'] != 'explicit_qualification' or not parent
                        or parent['source_version_id'] != subject['source_version_id']
                        or any(r['source_version_id'] != subject['source_version_id'] for r in related)):
                    raise ValueError('조건과 항목의 출처가 다르거나 명시적 조건 기록이 아닙니다.')
                result['qualifications'].append(bind_choice(sources, parent, q, subject, related))
            except ValueError as exc:
                result['errors'].append(str(exc))
        if result['qualifications'] and not result['errors']:
            result['status'] = 'source_linked_stored_model_record'
        elif row['status'] == 'not_stated' and not row.get('qualifications'):
            result['status'] = 'stored_not_stated_not_unconditional'
        consumed.append(result)
    return dict(contract=CONTRACT, original_run_id=prior['id'], original_unit_id=unit['id'],
                original_status=prior['status'], original_validation=deepcopy(prior.get('condition_validation')),
                semantic_status='unverified', human_approval=False, completeness='not_verified', records=consumed)


def product_facts(sources, snapshot, bindings, common):
    claims = {c['id']: c for c in snapshot['claims']}
    result, seen = [], set()
    for binding in bindings:
        ids = [binding.type_claim_id, binding.manufacturer_claim_id, binding.storage_claim_id]
        if len(set(ids)) != 3 or any(cid not in claims for cid in ids):
            raise ValueError('서로 다른 현재 snapshot 상품 사실 참조가 필요합니다.')
        typed, maker, storage = [claims[cid] for cid in ids]
        versions = {v for c in (typed, maker, storage) for v in c['source_version_ids']}
        if len(versions) != 1 or any(c.get('superseded_by') or c.get('extraction_error') for c in (typed, maker, storage)):
            raise ValueError('상품 사실은 동일한 유효 원문 버전에 속해야 합니다.')
        version = next(iter(versions)); raw = typed['raw']; name, category = raw.get('Head'), raw.get('Tail')
        if raw.get('Relation') != '식품 유형은' or category not in common or (version, name) in seen:
            raise ValueError('상품 유형이 문자 그대로의 공통 이름과 연결되지 않거나 중복됩니다.')
        seen.add((version, name))
        refs = [sources.exact(e) for c in (typed, maker, storage) for e in c['evidence']]
        if any(r['source_version_id'] != version for r in refs):
            raise ValueError('상품 근거가 다른 원문 버전을 참조합니다.')
        blocks = [b for b in sources.blocks.values() if b['source_version_id'] == version]
        names = [b for b in blocks if b['text'].rstrip() == '제품명: ' + name]
        types = [r for r in refs if r['quote'] == '식품 유형: ' + category]
        mr = maker['raw']
        role = [r for r in refs if r['quote'] == '영업소 구분: 제조원']
        companies = [r for r in refs if r['quote'] == '업체명: ' + str(mr.get('Head'))]
        sr = storage['raw']
        if (len(names) != 1 or len(types) != 1 or len(role) != 1 or len(companies) != 1
                or mr.get('Relation') != '제조원이다' or mr.get('Tail') != name
                or not (sr.get('Head') == name or sr.get('Entity') == [name])):
            raise ValueError('상품 이름·유형·제조원 역할의 원문 연결이 모호합니다.')
        prefixes = [sources.blocks[r['block_id']]['text'][:r['start_char']] for r in (role[0], companies[0])]
        if prefixes[0] != prefixes[1]:
            raise ValueError('제조원과 업체명이 같은 원문 행 그룹에 있지 않습니다.')
        name_block = names[0]
        refs.append(sources.exact(dict(source_version_id=version, parse_run_id=name_block['parse_run_id'],
            block_id=name_block['id'], start_char=0, end_char=len(name_block['text'].rstrip()),
            quote=name_block['text'].rstrip())))
        storage_refs = []
        for e in storage['evidence']:
            ref = sources.exact(e); text = sources.blocks[ref['block_id']]['text']
            label = '보관·취급방법: '
            if label in text and text.count(label) == 1:
                start = text.index(label) + len(label)
                if ref['end_char'] == len(text.rstrip()) and ref['start_char'] <= start:
                    storage_refs.append(sources.exact(dict(ref, start_char=start, quote=text[start:].rstrip())))
        if len(storage_refs) != 1:
            raise ValueError('보관·취급방법 값 전체의 유일한 근거가 필요합니다.')
        refs.extend(storage_refs)
        result.append(dict(name=name, type=category, manufacturer=mr['Head'], storage=storage_refs[0]['quote'],
            source_version_id=version, claim_ids=ids, evidence=refs,
            basis='stored_facts_and_literal_source_fields', semantic_status='unverified'))
    return result


def assemble(service, db, request, snapshot):
    spec = request.list_comparison
    sources = Sources(service, db, snapshot)
    fields = [sources.field(f) for f in spec.fields]
    comparison = compare_lists(*fields)
    if comparison['status'] != 'ready':
        raise ValueError('목록 경계가 모호하여 대조할 수 없습니다.')
    conditions = stored_conditions(service, db, sources, snapshot, spec, fields)
    products = product_facts(sources, snapshot, spec.products, {r['name'] for r in comparison['common']})
    references = {}
    def cite(ref):
        ref = {k: ref[k] for k in ADDRESS}
        identifier = autoschema.identifier('passage', ref)
        references[identifier] = ref
        return identifier
    for field in fields:
        cite(field['field'])
        for item in field['items']:
            for ref in item.values(): cite(ref)
    labels = {}
    for i, field in enumerate(fields, 1):
        version = service.repository.get(db, 'versions', field['field']['source_version_id'])
        source = service.repository.get(db, 'sources', version['source_id'])
        labels[version['id']] = f"{i}번 목록 · {source['title']}"
    sections = []
    def section(kind, text, refs, **metadata):
        sections.append(dict(kind=kind, text=text, citations=list(dict.fromkeys(cite(r) for r in refs)), **metadata))
    section('common', '두 원문 목록에 문자 그대로 함께 등장한 이름: ' + ', '.join(r['name'] for r in comparison['common']),
            [item['name'] for row in comparison['common'] for group in row['occurrences'] for item in group])
    for i, rows in enumerate(comparison['only'], 1):
        version = fields[i-1]['field']['source_version_id']
        section('only', labels[version] + '에만 등장한 이름: ' + ', '.join(r['name'] for r in rows),
                [item['name'] for row in rows for item in row['occurrences']], source_version_id=version)
    rendered = set()
    for row in conditions['records']:
        for q in row['qualifications']:
            for ref in q['evidence'].values(): cite(ref)
            key = tuple(cite(q['evidence'][k]) for k in ('condition', 'action'))
            if key not in rendered:
                rendered.add(key)
                version = row['source_version_id']
                section('stored_condition', labels[version] + '의 원문에서 연결된 조건: '
                        + q['evidence']['condition']['quote'] + ' → ' + q['evidence']['action']['quote'],
                        list(q['evidence'].values()), source_version_id=version,
                        item_refs=[q['subject_item_ref'], *q['related_item_refs']], semantic_status='unverified')
    for product in products:
        for ref in product['evidence']: cite(ref)
        section('product', f"{product['name']} — 식품 유형: {product['type']}; 제조원: {product['manufacturer']}; 보관·취급방법 원문: {product['storage']}",
                product['evidence'], source_version_id=product['source_version_id'], claim_ids=product['claim_ids'])
    limits = ['지정한 두 원문에서 같은 이름으로 기재된 재료를 대조했습니다. 모두 항상 필수라는 뜻은 아닙니다.',
              '조건은 원문 문구의 연결을 확인한 결과입니다. 전체 조건 해석의 정확성이나 사람의 승인을 뜻하지 않습니다.',
              '조건을 확인하지 못한 항목이 조건 없음을 뜻하지는 않습니다. 나머지 조건·예외는 확인이 필요합니다.',
              '동의어 관계, 특정 상품의 지정·대체 가능성·공급 계약은 확인하지 않았습니다.']
    return dict(answer=dict(answer='\n\n'.join(s['text'] for s in sections), choice=None,
                           citations=list(dict.fromkeys(c for s in sections for c in s['citations'])),
                           sections=sections, limitations=limits),
                source_reference_map=references, list_comparison=dict(fields=fields, comparison=comparison),
                condition_consumer=conditions, product_facts=products)


def execute(service, run, request, snapshot, requirements):
    from .business_use import restricted_sources
    from .business_changes import snapshot_invalidations
    started = monotonic()
    try:
        with service.repository.connect() as db:
            result = assemble(service, db, request, snapshot)
        with service.lock, service.repository.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            live = service.repository.get(db, 'runs', run['id'])
            restrictions = restricted_sources(db, snapshot['source_versions'])
            stale = [r['id'] for r in requirements if
                (current := service.repository.get(db, 'requirements', r['id']))['revision'] != r['revision']
                or current['status'] == 'needs_review']
            original = service.repository.get(db, 'runs', snapshot['run_id'])
            invalidations = snapshot_invalidations(service, db, snapshot, original)
            events = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM snapshot_events')]
            corrections = [e for e in events if e.get('event') == 'business_correction' and e['snapshot_id'] == snapshot['id']]
            if live['status'] == 'cancel_requested' or service.closed:
                run.update(status='cancelled', answer=None, answer_status='cancelled')
            elif restrictions or stale or any(i not in run['snapshot_invalidations'] for i in [*corrections, *invalidations]):
                run.update(status='partial', answer=None, answer_status='needs_review', restrictions=restrictions,
                           stale_requirement_ids=stale)
            else:
                run.update(result, status='succeeded', answer_status='partial',
                    provided_ids=list(result['source_reference_map']), retrieval=[],
                    answer_basis='explicit_source_lists_and_stored_condition_records', answer_contract=CONTRACT)
                run['execution_boundary'].update(answer_contract=CONTRACT,
                    new_model_calls=0, new_retrieval_calls=0, semantic_approval=False,
                    condition_support='complete_conditional_binary_seasoning_sentence_only_v1')
            run['finished_at'] = utcnow(); run['metrics']['elapsed_s'] = monotonic() - started
            service.repository.save(db, 'runs', run)
    except Exception as exc:
        with service.lock, service.repository.connect() as db:
            run.update(status='failed', answer=None, answer_status='unverified', finished_at=utcnow(),
                       error=f'{type(exc).__name__}: {exc}')
            run['metrics']['elapsed_s'] = monotonic() - started
            service.repository.save(db, 'runs', run)
        raise
    return dict(run_id=run['id'], snapshot_id=snapshot['id'], status=run['answer_status'],
                answer=run.get('answer'), source_reference_map=run.get('source_reference_map', {}),
                condition_consumer=run.get('condition_consumer'), list_comparison=run.get('list_comparison'),
                product_facts=run.get('product_facts', []), execution_boundary=run['execution_boundary'], qa_model_called=False)
