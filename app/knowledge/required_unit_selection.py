"""Fix source fact attribution once; request application can only reference those facts."""
from collections import Counter
from copy import deepcopy
import re
from typing import Literal

from pydantic import Field, create_model

from . import autoschema, business_review, business_run
from .business_models import MeaningApplicability, RequirementApplicationCheck
from .source_list_comparison import parse_field
from .source_list_service import Sources

CONTRACT = 'grounded-fact-reference-selection-v1-experimental'
GROUNDING_INSTRUCTION = '원문 사실을 먼저 정리한다. 아직 질문별 필요성이나 비교 결론을 판단하지 않는다.\ninspection_scopes는 질문에서 이미 확인한 서로 다른 대상·속성 범위다. source_property_catalog의 값을 그 값 자체가 나타내는 범위에 연결한다.\nrows는 source_facts의 각 key마다 하나다. facts에는 해당 원문에서 확인한 범위의 값을 property_ref와 scope_id로 연결한다. 범위의 값이 없으면 complete와 빈 facts로 남기고 미확정이면 unresolved와 이유를 남긴다.\n원문 필드 이름, 값, 제목과 부모 문맥을 함께 읽는다. 사실이 비교에 도움을 줄 수 있다는 이유로 그 값 자체의 속성이나 대상을 바꾸지 않는다.\n같은 원문 주소에 여러 속성이 실제로 함께 표현돼 있으면 각 scope에 각각 연결할 수 있다. 문서 전체를 선택했다고 그 안의 모든 속성이 해당 범위의 값이 되지는 않는다.\nidentity_refs는 원문에서 해당 값을 어느 대상에 귀속시키는지 확인하는 주소다. 대상 명칭의 모든 내용이 검사 속성인 것은 아니다.\ncondition_refs에는 그 사실 자체의 조건·예외·시점·AND/OR를 유지한다. condition_state는 not_applicable/selected/unresolved다. 질문의 비교 목적은 원문 성립 조건이 아니다.\n원문·기존 source_facts는 수정하지 않는다. 없는 값이나 새로운 요구를 만들지 않는다. 필요 여부·참고 여부는 후속 단계가 판단한다.\n'
APPLICATION_INSTRUCTION = '각 request_group마다 전체 source_facts의 필요성을 판단하고 facts에 key별 한 결정을 반환한다.\nfixed_source_facts는 앞 단계에서 원문 주소·대상·속성·식별 문맥·조건을 정리한 사실이다. 이 단계는 fact_id와 그 사실을 사용할 현재 요청의 criterion_id만 선택한다.\nuses의 necessity는 necessary/reference/unresolved다. 직접 답하는 값과 비교·판단한계의 전제를 모두 선택할 수 있다. 어떤 비교에 사용해도 원문 사실의 대상·속성은 바뀌지 않는다.\n질문에 직접 답하면 direct_answer, 답변·비교·판단한계에 필요한 기준이면 necessary_premise, 참고이면 background다. 필요한지 모르거나 필요한 사실이 정리되지 않았으면 unresolved이며 참고로 낮추지 않는다.\n전체 질문과 request_quote, question_inspections의 비교 대상을 함께 읽는다. 한계 요청도 레시피와 비교 상품의 사실이 필요할 수 있다. 모든 사실을 필수로 올리지는 않는다.\nproperty_ref, binding_id, 새 속성, 새 조건, requested_fact, required_content, evidence를 생성하지 않는다. 서버가 선택한 fact_id의 원문 사실을 그대로 전달한다.\n같은 key의 사실만 참조한다. 선택이 완료되지 않았으면 selection_state=unresolved다. 근거 있는 불필수는 complete와 빈 uses로 남긴다.\n공개 요청의 필요성과 원문의 전제·AND 관계를 구별한다. source_facts는 수정하지 않는다.\n'


def enabled(run):
    return run.get('required_unit_selection_experiment') == CONTRACT


def split_method(parent):
    """Only sequential top-level N. + whitespace; no content/condition detection."""
    text = parent['text']; stack = []; depths = []
    pairs = {')': '(', ']': '[', '}': '{'}
    for char in text:
        depths.append(len(stack))
        if char in '([{': stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]: raise ValueError('unbalanced_numbered_method')
        elif char in '\"\'': raise ValueError('quoted_numbered_syntax_unresolved')
    if stack: raise ValueError('unclosed_numbered_method')
    markers = [m for m in re.finditer(r'(?<!\S)([1-9]\d*)\.(?=\s)', text) if depths[m.start()] == 0]
    if not markers or [int(m.group(1)) for m in markers] != list(range(1, len(markers)+1)):
        raise ValueError('ambiguous_or_nonsequential_step_numbers')
    base = parent['source_reference']['start_char']
    if parent['source_reference']['end_char'] - base != len(text): raise ValueError('wrong_parent_span')
    def view(a, b):
        return dict(parent['source_reference'], start_char=base+a, end_char=base+b, quote=text[a:b])
    prefix = view(0, markers[0].start()) if markers[0].start() else None
    steps = [dict(ordinal=int(m.group(1)), text=text[m.start():end], source_reference=view(m.start(), end))
             for m, end in zip(markers, [*[x.start() for x in markers[1:]], len(text)])]
    if (prefix['quote'] if prefix else '') + ''.join(s['text'] for s in steps) != text:
        raise ValueError('nonlossless_step_partition')
    return prefix, steps


def contains(parent, child):
    return (all(parent[k] == child[k] for k in ('source_version_id', 'parse_run_id', 'block_id'))
            and parent['start_char'] <= child['start_char'] < child['end_char'] <= parent['end_char'])


def property_catalog(service, meanings, blocks, *, contract=CONTRACT):
    """Literal fields/list boundaries/numbering only; never split a semantic aspect."""
    with service.repository.connect() as db:
        sources = Sources(service, db, dict(blocks=blocks,
            source_versions=list(dict.fromkeys(b['source_version_id'] for b in blocks))))
        refs = {m['key']: [sources.exact(e) for e in business_run.exact_evidence(m['evidence'], blocks)]
                for m in meanings}
        rows, issues = [], []
        def add(ref, kind, label='', parent_ref=None, item_ref=None, **metadata):
            ref = sources.exact(ref)
            owners = [key for key, evidence in refs.items() if any(contains(e, ref) for e in evidence)]
            if not owners:
                return None
            existing = next((p for p in rows if p['source_reference'] == ref and p['kind'] == kind), None)
            if existing:
                return existing['property_ref']
            identifier = 'p' + str(len(rows)+1)
            rows.append(dict(property_ref=identifier, kind=kind, field_label=label,
                item_ref=item_ref or identifier, parent_ref=parent_ref, meaning_keys=owners,
                source_reference=ref, **metadata))
            return identifier
        for block in blocks:
            match = re.match(r'([^:\n]+):[ \t]*', block['text'])
            start = match.end() if match and '\n' not in block['text'].rstrip('\n') else 0
            end = len(block['text'].rstrip())
            if start >= end:
                continue
            ref = dict(source_version_id=block['source_version_id'], parse_run_id=block['parse_run_id'],
                block_id=block['id'], start_char=start, end_char=end, quote=block['text'][start:end])
            label = match[1] if start else ''
            parent = add(ref, 'field' if start else 'source_span', label)
            if parent is None:
                continue
            parsed = parse_field(ref, blocks)
            if parsed['status'] == 'ready':
                for n, item in enumerate(parsed['items'], 1):
                    for role in ('name', 'quantity'):
                        add(item[role], 'item_'+role, label, parent, parent+':item'+str(n))
            if re.search(r'(?<!\S)1\.(?=\s)', ref['quote']):
                try:
                    _, steps = split_method(dict(text=ref['quote'], source_reference=ref))
                    for step in steps:
                        add(step['source_reference'], 'numbered_step', label, parent, ordinal=step['ordinal'])
                except ValueError as exc:
                    issues.append(dict(property_ref=parent, reason=str(exc)))
        for evidence in refs.values():
            for ref in evidence:
                if not any(p['source_reference'] == ref for p in rows):
                    add(ref, 'source_span')
    return dict(contract=contract, properties=rows, issues=issues)


def model_properties(catalog):
    return [dict(**{k:v for k,v in p.items() if k != 'source_reference'},
        source_value=p['source_reference']['quote'],
        **{k:p['source_reference'][k] for k in ('source_version_id', 'parse_run_id', 'block_id')},
        span=[p['source_reference']['start_char'], p['source_reference']['end_char']])
        for p in catalog['properties']]


def criterion_sources(requirement):
    return [dict(field=field, text=text, span=[0, len(text)],
        character_addresses=[[i, char] for i, char in enumerate(text)])
        for field in ('question', 'criterion') if (text := requirement.get(field, ''))]


def inspection_scopes(criteria):
    """Deduplicate identical literal subject/attribute references, not semantic identities."""
    scopes = []
    for inspection in criteria:
        for binding in inspection['bindings']:
            basis = {k: deepcopy(binding[k]) for k in ('subject_ref', 'attribute_ref')}
            if any(all(s[k] == v for k, v in basis.items()) for s in scopes):
                continue
            scopes.append(dict(scope_id='s'+str(len(scopes)+1), **basis,
                question_binding=deepcopy(binding), question_inspection=deepcopy(inspection)))
    return scopes


def grounding_packet(catalog, criteria, meanings, blocks):
    return dict(source_facts=[business_review.application_fact(m) for m in meanings], blocks=blocks,
        source_property_catalog=model_properties(catalog), inspection_scopes=[
            {k: deepcopy(s[k]) for k in ('scope_id', 'subject_ref', 'attribute_ref')}
            for s in inspection_scopes(criteria)])


def grounding_type(catalog, criteria, meanings):
    ref = Literal[tuple(p['property_ref'] for p in catalog['properties'])]
    fact = create_model('GroundedSourceFact', __config__={'extra': 'forbid'},
        property_ref=(ref, ...), scope_id=(Literal[tuple(s['scope_id'] for s in inspection_scopes(criteria))], ...),
        identity_refs=(list[ref], ...), condition_refs=(list[ref], ...),
        condition_state=(Literal['not_applicable', 'selected', 'unresolved'], ...))
    row = create_model('GroundedMeaningFacts', __config__={'extra': 'forbid'},
        key=(Literal[tuple(m['key'] for m in meanings)], ...), state=(Literal['complete', 'unresolved'], ...),
        facts=(list[fact], ...), reason=(str, ...))
    return create_model('SourceFactGrounding', __config__={'extra': 'forbid'},
        rows=(list[row], Field(min_length=len(meanings), max_length=len(meanings))))


def bind_facts(output, catalog, criteria, meanings, blocks):
    properties = {p['property_ref']: p for p in catalog['properties']}
    scopes = {s['scope_id']: s for s in inspection_scopes(criteria)}
    facts, errors, seen = [], [], set()
    for meaning in meanings:
        key = meaning['key']
        rows = [r for r in (output or {}).get('rows', []) if r['key'] == key]
        if len(rows) != 1:
            errors.append(dict(key=key, reason='grounding_missing_or_duplicate_row')); continue
        if rows[0]['state'] != 'complete':
            errors.append(dict(key=key, reason='source_fact_grounding_unresolved'))
        for selected in rows[0]['facts']:
            try:
                prop = properties[selected['property_ref']]; scope = scopes[selected['scope_id']]
                if key not in prop['meaning_keys']:
                    raise ValueError('grounded_property_owner_mismatch')
                identity = (key, selected['property_ref'], selected['scope_id'])
                if identity in seen:
                    raise ValueError('duplicate_grounded_fact')
                seen.add(identity)
                resolved = dict(deepcopy(selected), meaning_key=key,
                    source_reference=business_run.exact_evidence([prop['source_reference']], blocks)[0],
                    criterion_reference=deepcopy(scope['attribute_ref']),
                    question_binding=deepcopy(scope['question_binding']),
                    question_inspection=deepcopy(scope['question_inspection']))
                for field, target in [('identity_refs', 'identity_references'), ('condition_refs', 'condition_references')]:
                    if len(selected[field]) != len(set(selected[field])):
                        raise ValueError('duplicate_context_reference')
                    refs = [properties[r] for r in selected[field]]
                    if any(key not in p['meaning_keys'] or p['source_reference']['source_version_id'] !=
                            prop['source_reference']['source_version_id'] for p in refs):
                        raise ValueError('context_reference_owner_mismatch')
                    resolved[target] = business_run.exact_evidence([p['source_reference'] for p in refs], blocks)
                if (selected['condition_state'] == 'unresolved' or
                        (selected['condition_state'] == 'selected') != bool(selected['condition_refs'])):
                    raise ValueError('source_fact_conditions_unresolved')
                facts.append(dict(fact_id='f'+str(len(facts)+1), **resolved))
            except (ValueError, KeyError) as exc:
                errors.append(dict(key=key, fact=deepcopy(selected), reason=str(exc)))
    if any(r['key'] not in {m['key'] for m in meanings} for r in (output or {}).get('rows', [])):
        errors.append(dict(reason='grounding_outside_source'))
    record = dict(contract=CONTRACT, basis=grounding_packet(catalog, criteria, meanings, blocks),
        scopes=list(scopes.values()), model_output=deepcopy(output), facts=facts, errors=errors,
        ready=not errors, semantic_status='not_assessed')
    record['fingerprint'] = autoschema.identifier(CONTRACT, record)
    return record


def validate_facts(record, catalog, criteria, meanings, blocks):
    expected = bind_facts(record.get('model_output'), catalog, criteria, meanings, blocks)
    if {k:v for k,v in record.items() if k != 'producer_unit_id'} != expected:
        raise ValueError('grounded_facts_source_or_scope_changed')
    if not record['ready']:
        raise ValueError('source_fact_grounding_unresolved')
    return deepcopy(record['facts'])


def model_facts(facts):
    return [dict(**{k: deepcopy(v) for k, v in f.items() if k not in {
        'question_inspection', 'question_binding', 'criterion_reference'}},
        subject_ref=deepcopy(f['question_binding']['subject_ref']),
        attribute_ref=deepcopy(f['question_binding']['attribute_ref'])) for f in facts]


def ground(service, run, requirement, source, blocks):
    from .question_inspection import public_items, validate
    if run.get('source_fact_grounding') is not None:
        raise ValueError('source_fact_grounding_requires_fresh_run')
    criteria = validate(run['question_inspection'], requirement, public_items(run, requirement))
    meanings = source['meanings']  # Fresh selection must not inherit an earlier request's selected subset.
    catalog = property_catalog(service, meanings, blocks)
    output = business_run.json_call(service, run, 'requirement_fact_grounding', GROUNDING_INSTRUCTION,
        grounding_packet(catalog, criteria, meanings, blocks), grounding_type(catalog, criteria, meanings))
    record = bind_facts(output, catalog, criteria, meanings, blocks)
    record['producer_unit_id'] = business_review.response_unit_id(run)
    run['source_fact_grounding'] = record
    business_run.save(service, run)
    return record


def application_type(facts, items, meanings, criteria):
    if not facts:
        raise ValueError('grounded_source_facts_unavailable')
    use = create_model('FixedFactUse', __config__={'extra': 'forbid'},
        fact_id=(Literal[tuple(f['fact_id'] for f in facts)], ...),
        criterion_id=(Literal[tuple(c['criterion_id'] for c in criteria)], ...),
        necessity=(Literal['necessary', 'reference', 'unresolved'], ...))
    fields = {k: (v.annotation, deepcopy(v)) for k, v in MeaningApplicability.model_fields.items()
        if k not in {'item_id', 'required_content', 'evidence'}}
    from .business_models import RequirementLink
    link = create_model('FixedInspectionRequirementLink', __config__={'extra': 'forbid'},
        **{k: (v.annotation, deepcopy(v)) for k, v in RequirementLink.model_fields.items() if k != 'requested_fact'})
    fields['requirement_link'] = (link, ...)
    fields.update(key=(Literal[tuple(m['key'] for m in meanings)], ...),
        selection_state=(Literal['complete', 'unresolved'], ...), uses=(list[use], ...))
    decision = create_model('RequestFactApplicability', __config__={'extra': 'forbid'}, **fields)
    group = create_model('RequestSelectionGroup', __config__={'extra': 'forbid'},
        item_id=(Literal[tuple(i['id'] for i in items)], ...),
        facts=(list[decision], Field(min_length=len(meanings), max_length=len(meanings))))
    return create_model('GroupedRequirementApplication', __base__=RequirementApplicationCheck,
        links=(list[group], Field(min_length=len(items), max_length=len(items))))


def project_output(output, items, meanings):
    if output is None:
        return None, dict(expected_pairs=len(items)*len(meanings), returned_rows=0,
            missing_pairs=[dict(item_id=i['id'], key=m['key']) for i in items for m in meanings],
            duplicate_pairs=[], outside_pairs=[])
    links = [dict(deepcopy(row), item_id=group['item_id']) for group in output['links'] for row in group['facts']]
    counts = Counter((row['item_id'], row['key']) for row in links)
    expected = {(i['id'], m['key']) for i in items for m in meanings}
    trace = dict(expected_pairs=len(expected), returned_rows=len(links),
        missing_pairs=[dict(item_id=i, key=k) for i, k in sorted(expected - counts.keys())],
        duplicate_pairs=[dict(item_id=i, key=k, count=n) for (i, k), n in counts.items() if n > 1],
        outside_pairs=[dict(item_id=i, key=k) for i, k in counts.keys() - expected])
    return dict(links=links, meaning_challenges=deepcopy(output.get('meaning_challenges', []))), trace


def matching_bindings(fact, inspection):
    return [b['binding_id'] for b in inspection['bindings'] if all(
        b[k] == fact['question_binding'][k] for k in ('subject_ref', 'attribute_ref'))]


def bind_selection(link, key, catalog, requirement, blocks, criteria, item_id, grounded):
    by_id = {f['fact_id']: f for f in grounded['facts']}
    selections, issues, seen = [], [], set()
    required = business_review.application_required(link)
    for use in link.get('uses', []):
        try:
            fact = by_id[use['fact_id']]
            if fact['meaning_key'] != key:
                raise ValueError('selected_fact_owner_mismatch')
            inspection = next((c for c in criteria if c['criterion_id'] == use['criterion_id']), None)
            if inspection is None or inspection['item_id'] != item_id:
                raise ValueError('inspection_request_owner_mismatch')
            identity = (use['fact_id'], use['criterion_id'])
            if identity in seen:
                raise ValueError('duplicate_request_fact_use')
            seen.add(identity)
            if use['necessity'] == 'unresolved':
                raise ValueError('fact_use_necessity_unresolved')
            matched = matching_bindings(fact, inspection)
            if not matched and inspection['comparison_kind'] == 'single_target':
                raise ValueError('different_attribute_without_comparison')
            selections.append(dict(deepcopy(fact), necessity=use['necessity'],
                request_inspection=deepcopy(inspection), matching_binding_ids=matched,
                use_relation='same_subject_attribute' if matched else 'comparison_context'))
        except (ValueError, KeyError) as exc:
            issues.append(dict(reason=str(exc), use=deepcopy(use), blocking=use.get('necessity') != 'reference'))
    necessary = [s for s in selections if s['necessity'] == 'necessary']
    decision_pending = required is None or required is False and bool(necessary)
    if decision_pending or required is True and not necessary:
        issues.append(dict(reason='necessity_or_required_selection_unresolved', blocking=True))
    if link.get('selection_state') != 'complete':
        issues.append(dict(reason='unselected_request_scope_pending', blocking=True))
    record = dict(contract=CONTRACT, state=('unresolved' if decision_pending or required is True and not necessary
        else 'partial' if issues else 'complete'), reported_state=link.get('selection_state'), decision_pending=decision_pending,
        catalog_id=autoschema.identifier(CONTRACT, catalog), grounding_fingerprint=grounded['fingerprint'],
        selections=selections, raw_uses=deepcopy(link.get('uses', [])),
        issues=issues, errors=[i['reason'] for i in issues if i['blocking']])
    return dict(selection_record=record, content_kind='request_criteria',
        required_content='\n'.join(dict.fromkeys('검사 기준: '+s['criterion_reference']['quote'] for s in necessary))
            if required is True and necessary and not decision_pending else None,
        inspection_targets=deepcopy(necessary) if required is True and not decision_pending else [],
        evidence=[deepcopy(e) for s in necessary for e in [s['source_reference'], *s['condition_references']]]
            if not decision_pending else [], content_evidence_bound=False)


def bound_targets(source, catalog):
    receipt = source.get('application_history', [{}])[-1]
    if receipt.get('property_selection_contract') != CONTRACT or catalog.get('contract') != CONTRACT:
        raise ValueError('request_selection_contract_unverified')
    items = {i['id']: i for i in receipt['public_answer_items']}
    public = dict(id=receipt['application_context']['id'], revision=receipt['application_context']['revision'],
        **receipt['answer_request'])
    from .question_inspection import validate
    criteria = validate(receipt['inspection_frame'], dict(**receipt['application_context'], **receipt['answer_request']),
        receipt['public_answer_items'])
    grounding = receipt['source_fact_grounding']
    # Rebuild from the recorded producer input; no model output is repaired here.
    validate_facts(grounding, catalog, criteria, grounding['basis']['source_facts'], grounding['basis']['blocks'])
    facts = {f['fact_id']: f for f in grounding['facts']}
    targets, blocked, references = {}, [], []
    for meaning in source['meanings']:
        for application in meaning.get('requirement_applications', []):
            owner = dict(meaning_key=meaning['key'], item_id=application['item_id'])
            record = application.get('selection_record', {})
            references.extend(dict(owner, issue=deepcopy(i)) for i in record.get('issues', []) if not i['blocking'])
            blocked.extend(dict(owner, issue=deepcopy(i)) for i in record.get('issues', []) if i['blocking'])
            required = business_review.application_required(application)
            if (record.get('contract') != CONTRACT or record.get('catalog_id') != autoschema.identifier(CONTRACT, catalog)
                    or record.get('grounding_fingerprint') != grounding['fingerprint']
                    or record.get('decision_pending') is not False or required is None):
                blocked.append(dict(owner, reason='request_selection_pending')); continue
            if required is False:
                continue
            if (not application.get('content_evidence_bound') or application.get('content_source_version')
                    != business_review.required_source_version(source, meaning)):
                blocked.append(dict(owner, reason='selected_request_source_version_unverified')); continue
            for selected in record['selections']:
                if selected['necessity'] != 'necessary':
                    continue
                fact = facts[selected['fact_id']]
                if fact['meaning_key'] != meaning['key'] or any(selected.get(k) != v for k, v in fact.items()):
                    raise ValueError('selected_fixed_fact_changed')
                inspection = next(c for c in criteria if c['criterion_id'] == selected['request_inspection']['criterion_id'])
                matched = matching_bindings(fact, inspection)
                if (inspection != selected['request_inspection'] or inspection['item_id'] != application['item_id']
                        or matched != selected['matching_binding_ids'] or selected['use_relation'] !=
                        ('same_subject_attribute' if matched else 'comparison_context')):
                    raise ValueError('selected_fact_use_changed')
                basis = dict(ref=fact['source_reference'], **{k: deepcopy(fact[k]) for k in (
                    'criterion_reference', 'question_binding', 'question_inspection', 'identity_references',
                    'condition_references', 'condition_state')})
                key = autoschema.identifier('selected_request', basis)
                target = targets.setdefault(key, dict(key=key, **deepcopy(basis), public_requirement=deepcopy(public),
                    request_items=[], required_for=[], request_uses=[], fact_ids=[]))
                if fact['fact_id'] not in target['fact_ids']: target['fact_ids'].append(fact['fact_id'])
                if owner not in target['required_for']: target['required_for'].append(owner)
                if items[application['item_id']] not in target['request_items']:
                    target['request_items'].append(deepcopy(items[application['item_id']]))
                use = dict(owner, fact_id=fact['fact_id'], inspection=deepcopy(inspection),
                    relation=selected['use_relation'], matching_binding_ids=matched)
                if use not in target['request_uses']: target['request_uses'].append(use)
    uses = [u for t in targets.values() for u in t['request_uses'] if u['matching_binding_ids']]
    selected_criteria = {u['inspection']['criterion_id'] for u in uses}
    selected_bindings = {b for u in uses for b in u['matching_binding_ids']}
    return dict(contract=CONTRACT, targets=list(targets.values()), blocked_ranges=blocked,
        criteria_without_necessary_source=[c['criterion_id'] for c in criteria if c['criterion_id'] not in selected_criteria],
        bindings_without_necessary_source=[b['binding_id'] for c in criteria for b in c['bindings']
                                          if b['binding_id'] not in selected_bindings],
        reference_issues=references, whole_requirement_complete=False)
