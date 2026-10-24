"""Consume stored leading timing clauses; no producer, search, or model dependency."""
from copy import deepcopy
from hashlib import sha256
import json
import re

from .source_meanings import remap

CONTRACT = 'stored-leading-step-timing-v1'
PRODUCER = 'source-numbered-steps-conditions-B-v1'
INSTRUCTION_SHA256 = 'c527f1457cbf7fa4edccda4372615bccc06e1a2d297925389be92d86c79ca897'


def stored(service, db, snapshot, run_id, unit_id, stage):
    run = service.repository.get(db, 'runs', run_id)
    if (not isinstance(run,dict) or not isinstance(run.get('query'),dict)
            or run.get('kind') != 'business_query' or run.get('snapshot_id') != snapshot['id']
            or run.get('query', {}).get('snapshot_id') != snapshot['id']
            or run.get('status') not in {'succeeded', 'partial'}):
        raise ValueError('저장 시점과 동일한 종료 snapshot 실행이 필요합니다.')
    if not isinstance(run.get('units'),list) or any(not isinstance(u,dict) for u in run['units']):
        raise ValueError('저장 unit 목록 형식이 다릅니다.')
    units = [u for u in run['units'] if u.get('id') == unit_id]
    if len(units) != 1 or units[0].get('stage') != stage or units[0]['status'] != 'succeeded':
        raise ValueError('저장 응답 unit의 실행 계약이 다릅니다.')
    unit = units[0]; response = unit['response']
    if (not isinstance(response,dict) or not isinstance(response.get('text'),str)
            or response.get('failure_kind') or not response['text'].strip()
            or json.loads(response['text']) != response['parsed']):
        raise ValueError('저장 원시 응답과 parsed가 비어 있거나 다릅니다.')
    if 'raw_response' in response or stage=='source_step_conditions':
        raw=response.get('raw_response')
        if (not isinstance(raw,dict) or not isinstance(raw.get('message'),dict)
                or raw['message'].get('content') != response['text']):
            raise ValueError('공급자 원시 응답과 저장 텍스트가 다릅니다.')
    mapping = unit.get('reference_map')
    if mapping is None: mapping={}
    if not isinstance(mapping,dict) or any(not isinstance(v,str) for v in mapping.values()):
        raise ValueError('저장 참조 별칭 형식이 다릅니다.')
    if len(set(mapping.values())) != len(mapping): raise ValueError('중복된 저장 참조 별칭입니다.')
    reverse = {v:k for k,v in mapping.items()}
    if (not isinstance(unit.get('messages'),list) or any(not isinstance(m,dict)
            or not isinstance(m.get('content'),str) for m in unit['messages'])):
        raise ValueError('저장 메시지 형식이 다릅니다.')
    messages = [m['content'] for m in unit['messages'] if m.get('role') == 'user']
    if len(messages) != 1: raise ValueError('실제 제공 문맥이 단일하지 않습니다.')
    return run, unit, remap(json.loads(messages[0]), reverse), remap(response['parsed'], reverse)


def step_views(sources, context):
    parents = {p['id']: p for p in context['context'] if p['kind'] == 'method'}
    prefixes, steps = {}, {}
    for row in context['method_prefixes']:
        if not isinstance(row,dict) or not isinstance(row.get('source_reference'),dict):
            raise ValueError('단계 머리글 주소 형식이 다릅니다.')
        key = row['method_ref']
        if key in prefixes: raise ValueError('중복된 단계 머리글입니다.')
        prefixes[key] = sources.exact(row['source_reference'])
    for row in context['method_steps']:
        if not isinstance(row,dict) or not isinstance(row.get('source_reference'),dict) or not isinstance(row.get('text'),str):
            raise ValueError('단계 주소 형식이 다릅니다.')
        if row['id'] in steps: raise ValueError('중복된 단계 ID입니다.')
        parent = parents[row['method_ref']]
        ref = sources.exact(row['source_reference'])
        if (ref['quote'] != row['text'] or any(ref[k] != parent['source_reference'][k]
                for k in ('source_version_id','parse_run_id','block_id'))):
            raise ValueError('단계와 실제 제공 부모 원문이 다릅니다.')
        marker = re.match(r'([1-9]\d*)\.\s+', row['text'])
        if type(row['ordinal']) is not int or not marker or int(marker[1]) != row['ordinal']:
            raise ValueError('단계 번호가 원문 번호와 다릅니다.')
        steps[row['id']] = dict(row, evidence=ref)
    if set(prefixes)-set(parents): raise ValueError('제공되지 않은 단계 머리글입니다.')
    for key, parent in parents.items():
        rows = [s for s in steps.values() if s['method_ref'] == key]
        if not rows or [s['ordinal'] for s in rows] != list(range(1,len(rows)+1)):
            raise ValueError('단계의 전수 순서가 다릅니다.')
        cursor = parent['source_reference']['start_char']; parts = []
        for ref in [*([prefixes[key]] if key in prefixes else []), *[s['evidence'] for s in rows]]:
            if (ref['block_id'] != parent['source_reference']['block_id'] or ref['start_char'] != cursor):
                raise ValueError('단계 주소가 겹치거나 누락됐습니다.')
            cursor = ref['end_char']; parts.append(ref['quote'])
        if cursor != parent['source_reference']['end_char'] or ''.join(parts) != parent['text']:
            raise ValueError('단계가 부모 원문 전체를 복원하지 못합니다.')
    return steps


def bind(sources, step, group, items, steps):
    from .source_list_service import fragment
    parent = step['evidence']
    quote = fragment(sources, parent, group['quote'])
    evidence = {role:fragment(sources, quote, group[role+'_quote']) for role in ('condition','action')}
    condition, action = evidence['condition']['quote'], evidence['action']['quote']
    subject = re.match(r'([1-9]\d*)(?:이|가)(?=\s)', condition)
    if (not subject or not condition.endswith('면') or not re.fullmatch(r'[가-힣]+(?:고|다|라|세요)[.!?]?', action)
            or re.search(r'않|아니|없|제외|금지|(?:^|\s)(?:안|못)(?:\s|$)', condition + ' ' + action)):
        raise ValueError('지원하는 번호 참조 조건과 단일 행위 구문이 아닙니다.')
    references = group['reference_quotes']
    if len(references) != 1 or references[0] not in {subject[1], subject[0]}:
        raise ValueError('반환된 번호 참조와 조건 주어가 다릅니다.')
    evidence['reference'] = fragment(sources, quote, references[0])
    evidence['reference_context'] = fragment(sources, quote, subject[0])
    prior = [s for s in steps.values() if s['method_ref'] == step['method_ref']
             and s['ordinal'] == int(subject[1]) and s['ordinal'] < step['ordinal']]
    if len(prior) != 1: raise ValueError('같은 부모의 앞 번호 문맥을 확인하지 못했습니다.')
    evidence['prior_number_context'] = prior[0]['evidence']
    targets = group['targets']
    if (not targets or len({t['item_ref'] for t in targets}) != len(targets)
            or group['connector_quote'] or group['related_item_refs'] or group['unresolved_reason']):
        raise ValueError('대상이 중복되거나 별도 선택·미확정이 섞인 시점입니다.')
    target_refs = []
    for target in targets:
        item = items[target['item_ref']]
        if item['source_version_id'] != parent['source_version_id'] or target['quote'] != item['name']:
            raise ValueError('시점 대상과 목록의 원문 이름·버전이 다릅니다.')
        target_refs.append(fragment(sources, quote, target['quote']))
    target_refs.sort(key=lambda r:r['start_char'])
    pattern = r'\s*(?:와|과|및)\s*'
    names = pattern.join(re.escape(r['quote']) for r in target_refs)
    if not re.fullmatch(re.escape(condition)+r'\s+'+names+r'(?:을|를)\s+'+re.escape(action), quote['quote']):
        raise ValueError('조건·대상·행위의 직접 순서와 범위를 확인하지 못했습니다.')
    prefix = step['text'][:quote['start_char']-parent['start_char']]
    suffix = step['text'][quote['end_char']-parent['start_char']:]
    if not re.fullmatch(r'[1-9]\d*\.\s*',prefix) or suffix and not (suffix[0].isspace() or suffix[0] in '.,;!?'):
        raise ValueError('단계 선두의 독립 시점 구절이 아닙니다.')
    # Conservative tail gate: never truncate a denial, quotation or report into
    # a positive instruction. Other clauses need a separately reviewed contract.
    if (re.search(r'아니|않|못|금지|제외|말라|말아|라고|다고|라며|다며|라는|다는|전해|것은|것이',suffix)
            or any(c in quote['quote']+suffix for c in '\"\'“”‘’')):
        raise ValueError('부정·인용·전언의 후행 범위를 확정할 수 없습니다.')
    evidence['quote'] = quote
    return dict(status='source_linked_stored_timing_record',kind='action_timing',evidence=evidence,
                targets=[dict(item_ref=t['item_ref'], evidence=fragment(sources,quote,t['quote'])) for t in targets],
                semantic_status='unverified',human_approval=False,
                reference_interpretation='literal_number_context_only_not_semantic_resolution')


def consume(service, db, sources, snapshot, spec):
    if spec.timing_run_id is None: return None
    result = dict(contract=CONTRACT,original_run_id=spec.timing_run_id,original_unit_id=spec.timing_unit_id,
                  status='unresolved',records=[],not_consumed=[],errors=[],semantic_status='unverified',human_approval=False)
    try:
        a, _, original, _ = stored(service,db,snapshot,spec.condition_run_id,spec.condition_unit_id,'source_list_conditions')
        b, unit, context, output = stored(service,db,snapshot,spec.timing_run_id,spec.timing_unit_id,'source_step_conditions')
        if (b.get('comparison_role') != PRODUCER or b['model_identity']['review'] != a['model_identity']['review']
                or b['recipe']['generation'] != a['recipe']['generation']):
            raise ValueError('저장 시점 생산 계약이 지원 버전과 다릅니다.')
        systems = [m['content'] for m in unit['messages'] if m.get('role')=='system']
        if len(systems)!=1 or sha256(systems[0].encode()).hexdigest()!=INSTRUCTION_SHA256:
            raise ValueError('저장 시점 지시문 계약이 다릅니다.')
        limits = unit['requested_limits']; options = b['recipe']['options']; response = unit['response']
        configuration = unit['request_configuration']
        if (limits != unit['executed_limits'] or limits != dict(max_tokens=options['review_tokens'],context_tokens=options['context_tokens'],think=options['think'])
                or response['model'] != b['recipe']['models']['review'] or response['provider'] != b['recipe']['generation']['provider']
                or configuration['model'] != response['model'] or configuration['generation'] != b['recipe']['generation']
                or configuration['identity'] != b['model_identity'] or configuration['timeout'] != options['timeout']
                or response.get('stage')!='source_step_conditions' or response.get('done') is not True or response.get('done_reason')!='stop'):
            raise ValueError('저장 시점의 실행 한도·종료 기록이 다릅니다.')
        if (set(context) != set(original)|{'method_steps','method_prefixes'}
                or {k:v for k,v in context.items() if k not in {'method_steps','method_prefixes'}} != original):
            raise ValueError('A와 B의 원문·목록·항목값·위치가 다릅니다.')
        # A has already passed the existing field/item and registered-source checks.
        items = {i['id']:dict(i,source_version_id=s['source_version_id']) for s in original['sources'] for i in s['items']}
        steps = step_views(sources,context)
        if (set(unit['schema']['properties'])!=set(steps) or set(unit['schema']['required'])!=set(steps)
                or not isinstance(output,dict) or set(output)-set(steps)):
            raise ValueError('저장 시점 출력의 단계 계약이 다릅니다.')
        result['original_validation'] = deepcopy(b.get('condition_validation'))
        for sid, step in steps.items():
            if sid not in output or not isinstance(output[sid],dict) or not isinstance(output[sid].get('groups'),list):
                result['errors'].append(dict(step_ref=sid,reason='missing_or_invalid_step')); continue
            groups = output[sid]['groups']
            quotes = [g.get('quote') for g in groups if isinstance(g,dict) and g.get('kind')=='action_timing']
            for index, group in enumerate(groups):
                provenance = dict(step_ref=sid,group_index=index,source_version_id=step['evidence']['source_version_id'])
                if not isinstance(group,dict) or group.get('kind') != 'action_timing':
                    result['not_consumed'].append(dict(provenance,kind=group.get('kind') if isinstance(group,dict) else None,
                                                     status='not_consumed_not_absence')); continue
                try:
                    if quotes.count(group.get('quote')) != 1: raise ValueError('중복된 시점 인용입니다.')
                    record=bind(sources,step,group,items,steps)
                    result['records'].append(dict(record,**provenance))
                except (ValueError,KeyError,TypeError) as exc:
                    result['records'].append(dict(provenance,status='unresolved',reason=str(exc)))
        result['status'] = 'partial' if any(r['status']=='source_linked_stored_timing_record' for r in result['records']) else 'unresolved'
    except (ValueError,KeyError,TypeError) as exc:
        result['errors'].append(dict(reason=str(exc)))
    return result
