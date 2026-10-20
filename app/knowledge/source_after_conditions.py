"""Read stored B '후' fields verbatim; exact addresses never approve their meaning."""
from copy import deepcopy
from hashlib import sha256
import json
import re

from . import autoschema, source_timing_consumer as timing
from .source_list_comparison import parse_field
from .source_list_service import ADDRESS, Sources, fragment

CONTRACT = 'stored-after-condition-fields-v1'
LABEL = '저장 모델이 반환한 조건/행위, 의미·대상 연결 미확정'


def read_view(snapshot, run_id=None):
    """An in-memory source read view; never store a replacement approval snapshot."""
    versions = snapshot.get('source_versions', snapshot.get('source_version_ids'))
    if (not isinstance(versions, (dict, list)) or not versions or len(set(versions)) != len(versions)
            or not isinstance(snapshot.get('blocks'), list) or not snapshot['blocks']
            or len({b['id'] for b in snapshot['blocks']}) != len(snapshot['blocks'])
            or any(b['source_version_id'] not in versions for b in snapshot['blocks'])):
        raise ValueError('저장 B의 출처 버전·블록 범위가 유일하지 않습니다.')
    return dict(snapshot, kind='stored_conditions', run_id=run_id,
                source_versions=list(versions), claims=[], concepts=[], assessments={},
                requirements=snapshot.get('requirements', []), human_approval=False)


def input_digest(service, db, snapshot_id, run_id):
    values = [service.repository.get(db, table, identifier)
              for table, identifier in [('snapshots', snapshot_id), ('runs', run_id)]]
    return sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def unchanged(service, db, run):
    spec = run['query']['stored_after_conditions']
    return run['stored_after_input_digest'] == input_digest(service, db, run['snapshot_id'], spec['run_id'])


def stored_items(sources, context):
    views, items, versions = {}, {}, set()
    for row in context['context']:
        if row['id'] in views:
            raise ValueError('제공 문맥 ID가 중복됩니다.')
        views[row['id']] = sources.exact(dict(row['source_reference'], quote=row['text']))
    for source in context['sources']:
        version = source['source_version_id']
        if version not in sources.versions or version in versions:
            raise ValueError('저장 목록 버전이 중복되거나 미등록입니다.')
        versions.add(version)
        rows = source['items']
        parents = {row['source_ref'] for row in rows}
        if len(parents) != 1:
            raise ValueError('전체 목록 부모가 단일하지 않습니다.')
        parent = views[next(iter(parents))]
        if parent['source_version_id'] != version:
            raise ValueError('저장 목록의 출처 버전이 다릅니다.')
        # The existing literal parser also accepts the frozen MFDS preamble.
        prefix = re.match(r'재료:\s*', parent['quote'])
        field = dict(parent)
        if prefix:
            field.update(start_char=parent['start_char'] + prefix.end(), quote=parent['quote'][prefix.end():].rstrip())
            field['end_char'] = field['start_char'] + len(field['quote'])
        actual = parse_field(field, list(sources.blocks.values()))
        if actual['status'] != 'ready' or len(rows) != len(actual['items']):
            raise ValueError('저장 항목 수와 전체 원문 목록 계산이 다릅니다.')
        for row, item in zip(rows, actual['items']):
            if row['id'] in items:
                raise ValueError('저장 항목 ID가 중복됩니다.')
            for role in ('entry', 'name', 'quantity'):
                ref = item[role]
                if (row[role+'_span'] != [ref['start_char'], ref['end_char']]
                        or role != 'entry' and row[role] != ref['quote']):
                    raise ValueError('저장 목록 값·위치가 원문과 다릅니다.')
            items[row['id']] = dict(row, source_version_id=version, evidence=item['name'])
    if versions != sources.versions:
        raise ValueError('snapshot과 저장 목록의 전체 버전이 다릅니다.')
    return items


def assemble(service, db, request, snapshot):
    spec = request.stored_after_conditions
    b, unit, context, output = timing.stored(service, db, snapshot, spec.run_id, spec.unit_id, 'source_step_conditions')
    systems = [m['content'] for m in unit['messages'] if m.get('role') == 'system']
    if (len(systems) != 1 or sha256(systems[0].encode()).hexdigest() != timing.INSTRUCTION_SHA256
            or (b.get('condition_validation') or {}).get('version') != timing.PRODUCER):
        raise ValueError('지원하는 저장 B 생산 계약이 아닙니다.')
    limits, options, response = unit['requested_limits'], b['recipe']['options'], unit['response']
    config = unit['request_configuration']
    if (limits != unit['executed_limits']
            or limits != dict(max_tokens=options['review_tokens'], context_tokens=options['context_tokens'], think=options['think'])
            or response['model'] != b['recipe']['models']['review'] or response['provider'] != b['recipe']['generation']['provider']
            or config['model'] != response['model'] or config['generation'] != b['recipe']['generation']
            or config['identity'] != b['model_identity'] or config['timeout'] != options['timeout']
            or response.get('stage') != 'source_step_conditions' or response.get('done') is not True
            or response.get('done_reason') != 'stop'):
        raise ValueError('저장 B의 실행 한도·종료 기록이 다릅니다.')
    try:
        autoschema.jsonschema.validate(response['parsed'], unit['schema'])
    except autoschema.jsonschema.ValidationError as exc:
        raise ValueError('저장 B 응답이 저장 출력 schema와 다릅니다.') from exc
    sources = Sources(service, db, snapshot)
    if set(b.get('input_version_ids', [])) != sources.versions:
        raise ValueError('저장 B 실행과 snapshot의 입력 버전이 다릅니다.')
    items = stored_items(sources, context)
    steps = timing.step_views(sources, context)
    titles = {}
    for version in sources.versions:
        registered = service.repository.get(db, 'versions', version)
        titles[version] = service.repository.get(db, 'sources', registered['source_id']).get('title') or '출처 이름 미기록 ('+version+')'
    if (set(context) != {'sources', 'context', 'method_steps', 'method_prefixes'}
            or set(unit['schema']['properties']) != set(steps) or set(unit['schema']['required']) != set(steps)
            or not isinstance(output, dict) or set(output) != set(steps)):
        raise ValueError('저장 B의 전체 단계 계약이 다릅니다.')
    references, sections, records, not_consumed = {}, [], [], []

    def cite(ref):
        identifier = autoschema.identifier('passage', {k:ref[k] for k in ADDRESS})
        references[identifier] = {k:ref[k] for k in ADDRESS}
        return identifier

    for sid, step in steps.items():
        groups = output[sid]['groups']
        keys = [(g['kind'], g['condition_quote'], g['action_quote']) for g in groups]
        for index, group in enumerate(groups):
            row = dict(original_run_id=b['id'], original_unit_id=unit['id'], step_ref=sid,
                       method_ref=step['method_ref'], ordinal=step['ordinal'], group_index=index,
                       source_version_id=step['evidence']['source_version_id'], raw=deepcopy(group),
                       semantic_status='unverified', target_link_status='unverified_stored_model_suggestion',
                       human_approval=False, label=LABEL, step_unresolved_reason=output[sid]['unresolved_reason'])
            row['source_title'] = titles[row['source_version_id']]
            selected = group['kind'] == 'action_timing' and group['condition_quote'].endswith('후')
            try:
                key = (group['kind'], group['condition_quote'], group['action_quote'])
                if keys.count(key) != 1:
                    raise ValueError('동일 조건·행위 역할이 중복됩니다.')
                parent = fragment(sources, step['evidence'], group['quote'])
                evidence = dict(step=step['evidence'], quote=parent)
                for role in ('condition', 'action', 'connector'):
                    if group[role+'_quote']:
                        evidence[role] = fragment(sources, parent, group[role+'_quote'])
                targets = []
                if len({t['item_ref'] for t in group['targets']}) != len(group['targets']):
                    raise ValueError('반환 대상 후보가 중복됩니다.')
                for target in group['targets']:
                    item = items[target['item_ref']]
                    if item['source_version_id'] != row['source_version_id']:
                        raise ValueError('반환 대상 후보가 다른 원문 목록에 있습니다.')
                    targets.append(dict(item_ref=target['item_ref'], quote=target['quote'],
                        evidence=fragment(sources, parent, target['quote']), item_evidence=item['evidence'],
                        link_status='unverified_stored_model_suggestion'))
                related = group['related_item_refs']
                if len(set(related)) != len(related) or any(items[i]['source_version_id'] != row['source_version_id'] for i in related):
                    raise ValueError('관련 항목 후보가 중복되거나 다른 원문입니다.')
                literal = [fragment(sources, parent, q) for q in group['reference_quotes']]
                row.update(evidence=evidence, targets=targets, literal_references=literal,
                           status='stored_after_fields' if selected else 'not_consumed_not_absence')
                if selected:
                    if not {'condition', 'action'} <= set(evidence):
                        raise ValueError('저장 조건·행위 인용이 비어 있습니다.')
                    citations = list(dict.fromkeys(cite(ref) for ref in [*evidence.values(),
                        *[ref for t in targets for ref in (t['evidence'], t['item_evidence'])], *literal]))
                    sections.append(dict(kind='stored_after_condition', text='출처: '+row['source_title']+' · '+str(step['ordinal'])+'단계\n'+LABEL+'\n저장 모델이 반환한 조건: '+group['condition_quote']
                        +'\n저장 모델이 반환한 행위: '+group['action_quote']+'\n반환 대상 후보(연결 미확정): '
                        +(', '.join(t['quote'] for t in targets) or '반환 없음')+'\n부모 원문: '+parent['quote'],
                        citations=citations, **{k:row[k] for k in ('original_run_id', 'original_unit_id', 'step_ref',
                            'source_title', 'source_version_id', 'ordinal', 'group_index', 'semantic_status', 'target_link_status', 'human_approval')}))
            except (ValueError, KeyError, TypeError) as exc:
                row.update(status='unresolved', reason=str(exc))
            (records if selected else not_consumed).append(row)
    consumer = dict(contract=CONTRACT, label=LABEL, original_run_id=b['id'], original_unit_id=unit['id'],
                    original_validation=deepcopy(b.get('condition_validation')), records=records, not_consumed=not_consumed,
                    semantic_status='unverified', human_approval=False, empty_not_absence=True)
    limits = [LABEL, '저장된 B의 후 조건 필드만 표시합니다. 미소비·누락은 조건 부재가 아니며 새 행위나 대상 동일성을 추론하지 않습니다.']
    return dict(answer=dict(answer='\n\n'.join(s['text'] for s in sections) or '전달 가능한 저장 후 조건이 없습니다. '+LABEL, choice=None,
                    sections=sections, citations=list(references), limitations=limits),
                source_reference_map=references, after_condition_consumer=consumer)
