"""Resolve model-declared literal anchors and references; never judge semantic support."""
from copy import deepcopy
import re

CONTRACT = 'provided_source_quote_links_v1'
PROMPT = (
    '\nsource_citations마다 응답 내 고유한 불투명 quote_id(sq_접두)를 부여한다. 순번이나 전역 ID가 아니다. '
    'answer_links에는 target(answer 또는 limitations), 해당 필드의 정확하고 유일한 literal anchor, '
    'claim_refs, quote_refs만 반환한다. claim_refs는 제공 context와 global citations 모두에 있는 ID이며 '
    '정확한 주장이 없으면 []를 쓴다. quote_refs는 이번 source_citations의 quote_id를 하나 이상 선택한다. '
    'limitations anchor는 모든 항목을 통틀어 유일해야 한다. offset이나 항목 번호를 계산하지 않는다. '
    '여러 참조와 quote 재사용을 허용한다. 두 참조 집합 사이의 개별 지지관계나 의미 검증을 뜻하지 않는다.'
)


def enabled(run, stage='business_qa'):
    return stage == 'business_qa' and run.get('query', {}).get('source_citation_contract') == CONTRACT


def generation_schema(schema):
    schema = deepcopy(schema)
    quote = schema['$defs'][schema['properties']['source_citations']['items']['$ref'].split('/')[-1]]
    quote['properties']['quote_id'] = dict(type='string', pattern=r'^sq_\S+$')
    quote['required'] = [*quote['required'], 'quote_id']
    schema['properties']['answer_links'] = dict(type='array', items=dict(type='object', additionalProperties=False,
        required=['target', 'anchor', 'claim_refs', 'quote_refs'], properties=dict(
            target=dict(type='string', enum=['answer', 'limitations']), anchor=dict(type='string', minLength=1),
            claim_refs=dict(type='array', items=deepcopy(schema['properties']['citations']['items'])),
            quote_refs=dict(type='array', minItems=1, items=dict(type='string', pattern=r'^sq_\S+$')))))
    schema['required'] = [*schema['required'], 'answer_links']
    return schema


def restore(parsed, reverse):
    """Keep literals untouched; detach optional metadata before legacy validation."""
    parsed = deepcopy(parsed)
    if not isinstance(parsed, dict):
        return parsed, {}
    metadata = dict(recorded='answer_links' in parsed, links=parsed.pop('answer_links', None), quote_ids=[])
    if isinstance(parsed.get('citations'), list):
        parsed['citations'] = [reverse.get(v, v) if isinstance(v, str) else v for v in parsed['citations']]
    for item in parsed.get('source_citations', []) if isinstance(parsed.get('source_citations'), list) else []:
        if isinstance(item, dict):
            metadata['quote_ids'].append(item.pop('quote_id', None))
            ref = item.get('evidence_ref')
            if isinstance(ref, str):
                item['evidence_ref'] = reverse.get(ref, ref)
        else:
            metadata['quote_ids'].append(None)
    if isinstance(metadata['links'], list):
        for link in metadata['links']:
            if isinstance(link, dict) and isinstance(link.get('claim_refs'), list):
                link['claim_refs'] = [reverse.get(v, v) if isinstance(v, str) else v for v in link['claim_refs']]
    return parsed, metadata


def quote_id(value):
    return isinstance(value, str) and re.fullmatch(r'sq_\S+', value) is not None


def quote_lookup(ids, indices, citations):
    lookup = {}
    for identifier, index in zip(ids, indices):
        if not quote_id(identifier):
            continue
        citation = citations[index]
        citation.setdefault('quote_ids', [])
        if identifier not in citation['quote_ids']:
            citation['quote_ids'].append(identifier)
        if identifier in lookup:
            lookup[identifier] = dict(status='unresolved', error='duplicate_quote_id')
        elif citation['address_status'] != 'matched':
            lookup[identifier] = dict(status='unresolved', error='source_address_unresolved')
        else:
            lookup[identifier] = dict(status='resolved', citation_index=index)
    return lookup


def record(run, output, provided_ids):
    if not enabled(run):
        return
    metadata = output.pop('_answer_link_metadata', {}) if output else {}
    result = dict(status='not_recorded', links=[], quote_lookup=metadata.get('quote_lookup', {}),
        quote_declarations=metadata.get('quote_ids', []), semantic_support='not_assessed',
        relation='model_declared', duplicates_removed=0,
        claims_without_resolved_links=list(output['citations']) if output else [])
    run['answer_links'] = result
    if not metadata.get('recorded'):
        return
    result['status'] = 'recorded'
    links = metadata['links']
    if not isinstance(links, list):
        result.update(status='unresolved', error='answer_links_not_list', declaration=links)
        return
    seen, linked = [], set()
    for declaration in links:
        if declaration in seen:
            result['duplicates_removed'] += 1
            continue
        seen.append(deepcopy(declaration))
        entry = dict(declaration=declaration, status='unresolved', errors=[])
        errors = entry['errors']
        if not isinstance(declaration, dict) or set(declaration) != {'target', 'anchor', 'claim_refs', 'quote_refs'}:
            errors.append('invalid_link_fields')
        else:
            target, anchor = declaration['target'], declaration['anchor']
            matches = []
            if target not in ('answer', 'limitations') or not isinstance(anchor, str) or not anchor:
                errors.append('invalid_anchor')
            else:
                texts = [output['answer']] if target == 'answer' else output['limitations']
                for index, text in enumerate(texts):
                    position = text.find(anchor)
                    while position >= 0:
                        matches.append(dict(target=target, start_char=position, end_char=position + len(anchor),
                            **(dict(limitation_index=index) if target == 'limitations' else {})))
                        position = text.find(anchor, position + 1)
                if len(matches) != 1:
                    errors.append('anchor_absent_or_non_unique')
                else:
                    entry['location'] = matches[0]
            claims, quotes = declaration['claim_refs'], declaration['quote_refs']
            if not isinstance(claims, list) or any(not isinstance(v, str) for v in claims):
                errors.append('invalid_claim_refs')
            elif not set(claims) <= set(provided_ids).intersection(output['citations']):
                errors.append('claim_not_provided_and_globally_cited')
            if not isinstance(quotes, list) or any(not isinstance(v, str) for v in quotes):
                errors.append('invalid_quote_refs')
            elif not quotes:
                errors.append('missing_quote_refs')
            elif any(result['quote_lookup'].get(v, {}).get('status') != 'resolved' for v in quotes):
                errors.append('quote_ref_unresolved')
            if not errors:
                entry['status'] = 'resolved'
                linked.update(claims)
        result['links'].append(entry)
    result['claims_without_resolved_links'] = [v for v in output['citations'] if v not in linked]
    if any(v['status'] != 'resolved' for v in result['links']):
        result['status'] = 'unresolved'


def withhold(run):
    if 'answer_links' in run:
        run['answer_links'] = dict(status='needs_review', links=[], quote_lookup={}, quote_declarations=[],
            claims_without_resolved_links=[], duplicates_removed=0, semantic_support='not_assessed', relation='model_declared')
