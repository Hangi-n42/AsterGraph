"""Read saved business scopes without inference or merging experimental runs."""
import json
from copy import deepcopy
from collections import Counter


def catalog(service):
    with service.repository.connect() as db:
        sources = {row['id']: json.loads(row['payload']) for row in db.execute('SELECT id,payload FROM sources')}
        versions = {row['id']: json.loads(row['payload']) for row in db.execute('SELECT id,payload FROM versions')}
        edited_runs = {row['run_id']: row['created_at'] for row in db.execute("""SELECT run.id run_id,
            json_extract(repair.value,'$.created_at') created_at
            FROM runs run, changesets change, json_each(change.payload,'$.edit_run_ids') edit,
                json_each(run.payload,'$.repairs') repair
            WHERE edit.value=run.id AND json_extract(repair.value,'$.origin')='user'
                AND json_extract(repair.value,'$.source_changeset_id')=change.id""")}
        scopes = []
        for row in db.execute("""SELECT id, json_extract(payload,'$.status') status,
                json_extract(payload,'$.started_at') started_at,
                json_extract(payload,'$.input_version_ids') version_ids
                FROM runs WHERE json_extract(payload,'$.kind')='business' ORDER BY rowid DESC"""):
            ids = json.loads(row['version_ids'] or '[]')
            titles = list(dict.fromkeys(sources.get(versions.get(v, {}).get('source_id'), {}).get('title', '출처 정보 미기록') for v in ids))
            scopes.append(dict(kind='run', id=row['id'], title=' · '.join(titles) or '자료 범위 미기록',
                               status=row['status'], created_at=(edited_runs[row['id']] or row['started_at']) if row['id'] in edited_runs else row['started_at'], version_ids=ids,
                               version_files=[{k: versions.get(v, {}).get(k) for k in ['id', 'filename', 'dates']} for v in ids],
                               data_label='직접 수정 저장 결과 · 미승인' if row['id'] in edited_runs else '자동 추출 결과 · 미승인'))
        for row in db.execute("""SELECT id, json_extract(payload,'$.kind') kind,
                json_extract(payload,'$.created_at') created_at, json_extract(payload,'$.reason') reason,
                json_extract(payload,'$.source_versions') source_versions, json_extract(payload,'$.activation') activation,
                json_extract(payload,'$.run_id') run_id
                FROM snapshots ORDER BY rowid DESC"""):
            if row['kind'] == 'source_graph':
                ids = list(json.loads(row['source_versions'] or '{}'))
                titles = list(dict.fromkeys(sources.get(versions.get(v, {}).get('source_id'), {}).get('title', '출처 정보 미기록') for v in ids))
                scopes.append(dict(kind='source_graph', id=row['id'], title=' · '.join(titles) or '출처 정보 미기록',
                                   status='selection_recorded', created_at=row['created_at'], data_label='출처 지식 선택 기록 · 온톨로지와 별도',
                                   version_files=[{k: versions.get(v, {}).get(k) for k in ['id', 'filename', 'dates']} for v in ids],
                                   version_ids=ids, activation=row['activation'], run_id=row['run_id']))
        return dict(scopes=scopes, registered_sources=len(sources), registered_versions=len(versions),
                    legacy_snapshots=db.execute("SELECT count(*) FROM snapshots WHERE json_extract(payload,'$.kind') IS NOT 'source_graph'").fetchone()[0],
                    ontology_versions=db.execute('SELECT count(*) FROM ontology_versions').fetchone()[0],
                    count_policy='선택한 저장 결과의 고유 ID 기준. 반복 실행을 합산하지 않음.')


def _edge_claim_ids(edge):
    return edge.get('claim_ids', []) or ([edge['claim_id']] if edge.get('claim_id') else [])


def _search_concept_graph(value, graph):
    """Project the existing retrieval links; keep stored source identities unchanged."""
    if not value.get('concepts') or not graph['nodes']:
        return graph
    from .graph_retrieval import build
    full, projected, _, _ = build(value, 'full')
    nodes = {n['id']: dict(n) for n in graph['nodes']}
    edges = {e['id']: dict(e) for e in graph['edges']}
    claims = {c['id'] for c in value.get('claims', [])}
    records = [c for c in value['concepts'] if c['status'] in {'unreviewed', 'accepted'}]
    for edge in projected:
        if edge['relation'] != 'has_concept' or edge['head'] not in nodes:
            continue
        label = full.nodes[edge['tail']]['label']
        bound = [c for c in records if c['target']['kind'] in {'entity', 'event'}
                 and c['target']['id'] == edge['head'] and label in c['concepts']
                 and set(c['target']['claim_ids']).intersection(claims)]
        claim_ids = list(dict.fromkeys(cid for c in bound for cid in c['target']['claim_ids'] if cid in claims))
        if not claim_ids:
            continue
        provenance = dict(claim_ids=claim_ids, concept_record_ids=[c['id'] for c in bound],
            request_ids=list(dict.fromkeys(c['request_id'] for c in bound if c.get('request_id'))),
            work_ids=list(dict.fromkeys(c['work_id'] for c in bound if c.get('work_id'))))
        edges[edge['id']] = dict(edge, **provenance)
        node = nodes.setdefault(edge['tail'], dict(id=edge['tail'], kind='search_concept', label=label,
            state='unapproved_search_concept', approved_is_a=False))
        for key, values in provenance.items():
            node[key] = list(dict.fromkeys([*node.get(key, []), *values]))
    for edge in edges.values():
        if edge['relation'] != 'has_concept' and full.has_edge(edge['head'], edge['tail'], edge['id']):
            concepts = full.edges[edge['head'], edge['tail'], edge['id']].get('concepts')
            if concepts is not None:
                edge['concepts'] = list(concepts)
    return dict(graph, nodes=list(nodes.values()), edges=list(edges.values()))


def _scope(service, kind, scope_id):
    if kind not in {'run', 'source_graph'}:
        raise ValueError('지원하지 않는 저장 범위입니다.')
    with service.repository.connect() as db:
        value = service.repository.get(db, 'runs' if kind == 'run' else 'snapshots', scope_id)
        if value.get('kind') != ('business' if kind == 'run' else 'source_graph'):
            raise ValueError('선택한 범위 종류와 저장 결과가 다릅니다.')
        sources = {row['id']: json.loads(row['payload']) for row in db.execute('SELECT id,payload FROM sources')}
        versions = {row['id']: json.loads(row['payload']) for row in db.execute('SELECT id,payload FROM versions')}
    if kind == 'run':
        graph = value.get('graph') or dict(nodes=[], edges=[])
    else:
        # Source-graph snapshots store accepted claims, not an approved ontology.
        from .autoschema import graph as stored_claim_graph
        graph = stored_claim_graph(value.get('claims', []), value.get('blocks', []))
    graph = _search_concept_graph(value, graph)
    return value, graph, sources, versions


def _claim_view(claim, blocks, sources, versions):
    evidence = []
    for ref in claim.get('evidence', []):
        block = blocks.get(ref.get('block_id'), {})
        version_id = ref.get('source_version_id') or block.get('source_version_id')
        source = sources.get(versions.get(version_id, {}).get('source_id'), {})
        evidence.append(dict(**ref, source_title=source.get('title'), source_url=source.get('source_url'),
                             rights=source.get('rights'), locator=block.get('locator'),
                             block_text=block.get('text'), source_id=source.get('id'),
                             version_file={k: versions.get(version_id, {}).get(k) for k in ['id', 'filename', 'dates']}))
    return dict(**{k: claim.get(k) for k in ['id', 'role', 'statement', 'conditions', 'exceptions', 'period',
                'references', 'review_status', 'qualifier_status', 'semantic_status', 'extraction_error', 'superseded_by']},
                evidence=evidence, meanings=(claim.get('interpretation') or {}).get('meanings', []),
                interpretation_errors=(claim.get('interpretation') or {}).get('errors', []),
                editable=claim.get('role') == 'event_entity' and not claim.get('extraction_error') and not claim.get('superseded_by'))


def usage(service, kind, scope_id):
    """Current read annotations; query guards still decide each requested scope."""
    from . import business_use, business_changes, availability
    from .service import utcnow
    value, _, _, versions = _scope(service, kind, scope_id)
    run_id = scope_id if kind == 'run' else value.get('run_id')
    with service.repository.connect() as db:
        original = value if kind == 'run' else service.repository.get(db, 'runs', run_id)
        state = availability._state(db)
        version_ids = value.get('input_version_ids') or list(value.get('source_versions') or [])
        restrictions = business_use.restricted_sources(db, version_ids)
        invalidations = []
        if kind == 'source_graph':
            invalidations = [event for row in db.execute('SELECT payload FROM snapshot_events')
                if (event := json.loads(row['payload'])).get('event') == 'business_correction'
                and event['snapshot_id'] == scope_id]
            invalidations.extend(business_changes.snapshot_invalidations(service, db, value, original))
        affected = {rid for event in invalidations for rid in event['requirement_ids']}
        assessments = value.get('assessments') or {}
        if isinstance(assessments, list):
            assessments = {a['requirement_id']: a for a in assessments}
        requirements = []
        for recorded in value.get('requirements', []):
            row = db.execute('SELECT payload FROM requirements WHERE id=?', (recorded['id'],)).fetchone()
            current = json.loads(row['payload']) if row else {}
            requirements.append(dict(id=recorded['id'], question=recorded.get('question'),
                recorded_revision=recorded.get('revision'), current_revision=current.get('revision'),
                recorded_status=assessments.get(recorded['id'], {}).get('status'), current_status=current.get('status'),
                revision_matches=isinstance(recorded.get('revision'), int) and current.get('revision') == recorded['revision'],
                source_change_requires_review=recorded['id'] in affected,
                current_assessment=current.get('current_assessment')))
        linked = [dict(id=s['id'], run_id=s.get('run_id'), activation=s.get('activation'),
            reason=s.get('reason'), actor=s.get('actor'), created_at=s.get('created_at'))
            for row in db.execute("SELECT payload FROM snapshots WHERE json_extract(payload,'$.kind')='source_graph' AND json_extract(payload,'$.run_id')=? ORDER BY rowid DESC", (run_id,))
            if (s := json.loads(row['payload']))]
    change_id = original.get('changeset_id')
    review = None
    if change_id:
        change = business_use.change_view(service, change_id)
        review = dict(changeset_id=change_id, eligible_ids=change['eligible_ids'], blocks=change['eligibility_blocks'],
            explicit_review_ids=[cid for option in change['explicit_review_options'] for cid in option['claim_ids']])
    return dict(scope=dict(kind=kind, id=scope_id), run_id=run_id, version_ids=version_ids,
        version_files=[{k: versions.get(v, {}).get(k) for k in ['id', 'filename', 'dates', 'sha256']} for v in version_ids],
        missing_version_ids=[v for v in version_ids if v not in versions],
        snapshot_id=scope_id if kind == 'source_graph' else None,
        activation=value.get('activation') if kind == 'source_graph' else None,
        actor=value.get('actor') if kind == 'source_graph' else None,
        reason=value.get('reason') if kind == 'source_graph' else None,
        **state, status_checked_at=utcnow(), source_restrictions=restrictions,
        requirements=requirements, invalidations=invalidations,
        excluded_claim_ids=sorted({cid for event in invalidations for cid in event['claim_ids']}),
        excluded_block_ids=sorted({bid for event in invalidations for bid in event.get('block_ids', [])}),
        linked_snapshots=linked, review=review)


def review_status(service, run_id):
    with service.repository.connect() as db:
        run = service.repository.get(db, 'runs', run_id)
    if run.get('kind') != 'business':
        raise ValueError('업무 지식 실행이 아닙니다.')
    repairs = run.get('repairs', [])
    changes = [c for r in repairs if r.get('origin') == 'user' for c in r.get('changes', [])]
    after_ids = {c['after']['id'] for c in changes}
    selected = next((n['id'] for n in (run.get('graph') or {}).get('nodes', [])
                     if n['kind'] == 'event' and after_ids.intersection(n.get('claim_ids', []))), None)
    return dict(id=run['id'], status=run['status'], changeset_id=run.get('changeset_id'), error=run.get('error'),
                selected_id=selected, llm_calls=(run.get('metrics') or {}).get('llm_calls'),
                changes=[dict(before=c.get('before', {}).get('statement'), after=c['after']['statement'],
                              entities=c['after'].get('raw', {}).get('Entity', [])) for c in changes],
                recheck_status=repairs[-1].get('status') if repairs else None)


def changes(service, kind, scope_id):
    value, _, sources, versions = _scope(service, kind, scope_id)
    ids = set(value.get('input_version_ids') or value.get('source_versions') or [])
    source_ids = {versions[v]['source_id'] for v in ids if v in versions}
    records, requirements = [], []
    scopes = catalog(service)['scopes']
    linked_ids = {r['id'] for r in value.get('requirements', [])}
    with service.repository.connect() as db:
        for row in db.execute("SELECT payload FROM runs WHERE json_extract(payload,'$.kind')='business_change' ORDER BY rowid DESC"):
            run = json.loads(row['payload'])
            if not ids.intersection(run.get('input_version_ids', [])):
                continue
            linked_ids.update(r['id'] for r in run.get('requirements', []))
            linked_ids.update(i['requirement_id'] for i in run.get('impacts', []))
            records.append(dict(id=run['id'], status=run['status'], created_at=run.get('finished_at'),
                before_version_id=run['request'].get('before_version_id'), after_version_id=run['request'].get('after_version_id'),
                before_version={k: versions.get(run['request'].get('before_version_id'), {}).get(k) for k in ['id', 'filename', 'dates']},
                after_version={k: versions.get(run['request'].get('after_version_id'), {}).get(k) for k in ['id', 'filename', 'dates']},
                diff=run.get('diff'), impacts=run.get('impacts', []),
                after_scopes=[s for s in scopes if run['request'].get('after_version_id') in s.get('version_ids', [])]))
        for row in db.execute('SELECT payload FROM requirements'):
            requirement = json.loads(row['payload'])
            if requirement['id'] in linked_ids or source_ids.intersection(requirement.get('source_ids', [])):
                requirements.append({k: requirement.get(k) for k in ['id', 'question', 'status', 'revision']})
    current_usage = usage(service, kind, scope_id)
    return dict(records=records, requirements=requirements, edit_impact=value.get('edit_impact'),
                snapshot_review_requirement_ids=sorted({rid for event in current_usage['invalidations'] for rid in event['requirement_ids']}),
                versions=[dict(id=v, title=sources.get(versions[v]['source_id'], {}).get('title'),
                               supersedes_version_id=versions[v].get('supersedes_version_id')) for v in ids if v in versions])


def answers(service, kind, scope_id, answer_id=None):
    value, graph, sources, versions = _scope(service, kind, scope_id)
    field = 'source_run_id' if kind == 'run' else 'snapshot_id'
    with service.repository.connect() as db:
        rows = db.execute(f"""SELECT id, json_extract(payload,'$.query.question') question,
            json_extract(payload,'$.query.retrieval') retrieval, json_extract(payload,'$.answer_status') status,
            json_extract(payload,'$.finished_at') finished_at FROM runs
            WHERE json_extract(payload,'$.kind')='business_query'
            AND json_extract(payload,'$.query.{field}')=? ORDER BY rowid DESC""", (scope_id,)).fetchall()
        items = [dict(r) for r in rows]
        if not answer_id:
            return dict(items=items, detail=None)
        if answer_id not in {r['id'] for r in rows}:
            raise KeyError(answer_id)
        run = service.repository.get(db, 'runs', answer_id)
    # Read the exact context and address map stored with that answer. Rebuilding
    # passage IDs with today's retrieval code can mismatch an older saved run.
    passages, recorded_links = {}, {}
    selected_edges = set((run.get('graph_retrieval') or {}).get('selected_edge_ids', []))
    for unit in run.get('units', []):
        reverse = {alias: identifier for identifier, alias in (unit.get('reference_map') or {}).items()}
        for message in unit.get('messages') or []:
            if message.get('role') != 'user':
                continue
            try:
                content = json.loads(message['content'])
            except (ValueError, TypeError):
                continue
            if not isinstance(content, dict):
                continue
            for row in content.get('candidate_facts', []):
                if isinstance(row, dict) and reverse.get(row.get('id'), row.get('id')) in selected_edges:
                    identifier = reverse.get(row.get('id'), row.get('id'))
                    recorded_links[identifier] = dict(id=identifier, text=row.get('triple'), status=row.get('status'),
                                                      concept_hint=identifier.startswith('has_concept_'))
            for row in content.get('context', []):
                if not isinstance(row, dict) or not isinstance(row.get('source_reference'), dict):
                    continue
                ref = {k: reverse.get(v, v) if isinstance(v, str) else v
                       for k, v in row['source_reference'].items()}
                ref['quote'] = row.get('text', '')
                passages[reverse.get(row.get('id'), row.get('id'))] = dict(evidence=ref, claim_ids=[])
    blocks = {b['id']: b for b in value.get('blocks', [])}
    claims = {c['id']: c for c in value.get('claims', [])}
    answer = run.get('answer') or {}
    cited = set(answer.get('citations', []))
    provided = set(run.get('provided_ids', []))
    retrieved = {r['block_id'] for r in run.get('retrieval', [])}
    evidence = []
    for identifier in dict.fromkeys([*answer.get('citations', []), *run.get('provided_ids', []), *sorted(retrieved)]):
        passage = passages.get(identifier)
        claim = claims.get(identifier)
        refs = [passage['evidence']] if passage else claim.get('evidence', []) if claim else []
        evidence.append(dict(id=identifier, cited=identifier in cited, provided=identifier in provided,
            retrieved=identifier in retrieved, claim_ids=passage.get('claim_ids', []) if passage else [identifier] if claim else [],
            statement=claim.get('statement') if claim else None,
            evidence=_claim_view(dict(evidence=refs), blocks, sources, versions)['evidence'],
            fallback_text=(run.get('passage_index') or {}).get('texts', {}).get(identifier)))
    retrieval = run.get('graph_retrieval') or {}
    source_citations = deepcopy(run.get('answer_source_citations') or dict(status='not_recorded', citations=[],
        duplicates_removed=0, semantic_support='not_assessed', answer_binding='global'))
    for ref in source_citations['citations']:
        if ref['address_status'] == 'matched':
            block = blocks.get(ref['block_id'], {})
            matching = (block.get('source_version_id') == ref['source_version_id']
                and (block.get('parse_run_id') or block.get('run_id')) == ref['parse_run_id'])
            ref.update(_claim_view(dict(evidence=[ref]),
                {ref['block_id']: block} if matching else {}, sources, versions)['evidence'][0])
    selected_links = [e for e in graph['edges'] if e['id'] in selected_edges]
    return dict(items=items, detail=dict(id=run['id'], question=run['query']['question'],
        status=run.get('answer_status'), answer=answer, finished_at=run.get('finished_at'),
        evidence=evidence, source_citations=source_citations, source_run_id=run['query'].get('source_run_id'),
        snapshot_id=run['query'].get('snapshot_id') or (None if run['query'].get('source_run_id') else run.get('snapshot_id')),
        context_mode=run.get('context_mode'), retrieval=run['query'].get('retrieval'),
        graph_links=selected_links, recorded_links=list(recorded_links.values()), recorded_edge_count=len(selected_edges),
        fallback=retrieval.get('fallback'), metrics=run.get('metrics'),
        used_version_ids=run.get('input_version_ids', []), requirement_ids=run['query'].get('requirement_ids', []),
        used_versions=[dict(id=v, title=sources.get(versions.get(v, {}).get('source_id'), {}).get('title'),
                            filename=versions.get(v, {}).get('filename'), dates=versions.get(v, {}).get('dates'))
                       for v in run.get('input_version_ids', [])],
        answer_mode=run['query'].get('answer_mode'), recorded_invalidations=run.get('snapshot_invalidations', []),
        current_usage=usage(service, kind, scope_id),
        note='저장된 답변과 당시 인용 기록입니다. 현재 생성 또는 의미 정확성 검증 결과가 아닙니다.'))


def explore(service, kind, scope_id, *, q='', selected_id=None, item_kind='all', offset=0, limit=40,
            relation_type='', direction='both', source_id='', review_state='', depth=1, graph_root=''):
    if item_kind not in {'all', 'node', 'entity', 'event', 'relation', 'claim', 'concept', 'search_concept'} or offset < 0 or not 1 <= limit <= 100:
        raise ValueError('목록 조건이 올바르지 않습니다.')
    if direction not in {'both', 'out', 'in'} or not 1 <= depth <= 3:
        raise ValueError('그래프 탐색 조건이 올바르지 않습니다.')
    value, graph, sources, versions = _scope(service, kind, scope_id)
    graph_available = kind == 'source_graph' or isinstance(value.get('graph'), dict)
    nodes = {n['id']: n for n in graph['nodes']}
    edges = {e['id']: e for e in graph['edges']}
    claims = {c['id']: c for c in value.get('claims', [])}
    blocks = {b['id']: b for b in value.get('blocks', [])}
    stored_concepts = value.get('concepts', [])
    known_claims = set(claims)
    if kind == 'source_graph' and value.get('run_id'):
        with service.repository.connect() as db:
            known_claims.update(row[0] for row in db.execute("""SELECT json_extract(claim.value,'$.id')
                FROM runs, json_each(runs.payload,'$.claims') claim WHERE runs.id=?""", (value['run_id'],)))
    concept_records, concept_issues = [], {}
    for record in stored_concepts:
        target = record['target']
        ids = set(target.get('claim_ids', []))
        if kind == 'source_graph' and ids and ids <= known_claims and not ids.intersection(claims):
            continue  # Known unselected claims remain in the stored snapshot and original run.
        concept_records.append(record)
        if kind == 'source_graph':
            linked = (any(e['relation'] == target['label'] and ids.intersection(_edge_claim_ids(e)) for e in edges.values())
                      if target['kind'] == 'relation' else target['id'] in nodes)
            if not ids or not ids <= known_claims or not linked:
                concept_issues[record['id']] = '현재 주장·그래프의 대상 연결 확인 필요'
    rows = [dict(id=n['id'], kind=n['kind'], label=n['label'], claim_ids=n.get('claim_ids', []),
                 **{k:n[k] for k in ('concept_record_ids', 'request_ids', 'work_ids', 'state') if k in n}) for n in nodes.values()]
    rows += [dict(id=e['id'], kind='relation', label=e['relation'], claim_ids=_edge_claim_ids(e),
                  **{k:e[k] for k in ('concept_record_ids', 'request_ids', 'work_ids', 'concepts', 'approved_is_a') if k in e},
                  head=e['head'], tail=e['tail'], head_label=nodes.get(e['head'], {}).get('label'),
                  tail_label=nodes.get(e['tail'], {}).get('label')) for e in edges.values()]
    graph_rows = rows[:]
    names = Counter(n['label'] for n in nodes.values())
    for row in rows:
        if row['kind'] in {'entity', 'event'} and names[row['label']] > 1:
            own = next((claims[c] for c in row['claim_ids'] if c in claims), {})
            titles = list(dict.fromkeys(sources.get(versions.get(v, {}).get('source_id'), {}).get('title')
                or versions.get(v, {}).get('filename') or v for c in row['claim_ids'] if c in claims
                for v in claims[c].get('source_version_ids', [])))
            row['disambiguation'] = ' · '.join([*titles, own.get('statement', '')]).strip(' ·')
    rows += [dict(id=c['id'], kind='claim', label=c.get('statement') or '문장 미기록', claim_ids=[c['id']],
                  state=c.get('review_status', 'unrecorded'), issue=c.get('extraction_error')) for c in claims.values()]
    rows += [dict(id=c['id'], kind='concept', label=c['target']['label'],
                  claim_ids=([cid for cid in c['target'].get('claim_ids', []) if cid in claims]
                             if kind == 'source_graph' else c['target'].get('claim_ids', [])),
                  state=c['status'], concepts=c.get('concepts', []), issue=concept_issues.get(c['id']),
                  request_ids=[c['request_id']] if c.get('request_id') else [],
                  work_ids=[c['work_id']] if c.get('work_id') else []) for c in concept_records]
    query = q.strip().casefold()
    def claim_matches(claim_id):
        claim = claims.get(claim_id, {})
        ids = claim.get('source_version_ids') or [e.get('source_version_id') for e in claim.get('evidence', [])]
        return (not source_id or any(versions.get(v, {}).get('source_id') == source_id for v in ids)) and (
            not review_state or claim.get('review_status', 'unrecorded') == review_state)
    if source_id or review_state:
        records = {c['id']: c for c in concept_records}
        for row in rows:
            if row['kind'] != 'search_concept':
                continue
            row['claim_ids'] = [cid for cid in row['claim_ids'] if claim_matches(cid)]
            bound = [records[rid] for rid in row['concept_record_ids']
                     if set(records[rid]['target']['claim_ids']).intersection(row['claim_ids'])]
            row['concept_record_ids'] = [c['id'] for c in bound]
            row['request_ids'] = list(dict.fromkeys(c['request_id'] for c in bound if c.get('request_id')))
            row['work_ids'] = list(dict.fromkeys(c['work_id'] for c in bound if c.get('work_id')))
    eligible_edges = [e for e in edges.values() if (not relation_type or e['relation'] == relation_type)
                      and any(claim_matches(cid) for cid in _edge_claim_ids(e))]
    linked_ids = {n for e in eligible_edges for n in [e['head'], e['tail']]}
    eligible_nodes = {n['id'] for n in nodes.values() if (not relation_type or n['id'] in linked_ids)
                      and any(claim_matches(c) for c in n.get('claim_ids', []))}
    eligible_ids = eligible_nodes | {e['id'] for e in eligible_edges}
    eligible_ids.update(r['id'] for r in rows if r['kind'] in {'claim', 'concept'} and
                        (not source_id and not review_state or any(claim_matches(c) for c in r['claim_ids'])))
    filtered = [r for r in rows if r['id'] in eligible_ids and ((item_kind == 'all' and r['kind'] in {'entity', 'event', 'relation', 'search_concept'}) or r['kind'] == item_kind or (item_kind == 'node' and r['kind'] in {'entity', 'event', 'search_concept'}))
                and (not query or query in ' '.join(str(r.get(k) or '') for k in ['label', 'head_label', 'tail_label', 'id']).casefold())]
    selected = next((r for r in rows if r['id'] == selected_id), None)
    if selected_id and selected is None:
        raise KeyError(selected_id)
    anchor = next((r for r in rows if r['id'] == graph_root), None)
    roots = [anchor] if anchor and graph_root in eligible_ids else filtered[:12] if not anchor else []
    node_limit = {1: 8, 2: 20, 3: 40}[depth]
    visible_nodes = set()
    for root in roots:
        if root['kind'] in {'claim', 'concept'}:
            visible_nodes.update(n['id'] for n in nodes.values() if set(root['claim_ids']).intersection(n.get('claim_ids', [])))
        else:
            visible_nodes.update([root['head'], root['tail']] if root['kind'] == 'relation' else [root['id']])
    source_root = any(root['kind'] in {'claim', 'concept'} for root in roots)
    visible_nodes = set(sorted(visible_nodes, key=lambda n: (source_root and nodes[n]['kind'] == 'search_concept', n))[:node_limit])
    frontier = set(visible_nodes)
    traversed = set()
    for _ in range(depth):
        adjacent = [e for e in eligible_edges if
                    (direction != 'in' and e['head'] in frontier) or (direction != 'out' and e['tail'] in frontier)]
        following = set()
        for edge in adjacent:
            endpoints = {edge['head'], edge['tail']}
            if len(visible_nodes | endpoints) <= node_limit and len(traversed) < 80:
                following.update(endpoints - visible_nodes)
                visible_nodes.update(endpoints)
                traversed.add(edge['id'])
        frontier = following
    # Keep parallel edges between visible endpoints; each keeps its own ID and claim.
    drawn_edges = [e for e in eligible_edges if e['id'] in traversed]
    drawn_ids = visible_nodes | traversed
    graph_view = dict(items=[r for r in graph_rows if r['id'] in drawn_ids], depth=depth,
        nodes=len(visible_nodes), relations=len(drawn_edges), eligible_nodes=len(eligible_nodes),
        eligible_relations=len(eligible_edges), omitted_nodes=len(nodes) - len(visible_nodes),
        omitted_relations=len(edges) - len(drawn_edges),
        filter_excluded_relations=len(edges) - len(eligible_edges),
        selected_excluded=bool(selected and selected_id not in eligible_ids),
        reason=f'선택 또는 검색 결과에서 방향에 맞는 이웃만 표시 · 이번 범위 최대 {node_limit}개 대상 / 80개 관계. 미표시 항목은 필터·이웃 범위·표시 한도에 따라 제외됩니다.')
    detail = None
    if selected:
        connected = [e for e in eligible_edges if selected_id in (e['head'], e['tail'])]
        detail = dict(item=selected, claims=[_claim_view(claims[c], blocks, sources, versions)
                      for c in selected['claim_ids'] if c in claims and claim_matches(c)],
                      concept_records=[dict({k:c.get(k) for k in ('id', 'concepts', 'status', 'request_id', 'work_id')},
                          target=dict(c['target'], claim_ids=[cid for cid in c['target'].get('claim_ids', [])
                              if cid in claims and claim_matches(cid)]) if kind == 'source_graph' else c['target'])
                          for c in concept_records if c['id'] in selected.get('concept_record_ids', [])
                          and any(claim_matches(cid) for cid in c['target'].get('claim_ids', []))],
                      relations=[dict(**e, head_label=nodes.get(e['head'], {}).get('label'),
                                      tail_label=nodes.get(e['tail'], {}).get('label')) for e in connected],
                      changeset_id=value.get('changeset_id'), run_id=value['id'] if kind == 'run' else value.get('run_id'),
                      history=[dict(id=r['id'], actor=r.get('actor'), reason=r.get('reason'), status=r.get('status'),
                          changes=[dict(before=c.get('before', {}).get('statement'), after=c.get('after', {}).get('statement'))
                                   for c in r.get('changes', []) if c.get('after', {}).get('id') in selected['claim_ids']])
                               for r in value.get('repairs', []) if any(c.get('after', {}).get('id') in selected['claim_ids'] for c in r.get('changes', []))])
    version_ids = value.get('input_version_ids') or list(value.get('source_versions') or [])
    if not version_ids:
        version_ids = list(dict.fromkeys(b.get('source_version_id') for b in blocks.values() if b.get('source_version_id')))
    source_ids = set(versions.get(v, {}).get('source_id') for v in version_ids) - {None}
    return dict(scope=dict(kind=kind, id=scope_id, status=value.get('status') if kind == 'run' else 'selection_recorded', created_at=value.get('started_at') or value.get('created_at'),
                    data_label='자동 추출 결과 · 미승인' if kind == 'run' else '출처 지식 선택 기록 · 온톨로지와 별도',
                    title=' · '.join(sources[s]['title'] for s in sources if s in source_ids) or '출처 정보 미기록',
                    changeset_id=value.get('changeset_id'), version_ids=version_ids, graph_available=graph_available,
                    partial=value.get('status') in {'partial', 'cancelled', 'failed'} or value.get('extraction_complete') is False),
                counts=dict(nodes=len(nodes) if graph_available else None, relations=len(edges) if graph_available else None,
                    claims=len(claims), blocks=len(blocks),
                    sources=len(source_ids), versions=len(version_ids), concepts=len(concept_records),
                    stored_concepts=len(stored_concepts), historical_concepts=len(stored_concepts) - len(concept_records),
                    unresolved_concept_links=len(concept_issues),
                    search_concepts=sum(n['kind'] == 'search_concept' for n in nodes.values()),
                    failed_concepts=sum(c.get('status') == 'failed' for c in concept_records),
                    excluded_claims=sum(bool(c.get('extraction_error') or c.get('superseded_by')) for c in claims.values()),
                    claim_review=dict(Counter(c.get('review_status', 'unrecorded') for c in claims.values()))),
                items=filtered[offset:offset + limit], filtered_count=len(filtered), offset=offset, limit=limit,
                detail=detail, graph=graph_view,
                filters=dict(relation_types=sorted({e['relation'] for e in edges.values()}),
                    sources=[dict(id=s, title=sources[s]['title']) for s in sources if s in source_ids],
                    review_states=sorted({c.get('review_status', 'unrecorded') for c in claims.values()})),
                count_policy='선택한 단일 저장 결과의 ID 기준이며 반복 실행을 합산하지 않습니다.')
