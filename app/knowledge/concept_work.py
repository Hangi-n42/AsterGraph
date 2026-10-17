"""Exact concept execution identity and provenance; target IDs remain independent."""
from copy import deepcopy
from hashlib import sha256
import json

VERSION = 'exact-original-concept-work-v1'


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def prepare(run, item):
    target, selection = item['target'], item['selection']
    dependencies = deepcopy(selection['source_dependencies'])
    meanings = [m for cid in target['claim_ids'] for m in run['graph'].get('interpretations', {}).get(cid, {}).get('meanings', [])]
    qualifiers = [{k:m.get(k) for k in ['conditions','exceptions','time','local_negation','references','premises']} for m in meanings]
    recipe = run['recipe']; options = recipe['options']
    return dict(input_complexity=dict(claims=len(target['claim_ids']), meanings=len(meanings),
        qualifier_chars=len(json.dumps(qualifiers, ensure_ascii=False, sort_keys=True))),
        version=VERSION, stage='concept_' + target['kind'], kind=target['kind'], label=target['label'],
        messages_sha256=digest(item['messages']), schema_sha256=digest(None),
        reference_map=deepcopy(selection['source_reference_map']), context_dependencies=dependencies,
        selection=deepcopy(selection),
        actual_neighbor_edge_ids=list(selection['selected_edge_ids']) if target['kind'] == 'entity' else [],
        request_configuration=dict(model=recipe.get('models', {}).get('draft'), generation=deepcopy(recipe.get('generation')),
            identity=deepcopy(run.get('model_identity')), temperature=0, timeout=options.get('timeout')),
        requested_limits={k:options.get(v) for k,v in [('max_tokens','concept_tokens'),('context_tokens','context_tokens'),('think','think')]},
        runtime=None)


def unknown_fields(contract):
    if not contract:
        return ['concept_work_input']
    missing = []
    configuration = contract['request_configuration']; runtime = contract.get('runtime') or {}
    identities = configuration.get('identity') or {}
    identity = identities.get('draft') if isinstance(identities, dict) else None
    identity = identity if isinstance(identity, dict) else {}
    for key, value in [('model_digest',identity.get('digest')), ('provider',(configuration.get('generation') or {}).get('provider')),
                       ('engine',runtime.get('engine')), ('engine_version',runtime.get('engine_version')),
                       ('weights_precision',(runtime.get('precision') or {}).get('weights'))]:
        if not value: missing.append(key)
    sampling = runtime.get('sampling') or {}
    if sampling.get('contract') != 'ollama-request-and-model-defaults-v1': missing.append('sampling_contract')
    for key in ['model_parameters','model_configuration_sha256']:
        if sampling.get(key) is None: missing.append('sampling.' + key)
    wanted = dict(temperature=configuration.get('temperature'), num_predict=contract['requested_limits'].get('max_tokens'),
                  num_ctx=contract['requested_limits'].get('context_tokens'))
    if sampling.get('request_options') != wanted or sampling.get('think') != contract['requested_limits'].get('think'):
        missing.append('actual_request_options')
    if runtime.get('engine') != (configuration.get('generation') or {}).get('provider'):
        missing.append('current_engine')
    if runtime.get('model_digest') != identity.get('digest'):
        missing.append('current_model_digest')
    for key in ['max_tokens','context_tokens','think']:
        if contract['requested_limits'].get(key) is None: missing.append(key)
    for dep in contract['context_dependencies']:
        if dep.get('unresolved') or not dep.get('source_version_id') or not dep.get('parse_run_id') or not dep.get('text_sha256'):
            missing.append('source_dependency:' + dep['alias'])
    if not contract['context_dependencies']: missing.append('source_dependencies')
    return missing


def complete(unit):
    response = unit.get('response') or {}
    return (unit.get('status') == 'succeeded' and not unit.get('error') and not unit.get('discarded')
            and not unit.get('superseded_by') and response.get('done') is True
            and response.get('done_reason') in {'stop','eos','end_turn'} and not response.get('failure_kind')
            and any(x.strip() for x in response.get('text', '').split(',')))


def reusable(service, run, unit, expected, donor_run_id):
    if unknown_fields(expected) or unit.get('concept_work_input') != expected or not complete(unit):
        return False
    if unit.get('requested_limits') != unit.get('executed_limits') or unit.get('executed_limits') != expected['requested_limits']:
        return False
    donor = run
    if donor_run_id != run['id']:
        if donor_run_id not in {run.get('parent_run_id'),run.get('reuse_pool_parent_run_id')}:
            return False
        with service.repository.connect() as db:
            donor = service.repository.get(db, 'runs', donor_run_id)
        original = next((u for u in donor['units'] if u['id'] == unit['id']), None)
        if original != unit:
            return False
    return all(c['status'] not in {'failed','rejected','discarded','superseded'} and not c.get('superseded_by') and not c.get('discarded')
               for c in donor.get('concepts', []) if c.get('request_id') == unit['id'])


def validate_request(contract, unit):
    if (contract['stage'] != unit['stage'] or contract['messages_sha256'] != digest(unit['messages'])
            or contract['schema_sha256'] != digest(unit['schema']) or contract['reference_map'] != unit['reference_map']
            or contract['request_configuration'] != unit['request_configuration']
            or contract['requested_limits'] != unit['requested_limits']):
        raise ValueError('개념화 작업 계약과 실제 요청이 다릅니다.')


def source_input_fingerprint(item):
    value = item['work_input']
    return digest({k:value[k] for k in ['kind','label','messages_sha256','schema_sha256','reference_map',
        'context_dependencies','actual_neighbor_edge_ids']})


def same_input(unit, concept, item):
    if concept.get('source_input_fingerprint'):
        return concept['source_input_fingerprint'] == source_input_fingerprint(item)
    return (unit.get('messages') == item['messages'] and unit.get('schema') is None
            and concept.get('selection', {}).get('source_reference_map') == item['selection']['source_reference_map']
            and unit.get('reference_map') in (None, item['selection']['source_reference_map']))
