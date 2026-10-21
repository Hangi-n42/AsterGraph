"""Frozen R2/J0+J1 → G1 → W1 candidate producer; no model or graph mutation."""
from copy import deepcopy
import json


CONTRACT = 'r2_g1_w1'
GROUP_INSTRUCTION = ('\n후보는 candidate_fact_groups로 묶여 있다. shared_event_text는 기존 관계의 공통 head 문장이다. '
    'head_shared_event=true인 member는 그 문장을 head로, relation과 tail을 원래 방향으로 읽는다. '
    'selected_ids에는 필요한 개별 member id만 최대30개 반환한다. group_id는 선택하지 않는다.')
WORK_INSTRUCTION = ('\nreview_work_units는 candidate_fact_groups의 child_group_ids를 묶은 검토 작업 단위다. '
    '각 child는 서로 다른 원래 주장/표현으로 유지되며, 묶음이 의미 동등성이나 승인을 뜻하지 않는다. '
    'selected_ids에는 필요한 개별 member id만 최대30개 반환한다. review_unit_id와 group_id는 선택하지 않는다.')
EVIDENCE_FIELDS = ('source_version_id', 'parse_run_id', 'block_id', 'start_char', 'end_char', 'quote', 'context_only', 'precision')
CLAIM_FIELDS = ('conditions', 'exceptions', 'period', 'references', 'qualifier_status', 'review_status', 'semantic_status')
INTERPRETATION_FIELDS = ('contract', 'semantic_status', 'target_status', 'errors')
MEANING_FIELDS = ('statement_type', 'relation_kind', 'subject', 'action', 'object', 'applies_to', 'modality',
    'conditions', 'exceptions', 'time', 'local_negation', 'references', 'premises', 'evidence')
PARTICIPANT_FIELDS = ('field', 'entity_index', 'value', 'evidence', 'address_status', 'address_errors', 'meaning_refs')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class NotShareable(ValueError):
    pass


def project(value, fields):
    if not isinstance(value, dict) or any(k not in value for k in fields):
        raise NotShareable('missing_required_field')
    return {k: deepcopy(value[k]) for k in fields}


def addresses(items, blocks):
    if not isinstance(items, list) or not items:
        raise NotShareable('missing_evidence')
    result = []
    for ev in items:
        row = project(ev, EVIDENCE_FIELDS)
        block = blocks.get(row['block_id'])
        if not block or any(block.get(k) != row[k] for k in ('source_version_id', 'parse_run_id')):
            raise NotShareable('source_address_unresolved')
        lo, hi = row['start_char'], row['end_char']
        if (type(lo) != int or type(hi) != int or not 0 <= lo <= hi <= len(block['text'])
                or block['text'][lo:hi] != row['quote']):
            raise NotShareable('source_substring_mismatch')
        result.append(row)
    return result


def signature(claim, edges, nodes, blocks, snapshot_id):
    """Share review work only; keep every claim, role, unknown and error separately."""
    cid, raw, interpretation = claim['id'], claim['raw'], claim.get('interpretation')
    if not isinstance(interpretation, dict):
        raise NotShareable('missing_interpretation')
    guard = dict(snapshot=snapshot_id, sources=deepcopy(claim['source_version_ids']),
        evidence=addresses(claim['evidence'], blocks), claim_fields=project(claim, CLAIM_FIELDS),
        interpretation_fields=project(interpretation, INTERPRETATION_FIELDS))
    if not isinstance(interpretation.get('meanings'), list) or not interpretation['meanings']:
        raise NotShareable('missing_meanings')
    if not isinstance(interpretation.get('mentions'), list):
        raise NotShareable('missing_mentions')
    mids = {m['id'] for m in interpretation['meanings'] if 'id' in m}
    available = {n for e in edges for n in (e['head'], e['tail']) if nodes.get(n, {}).get('kind') == 'entity'}
    event = 'Event' in raw
    if event:
        if not isinstance(raw.get('Entity'), list) or len(raw['Entity']) != 2:
            raise NotShareable('no_bijective_entity_roles')
        if not edges or any(e['head_kind'] != 'event' or e['head_label'] != raw['Event']
                            or e['relation'] != 'participation' for e in edges):
            raise NotShareable('event_edge_shape_unresolved')
    elif not all(k in raw for k in ('Head', 'Relation', 'Tail')):
        raise NotShareable('unsupported_raw_shape')

    def participant(p):
        project(p, PARTICIPANT_FIELDS)
        if (p['address_status'] != 'resolved' or p['address_errors'] != []
                or not isinstance(p['meaning_refs'], list) or not p['meaning_refs']
                or not set(p['meaning_refs']) <= mids):
            raise NotShareable('participant_address_or_reference_unresolved')
        addr = addresses(p['evidence'], blocks)
        if event and p['field'] == 'Event':
            if p['entity_index'] is not None or p['value'] != raw['Event']:
                raise NotShareable('event_self_role_mismatch')
            return None
        if event:
            idx = p['entity_index']
            if (p['field'] != 'Entity' or type(idx) != int or not 0 <= idx < len(raw['Entity'])
                    or p['value'] != raw['Entity'][idx]):
                raise NotShareable('entity_role_mismatch')
        elif p['field'] not in {'Head', 'Tail'} or p['entity_index'] is not None or p['value'] != raw[p['field']]:
            raise NotShareable('direct_role_mismatch')
        matching = [n for n in available if nodes[n]['label'] == p['value'] and cid in nodes[n]['claim_ids']]
        if (len(matching) != 1 or not isinstance(p['value'], str) or not p['value']
                or not all(p['value'] in a['quote'] for a in addr)):
            raise NotShareable('entity_node_or_literal_not_unique')
        return dict(node=matching[0], value=p['value'], evidence=addr)

    all_roles = [participant(p) for p in interpretation['mentions']]
    entity_roles = [r for r in all_roles if r is not None]
    if len(entity_roles) != 2 or len({canonical(r) for r in entity_roles}) != 2:
        raise NotShareable('mention_roles_not_bijective')
    if event and sum(r is None for r in all_roles) != 1:
        raise NotShareable('event_self_not_unique')
    if not event and (len(edges) != 1 or edges[0]['head_label'] != raw['Head']
                     or edges[0]['tail_label'] != raw['Tail'] or edges[0]['relation'] != raw['Relation']):
        raise NotShareable('direct_edge_mismatch')
    guard['meanings'] = []
    for meaning in interpretation['meanings']:
        fields = project(meaning, MEANING_FIELDS)
        fields['evidence'] = addresses(meaning['evidence'], blocks)
        if meaning.get('address_errors') != [] or not isinstance(meaning.get('participants'), list):
            raise NotShareable('meaning_address_or_participants_unresolved')
        roles = []
        for p in meaning['participants']:
            if p not in interpretation['mentions']:
                raise NotShareable('participant_mention_not_exact')
            value = participant(p)
            if value is not None:
                roles.append(value)
        if sorted(canonical(r) for r in roles) != sorted(canonical(r) for r in entity_roles):
            raise NotShareable('meaning_entity_roles_not_bijective')
        mapped = {}
        for role in ('subject', 'object'):
            found = [r for r in roles if r['value'] == meaning[role]]
            if len(found) != 1:
                raise NotShareable('subject_value_role_unknown')
            mapped[role] = found[0]
        if mapped['subject'] == mapped['object']:
            raise NotShareable('subject_object_not_distinct')
        fields['role_addresses'] = mapped
        guard['meanings'].append(fields)
    return guard


def rank_edges(snapshot, nodes, edges, passages, edge_scores, source_ranking):
    """R2: RRF dense rank + best J0/J1 source rank, k=60; exact one-hop Head only."""
    claims = {c['id']: c for c in snapshot['claims']}
    blocks = {b['id']: b for b in snapshot['blocks']}
    by_claim = {}
    for edge in edges:
        if edge.get('claim_id'):
            by_claim.setdefault(edge['claim_id'], []).append(edge)

    def valid(ref, version=None):
        block = blocks.get(ref.get('block_id'))
        lo, hi = ref.get('start_char'), ref.get('end_char')
        return bool(block and type(lo) is int and type(hi) is int and 0 <= lo < hi <= len(block['text'])
            and all(block.get(k) == ref.get(k) for k in ('source_version_id', 'parse_run_id'))
            and (version is None or ref['source_version_id'] == version)
            and block['text'][lo:hi] == ref.get('quote') and not ref.get('context_only'))

    def participants(claim, field):
        return [p for m in (claim.get('interpretation') or {}).get('meanings', [])
                for p in m.get('participants', []) if p.get('field') == field]

    eligible = {}
    for cid, claim in claims.items():
        raw = claim['raw']
        direct = all(k in raw for k in ('Head', 'Relation', 'Tail'))
        direct_edges = [e for e in by_claim.get(cid, []) if direct and e['relation'] == raw['Relation']
            and nodes[e['head']]['kind'] == 'entity' and nodes[e['head']]['label'] == raw['Head']
            and nodes[e['tail']]['label'] == raw['Tail']
            and nodes[e['head']].get('identity_scope') == 'source_version+exact_mention+kind+endpoint_text']
        heads = participants(claim, 'Head')
        if len(direct_edges) != 1 or not heads or any(p.get('address_status') != 'resolved'
            or p.get('address_errors') or p.get('value') != raw.get('Head') or not p.get('evidence')
            or any(not valid(r) or r['quote'] != raw['Head'] for r in p['evidence']) for p in heads):
            continue
        keys = {tuple(r[k] for k in EVIDENCE_FIELDS[:6]) + ('Head',) for p in heads for r in p['evidence']}
        eligible[cid] = dict(edge=direct_edges[0], keys=keys)
    links = {e['id']: [] for e in edges}
    for position, hit in enumerate(source_ranking, 1):
        passage = passages[hit['block_id']]
        version = passage['evidence']['source_version_id']
        if hit['score'] <= 0 or hit['file_id'] != version:
            raise ValueError('원문 검색 점수·출처가 후보 원문과 일치하지 않습니다.')
        for edge in edges:
            if edge.get('claim_id') in passage['claim_ids']:
                links[edge['id']].append(dict(kind='J0', rank=position, passage_id=hit['block_id']))
        if not valid(passage['evidence'], version):
            continue
        for anchor_id in passage['claim_ids']:
            if anchor_id not in eligible or version not in claims[anchor_id]['source_version_ids']:
                continue
            anchor = eligible[anchor_id]
            for cid, target in eligible.items():
                if cid in passage['claim_ids']:
                    continue
                shared = sorted(k for k in anchor['keys'] & target['keys'] if k[0] == version)
                if not shared or anchor['edge']['head'] != target['edge']['head']:
                    continue
                claim, tails = claims[cid], participants(claims[cid], 'Tail')
                evidence = claim.get('evidence', [])
                if (version not in claim['source_version_ids'] or not evidence or any(not valid(r, version) for r in evidence)
                    or not tails or any(p.get('address_status') != 'resolved' or p.get('address_errors')
                        or p.get('value') != claim['raw']['Tail'] or not p.get('evidence')
                        or any(not valid(r, version) or r['quote'] != claim['raw']['Tail'] for r in p['evidence']) for p in tails)):
                    continue
                links[target['edge']['id']].append(dict(kind='J1', rank=position,
                    passage_id=hit['block_id'], anchor_claim_id=anchor_id))
    dense = sorted(range(len(edges)), key=lambda i: (-edge_scores[i], edges[i]['id']))
    rows = {}
    for position, i in enumerate(dense, 1):
        eid = edges[i]['id']
        linked = sorted(links[eid], key=lambda row: row['kind'])  # Existing J0 paths precede J1 paths.
        best = min((row['rank'] for row in linked), default=None)
        source = 1 / (60 + best) if best else 0
        rows[eid] = dict(dense_rank=position, dense_contribution=1 / (60 + position),
            source_rank=best, source_contribution=source, source_passages=linked,
            score=1 / (60 + position) + source, J1_path_count=sum(r['kind'] == 'J1' for r in linked))
    ordered = sorted(rows, key=lambda eid: (-rows[eid]['score'], rows[eid]['dense_rank'], eid))
    return dict(rrf_k=60, edge_scores=rows, ranked_edge_ids=ordered, source_ranking=deepcopy(source_ranking))


def packet(snapshot, graph, edges, collection, construction_graph):
    """G1 typed children and W1 exact review sharing, preserving G1's first-30 aliases."""
    claims = {c['id']: c for c in snapshot['claims']}
    blocks = {b['id']: b for b in snapshot['blocks']}
    historical = {e['id']: e for e in construction_graph['edges']}
    metadata = {e['id']: dict(e, head_label=graph.nodes[e['head']]['label'], tail_label=graph.nodes[e['tail']]['label'],
        head_kind=graph.nodes[e['head']]['kind'], tail_kind=graph.nodes[e['tail']]['kind']) for e in edges}
    units = {}
    for eid in collection['ranked_edge_ids']:
        edge = metadata[eid]
        key = (('search_concept_singleton', snapshot['id'], eid) if edge['relation'] == 'has_concept' else
               ('factual_claim', snapshot['id'], edge['claim_id'], tuple(sorted(set(claims[edge['claim_id']]['source_version_ids'])))))
        if key not in units:
            units[key] = dict(key=key, kind=key[0], representative_edge_id=eid,
                score=collection['edge_scores'][eid]['score'], member_edge_ids=[])
        units[key]['member_edge_ids'].append(eid)
    children = [dict(u, group_id=f'g{i}', original_G1_position=i) for i, u in enumerate(units.values(), 1)]
    aliases = {eid: f'e{i}' for i, eid in enumerate([e for u in children[:30] for e in u['member_edge_ids']], 1)}
    work, eligibility = {}, []
    for child in children:
        pos = child['original_G1_position']
        if child['kind'] == 'factual_claim':
            claim = claims[child['key'][2]]
            try:
                sig = signature(claim, [metadata[e] for e in child['member_edge_ids']], graph.nodes, blocks, snapshot['id'])
                key, reason = ('eligible_review_work', canonical(sig)), 'exact_stored_fields_and_unique_roles_only'
            except NotShareable as exc:
                sig, key, reason = None, ('nonshared_child', pos), str(exc)
            eligibility.append(dict(claim_id=claim['id'], original_position=pos,
                eligible_for_work_sharing=sig is not None, reason=reason, signature=sig))
        else:
            key = ('concept_singleton', pos)
        if key not in work:
            work[key] = dict(review_unit_id=f'w{len(work)+1}', first_G1_position=pos, score=child['score'], children=[])
        work[key]['children'].append(child)
    selected = list(work.values())[:30]
    display, bindings, views, used = [], {}, [], set()
    for unit in selected:
        view = dict(review_unit_id=unit['review_unit_id'], child_group_ids=[])
        for child in unit['children']:
            gid = child['group_id']
            view['child_group_ids'].append(gid)
            claim = claims[child['key'][2]] if child['kind'] == 'factual_claim' else None
            event = claim['raw'].get('Event') if claim else None
            shared = isinstance(event, str) and bool(event) and all(metadata[e]['head_kind'] == 'event'
                and metadata[e]['head_label'] == event and metadata[e]['text'] == event + ' ' + metadata[e]['relation']
                + ' ' + metadata[e]['tail_label'] for e in child['member_edge_ids'])
            group = dict(group_id=gid, kind=child['kind'], members=[])
            if shared:
                group['shared_event_text'] = event
            for eid in child['member_edge_ids']:
                if eid not in aliases:
                    aliases[eid] = f'e{len(aliases)+1}'
                used.add(eid)
                edge, alias = metadata[eid], aliases[eid]
                member = (dict(id=alias, head_shared_event=True, relation=edge['relation'], tail=edge['tail_label'], status=edge['status'])
                    if shared else dict(id=alias, triple=edge['text'], status=edge['status']))
                group['members'].append(member)
                bindings[alias] = dict(group_id=gid, edge_id=eid, edge=deepcopy(edge),
                    construction_edge=deepcopy(historical.get(eid)), original_claim=deepcopy(claim),
                    source_version_ids=deepcopy(claim['source_version_ids']) if claim else None,
                    source_evidence=deepcopy(claim['evidence']) if claim else None,
                    inherited_interpretation=deepcopy(claim.get('interpretation')) if claim else None,
                    inherited_qualifiers={k: deepcopy(claim.get(k)) for k in ('conditions', 'exceptions', 'period', 'semantic_status')} if claim else None)
            display.append(group)
        views.append(view)
    return dict(candidate_fact_groups=display, review_work_units=views,
        aliases={e: a for e, a in aliases.items() if e in used}, bindings=bindings,
        all_groups=children, all_review_units=list(work.values()), eligibility=eligibility)
