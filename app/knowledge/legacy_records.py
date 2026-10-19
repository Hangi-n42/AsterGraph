"""Read-only compatibility for historical schema-first records; no model or write path."""
from copy import deepcopy
import json
import yaml


def _optional(repo, db, table, identifier):
    if not identifier:
        return None
    try:
        return repo.get(db, table, identifier)
    except KeyError:
        if table == 'evidence':
            block = _optional(repo, db, 'blocks', identifier)
            if block:
                return dict(id=identifier, block_id=block['id'], quote=block['text'], start_char=0,
                            end_char=len(block['text']), alignment_status='matched')
        return None


def annotated(obj, name, default=None):
    raw = obj.get('annotations', {}).get(name)
    return json.loads(raw['value']) if raw else deepcopy(default)


def targets(version):
    """Read v1 identities without migration; read v2 definitions from their canonical owner."""
    if not version:
        return {}
    schema = yaml.safe_load(version['linkml_yaml'])
    result = {}
    for group in ('classes', 'slots'):
        for symbol, d in schema.get(group, {}).items():
            item = annotated(d, 'ontology_target')
            if item is None:
                legacy = annotated(d, 'candidate')
                if legacy is None:
                    continue
                item = dict(legacy, kind='class' if legacy['kind']=='concept' else legacy['kind'])
                item['evidence_refs'] = item.pop('evidence', [])
            item.update(symbol=symbol, name=d.get('title', symbol), definition=d.get('description', ''),
                        deprecated=bool(d.get('deprecated')))
            if group == 'slots':
                item.update(domain_id=d.get('domain'), range=d.get('range', 'string'),
                            required=bool(d.get('required')), multivalued=bool(d.get('multivalued')))
                enum = schema.get('enums', {}).get(item['range'])
                if enum:
                    item.update(range='string', enum_values=list(enum.get('permissible_values', {})))
            result[item['id']] = item
    # References use stable IDs; symbols are only LinkML names.
    ids = {t['symbol']: t['id'] for t in result.values()}
    for t in result.values():
        for key in ('domain_id', 'range'):
            if key in t:
                t[key] = ids.get(t[key], t[key])
    result.update({t['id']: t for t in annotated(schema, 'ontology_links', [])})
    result.update(deepcopy(version.get('vocabulary_registry', {}).get('targets', {})))
    return result


def evidence_ids(version):
    items = targets(version)
    return {identifier for t in items.values() if not t.get('deprecated')
            for identifier in [*[e['evidence_id'] for e in [*t.get('evidence_refs', []), *t.get('counter_evidence_refs', [])]],
                               *t.get('dependency_block_ids', [])]}


def extraction_candidates(service, changeset_id):
    with service.repository.connect() as db:
        change = service.repository.get(db, "changesets", changeset_id)
        if change.get("kind") != "extraction":
            return []
        return [_optional(service.repository, db, "entity_links", identifier)
                or service.repository.get(db, "assertions", identifier)
                for identifier in change["candidate_ids"]]
