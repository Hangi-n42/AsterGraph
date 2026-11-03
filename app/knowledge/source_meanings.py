"""Source meaning records and address mapping shared by current business workflows."""
from copy import deepcopy
from typing import Literal
from pydantic import BaseModel, Field


class Record(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}


class SourceMeaning(Record):
    local_ref: str
    proposition_refs: list[str] = Field(default_factory=list)
    meaning: str
    applies_to: str
    statement_type: Literal['definition', 'rule', 'instance', 'design_proposal', 'unresolved'] = 'unresolved'
    judgment_kind: Literal['source_content','case_application','derived_link'] = 'source_content'
    local_negation: str = ''
    relation_kind: Literal['definition','obligation','authority','reference','comparison','identity','inheritance','other']
    conditions: str
    exceptions: str
    time: str
    negation: Literal['affirmed','negated']
    applicability: Literal['required','not_applicable','unknown'] = Field(description='현재 질문에서 표현해야 하는 의미인지. 구체 사례의 규칙 적용 조건 충족 여부와 다름.')
    source_status: Literal['supported','refuted','unknown']
    source_refs: list[str]
    missing_source: str = Field(description='미제공 자료의 실제 문서명/조항명. 상태값이나 none이 아님; 해당 없으면 빈 문자열.')
    availability: Literal['provided','internal_unselected','external_missing','capacity','ambiguous']
    read_block_ids: list[str] = Field(default_factory=list)
    premise_refs: list[str]
    premises_complete: bool
    reason: str
    supersedes: str = ''


def affected_keys(meanings,keys):
    """Only a challenged meaning and its dependents are blocked, not its siblings."""
    affected=set(keys)
    while True:
        more={m['meaning_key'] for m in meanings if set(m.get('premise_keys',[])) & affected}
        if more<=affected: return affected
        affected.update(more)


def remap(value, mapping):
    if isinstance(value, list):
        return [remap(v, mapping) for v in value]
    if isinstance(value, dict):
        literal = {'endpoint_labels'} | ({'subject','object'} if value.get('endpoint_mode')=='source_text' and not value.get('source_relation') else set())
        if {'claim_id','field','quote'} <= value.keys():
            literal |= {'field','quote'}
        if {'block_id','quote'} <= value.keys() or {'evidence_ref','span','quote'} <= value.keys():
            literal.add('quote')
        if 'fact_id' in value or {'subject_ref', 'attribute_ref', 'scope_id'} <= value.keys():
            literal |= {'fact_id', 'scope_id', 'matching_binding_ids'}
        if 'property_ref' in value:
            literal.add('scope_id')
            literal |= {'property_ref','parent_ref','item_ref','source_value','identity_refs','condition_refs'}
        if 'criterion_id' in value:
            literal.add('criterion_id')
        if 'binding_id' in value:
            literal.add('binding_id')
        if {'field','quote'} <= value.keys():
            literal |= {'field','quote'}
        if {'requirement_id','requirement_revision','field','span','quote'} <= value.keys():
            literal |= {'field','quote'}
        if set(value) == {'field','span'}:
            literal.add('field')
        if {'requirement_id','request_quote'} <= value.keys():
            literal |= {'field','request_quote'}
        if {'question','criterion'} <= value.keys():
            literal |= {'question','criterion'}
        if 'character_addresses' in value:
            literal |= {'field','text','character_addresses'}
        return {k: deepcopy(v) if k in literal else remap(v, mapping) for k,v in value.items()}
    return mapping.get(value, value) if isinstance(value, str) else value
