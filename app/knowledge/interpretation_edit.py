"""Explicit, source-bound edits of two interpretation fields, without model work."""
from copy import deepcopy
import json

from . import autoschema, business_run, business_use, concept_work
from .service import KnowledgeConflict, encode, utcnow
from .source_meanings import remap


def source_fingerprint(run, claim):
    versions = set(claim['source_version_ids'])
    return concept_work.digest(dict(sources={v: run['sources'][v] for v in sorted(versions)},
        blocks=[b for b in run['blocks'] if b['source_version_id'] in versions]))


def basis(run, claim):
    return dict(claim_id=claim['id'], expected_claim_version=autoschema.identifier('claim', claim),
        expected_source_fingerprint=source_fingerprint(run, claim),
        meanings=[dict(id=m['id'], version=concept_work.digest(m), conditions=deepcopy(m['conditions']),
            relation_kind=m['relation_kind']) for m in (claim.get('interpretation') or {}).get('meanings', [])])


def concept_packets(run):
    chunks = business_run.source_chunks(run)
    packets = {}
    for target in autoschema.concept_targets(run['graph']):
        messages, selection = autoschema.concept_messages(target, run['graph'], chunks,
                                                        run['recipe']['options']['neighbor_mode'])
        packets[target['id']] = concept_work.digest(dict(target=target, messages=messages, selection=selection))
    return packets


def start(service, changeset_id, request):
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        identifier = autoschema.identifier('interpretation_edit', [changeset_id, request.idempotency_key])
        existing = db.execute('SELECT payload FROM runs WHERE id=?', (identifier,)).fetchone()
        if existing:
            child = json.loads(existing['payload'])
            if child['interpretation_edit']['request'] != request.model_dump():
                raise KnowledgeConflict('같은 멱등 키에 다른 정정 요청이 있습니다.')
            return dict(run_id=identifier, changeset_id=child['changeset_id'], status=child['status'], duplicate_request=True)
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('기존 실행 종료 후 해석 필드를 정정하세요.')
        change = service.repository.get(db, 'changesets', changeset_id)
        if change.get('kind') != 'source_graph' or change['revision'] != request.expected_revision:
            raise KnowledgeConflict('변경안 버전이 다릅니다.')
        parent = service.repository.get(db, 'runs', change['run_id'])
        from .business_rebuild import validate_run, inherit_review_guard
        validate_run(service, db, parent)
        if parent['status'] in {'running', 'queued', 'cancel_requested'}:
            raise KnowledgeConflict('종료된 후보만 정정할 수 있습니다.')
        if business_use.restricted_sources(db, parent['input_version_ids']):
            raise KnowledgeConflict('사용이 제한된 원문이 있습니다.')
        for requirement in parent['requirements']:
            current = service.repository.get(db, 'requirements', requirement['id'])
            if current['revision'] != requirement['revision'] or current['status'] == 'needs_review':
                raise KnowledgeConflict('요구·원문 변경 이후 재검수가 필요합니다.')
        if len({c.claim_id for c in request.claims}) != len(request.claims):
            raise ValueError('중복 주장 정정입니다.')
        child = deepcopy(parent)
        child.update(id=identifier, parent_run_id=parent['id'], status='partial', started_at=utcnow(), finished_at=utcnow(),
                     metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0))
        records = []
        changed = {item.claim_id for item in request.claims}
        for item in request.claims:
            old = next((c for c in parent['claims'] if c['id'] == item.claim_id), None)
            published = next((c for c in change['candidates'] if c['id'] == item.claim_id), None)
            if (old is None or old != published or old.get('superseded_by') or old.get('extraction_error')
                    or autoschema.identifier('claim', old) != item.expected_claim_version
                    or source_fingerprint(parent, old) != item.expected_source_fingerprint):
                raise KnowledgeConflict('주장 또는 자기 원문의 검토 버전이 변경됐습니다.')
            for vid in old['source_version_ids']:
                version = service.repository.get(db, 'versions', vid)
                if version['sha256'] != parent['sources'][vid]['sha256']:
                    raise KnowledgeConflict('원문 파일 해시가 변경됐습니다.')
            scope = old.get('interpretation') or {}
            if scope.get('contract') != autoschema.SCOPE_CONTRACT or scope.get('errors'):
                raise ValueError('현재 주소 결속이 유효한 추출 해석만 정정할 수 있습니다.')
            value = next(c for c in child['claims'] if c['id'] == old['id'])
            if len({(p.meaning_id, p.field) for p in item.changes}) != len(item.changes):
                raise ValueError('중복 해석 필드 정정입니다.')
            original_meanings = {m['id']: m for m in scope['meanings']}
            ids, edits = {}, []
            for patch in item.changes:
                before = original_meanings.get(patch.meaning_id)
                if (before is None or concept_work.digest(before) != patch.expected_meaning_version
                        or before.get(patch.field) != patch.before):
                    raise KnowledgeConflict('해석 의미 또는 정정 전 필드 값이 변경됐습니다.')
                refs = business_run.exact_evidence([e.model_dump() for e in patch.evidence], parent['blocks'])
                own = {e['block_id'] for e in before['evidence']}
                if (not own.intersection(e['block_id'] for e in refs)
                        or any(e['source_version_id'] not in old['source_version_ids'] for e in refs)):
                    raise ValueError('해당 의미의 자기 원문 근거가 필요합니다.')
                if patch.field == 'conditions' and patch.after['state'] == 'present' and not any(
                        patch.after['text'] in e['quote'] for e in refs):
                    raise ValueError('정정한 조건 본문이 선택한 원문에 없습니다.')
                meaning = next(m for m in value['interpretation']['meanings'] if m['id'] == patch.meaning_id)
                meaning[patch.field] = deepcopy(patch.after)
                edits.append(dict(meaning_id=patch.meaning_id, before_version=patch.expected_meaning_version,
                    field=patch.field, before=deepcopy(patch.before), after=deepcopy(patch.after), evidence=refs,
                    reason=patch.reason, scope='this_proposition_and_reviewed_source_only'))
            for mid in {p.meaning_id for p in item.changes}:
                meaning = next(m for m in value['interpretation']['meanings'] if m['id'] == mid)
                ids[mid] = autoschema.identifier('interpretation', [mid, meaning, item.expected_source_fingerprint])
            # Keep the producer payload byte-for-byte in history/raw; only the current view receives new meaning IDs.
            current = {k: v for k, v in value['interpretation'].items() if k != 'raw'}
            value['interpretation'] = dict(remap(current, ids), raw=deepcopy(scope['raw']))
            value.setdefault('interpretation_history', []).append(deepcopy(scope))
            value.update(review_status='unreviewed', semantic_status='unknown', qualifier_status='explicit_reviewer_correction_unverified')
            for edit in edits:
                mid = edit['meaning_id']; after = next(m for m in value['interpretation']['meanings'] if m['id'] == ids[mid])
                edit.update(after_meaning_id=ids[mid], after_version=concept_work.digest(after))
            records.append(dict(claim_id=old['id'], before_claim_version=item.expected_claim_version,
                after_claim_version=autoschema.identifier('claim', value), source_fingerprint=item.expected_source_fingerprint,
                changes=edits))
        child['graph'] = autoschema.graph(child['claims'], child['blocks'])
        before_packets, after_packets = concept_packets(parent), concept_packets(child)
        affected = {tid for tid in before_packets if before_packets[tid] != after_packets.get(tid)}
        stale_concepts = set()
        for concept in child['concepts']:
            if concept['target']['id'] in affected:
                stale_concepts.add(concept['id'])
                concept.update(previous_status=concept['status'], status='needs_review', stale_reason='interpretation_input_corrected')
        for binding in child.get('concept_bindings', []):
            if binding['concept_id'] in stale_concepts:
                binding.update(previous_status=binding['status'], status='needs_review')
        child['interpretation_edit'] = dict(actor=request.actor, reason=request.reason, origin='explicit_reviewer',
            request=request.model_dump(), records=records, parent_fingerprint=concept_work.digest(parent),
            affected_candidate_review_ids=[r['id'] for r in parent.get('candidate_reviews', []) if changed.intersection(r['claim_ids'])],
            affected_assessment_ids=[a['id'] for a in parent['assessments']
                if a.get('input_fingerprint') != business_run.assessment_fingerprint(child,
                    next(r for r in child['requirements'] if r['id'] == a['requirement_id']), a['source'], a.get('review_scope'))],
            affected_concept_ids=sorted(stale_concepts), changed_concept_target_ids=sorted(affected),
            new_concept_target_ids=sorted(after_packets.keys()-before_packets.keys()),
            producer_work_preserved=True, automatic_reassessment=False, automatic_approval=False)
        child['interpretation_edit']['affected_requirement_ids'] = sorted({a['requirement_id'] for a in parent['assessments']
            if a['id'] in child['interpretation_edit']['affected_assessment_ids']})
        child.pop('changeset_id', None)
        child['stored_pool'] = dict(deepcopy(parent.get('stored_pool', {})), parent_run_id=parent['id'],
            claims_hash=autoschema.identifier('claims', child['claims']), source_hash=autoschema.identifier('source', child['blocks']),
            graph_hash=autoschema.identifier('graph', child['graph']), assessment_inherited=False, approval_inherited=False)
        inherit_review_guard(service, db, parent, child)
        published = business_use.publish(service, child, connection=db)
        child['changeset_id'] = published['id']
        db.execute('INSERT INTO runs VALUES(?,?)', (identifier, encode(child)))
        change['revision'] += 1
        change.setdefault('edit_run_ids', []).append(identifier)
        change['invalidated_claim_ids'] = sorted(set(change.get('invalidated_claim_ids', [])) | changed)
        service.repository.save(db, 'changesets', change)
        for row in db.execute('SELECT payload FROM snapshots').fetchall():
            snapshot = json.loads(row['payload'])
            ids = changed.intersection(c['id'] for c in snapshot.get('claims', []))
            if snapshot.get('run_id') == parent['id'] and ids:
                event_id = autoschema.identifier('interpretation_invalidation', [identifier, snapshot['id']])
                db.execute('INSERT INTO snapshot_events VALUES(?,?)', (event_id, encode(dict(id=event_id,
                    event='business_correction', snapshot_id=snapshot['id'], run_id=identifier,
                    claim_ids=sorted(ids), requirement_ids=child['interpretation_edit']['affected_requirement_ids'],
                    reason='explicit_interpretation_field_correction'))))
    return dict(run_id=identifier, changeset_id=child['changeset_id'], changeset_revision=published['revision'],
                parent_changeset_revision=change['revision'],
                status='partial', duplicate_request=False)
