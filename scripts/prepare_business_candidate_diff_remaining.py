"""Prepare existing B1 on two exposed SC failures; keep the B2 judge unchanged."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import compare_business_actual_proposal_pair as b2
import compare_business_candidate_text_diff as b1

OUT = ROOT / 'data/knowledge/evaluations/business_candidate_diff_remaining_20261011'
read, write, sha = b1.read, b1.write, b1.sha


def prepare():
    b1.selfcheck()
    assert not OUT.exists(), 'Do not overwrite frozen preparation'
    old_rows = read(b2.OUT / 'requests.json')
    rows, files = [], [Path(__file__), b2.OUT / 'requests.json', b2.OUT / 'props.json', b2.OUT / 'runtime_identity.json']
    old_result = {row['id']: row for row in read(b2.OUT / 'run/result.json')['records']}
    for ident in ['SC03_joint', 'SC04_joint']:
        old = next(row for row in old_rows if row['id'] == ident)
        assert old['prompt'] == b1.prior.prompt(old['cases'])
        assert len(old['cases']['X']['blocks']) == 8 and len(old['cases']['X']['source_parents']) == 6
        response = b2.OUT / 'run' / f'{ident}_response.json'
        raw = read(response)
        assert raw['stop_type'] == 'eos' and not raw['truncated']
        assert old_result[ident]['labels'] == dict(X='contradicted', Y='supported')
        prompt = b1.add_diff(old['prompt'], old['cases'])
        user = lambda value: json.loads(value.split('<|im_start|>user\n', 1)[1].split('<|im_end|>', 1)[0])
        payload = user(prompt); payload.pop('candidate_text_diff')
        assert payload == user(old['prompt']) and prompt.split('<|im_start|>user\n', 1)[0] == old['prompt'].split('<|im_start|>user\n', 1)[0]
        assert old['parameters'] == {key: value for key, value in old['request'].items() if key != 'prompt'}
        baseline = dict(old_id=ident, prompt=old['prompt'], request=old['request'],
            request_path=str(b2.OUT / 'requests.json'), response_path=str(response), response_sha256=sha(response),
            props_path=str(b2.OUT / 'props.json'), runtime_path=str(b2.OUT / 'runtime_identity.json'),
            contract_pass=old_result[ident]['contract_pass'], original_error=old_result[ident].get('error'),
            input_tokens=raw['timings']['prompt_n'], output_tokens=raw['timings']['predicted_n'],
            model_s=(raw['timings']['prompt_ms'] + raw['timings']['predicted_ms']) / 1000)
        rows.append(dict(id=ident, cases=old['cases'], canonical_views=old['canonical_views'], prompt=prompt,
            parameters=old['parameters'], expected=old['expected'], baseline=baseline, context=8192))
        files.append(response)
    assert len(rows) == 2 and sum(len(row['cases']) for row in rows) == 4
    assert rows[0]['baseline']['contract_pass'] is False and rows[1]['baseline']['contract_pass'] is True
    OUT.mkdir()
    write(OUT / 'inputs.json', rows)
    write(OUT / 'criteria.json', dict(issue=657, status='prepared_GPU_release_pending', maximum_new_calls=2,
        reused_joint_baselines=2, new_independent_method=False, mechanism='Existing B1 candidate_text_diff plus its original fixed warning only.',
        expected={row['id']: row['expected'] for row in rows}, all_development_exposed=True,
        source_gold_proposal_reason_provenance_added_to_model_input=False,
        comparisons=['before U/C corrections and correct reason/location', 'after two normal claims preserved',
                     'readable labels versus original strict contracts', 'source and candidate addresses', 'calls/tokens/time including failures'],
        source_reason_checks=dict(SC03='Only field-trip applicants are supported; do not invent an exemption for all other visitors or call permission/scope silence explicit contradiction.',
                                 SC04='Cancellation before session start is permitted; automatic cancellation after no entry does not explicitly refute prior-time obligation.'),
        baseline_contract_limit='SC03 stored joint Entity array quote fails the unchanged parser. Preserve that failure; apply the same parser to new outputs, no alias/path or deletion repair.',
        use_decision='Report each correction and regression. One failed item does not erase another gain. No agreement/confidence-based automatic correction authority. Actual edited/stored versions require separate product validation.',
        stop='Exactly two requests after coordinator GPU release. No prompt/seed/context retry, new source/gold, extra variants or after-result case exclusion.',
        interpretation='After candidates are actual native unapplied proposals in this historical packet, not gold. Existing source and expected evaluation are separate from model input.'))
    dependencies = [Path(__file__), Path(b1.__file__), Path(b2.__file__), Path(b1.prior.__file__), Path(b1.base.__file__),
        Path(b1.prior.previous.__file__), Path(b1.prior.previous.previous.__file__), Path(b1.prior.previous.previous.refs.__file__),
        ROOT / 'scripts/compare_business_modality_spans.py', ROOT / 'scripts/compare_business_nli.py', ROOT / 'app/knowledge/business_run.py']
    for source in dict.fromkeys(dependencies):
        target = OUT / 'frozen_code' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(source.read_bytes())
    files.extend(dependencies); files.extend(path for path in OUT.rglob('*') if path.is_file())
    write(OUT / 'prepared.json', dict(files={str(path): sha(path) for path in dict.fromkeys(files)},
        calls=0, runtime_exact_reuse_pending=True, new_source_or_candidate=0))
    print('Prepared existing B1 two SC requests / four exposed judgments; no model load/tokenize/completion')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'selfcheck'])
    mode = parser.parse_args().mode
    prepare() if mode == 'prepare' else b1.selfcheck()
