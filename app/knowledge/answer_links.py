"""Resolve model-declared literal anchors and references; never judge semantic support."""
from copy import deepcopy
import re

CONTRACT = 'provided_source_quote_links_v1'
# Opt-in only: the native trial linked review scopes but failed literal anchors and bounded wording.
REVIEW_CONTRACT = 'provided_review_scope_links_v1'
# Explicit schema change; native end-to-end QA awaits a passing bounded final review.
SEGMENT_CONTRACT = 'provided_review_scope_segments_v1'
PROMPT = (
    '\nsource_citations마다 응답 내 고유한 불투명 quote_id(sq_접두)를 부여한다. 순번이나 전역 ID가 아니다. '
    'answer_links에는 target(answer 또는 limitations), 해당 필드의 정확하고 유일한 literal anchor, '
    'claim_refs, quote_refs만 반환한다. claim_refs는 제공 context와 global citations 모두에 있는 ID이며 '
    '정확한 주장이 없으면 []를 쓴다. quote_refs는 이번 source_citations의 quote_id를 하나 이상 선택한다. '
    'limitations anchor는 모든 항목을 통틀어 유일해야 한다. offset이나 항목 번호를 계산하지 않는다. '
    '여러 참조와 quote 재사용을 허용한다. 두 참조 집합 사이의 개별 지지관계나 의미 검증을 뜻하지 않는다.'
)
REVIEW_PROMPT = (
    '\nanswer_links는 target, anchor, claim_refs, quote_refs, review_refs를 반환한다. '
    '확인된 원문 사실은 quote_refs로 연결하고 review_refs=[]로 둔다. '
    '확정 불가 판단은 review_scope_refs에 제공한 검수 참조로 연결하고 quote_refs=[]로 둔다. '
    '검수 참조는 선택한 원문·속성을 비교한 모델 판단이며 전체 자료의 부재 증명이 아니다. '
    '확정 불가 문장과 limitations 각각에 연결을 남기고, 확인한 비교 전제만으로 무엇을 확정할 수 없는지 범위를 명시한다. '
    '한 원문 구절을 자료 전체의 부재 근거로 쓰거나 이전 검수 문장의 부재 표현을 전체 자료로 확대하지 않는다.'
)


def instruction(contract):
    if contract == CONTRACT:
        return PROMPT
    if contract == REVIEW_CONTRACT:
        return PROMPT.replace('claim_refs, quote_refs만', 'claim_refs, quote_refs, review_refs만').replace(
            'quote_refs는 이번 source_citations의 quote_id를 하나 이상 선택한다.',
            'quote_refs는 이번 source_citations의 quote_id만 선택한다.') + REVIEW_PROMPT
    if contract == SEGMENT_CONTRACT:
        return (
            '\nanswer와 limitations는 각각 {text, claim_refs, quote_refs, review_refs} 객체의 배열이다. '
            '문장과 해당 문장의 근거를 같은 객체에 한 번만 작성한다. text가 그대로 표시되므로 Markdown도 그 안에 쓴다. '
            '별도의 answer_links, anchor, 위치, 문장 ID는 생성하지 않는다. 프로그램이 배열 순서대로 본문과 정확한 위치를 만든다. '
            '각 객체의 text는 하나의 사실 또는 판단이며, 확인된 사실과 확정 불가 판단을 같은 객체에 섞지 않는다. '
            'source_citations에는 응답 내 고유한 quote_id(sq_접두)를 부여한다. '
            'claim_refs는 제공 context와 global citations에 있는 ID만 쓴다. 정확한 주장이 없으면 []다. '
            '원문 사실은 이번 source_citations의 quote_id를 quote_refs로 연결하고 review_refs=[]로 둔다. '
            '확정 불가 판단은 review_scope_refs의 참조를 review_refs로 연결하고 quote_refs=[]로 둔다. '
            '모든 객체는 원문 인용 또는 검수 참조 중 하나를 가져야 한다. '
            '확정 불가 문장과 limitations는 selected_requirement_review의 source_observations와 실제 비교 전제 안에서 작성한다. '
            '어떤 사실만으로 어떤 결론을 도출할 수 없는지 설명하며, 전체 원문에 근거가 없다는 주장으로 넓히지 않는다. '
            '검수 참조는 모델 판단의 추적이며 원문 사실·전체 자료의 부재 증명·사용 승인이 아니다.'
        )
    return ''


def enabled(run, stage='business_qa'):
    return stage == 'business_qa' and run.get('query', {}).get('source_citation_contract') in {CONTRACT, REVIEW_CONTRACT, SEGMENT_CONTRACT}


def generation_schema(schema, review_refs=None, *, segments=False):
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
    if review_refs is not None:
        row = schema['properties']['answer_links']['items']
        row['required'].append('review_refs')
        row['properties']['quote_refs']['minItems'] = 0
        row['properties']['review_refs'] = dict(type='array', uniqueItems=True,
            items=dict(type='string', enum=list(review_refs)) if review_refs else dict(type='string'),
            **({} if review_refs else dict(maxItems=0)))
    if segments:
        row = schema['properties'].pop('answer_links')['items']
        row['properties'].pop('target')
        text = row['properties'].pop('anchor')
        row['properties'] = dict(text=text, **row['properties'])
        row['required'] = ['text', 'claim_refs', 'quote_refs', 'review_refs']
        schema['required'].remove('answer_links')
        for target in ('answer', 'limitations'):
            schema['properties'][target] = dict(type='array', items=deepcopy(row), minItems=1 if target == 'answer' else 0)
    return schema


def restore(parsed, reverse, *, contract=CONTRACT):
    """Keep literals untouched; detach optional metadata before legacy validation."""
    parsed = deepcopy(parsed)
    if not isinstance(parsed, dict):
        return parsed, {}
    locations = []
    if contract == SEGMENT_CONTRACT:
        if 'answer_links' in parsed:
            raise ValueError('segments_cannot_declare_copied_anchors')
        links = []
        for target in ('answer', 'limitations'):
            parts = parsed.get(target)
            if not isinstance(parts, list) or target == 'answer' and not parts:
                raise ValueError('answer_segments_required')
            texts = []; offset = 0
            for index, part in enumerate(parts):
                if (not isinstance(part, dict) or set(part) != {'text', 'claim_refs', 'quote_refs', 'review_refs'}
                        or not isinstance(part['text'], str) or not part['text'].strip()):
                    raise ValueError('invalid_answer_segment')
                text = part['text']; texts.append(text)
                links.append(dict(target=target, anchor=text, **{k: part[k] for k in ('claim_refs', 'quote_refs', 'review_refs')}))
                start = offset if target == 'answer' else 0
                locations.append(dict(target=target, start_char=start, end_char=start + len(text),
                    **(dict(limitation_index=index) if target == 'limitations' else {})))
                offset += len(text) + 2
            parsed[target] = '\n\n'.join(texts) if target == 'answer' else texts
        parsed['answer_links'] = links
    metadata = dict(recorded='answer_links' in parsed, links=parsed.pop('answer_links', None), quote_ids=[])
    if contract == SEGMENT_CONTRACT:
        metadata['segment_locations'] = locations
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
    segment_mode = run['query']['source_citation_contract'] == SEGMENT_CONTRACT
    review_mode = run['query']['source_citation_contract'] in {REVIEW_CONTRACT, SEGMENT_CONTRACT}
    if review_mode:
        from .selected_review_answer import review_scopes
        result['review_scopes'] = review_scopes(run.get('selected_review_context'), provided_ids)
    if not metadata.get('recorded'):
        return
    result['status'] = 'recorded'
    links = metadata['links']
    if not isinstance(links, list):
        result.update(status='unresolved', error='answer_links_not_list', declaration=links)
        return
    seen, linked = [], set()
    for link_index, declaration in enumerate(links):
        if not segment_mode and declaration in seen:
            result['duplicates_removed'] += 1
            continue
        seen.append(deepcopy(declaration))
        entry = dict(declaration=declaration, status='unresolved', errors=[])
        errors = entry['errors']
        fields = {'target', 'anchor', 'claim_refs', 'quote_refs'} | ({'review_refs'} if review_mode else set())
        if not isinstance(declaration, dict) or set(declaration) != fields:
            errors.append('invalid_link_fields')
        else:
            target, anchor = declaration['target'], declaration['anchor']
            matches = []
            if target not in ('answer', 'limitations') or not isinstance(anchor, str) or not anchor:
                errors.append('invalid_anchor')
            elif segment_mode:
                locations = metadata.get('segment_locations', [])
                location = locations[link_index] if link_index < len(locations) else None
                if location is None:
                    errors.append('segment_location_missing')
                else:
                    text = output['answer'] if target == 'answer' else output['limitations'][location['limitation_index']]
                    if text[location['start_char']:location['end_char']] != anchor:
                        errors.append('segment_text_changed')
                    else:
                        entry.update(location=location, segment_index=link_index)
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
            elif not quotes and not (review_mode and declaration['review_refs']):
                errors.append('missing_quote_refs')
            elif any(result['quote_lookup'].get(v, {}).get('status') != 'resolved' for v in quotes):
                errors.append('quote_ref_unresolved')
            if review_mode:
                reviews = declaration['review_refs']
                if not isinstance(reviews, list) or any(not isinstance(v, str) for v in reviews):
                    errors.append('invalid_review_refs')
                elif any(v not in result['review_scopes'] for v in reviews):
                    errors.append('review_ref_unresolved')
                if reviews and quotes:
                    errors.append('review_scope_is_not_source_quote_support')
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
