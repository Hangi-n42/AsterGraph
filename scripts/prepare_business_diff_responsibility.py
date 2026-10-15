"""Freeze one research change: B1 keeps its input diff; emits judgments only."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import compare_business_candidate_text_diff as b1
from check_business_candidate_diff_contract import ALIASES

OUT = ROOT / 'data/knowledge/evaluations/business_diff_responsibility_20261011'
read, write, sha = b1.read, b1.write, b1.sha


def judgments_prompt(prompt):
    original = b1.prior.INSTRUCTION
    lines = original.splitlines()
    removed = [line for line in lines if line.startswith(('후보들의 실제 달라진 구절', 'differences는 목록이다.'))]
    assert len(removed) == 2
    old = '출력은 differences와 judgments를 이 순서로 가진 JSON 하나다.'
    new = '출력은 judgments만을 가진 JSON 하나다.'
    assert lines.count(old) == 1 and prompt.count(original) == 1
    instruction = '\n'.join(new if line == old else line for line in lines if line not in removed)
    changed = prompt.replace(original, instruction, 1)
    assert changed.split('<|im_start|>user\n', 1)[1] == prompt.split('<|im_start|>user\n', 1)[1]
    return changed


def judgment_view(content, cases, canonical, baseline=False):
    answer = json.loads('{' + content, object_pairs_hook=b1.prior.previous.previous.strict_object)
    expected = ['differences', 'judgments'] if baseline else ['judgments']
    if not isinstance(answer, dict) or list(answer) != expected:
        raise ValueError('output_schema')
    raw = deepcopy(answer['judgments'])
    adapted = dict(differences=[], judgments=deepcopy(raw))
    for row in adapted['judgments'].values():
        row['label'] = ALIASES.get(row['label'], row['label'])
    parsed = b1.prior.parse(json.dumps(adapted, ensure_ascii=False)[1:], cases, canonical)
    return dict(raw_judgments=raw, normalized_labels={key: row['label'] for key, row in adapted['judgments'].items()},
                strict_numeric_labels=all(row['label'] in {'1', '2', '3', None} for row in raw.values()),
                parsed=parsed, baseline_difference_not_semantically_repaired=baseline)


def selfcheck():
    case = dict(id='fixture', raw=dict(Event='관람할 수 있다.'),
                blocks=[dict(id='b1', text='관람할 수 있다.')], source_parents=[])
    cases = dict(X=case, Y=deepcopy(case))
    prompt = b1.add_diff(b1.prior.prompt(cases), cases)
    changed = judgments_prompt(prompt)
    assert '출력은 judgments만을' in changed and 'differences는 목록이다.' not in changed
    row = dict(label='1', error_fields=[], error_spans=[], evidence=['e1'], reason='원문의 허용과 같다.')
    answer = dict(judgments=dict(X=deepcopy(row), Y=deepcopy(row)))
    encode = lambda value: json.dumps(value, ensure_ascii=False)[1:]
    assert judgment_view(encode(answer), cases, None)['raw_judgments'] == answer['judgments']
    saved = dict(differences=[], judgments=deepcopy(answer['judgments']))
    saved['judgments']['X']['label'] = 'supported'
    assert not judgment_view(encode(saved), cases, None, baseline=True)['strict_numeric_labels']
    invalid = []
    invalid.append(dict(differences=[], **answer))
    missing = deepcopy(answer); missing['judgments'].pop('Y'); invalid.append(missing)
    outside = deepcopy(answer); outside['judgments']['Z'] = row; invalid.append(outside)
    evidence = deepcopy(answer); evidence['judgments']['X']['evidence'] = ['e99']; invalid.append(evidence)
    label = deepcopy(answer); label['judgments']['X']['label'] = 'invalid'; invalid.append(label)
    quote = deepcopy(answer); quote['judgments']['X'].update(label='2', error_fields=['Event'],
        error_spans=[dict(field='Event', quote='없는 차이')]); invalid.append(quote)
    for value in invalid:
        try:
            judgment_view(encode(value), cases, None)
        except (ValueError, KeyError, TypeError, AssertionError):
            pass
        else:
            raise AssertionError('invalid response accepted')
    print('PASS: unchanged full user input, exact judgment/address contract, fixed aliases, six invalid outputs rejected')


def prepare():
    selfcheck()
    assert not OUT.exists(), 'Frozen preparation already exists; do not overwrite'
    rows, files = [], []
    first = read(b1.OUT / 'requests.json')
    nie = ROOT / 'data/knowledge/evaluations/business_candidate_diff_confirmation_20261011/execution'
    later = next(row for row in read(nie / 'requests.json') if row['id'] == 'permission_place_diff')
    sources = [(row, b1.OUT / 'run' / f"{row['id']}_response.json", b1.OUT, 8192) for row in first]
    sources.append((later, nie / 'run/permission_place_diff_response.json', nie, 11264))
    assert [row['id'] for row, *_ in sources] == ['normal_detail', 'condition', 'permission', 'explicit_refutation', 'permission_place_diff']
    for row, response_path, folder, context in sources:
        response = read(response_path)
        view = judgment_view(response['content'], row['cases'], row['canonical_views'], baseline=True)
        timings = response['timings']
        original_payload = json.loads(row['prompt'].split('<|im_start|>user\n', 1)[1].split('<|im_end|>', 1)[0])
        assert set(original_payload) == {'context', 'candidates', 'candidate_text_diff'}
        assert original_payload['candidates'] == {key: value['raw'] for key, value in row['cases'].items()}
        rows.append(dict(id=row['id'], cases=row['cases'], canonical_views=row['canonical_views'],
            prompt=judgments_prompt(row['prompt']), parameters=row['parameters'], context=context,
            expected=row['expected'], baseline=dict(prompt=row['prompt'], request=row['request'],
                request_path=str(folder / 'requests.json'), response_path=str(response_path),
                response_sha256=sha(response_path), props_path=str(folder / 'props.json'),
                runtime_path=str(folder / 'runtime_identity.json'), judgment_view=view,
                input_tokens=timings['prompt_n'], output_tokens=timings['predicted_n'],
                model_s=(timings['prompt_ms'] + timings['predicted_ms']) / 1000)))
        files.extend([folder / name for name in ['requests.json', 'props.json', 'runtime_identity.json']])
        files.append(response_path)
    assert len(rows) == 5 and sum(len(row['cases']) for row in rows) == 13
    OUT.mkdir()
    write(OUT / 'inputs.json', rows)
    write(OUT / 'criteria.json', dict(status='prepared_not_released', new_model_calls=0, maximum_new_calls=5,
        baseline_calls_reused=5, all_development_exposed=True, unused_confirmation_cases=0,
        expected={row['id']: row['expected'] for row in rows},
        change='Remove model-generated differences output and its instructions only; preserve B1 full user payload, per-candidate judgment contract and settings.',
        hypothesis='Removing redundant candidate-difference generation may reduce invented differences and individual reasons; causal effect is not yet established.',
        comparisons=['corrected_labels', 'new_wrong_labels', 'normal_claim_losses', 'source_grounded_reasons',
                     'candidate_error_locations', 'original_and_common_contracts', 'execution_or_unknown', 'tokens_and_elapsed'],
        reason_failures=['condition.Y: unprovided visit exemption/exclusivity',
                         'permission_place_diff: difference adds place exclusivity absent from candidate Y'],
        not_claimed=['unused-data generalization', 'new automatic finding', 'actual edit or storage', 'all unresolved U/C errors fixed'],
        release='Coordinator must release GPU and select method before any model load, tokenize or completion. Exact baseline token/settings/props verification is pending.',
        stop='No prompt retry, seed search, normal-condition removal or gold-driven case exclusion. Preserve all 13 occurrences, including failures and unknowns.'))
    dependencies = [Path(__file__), Path(b1.__file__), Path(b1.prior.__file__), Path(b1.base.__file__),
        Path(b1.prior.previous.__file__), Path(b1.prior.previous.previous.__file__),
        Path(b1.prior.previous.previous.refs.__file__), ROOT / 'scripts/compare_business_modality_spans.py',
        ROOT / 'scripts/compare_business_nli.py', ROOT / 'scripts/check_business_candidate_diff_contract.py',
        ROOT / 'app/knowledge/business_run.py']
    frozen = OUT / 'frozen_code'
    for source in dict.fromkeys(dependencies):
        target = frozen / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(source.read_bytes())
    files.extend(dependencies)
    files.extend(path for path in frozen.rglob('*') if path.is_file())
    files.extend([OUT / 'inputs.json', OUT / 'criteria.json'])
    write(OUT / 'freeze.json', dict(files={str(path): sha(path) for path in dict.fromkeys(files)},
        new_model_calls=0, token_preflight=False, baseline_exact_runtime_verified=False,
        historical_baseline_model_s=sum(row['baseline']['model_s'] for row in rows)))
    print('Prepared five fixed requests / 13 exposed judgment occurrences; model calls 0; GPU release required')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['selfcheck', 'prepare'])
    globals()[parser.parse_args().mode]()
