"""B1: frozen candidate-character diff input, unchanged A judge and four calls."""
import argparse
from copy import deepcopy
import difflib
from itertools import combinations
import json
from pathlib import Path
import time

import compare_business_condition_contrast as prior
import compare_business_label_selection as base
from compare_business_modality_spans import raw_fields

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/knowledge/evaluations/business_candidate_text_diff_20261011'
read, write, sha = base.read, base.write, base.sha
NOTE = ('서버가 후보 raw 사이의 문자상 공통/차이만 계산했다. 문자 차이는 의미 차이가 아니며, '
        '공통 부분은 원문 지지의 증거가 아니다. 상대적 상세함이나 공통 부분으로 다른 후보의 '
        '판정을 복사하지 말고, 기존 과제대로 전체 원문/부모와 각 전체 후보의 주장을 판단한다.')


def character_diff(candidates):
    pairs = []
    for x, y in combinations(candidates, 2):
        left, right = dict(raw_fields(candidates[x])), dict(raw_fields(candidates[y]))
        assert left.keys() == right.keys()
        fields, identical = [], []
        for field, a in left.items():
            b = right[field]
            if a == b:
                identical.append(field)
                continue
            segments = [dict(op=op, **{x: [i, j, a[i:j]], y: [k, l, b[k:l]]})
                        for op, i, j, k, l in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()]
            fields.append(dict(field=field, segments=segments))
        pairs.append(dict(candidates=[x, y], identical_string_fields=identical, fields=fields))
    return dict(offsets='Python Unicode code points, [start,end)', interpretation_note=NOTE, pairs=pairs)


def add_diff(prompt, cases):
    before, tail = prompt.split('<|im_start|>user\n', 1)
    body, after = tail.split('<|im_end|>', 1)
    payload = json.loads(body)
    assert set(payload) == {'context', 'candidates'}
    assert payload['candidates'] == {k: c['raw'] for k, c in cases.items()}
    assert json.dumps(payload, ensure_ascii=False) == body
    annotated = dict(payload, candidate_text_diff=character_diff(payload['candidates']))
    return before + '<|im_start|>user\n' + json.dumps(annotated, ensure_ascii=False) + '<|im_end|>' + after


def selfcheck():
    for a, b in [('가나다', '가X다'), ('반복반복', '반복'), ('', '추가'),
                 ('삭제', ''), ('가🙂나\n', '가🙂\n나'), ('abab', 'baba'), ('같음', '같음')]:
        raw = dict(X=dict(Event=a, Entity=['공통']), Y=dict(Event=b, Entity=['공통']))
        original = deepcopy(raw)
        result = character_diff(raw)
        assert raw == original
        for field in result['pairs'][0]['fields']:
            for key, text in [('X', a), ('Y', b)]:
                cursor = 0
                for segment in field['segments']:
                    start, end, quote = segment[key]
                    assert start == cursor and quote == text[start:end]
                    cursor = end
                    if segment['op'] == 'equal': assert segment['X'][2] == segment['Y'][2]
                assert cursor == len(text)
                assert ''.join(s[key][2] for s in field['segments']) == text
        if a == b: assert result['pairs'][0]['fields'] == []
    case = dict(id='fixture', raw=dict(Event='원래 문자'), blocks=[dict(id='b1', text='전체 원문')], source_parents=[])
    cases = dict(X=case, Y=dict(case, raw=dict(Event='다른 문자')))
    old = prior.prompt(cases)
    new = add_diff(old, cases)
    user = lambda p: json.loads(p.split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
    restored = user(new); restored.pop('candidate_text_diff')
    assert restored == user(old) and new.split('<|im_start|>user\n')[0] == old.split('<|im_start|>user\n')[0]
    assert len(character_diff(dict(X=case['raw'], Y=case['raw'], Z=case['raw']))['pairs']) == 3
    print('PASS: exact Unicode spans/reconstruction, repeats, insertion/deletion, no mutation, full context/candidate preservation')


def prepare():
    selfcheck()
    assert not OUT.exists()
    sources = [
        ('normal_detail', 'business_source_entity_replacement_20261011/execution', 'c46_replacement_joint', 'run/c46_replacement_joint_response.json', dict(X='supported', Y='supported')),
        ('condition', 'business_condition_contrast_20261010/followup', 'c46_joint', 'run/c46_joint_response.json', dict(X='supported', Y='unsupported')),
        ('permission', 'business_condition_contrast_20261010', 'na', 'contracts/na_response.json', dict(X='supported', Y='unsupported', Z='unsupported')),
        ('explicit_refutation', 'business_condition_contrast_20261010', 'p2', 'contracts/p2_response.json', dict(X='supported', Y='supported', Z='contradicted')),
    ]
    rows, files = [], [Path(__file__), Path(prior.__file__), Path(base.__file__)]
    for ident, folder, old_id, response_name, expected in sources:
        folder = OUT.parent / folder
        path, response = folder/'requests.json', folder/response_name
        old = next(r for r in read(path) if r['id'] == old_id and 'cases' in r)
        assert old['prompt'] == prior.prompt(old['cases'])
        parsed = prior.parse(read(response)['content'], old['cases'], old['canonical_views'])
        settings = {k:v for k,v in old['request'].items() if k != 'prompt'}
        new = add_diff(old['prompt'], old['cases'])
        rows.append(dict(id=ident, cases=old['cases'], canonical_views=old['canonical_views'], prompt=new,
                         parameters=settings, baseline=dict(request_path=str(path), response_path=str(response),
                         request_sha256=sha(path), response_sha256=sha(response), old_id=old_id,
                         prompt=old['prompt'], request=old['request'], props_path=str(folder/'props.json'),
                         runtime_path=str(folder/'runtime_identity.json'), answer=parsed['selected']), expected=expected))
        files.extend([path, response, folder/'props.json', folder/'runtime_identity.json'])
    assert all(r['parameters'] == rows[0]['parameters'] for r in rows)
    OUT.mkdir()
    criteria = dict(expected={r['id']:r['expected'] for r in rows}, maximum_new_calls=4, reused_responses=4,
        normal_candidates=6, error_candidates=4, product_adoption=False, development_exposed=True,
        reason_checks=dict(normal_detail='Both partial and qualified claims supported; missing unclaimed detail is not an error; no claim that Y contains every source detail.',
                          condition='Removed non-attendance condition broadens scope; source does not establish the broader claim, not an explicit prohibition.',
                          permission='Permission neither establishes obligation nor explicitly denies obligation. Y and Z unsupported, not contradicted.',
                          explicit_refutation='Same condition source expressly requires receiving the pass; Z denies that obligation, a genuine contradiction.'),
        location_checks=dict(condition=dict(Y=['미방문', '조건']), permission=dict(Y='산정해야 한다', Z='산정할 의무는 없다'), explicit_refutation=dict(Z='수령할 의무는 없다')),
        gate='All 10 labels, all 6 normal claims preserved, exact addresses, real changed meaning, source-grounded reasons/error locations, no U/C confusion. Evaluate source/output separately from parser. Failure stops without prompt retry.',
        treatment='Only candidate_text_diff input object with deterministic spans and interpretation warning; package effect, not isolated diff-computation effect.',
        A_before=5, A_number_pending_actual_result=True, gold_not_in_prompt=True,
        exclusions=['c47 before/after rerun', 'new candidates or source', 'product writes', 'new judge', 'model/training changes', 'confirmation execution'])
    write(OUT/'inputs.json', rows)
    write(OUT/'criteria.json', criteria)
    files.extend([OUT/'inputs.json', OUT/'criteria.json'])
    frozen = OUT/'frozen_code'; frozen.mkdir()
    dependencies = [Path(__file__), Path(prior.__file__), Path(base.__file__), Path(prior.previous.__file__),
                    Path(prior.previous.previous.__file__), Path(prior.previous.previous.refs.__file__),
                    ROOT/'scripts/compare_business_modality_spans.py', ROOT/'scripts/compare_business_nli.py',
                    ROOT/'app/knowledge/business_run.py']
    for p in dependencies:
        target = frozen/p.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(p.read_bytes())
    files.extend(dependencies)
    files.extend(p for p in frozen.rglob('*') if p.is_file())
    write(OUT/'prepared.json', dict(files={str(p):sha(p) for p in dict.fromkeys(files)}, calls=0,
        baseline_head='4b674459b83d5dbb5a4b2be2e77b33ae3436de5b', criteria_sha256=sha(OUT/'criteria.json')))
    print('Prepared fixed four requests / ten judgments; no model calls')


def check():
    assert all(sha(Path(p)) == h for p,h in read(OUT/'prepared.json')['files'].items())


def preflight():
    check()
    props = base.api('/props')
    rows = read(OUT/'inputs.json')
    for row in rows:
        baseline = row['baseline']
        old_props = read(Path(baseline['props_path']))
        assert {k:v for k,v in props.items() if k != 'media_marker'} == {k:v for k,v in old_props.items() if k != 'media_marker'}
        ids = base.api('/tokenize', dict(content=baseline['prompt'], add_special=False, parse_special=True))['tokens']
        assert dict(row['parameters'], prompt=ids) == baseline['request']
        tokens = base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
        assert len(tokens) + row['parameters']['n_predict'] < 8192
        row.update(input_tokens=len(tokens), request=dict(row['parameters'], prompt=tokens), baseline_token_ids_verified=True)
    write(OUT/'requests.json', rows); write(OUT/'props.json', props)
    write(OUT/'freeze.json', dict(files={str(OUT/n):sha(OUT/n) for n in ['prepared.json','requests.json','props.json','runtime_identity.json']}))
    print('Fresh tokenizer/parameters/props verified; reused baselines4:', [(r['id'],r['input_tokens']) for r in rows])


def run():
    check()
    assert all(sha(Path(p)) == h for p,h in read(OUT/'freeze.json')['files'].items())
    assert base.api('/props') == read(OUT/'props.json')
    dest = OUT/'run'; dest.mkdir()
    result = dict(calls=0, reused_calls=4, records=[], semantic_review='pending', product_adoption=False)
    started = time.monotonic()
    for row in read(OUT/'requests.json'):
        record = dict(id=row['id'], input_tokens=row['input_tokens'], contract_pass=False)
        result['records'].append(record); result['calls'] += 1
        write(dest/'result.json', result); before = time.monotonic()
        try:
            raw = base.call('/completion', row['request'])
            path = dest/f"{row['id']}_response.json"; path.write_bytes(raw)
            response = json.loads(raw)
            record.update(raw_sha256=sha(path), timings=response.get('timings'), stop_type=response.get('stop_type'),
                          truncated=response.get('truncated'), tokens_evaluated=response.get('tokens_evaluated'),
                          tokens_predicted=response.get('tokens_predicted'), tokens_cached=response.get('tokens_cached'))
            if response.get('stop_type') != 'eos' or response.get('truncated'): raise ValueError('incomplete_generation')
            record['answer'] = json.loads('{' + response['content'])
            record['labels'] = {k:base.MAPPINGS['primary'].get(v.get('label')) for k,v in record['answer']['judgments'].items()}
            record['label_pass'] = record['labels'] == row['expected']
            record['restored'] = prior.parse(response['content'], row['cases'], row['canonical_views'])
            record['contract_pass'] = True
        except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
            record['error'] = repr(error)
        record['elapsed_s'] = time.monotonic() - before
        result['completion_driver_s'] = time.monotonic() - started
        write(dest/'result.json', result)
        print(record['id'],record.get('labels'),record['contract_pass'],flush=True)
    print('Fixed bundle complete; semantic source/output review pending, no retries')


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['selfcheck','prepare','preflight','run'])
    globals()[cli.parse_args().mode]()
