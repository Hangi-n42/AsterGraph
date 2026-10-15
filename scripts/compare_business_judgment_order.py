"""One frozen top-level output-order comparison; no product writes or retries."""
import argparse
from copy import deepcopy
import difflib
import json
from pathlib import Path
import time

import compare_business_condition_contrast as prior
import compare_business_label_selection as base

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'data/knowledge/evaluations/business_source_entity_replacement_20261011/execution'
OUT = ROOT / 'data/knowledge/evaluations/business_judgment_order_20261011'
read, write, sha = base.read, base.write, base.sha
OLD_ORDER = '출력은 differences와 judgments를 이 순서로 가진 JSON 하나다.'
NEW_ORDER = '출력은 judgments와 differences를 이 순서로 가진 JSON 하나다.'
INNER = ['label', 'error_fields', 'error_spans', 'evidence', 'reason']


def parse(content, row):
    answer = json.loads('{' + content, object_pairs_hook=prior.previous.previous.strict_object)
    if list(answer) != ['judgments', 'differences'] or list(answer['judgments']) != list(row['cases']):
        raise ValueError('actual_output_order')
    if any(list(v) != INNER for v in answer['judgments'].values()):
        raise ValueError('judgment_internal_order')
    # Only reorder the top-level container for the unchanged address/schema validator.
    validation = dict(differences=answer['differences'], judgments=answer['judgments'])
    restored = prior.parse(json.dumps(validation, ensure_ascii=False)[1:], row['cases'], row['canonical_views'])
    return answer, restored


def prepare():
    assert not OUT.exists()
    OUT.mkdir(parents=True)
    old = next(x for x in read(OLD / 'requests.json') if x['id'] == 'c46_replacement_joint')
    raw_path = OLD / 'run/c46_replacement_joint_response.json'
    baseline = json.loads('{' + read(raw_path)['content'])
    assert list(baseline) == ['differences', 'judgments']
    assert [v['label'] for v in baseline['judgments'].values()] == ['2', '1']
    assert all(list(v) == INNER for v in baseline['judgments'].values())
    assert old['prompt'].count(OLD_ORDER) == 1
    row = deepcopy(old)
    row['id'] = 'c46_judgments_first'
    row['prompt'] = old['prompt'].replace(OLD_ORDER, NEW_ORDER, 1)
    row.pop('request')
    row.pop('input_tokens')
    assert row['prompt'].replace(NEW_ORDER, OLD_ORDER, 1) == old['prompt']
    assert row['cases'] == old['cases'] and row['canonical_views'] == old['canonical_views']
    write(OUT / 'input.json', row)
    write(OUT / 'baseline.json', dict(response_path=str(raw_path), response_sha256=sha(raw_path),
          request_sha256=sha(OLD / 'requests.json'), answer=baseline, reused_calls=1, new_calls=0))
    write(OUT / 'criteria.json', dict(expected=dict(X='supported', Y='supported'), maximum_calls=1,
          contract='actual top-level judgments/differences and unchanged X/Y/internal key orders; old schema/address checks',
          semantic='Claims are supported, not required to enumerate all source detail. No mandatory-detail omission for normal X; no all-source-details claim for Y if a detail remains absent.',
          gate='Both labels, schema/addresses and meaningful reasons must pass. Otherwise stop; no retry. Pass pauses for control proposals.',
          old_failure_unchanged=True, product_adoption=False, expected_not_in_prompt=True))
    (OUT / 'prompt.diff').write_text(''.join(difflib.unified_diff(old['prompt'].splitlines(True),
          row['prompt'].splitlines(True), fromfile='frozen_differences_first', tofile='judgments_first')))
    files = [Path(__file__), Path(prior.__file__), OUT/'input.json', OUT/'baseline.json', OUT/'criteria.json',
             OUT/'prompt.diff', OLD/'requests.json', raw_path, OLD/'freeze.json']
    write(OUT/'prepared.json', dict(files={str(p):sha(p) for p in files}, maximum_calls=1,
          source_candidates_sha256=__import__('hashlib').sha256(json.dumps(old['cases'], ensure_ascii=False).encode()).hexdigest(),
          parameters=old['parameters'], evaluation_excluded_from_prompt=True))


def check():
    assert all(sha(Path(p)) == value for p, value in read(OUT/'prepared.json')['files'].items())


def preflight():
    check()
    row = read(OUT/'input.json')
    props = base.api('/props')
    old_props = read(OLD/'props.json')
    assert {k:v for k,v in props.items() if k!='media_marker'} == {k:v for k,v in old_props.items() if k!='media_marker'}
    old = next(x for x in read(OLD/'requests.json') if x['id']=='c46_replacement_joint')
    old_tokens = base.api('/tokenize', dict(content=old['prompt'], add_special=False, parse_special=True))['tokens']
    assert dict(old['parameters'], prompt=old_tokens) == old['request']
    tokens = base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
    assert len(tokens)+row['parameters']['n_predict'] < 8192
    row.update(input_tokens=len(tokens), request=dict(row['parameters'], prompt=tokens))
    write(OUT/'request.json', row)
    write(OUT/'props.json', props)
    write(OUT/'baseline_reuse_verified.json', dict(prompt_tokens_equal=True, parameters_equal=True,
          old_token_count=len(old_tokens), props_equal_except_media_marker=True,
          runtime_equal=read(OUT/'runtime_identity.json')['same_runtime_as_baseline'], reused_calls=1, new_calls=0))
    write(OUT/'freeze.json', dict(files={str(OUT/n):sha(OUT/n) for n in
          ['prepared.json','request.json','props.json','runtime_identity.json','baseline_reuse_verified.json']}))


def run():
    check()
    assert all(sha(Path(p))==v for p,v in read(OUT/'freeze.json')['files'].items())
    assert base.api('/props') == read(OUT/'props.json')
    assert not (OUT/'result.json').exists()
    row = read(OUT/'request.json')
    result = dict(calls=1, reused_calls=1, semantic_review='pending', format_pass=False,
                  further_calls_authorized=False, product_adoption=False)
    write(OUT/'result.json', result)
    started = time.monotonic()
    try:
        raw = base.call('/completion', row['request'])
        (OUT/'response.json').write_bytes(raw)
        response = json.loads(raw)
        result.update(raw_sha256=sha(OUT/'response.json'), timings=response['timings'],
                      stop_type=response.get('stop_type'), truncated=response.get('truncated'))
        if response['stop_type']!='eos' or response['truncated']:
            raise ValueError('incomplete_generation')
        answer = json.loads('{'+response['content'])
        result['answer'] = answer
        result['labels'] = {k:base.MAPPINGS['primary'].get(v.get('label')) for k,v in answer.get('judgments',{}).items()}
        result['label_pass'] = result['labels'] == read(OUT/'criteria.json')['expected']
        _, result['restored'] = parse(response['content'], row)
        result['format_pass'] = True
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        result['error'] = repr(error)
    result['wall_s'] = time.monotonic()-started
    write(OUT/'result.json', result)
    print(json.dumps({k:result.get(k) for k in ['calls','labels','label_pass','format_pass','error','wall_s']},ensure_ascii=False))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['prepare','preflight','run'])
    globals()[cli.parse_args().mode]()
