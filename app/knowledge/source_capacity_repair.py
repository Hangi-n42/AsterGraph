"""Bounded source-role capacity repair using existing extraction and storage helpers."""
from copy import deepcopy
import json

from . import autoschema, business_run


def views(chunk, groups=None, required_context_views=None, additional_context_views=(), canonical_blocks=()):
    if not groups:
        assert not additional_context_views
        return [deepcopy(chunk)]
    key = lambda b: (b.get('block_id',b.get('id')), tuple(b.get('span') or ()))
    originals = {key(b):b for b in chunk['blocks']}
    canonical = {b['id']:b for b in canonical_blocks}
    for ref in additional_context_views:
        block = canonical[ref['block_id']]
        assert ref['source_version_id'] == block['source_version_id'] == chunk['source_version_id']
        assert ref['parse_run_id'] == (block.get('parse_run_id') or block.get('run_id'))
        assert ref['quote'] == block['text'] and ref['locator'] == block.get('locator')
        assert ref.get('span') is None and key(block) not in originals
        originals[key(block)] = dict(deepcopy(block), context_only=True)
    wanted = {key(b) for b in chunk['blocks'] if not b.get('context_only')}
    contexts = {k for k,b in originals.items() if b.get('context_only')}
    required = contexts if required_context_views is None else {key(b) for b in required_context_views}
    assert required <= contexts
    actual = []; result = []; included_contexts = set()
    for group in groups:
        included = [key(b) for b in group['included_views']]
        targets = {key(b) for b in group['target_views']}
        assert len(included) == len(set(included)) and set(included) <= originals.keys()
        assert required <= set(included) and targets <= wanted and targets <= set(included)
        included_contexts.update(contexts & set(included))
        blocks = [dict(originals[k], context_only=k not in targets) for k in included]
        view = deepcopy(chunk)
        view.update(id=group['id'], blocks=blocks, text=autoschema.source_text(blocks),
                    target_chars=sum(len(b['text']) for b in blocks if not b.get('context_only')),
                    source_reference_map={f'b{i+1}':dict(block_id=b['id'], span=b.get('span')) for i,b in enumerate(blocks)})
        result.append(view); actual.extend(targets)
    assert len(actual) == len(set(actual)) and set(actual) == wanted
    assert contexts <= included_contexts
    return result


def empty_event_dependency(run, row):
    """Only an original successful-empty dependent response can be refreshed here."""
    if row['role'] != 'event_entity':
        return None
    previous = [u for u in run['units'] if u['stage'] == 'event_relation'
                and u.get('source_chunk_id') == row['chunk_id']]
    if not previous:
        return None
    if (len(previous) != 1 or previous[0]['status'] != 'succeeded'
            or (previous[0].get('response') or {}).get('parsed') != []):
        raise ValueError('nonempty_or_unfinished_event_relation_dependency_not_supported')
    if row.get('groups'):
        raise ValueError('split_event_entity_dependency_not_supported')
    previous = previous[0]
    materialized = {cid for u in run['units']
        if (u.get('dependency_refresh_origin') or {}).get('unit_id') == previous['id']
        for cid in u.get('materialized_claim_ids', [])}
    if any(c['role'] == 'event_relation' and c['chunk_id'] == row['chunk_id']
           and c['id'] not in materialized for c in run['claims']):
        raise ValueError('existing_event_relation_claims_not_supported')
    return previous


def refresh_empty_event_relation(service, run, row, original):
    chunk = next(c for c in run['chunks'] if c['id'] == row['chunk_id'])
    upstream = [u for u in run['units'] if u['stage'] == 'capacity_repair_event_entity'
        and (u.get('capacity_repair_origin') or {}).get('unit_id') == row['failed_unit_id']
        and u.get('repair_view_id') == chunk['id']
        and (u.get('requested_limits') or {}).get('max_tokens') == row['output_tokens']
        and (u.get('request_configuration') or {}).get('timeout') == row['timeout']]
    if not upstream or any(u['status'] != 'succeeded' or 'materialized_claim_ids' not in u for u in upstream):
        return  # A failed/incomplete upstream repair does not complete its dependency.
    messages = business_run.extraction_messages(run, chunk, 'event_relation')
    schema = autoschema.extraction_schema('event_relation')
    assert original['schema'] == schema and original['reference_map'] == chunk['source_reference_map']
    if messages == original['messages']:
        return
    options = run['recipe']['options']
    cfg = dict(model=run['recipe']['models']['draft'], generation=run['recipe']['generation'],
        identity=run['model_identity'], temperature=0, timeout=original['request_configuration']['timeout'])
    limits = dict(max_tokens=original['executed_limits']['max_tokens'],
                  context_tokens=options['context_tokens'], think=options['think'])
    assert original['request_configuration'] == cfg and original['requested_limits'] == original['executed_limits'] == limits
    metadata = dict(source_chunk_id=chunk['id'], dependency_refresh_origin=dict(
        run_id=row['origin_run_id'], unit_id=original['id'], failed_upstream_unit_id=row['failed_unit_id'],
        repaired_upstream_unit_ids=[u['id'] for u in upstream], input_changed=True))
    prior = [u for u in run['units'] if u['stage'] == 'capacity_dependency_event_relation'
             and (u.get('dependency_refresh_origin') or {}).get('unit_id') == original['id']]
    matching = [u for u in prior if all(u.get(k) == v for k,v in metadata.items())
        and u.get('messages') == messages and u.get('schema') == schema
        and u.get('reference_map') == chunk['source_reference_map'] and u.get('request_configuration') == cfg
        and u.get('requested_limits') == limits
        and (u.get('executed_limits') == limits or u.get('error') == 'input_capacity')]
    if len(matching) != len(prior):
        raise ValueError('changed_prior_dependency_refresh_not_supported')
    finished = [u for u in matching if 'materialized_claim_ids' in u]
    if finished:
        for unit in finished:
            ids = unit['materialized_claim_ids']
            assert len(ids) == len(set(ids)) and set(ids) <= {c['id'] for c in run['claims']}
        return
    unit = next((u for u in matching if u['status'] == 'succeeded' and u.get('response')
                 and not u['response'].get('failure_kind')), None)
    if unit:
        response = unit['response']
    elif any(u['status'] in {'failed', 'partial'} for u in matching):
        return  # Do not retry the same failed request without a new cause/fix.
    else:
        response = business_run.call(service, run, 'capacity_dependency_event_relation', messages, schema,
            reference_map=chunk['source_reference_map'], max_tokens=limits['max_tokens'],
            timeout=cfg['timeout'], capacity_repair=metadata)
        unit = run['units'][-1]
    before = len(run['claims'])
    if response is not None:
        try:
            business_run.store_extraction(run, chunk, 'event_relation', response, unit)
        except ValueError as exc:
            unit.update(status='failed', error=str(exc))
    unit['materialized_claim_ids'] = [c['id'] for c in run['claims'][before:]]
    business_run.save(service, run)


def repair(service, run, plan):
    """Keep failed attempts intact; only full new responses enter normal validation."""
    by_id = {u['id']:u for u in run['units']}
    chunks = {c['id']:c for c in run['chunks']}
    # Existing upstream-only plans keep their behavior; refreshing a dependent
    # response is a separate, explicitly selected operation with narrower bounds.
    dependencies = [(row, empty_event_dependency(run, row)) for row in plan
                    if row.get('refresh_empty_event_relation')]
    for row in plan:
        if business_run.cancelled(service, run):
            return
        original = by_id[row['failed_unit_id']]
        assert original['status'] == 'failed' and original['error'] == 'truncated'
        assert original['stage'] == row['role'] and original['source_chunk_id'] == row['chunk_id']
        chunk = chunks[row['chunk_id']]
        assert original['messages'] == business_run.extraction_messages(run, chunk, row['role'])
        assert original['schema'] == autoschema.extraction_schema(row['role'])
        assert original['reference_map'] == chunk['source_reference_map']
        for view in views(chunk, row.get('groups'), row.get('required_context_views'),
                          row.get('additional_context_views', ()), run.get('blocks', ())):
            if business_run.cancelled(service, run):
                return
            stored_view = run.get('capacity_repair_views', {}).get(view['id'])
            assert stored_view is None or stored_view == view
            run.setdefault('capacity_repair_views', {})[view['id']] = deepcopy(view)
            messages = business_run.extraction_messages(run, view, row['role'])
            schema = autoschema.extraction_schema(row['role'])
            metadata = dict(source_chunk_id=chunk['id'], repair_view_id=view['id'],
                capacity_repair_origin=dict(run_id=row['origin_run_id'], unit_id=original['id'],
                    original_limits=deepcopy(original['executed_limits']), strategy=row['strategy']))
            if row.get('preceding_failed_attempts'):
                metadata['capacity_repair_origin']['preceding_failed_attempts'] = deepcopy(row['preceding_failed_attempts'])
            options = run['recipe']['options']
            cfg = dict(model=run['recipe']['models']['draft'], generation=run['recipe']['generation'],
                identity=run['model_identity'], temperature=0, timeout=row['timeout'])
            limits = dict(max_tokens=row['output_tokens'], context_tokens=options['context_tokens'], think=options['think'])
            previous = [u for u in run['units'] if u['stage'] == 'capacity_repair_' + row['role']
                and all(u.get(k) == v for k,v in metadata.items()) and u.get('messages') == messages
                and u.get('schema') == schema and u.get('reference_map') == view['source_reference_map']
                and u.get('request_configuration') == cfg and u.get('requested_limits') == limits
                and (u.get('executed_limits') == limits or u.get('error') == 'input_capacity')
                and u.get('error') != 'cancelled' and (u.get('response') or {}).get('failure_kind') != 'cancelled']
            finished = [u for u in previous if u['status'] in {'succeeded','partial','failed'} and 'materialized_claim_ids' in u]
            if finished:
                for u in finished:
                    ids = u['materialized_claim_ids']
                    assert len(ids) == len(set(ids)) and set(ids) <= {c['id'] for c in run['claims']}
                continue
            unit = next((u for u in previous if u['status'] == 'succeeded' and u.get('response')
                and not u['response'].get('failure_kind')), None)
            if unit:
                result = unit['response']
            elif any(u['status'] in {'failed','partial'} for u in previous):
                continue
            else:
                result = business_run.call(service, run, 'capacity_repair_' + row['role'], messages,
                    schema, reference_map=view['source_reference_map'], max_tokens=row['output_tokens'],
                    timeout=row['timeout'], capacity_repair=metadata)
                unit = run['units'][-1]
            before = len(run['claims'])
            if result is not None:
                try:
                    business_run.store_extraction(run, view, row['role'], result, unit)
                except ValueError as exc:
                    unit.update(status='failed', error=str(exc))
            added = run['claims'][before:]
            original_blocks = {(b['id'],tuple(b.get('span',[0,len(b['text'])]))):b for b in chunk['blocks']}
            original_blocks.update({(b['id'],tuple(b.get('span',[0,len(b['text'])]))):b for b in run.get('blocks', ())
                if b['id'] in {r['block_id'] for r in row.get('additional_context_views', ())}})
            source_fields_preserved = all(all(b.get(k) == original_blocks[
                b['id'],tuple(b.get('span',[0,len(b['text'])]))].get(k)
                for k in ('text','locator','source_version_id','parse_run_id','run_id','span')) for b in view['blocks'])
            signature = lambda c: json.dumps((c['role'],c['raw'],c.get('interpretation',{}).get('evidence'),
                [{k:m.get(k) for k in ('subject','action','object','applies_to','modality','conditions','exceptions','time','local_negation','references','premises')}
                 for m in c.get('interpretation',{}).get('meanings',[])]),ensure_ascii=False,sort_keys=True)
            signatures = [signature(c) for c in added]
            prior_signatures = {signature(c) for c in run['claims'][:before]}
            graph = autoschema.graph(added)
            graph_claims = {edge['claim_id'] for edge in graph['edges']}
            graph_claims.update(cid for node in graph['nodes'] for cid in node.get('claim_ids',[]))
            unit['materialized_claim_ids'] = [c['id'] for c in added]
            unit['unverified_storage_check'] = dict(
                source_fields_preserved=source_fields_preserved, target_view_id=view['id'],
                reference_only_excluded=sum(c.get('interpretation', {}).get('target_status') == 'reference_only' for c in added),
                unresolved_address_claims=sum(bool(c.get('interpretation', {}).get('errors')) for c in added),
                exact_duplicate_claims_within_response=len(signatures)-len(set(signatures)),
                exact_same_source_raw_qualifiers_in_prior_claims=sum(v in prior_signatures for v in signatures),
                duplicate_claims_not_silently_merged=True,
                claim_ids_used_in_graph=sorted(graph_claims),
                claim_ids_excluded_from_graph=sorted({c['id'] for c in added}-graph_claims),
                semantic_quality_approved=False)
            business_run.save(service, run)
    for row, original in dependencies:
        if business_run.cancelled(service, run):
            return
        if original is not None:
            refresh_empty_event_relation(service, run, row, original)
