"""Current source/evidence availability ledger, independent of schema-first execution."""
import json
from uuid import uuid4
from . import legacy_records as store
from .repository import VersionConflict
from .schemas import AvailabilityRequest
from .service import encode, utcnow


def _state(db):
    return dict(db.execute('SELECT active_snapshot_id,status_revision FROM knowledge_state WHERE id=1').fetchone())


def _statuses(db):
    # ponytail: scan the small local history; index latest rows if the pilot grows.
    return {(row['target_type'], row['target_id']): json.loads(row['payload'])
            for row in db.execute('SELECT * FROM availability_history ORDER BY status_revision')}


def _write_status(db, targets, state, actor, reason):
    revision = _state(db)['status_revision'] + 1
    now = utcnow()
    for kind, identifier in sorted(set(targets)):
        value = dict(id=uuid4().hex, type=kind, target_id=identifier, state=state,
                     status_revision=revision, actor=actor, reason=reason, recorded_at=now)
        db.execute('INSERT INTO availability_history VALUES(?,?,?,?,?)',
                   (value['id'], revision, kind, identifier, encode(value)))
    db.execute('UPDATE knowledge_state SET status_revision=? WHERE id=1', (revision,))
    return revision


def availability(service, kind, identifier):
    with service.lock, service.repository.connect() as db:
        _target_exists(service.repository, db, kind, identifier)
        history = [json.loads(row['payload']) for row in db.execute(
            'SELECT payload FROM availability_history WHERE target_type=? AND target_id=? ORDER BY status_revision DESC',
            (kind, identifier))]
        return dict(type=kind, target_id=identifier, state=history[0]['state'] if history else 'allowed',
                    history=history, **_state(db))


def _target_exists(repo, db, kind, identifier):
    table = {'assertion': 'assertions', 'evidence': 'evidence', 'source_version': 'versions'}.get(kind)
    if not table:
        raise ValueError('지원하지 않는 사용 상태 대상입니다.')
    if store._optional(repo, db, table, identifier) is None:
        raise KeyError(identifier)


def set_availability(service, request):
    request = AvailabilityRequest.model_validate(request)
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if _state(db)['status_revision'] != request.expected_status_revision:
            raise VersionConflict('사용 상태가 변경되었습니다. 다시 조회해 주세요.')
        targets = [(t.type, t.id) for t in request.targets]
        if len(set(targets)) != len(targets):
            raise ValueError('같은 상태 대상을 중복 지정할 수 없습니다.')
        for kind, identifier in targets:
            _target_exists(service.repository, db, kind, identifier)
        revision = _write_status(db, targets, request.state, request.actor, request.reason)
        return dict(status_revision=revision, status_checked_at=utcnow())


def _evidence_ids(candidate):
    fields, dates = candidate.get('field_evidence'), candidate.get('dates')
    groups = [candidate.get('evidence_ids'), candidate.get('dependency_evidence_ids')]
    if isinstance(fields, dict):
        groups.extend(fields.values())
    if isinstance(dates, list):
        groups.extend(d.get('evidence_ids') for d in dates if isinstance(d, dict))
    return {i for group in groups if isinstance(group, list) for i in group if isinstance(i, str)}


def current_restrictions(repo, db, candidate, statuses=None):
    """Availability annotations for the existing review screen (not persisted)."""
    statuses = _statuses(db) if statuses is None else statuses
    ids = _evidence_ids(candidate)
    ontology = store._optional(repo, db, 'ontology_versions', candidate.get('ontology_version_id'))
    if ontology and ontology.get('payload_version') == 2:
        ids.update(store.evidence_ids(ontology))
    links = [candidate] if candidate.get('kind') == 'entity_link' else []
    for key in ('subject_link_id', 'object_link_id'):
        link = store._optional(repo, db, 'entity_links', candidate.get(key))
        if link:
            links.append(link)
    for link in links:
        ids.update(_evidence_ids(link))
        entity = store._optional(repo, db, 'entities', link.get('target_entity_id')) or {}
        ids.update(entity.get('evidence_ids', []))
    targets = {('assertion', candidate['id'])} if candidate.get('kind') == 'assertion' else set()
    for identifier in ids:
        targets.add(('evidence', identifier))
        ev = store._optional(repo, db, 'evidence', identifier) or {}
        block = store._optional(repo, db, 'blocks', ev.get('block_id')) or {}
        if block.get('source_version_id'):
            targets.add(('source_version', block['source_version_id']))
    return [dict(type=kind, id=identifier, state=statuses[kind, identifier]['state'])
            for kind, identifier in sorted(targets) if statuses.get((kind, identifier), {}).get('state', 'allowed') != 'allowed']
