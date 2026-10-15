"""Issue 654 preparation only: replace one stored Entity; never call a model."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

import run_business_source_limit_contrast as prior

ROOT, read, write, sha = prior.ROOT, prior.read, prior.write, prior.sha
OUT = ROOT / 'data/knowledge/evaluations/business_source_entity_replacement_20261011'
JUDGE = prior.prior.trial


def construct(case, proposal, canonical_views):
    selected = prior.trial.construct(case, proposal, canonical_views)
    if selected['status'] == 'unsupported':
        return selected
    raw, field = case['raw'], proposal['field']
    quote, anchor = proposal['source']['quote'], proposal['anchor']
    entities = [entity for entity in raw.get('Entity', [])
                if isinstance(entity, str) and entity and quote.startswith(entity)
                and quote[len(entity):].startswith('(')
                and anchor.count(entity) == 1 and raw[field].count(entity) == 1]
    if field != 'Event' or len(entities) != 1 or quote in raw[field]:
        return dict(status='unsupported', proposal=deepcopy(proposal),
                    reason='No unique Event Entity linked to the selected qualifier and anchor.',
                    semantic_validity='not_assessed')
    entity, text = entities[0], raw[field]
    start = text.index(entity)
    end = start + len(entity)
    changed = deepcopy(raw)
    changed[field] = text[:start] + quote + text[end:]
    assert changed[field][:start] == text[:start]
    assert changed[field][start + len(quote):] == text[end:]
    assert {k: v for k, v in changed.items() if k != field} == {k: v for k, v in raw.items() if k != field}
    return dict(status='constructed_unverified', raw=changed, field=field,
                before_span=[start, end], after_span=[start, start + len(quote)],
                replaced_entity=entity, source_evidence=selected['source_evidence'],
                proposal=deepcopy(proposal), semantic_validity='unverified')


def selfcheck():
    # Synthetic address fixtures; these are not semantic evidence.
    quote = '문서(수식A 및 수식B)'
    raw = dict(Event='대상이 미방문 시 증명서(기존조건), 문서를 구비한다.', Entity=['대상', '증명서', '문서'])
    case = dict(id='test', raw=raw, blocks=[dict(id='b1', text=quote)],
                source_parents=[dict(block_id='b1', parent_block_ids=['parent'])])
    views = dict(e1=dict(id='actual', text=quote, source_version_id='version', parse_run_id='parse'))
    proposal = dict(status='constructed', source=dict(evidence_ref='e1', quote=quote),
                    field='Event', anchor='문서를 구비한다.', reason='Address fixture')
    before = deepcopy(case)
    made = construct(case, proposal, views)
    assert made['raw'] == dict(raw, Event=raw['Event'].replace('문서', quote))
    assert case == before and made['source_evidence']['quote'] == quote
    for candidate in [dict(raw, Entity=[]), dict(raw, Entity=raw['Entity'] + ['문서']),
                      dict(raw, Event='문서와 ' + raw['Event'])]:
        assert construct(dict(case, raw=candidate), proposal, views)['status'] == 'unsupported'
    qualified = dict(case, raw=made['raw'])
    assert construct(qualified, dict(proposal, anchor=quote + '를 구비한다.'), views)['status'] == 'unsupported'
    for changed in [dict(proposal, anchor='없는 위치'),
                    dict(proposal, source=dict(evidence_ref='e1', quote='없는 원문'))]:
        try:
            construct(case, changed, views)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid source/anchor accepted')
    print('PASS: unique Entity replacement, suffix/other raw/context preservation, ambiguity and no-op rejection')


def prepare():
    selfcheck()
    prior.check()
    assert not OUT.exists()
    originals = read(prior.OUT / 'inputs.json')
    generated = {row['id']: row for row in read(prior.OUT / 'generate/result.json')['records']}
    rows = [dict(id=row['id'], case=row['case'], canonical_views=row['canonical_views'],
                 proposal=generated[row['id']]['answer'],
                 construction=construct(row['case'], generated[row['id']]['answer'], row['canonical_views']))
            for row in originals]
    assert [(row['id'], row['construction']['status']) for row in rows] == [
        ('c13', 'unsupported'), ('c46', 'constructed_unverified'), ('c47', 'unsupported')]
    row = next(row for row in rows if row['id'] == 'c46')
    original, made = row['case'], row['construction']
    assert made['before_span'] == [53, 58]
    assert made['source_evidence'] == generated['c46']['construction']['source_evidence']
    counterpart = dict(deepcopy(original), raw=made['raw'])
    settings = read(prior.OUT / 'settings.json')
    baseline_path = prior.prior.OUT / 'followup/requests.json'
    baseline = next(row for row in read(baseline_path) if row['id'] == 'c46_single')
    response_path = prior.prior.OUT / 'followup/run/c46_single_response.json'
    response = read(response_path)
    original_prompt = JUDGE.prompt(dict(X=original))
    assert original_prompt == baseline['prompt'] == response['prompt']
    assert settings == {k: v for k, v in baseline['request'].items() if k != 'prompt'}
    assert len(baseline['request']['prompt']) == baseline['input_tokens'] == response['tokens_evaluated']
    assert response['stop_type'] == 'eos' and not response['truncated']
    JUDGE.parse(response['content'], dict(X=original), row['canonical_views'])
    old_props, old_runtime = read(prior.prior.OUT / 'props.json'), read(prior.prior.OUT / 'runtime_identity.json')
    props, runtime = read(prior.OUT / 'props.json'), read(prior.OUT / 'runtime_identity.json')
    assert {k: v for k, v in props.items() if k != 'media_marker'} == {k: v for k, v in old_props.items() if k != 'media_marker'}
    assert all(runtime[k] == old_runtime[k] for k in ['engine_sha256', 'gguf_sha256', 'args'])
    planned = []
    for ident, cases in [('c46_replacement_single', dict(X=counterpart)),
                         ('c46_replacement_joint', dict(X=original, Y=counterpart))]:
        prompt = JUDGE.prompt(cases)
        payload = json.loads(prompt.split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
        assert set(payload) == {'context', 'candidates'}
        assert payload['candidates'] == {key: case['raw'] for key, case in cases.items()}
        assert 'proposal' not in payload['context']
        planned.append(dict(id=ident, cases=cases, canonical_views=row['canonical_views'],
                            prompt=prompt, parameters=settings, token_request=None,
                            model_execution_authorized=False))
    reuse = dict(prompt_equal=True, parameters_equal=True, historical_token_count=baseline['input_tokens'],
                 historical_token_ids=baseline['request']['prompt'], historical_request=baseline['request'],
                 old_request_sha256=sha(baseline_path), old_response_sha256=sha(response_path),
                 historical_runtime_equal=True, historical_props_equal_except_media_marker=True,
                 current_tokenization_executed=False, reuse_authorized=False,
                 condition='Only reuse after allocated runtime hashes/props and fresh tokenizer IDs match the exact stored request.')
    criteria = dict(issue=654, completed_A_comparisons=4, new_A_number=None, new_model_calls=0,
                    generation_calls=0, maximum_possible_judgment_calls=2, model_execution_authorized=False,
                    expected_labels=dict(original='S', counterpart='S'), expected_label_scope='Source-backed normal-detail control, not an error discovery.',
                    single_edit_is_not_single_meaning_proof=True, source_qualifier_has_two_stamp_targets=True,
                    preserve=['outside Event bytes', 'Entity', 'source blocks/parents/versions', 'existing list and legal-person condition', 'canonical source quote/address'],
                    separate_checks=['address/schema', 'grammar', 'actual added meaning', 'normal support', 'exact evidence/reason', 'single versus joint contribution'],
                    unsupported_ids=['c13', 'c47'], denominator=3, independent_normal_pair_deferred=True,
                    R38_original_gate_remains_failed=True, product_default_adoption=False)
    inputs = [prior.OUT / name for name in ['inputs.json', 'generate/result.json', 'prepared.json', 'freeze.json', 'settings.json', 'props.json', 'runtime_identity.json']]
    inputs += [baseline_path, response_path, prior.prior.OUT / 'props.json', prior.prior.OUT / 'runtime_identity.json']
    files = [Path(__file__), Path(prior.__file__), Path(prior.trial.__file__), Path(JUDGE.__file__)] + inputs
    OUT.mkdir()
    write(OUT / 'inputs.json', rows)
    write(OUT / 'judgment_inputs.json', planned)
    write(OUT / 'baseline_reuse.json', reuse)
    write(OUT / 'criteria.json', criteria)
    (OUT / 'settings.json').write_bytes((prior.OUT / 'settings.json').read_bytes())
    (OUT / 'frozen_code').mkdir()
    (OUT / 'frozen_code' / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    files += [OUT / name for name in ['inputs.json', 'judgment_inputs.json', 'baseline_reuse.json', 'criteria.json', 'settings.json']]
    files.append(OUT / 'frozen_code' / Path(__file__).name)
    write(OUT / 'prepared.json', dict(version='source-entity-replacement-v1', issue=654,
          new_model_calls=0, resource_allocated=False, files={str(path): sha(path) for path in files},
          runtime_token_preflight='pending resource allocation; no HTTP calls made'))
    preflight()


def preflight():
    prior.check()
    prepared = read(OUT / 'prepared.json')
    assert all(sha(Path(path)) == digest for path, digest in prepared['files'].items())
    assert prepared['new_model_calls'] == 0 and prepared['resource_allocated'] is False
    rows = read(OUT / 'inputs.json')
    for row in rows:
        assert construct(row['case'], row['proposal'], row['canonical_views']) == row['construction']
    planned = read(OUT / 'judgment_inputs.json')
    assert len(planned) == 2 and all(row['token_request'] is None and row['model_execution_authorized'] is False for row in planned)
    for row in planned:
        assert row['prompt'] == JUDGE.prompt(row['cases'])
    print('PASS: offline frozen inputs/preflight; c46 constructed, c13/c47 unsupported; runtime/token preflight and model calls remain unexecuted')


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['selfcheck', 'prepare', 'preflight'])
    globals()[cli.parse_args().mode]()
