"""Select source-literal participants without changing the proposed proposition."""
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, Field, create_model

from . import autoschema
from .business_checkpoint import digest

CONTRACT = 'source-literal-event-participant-v1'
FROZEN = ('meaning_key', 'target_id', 'conditions', 'exceptions', 'period', 'references', 'evidence')


class ParticipantChoice(BaseModel):
    model_config = {'extra': 'forbid'}
    proposal_index: int
    entity_index: int = Field(ge=0)
    evidence_index: int = Field(ge=0)
    literal: str = Field(min_length=1)
    reason: str = Field(min_length=1)


def original_refs(patch, blocks):
    from .business_run import exact_evidence, contiguous_evidence_views
    refs = exact_evidence(patch['evidence'], blocks)
    for item, ref in zip(patch['evidence'], refs):
        if 'start_char' in item and 'end_char' in item:
            continue
        positions = set()
        for view in contiguous_evidence_views(blocks, ref['block_id']):
            if view['source_version_id'] != ref['source_version_id'] or (view.get('parse_run_id') or view.get('run_id')) != ref['parse_run_id']:
                continue
            offset = 0
            while (at := view['text'].find(item['quote'], offset)) >= 0:
                positions.add(view['span'][0] + at)
                offset = at + 1
        if len(positions) != 1:
            raise ValueError('원제안 근거 인용의 위치가 유일하지 않음')
    return refs


def address(literal, refs, evidence_index, blocks):
    from .business_run import exact_evidence
    if type(evidence_index) is not int or not 0 <= evidence_index < len(refs) or not isinstance(literal, str) or not literal:
        raise ValueError('선택한 제안 근거 밖 참여자')
    parent = refs[evidence_index]
    positions = []
    offset = 0
    while (at := parent['quote'].find(literal, offset)) >= 0:
        positions.append(at)
        offset = at + 1
    if len(positions) != 1:
        raise ValueError('선택 원문 내 참여자가 없거나 중복됨')
    start = parent['start_char'] + positions[0]
    ref = dict(parent, quote=literal, start_char=start, end_char=start + len(literal))
    if exact_evidence([ref], blocks) != [ref]:
        raise ValueError('참여자의 정식 원문 버전·파싱·위치 불일치')
    return ref


def validate(claim, blocks):
    binding = claim['literal_grounding']
    original = binding['unverified_proposal']
    if (binding['contract'] != CONTRACT or digest(original) != binding['proposal_sha256']
            or claim['role'] != 'event_entity' or claim['raw']['Event'] != original['raw']['Event']
            or claim['statement'] != original['raw']['Event']
            or any(claim[k] != original[k] for k in ('conditions', 'exceptions', 'period', 'references'))):
        raise ValueError('참여자 선택에서 원제안 명제·조건 변경')
    refs = original_refs(original, blocks)
    if (refs != binding['original_evidence'] or claim['evidence_context'] != refs or claim['evidence'] != refs
            or claim['source_version_ids'] != sorted({r['source_version_id'] for r in refs})):
        raise ValueError('원제안의 근거 범위 변경')
    choices = binding['choices']
    if (len(choices) != len(original['raw']['Entity']) or any(type(c['entity_index']) is not int or c['entity_index'] < 0 for c in choices) or
            [c['entity_index'] for c in choices] != list(range(len(choices)))):
        raise ValueError('참여자 인덱스 누락·중복')
    participants = [address(c['literal'], refs, c['evidence_index'], blocks) for c in choices]
    if (claim['raw']['Entity'] != [c['literal'] for c in choices]
            or claim['edit_participants'] != participants):
        raise ValueError('선택 참여자와 실제 후보·주소 불일치')
    return participants


def select(service, run, output, blocks, allowed_keys):
    from . import business_run as execution
    tasks = {}
    for index, patch in enumerate(output['patches']):
        if patch.get('meaning_key') not in allowed_keys or patch.get('target_id') is not None or patch.get('role') != 'event_entity':
            continue
        try:
            execution.recovered_statement_patch(patch, blocks)
        except ValueError as exc:
            if str(exc) != '복구 참여자가 선택한 정확 원문 인용에서 유일하지 않음':
                continue
            try:
                refs = original_refs(patch, blocks)
            except ValueError:
                continue
            tasks[index] = dict(unverified_proposal=deepcopy(patch), original_evidence=refs)
    if not tasks:
        return output
    choice = create_model('SelectedParticipant', __base__=ParticipantChoice,
        proposal_index=(Literal[tuple(tasks)], Field(...)))
    result_type = create_model('LiteralParticipants',
        choices=(list[choice], Field(...)), unresolved=(list[int], Field(...)))
    selected = execution.json_call(service, run, 'source_literal_participants',
        '''각 미검증 제안의 Event와 조건·예외·기간·참조·근거 범위를 그대로 유지한다.
기존 Entity와 그 행위자 역할은 정답이 아니다. Event에 실제 참여하는 행위자 또는 영향을 받는 대상의 원문 표현을 선택한다.
각 원래 Entity 인덱스에 대해 그 제안의 original_evidence[evidence_index] 안에 유일하게 있는 literal을 복사한다.
단지 원문에 있는 명사는 불충분하다. 고정된 Event와 조건 아래 실제 참여 관계를 원문이 지지해야 한다.
Entity가 바뀌면 표현·참여 대상 변경이며 같은 행위자의 주소 복원이라고 주장하지 않는다.
누락·중복·새 참여자 추가를 금지한다. 확정 못한 제안은 전체를 unresolved로 둔다. reason에 선택한 참여 관계와 변경을 설명한다.
Scope 등 이전 제안 해석은 승인되지 않았다. 새 명제·정답·주소를 만들지 않는다.''',
        dict(proposals=[dict(proposal_index=i, **task) for i, task in tasks.items()]), result_type)
    result = deepcopy(output)
    receipt = dict(unit_id=run['units'][-1]['id'], output=selected, errors=[])
    result['participant_selection'] = receipt
    if not selected:
        return result
    for index, task in tasks.items():
        try:
            choices = sorted([c for c in selected['choices'] if c['proposal_index'] == index], key=lambda c:c['entity_index'])
            original = task['unverified_proposal']
            if index in selected['unresolved'] or [c['entity_index'] for c in choices] != list(range(len(original['raw']['Entity']))):
                raise ValueError('참여자 선택 미해소·누락·중복')
            participants = [address(c['literal'], task['original_evidence'], c['evidence_index'], blocks) for c in choices]
            patch = deepcopy(original)
            patch['raw']['Entity'] = [c['literal'] for c in choices]
            patch = execution.recovered_statement_patch(patch, blocks)
            # Both the selected address and the general recovery uniqueness guard must agree.
            if patch['server_participants'] != participants:
                raise ValueError('제안 전체 근거의 유일한 참여자 주소와 불일치')
            patch['literal_grounding'] = dict(contract=CONTRACT, **task, proposal_sha256=digest(original),
                choices=choices, selection_unit_id=receipt['unit_id'], authority='unverified_generic_participation; requires_own_source_review')
            assert all(patch[k] == original[k] for k in FROZEN)
            result['patches'][index] = patch
        except (ValueError, IndexError) as exc:
            receipt['errors'].append(dict(proposal_index=index, error=str(exc)))
    return result


def verified_proposals(run, instruction, context, output_type, unit):
    """Rebuild the original generation request; never reinterpret cached text as a new call."""
    from . import business_run as execution
    from .source_meanings import remap
    request = execution.json_request(run, 'requirement_repair', instruction, context, output_type)
    options = run['recipe']['options']
    limits = dict(max_tokens=request['max_tokens'] or options['review_tokens'],
        context_tokens=options['context_tokens'], think=options['think'])
    config = dict(model=run['recipe']['models']['review'], generation=run['recipe']['generation'],
        identity=run['model_identity'], temperature=0, timeout=options['timeout'])
    if (unit['stage'] != 'requirement_repair' or unit['status'] != 'succeeded' or unit.get('error')
            or any(unit.get(k) != request[k] for k in ('messages', 'schema', 'reference_map'))
            or unit['request_configuration'] != config or unit['requested_limits'] != limits
            or unit['executed_limits'] != limits or (unit.get('response') or {}).get('failure_kind')):
        raise ValueError('원복구 요청·참조·모델·한도·결과 불일치')
    reverse = {v:k for k,v in (request['reference_map'] or {}).items()}
    parsed = execution.remap_expression_keys(remap(unit['response']['parsed'], reverse), reverse)
    return output_type.model_validate(parsed).model_dump()
