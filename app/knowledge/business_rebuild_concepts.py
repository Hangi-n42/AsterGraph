"""Verified source-result bindings, separate from exact original concept work."""
from copy import deepcopy

from . import autoschema, business_concepts, concept_work
from .business_rebuild_html import project


def projected_parent(parent, run):
    mapping = run['source_rebuild']['source_address_map']
    claims = {c['id']: c for c in run['claims']}
    chunks = {c['id']: c for c in run['chunks']}
    view = deepcopy(parent)
    view['claims'] = [deepcopy(claims.get(mapping.get(c['id']), c)) for c in parent['claims']]
    view['chunks'] = [deepcopy(chunks.get(mapping.get(c['id']), c)) for c in parent['chunks']]
    view['graph'] = autoschema.graph(view['claims'])
    view['blocks'] = [deepcopy(next((b for b in run['blocks'] if b['id'] == mapping.get(old['id'])), old))
                      for old in parent['blocks']]
    return view


def bind_unchanged(service, run, planned):
    receipt = run.get('source_rebuild') or {}
    if not receipt.get('source_claim_bindings') or run['recipe']['options'].get('concept_source_context', 'whole') != 'whole':
        return set()
    with service.repository.connect() as db:
        parent = service.repository.get(db, 'runs', receipt['parent_run_id'])
    if (parent['recipe'].get('concept_work_contract') != concept_work.VERSION
            or run['recipe'].get('concept_work_contract') != concept_work.VERSION
            or any(parent['recipe'].get(k) != run['recipe'].get(k) for k in ('generation', 'models'))
            or any(parent['recipe']['options'].get(k) != run['recipe']['options'].get(k)
                   for k in ('neighbor_mode', 'concept_source_context', 'concept_tokens', 'context_tokens', 'think', 'timeout'))
            or parent['model_identity'] != run['model_identity']):
        return set()
    mode = run['recipe']['options']['neighbor_mode']
    old = business_concepts.prepare(parent, autoschema.concept_targets(parent['graph']),
                                    parent['recipe']['options']['neighbor_mode'], service=service)
    view = projected_parent(parent, run)
    projected = business_concepts.prepare(view, autoschema.concept_targets(view['graph']), mode, service=service)
    mapping = receipt['source_address_map']
    paired = {}
    # Full node/target shape includes source ownership, multiplicity and exact mention identity.
    for item in old:
        target = project({k: v for k, v in item['target'].items() if k != 'id'}, mapping)
        matches = [p for p in projected if {k: v for k, v in p['target'].items() if k != 'id'} == target]
        if len(matches) == 1:
            paired[item['target']['id']] = matches[0]
    bound = set()
    for item in planned:
        donors = [(o, paired[o['target']['id']]) for o in old if o['target']['id'] in paired
                  and paired[o['target']['id']]['target'] == item['target']]
        if len(donors) != 1:
            continue
        original, projected_item = donors[0]
        if any(projected_item[k] != item[k] for k in ('target', 'messages', 'selection', 'work_input')):
            continue
        concepts = [c for c in parent['concepts'] if c['target'] == original['target']
                    and c['status'] in {'unreviewed', 'accepted'} and not c.get('discarded') and not c.get('superseded_by')]
        if len(concepts) != 1:
            continue
        donor = concepts[0]
        units = [u for u in parent['units'] if u['id'] == donor.get('request_id')]
        if len(units) != 1:
            continue
        unit = units[0]
        expected = deepcopy(original['work_input'])
        expected['runtime'] = deepcopy((unit.get('concept_work_input') or {}).get('runtime'))
        if (unit.get('messages') != original['messages'] or unit.get('schema') is not None
                or unit.get('reference_map') != original['selection']['source_reference_map']
                or not concept_work.reusable(service, parent, unit, expected, parent['id'])):
            continue
        current = deepcopy(item['work_input'])
        business_concepts.observe_execution(run, current)
        if (concept_work.unknown_fields(current) or any(current[k] != expected[k]
                for k in ('request_configuration', 'requested_limits', 'runtime'))):
            continue
        existing = [c for c in run['concepts'] if c['target'] == item['target']
            and c['status'] == 'unreviewed' and c.get('source_result_binding', {}).get('donor_unit_id') == unit['id']
            and c.get('source_input_fingerprint') == concept_work.source_input_fingerprint(item)]
        if len(existing) == 1:
            bound.add(item['target']['id'])
            continue
        identifier = autoschema.identifier('source_concept', [run['id'], donor['id'], item['target']['id']])
        binding = dict(concept_id=identifier, target=deepcopy(item['target']), donor_run_id=parent['id'],
            donor_concept_id=donor['id'], donor_unit_id=unit['id'], donor_work_id=donor.get('work_id'),
            original_input_sha256=concept_work.digest(expected), projected_input_sha256=concept_work.digest(item['work_input']),
            source_reference_map=deepcopy(item['selection']['source_reference_map']),
            method='verified_source_result_rebinding; not_exact_work_reuse', approval_inherited=False,
            status='unreviewed', relation='has_concept', approved_is_a=False)
        existing = [c for c in run['concepts'] if c['id'] == identifier]
        if not existing:
            run['concepts'].append(dict(id=identifier, target=deepcopy(item['target']), selection=deepcopy(item['selection']),
                concepts=deepcopy(donor['concepts']), status='unreviewed', relation='has_concept', approved_is_a=False,
                source_result_binding=binding, source_input_fingerprint=concept_work.source_input_fingerprint(item)))
            run.setdefault('source_concept_bindings', []).append(binding)
        bound.add(item['target']['id'])
    return bound
