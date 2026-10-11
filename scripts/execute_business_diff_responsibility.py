"""Run the released #657 five-request comparison once with exact stored baselines."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import prepare_business_diff_responsibility as prepared
import execute_business_candidate_diff_confirmation as runtime

OUT = prepared.OUT
EXEC = OUT / 'execution_after_preflight_repair'
base, read, sha = runtime.base, runtime.read, runtime.sha


def execute():
    assert not EXEC.exists(), 'One execution only; do not retry or overwrite'
    for name in ['freeze.json', 'release_preparation_v2.json']:
        assert all(sha(Path(path)) == value for path, value in read(OUT / name)['files'].items())
    rows = read(OUT / 'inputs.json')
    assert len(rows) == 5 and sum(len(row['cases']) for row in rows) == 13
    EXEC.mkdir(); runtime.EXEC = EXEC; runtime.starts = []; runtime.stops = []
    write = runtime.write
    result = dict(calls=0, reused_calls=5, records=[], semantic_review='pending', product_adoption=False)
    process = args = None; started = time.monotonic()
    try:
        active = []
        for line in subprocess.check_output(['ps', '-axo', 'pid,ppid,command'], text=True).splitlines()[1:]:
            parts = line.strip().split(None, 2)
            if len(parts) < 3 or int(parts[0]) == os.getpid() or '/bin/zsh -' in parts[2]:
                continue
            if re.search(r'llama-server|llama-cli|ollama runner|mlx.*server|run_business', parts[2], re.I):
                active.append(line)
        models = runtime.ollama('/api/ps')['models']
        write('resource_preflight.json', dict(active_known_model_processes=active, ollama_models=models,
            port11435_open=runtime.port_open(), checked_at_utc=runtime.utc()))
        assert not active and not models and not runtime.port_open(), 'Model resource conflict; no load'
        identities = {context: read(Path(next(row for row in rows if row['context'] == context)['baseline']['runtime_path']))
                      for context in [11264, 8192]}
        first = identities[8192]; before_hash = time.monotonic()
        for key in ['engine', 'gguf']:
            assert sha(Path(first[key + '_path'])) == first[key + '_sha256']
            assert all(identity[key + '_sha256'] == first[key + '_sha256'] for identity in identities.values())
        tag = next(model for model in runtime.ollama('/api/tags')['models'] if model['name'] == 'qwen3.8:27b-q4_K_M')
        manifest = Path('/Users/hyeongi/.ollama/models/manifests/registry.ollama.ai/library/qwen3.8/27b-q4_K_M')
        assert sha(manifest) == tag['digest'] == first['tag_digest'] == identities[11264]['tag_manifest_sha256']
        assert any(layer['digest'] == 'sha256:' + first['gguf_sha256'] for layer in read(manifest)['layers'])
        write('model_identity.json', dict(engine_path=first['engine_path'], engine_sha256=first['engine_sha256'],
            gguf_path=first['gguf_path'], gguf_sha256=first['gguf_sha256'], tag=tag,
            hash_verification_s=time.monotonic() - before_hash, checked_at_utc=runtime.utc()))
        # Preflight both original contexts before any completion, then keep frozen request order.
        for context in [11264, 8192, 11264]:
            args = list(identities[context]['args'])
            assert args[args.index('-c') + 1] == str(context)
            process = runtime.start_server(args, f'server_{len(runtime.starts)}_ctx{context}.log')
            runtime.wait_health(process); props = base.api('/props')
            current = {key: value for key, value in props.items() if key != 'media_marker'}
            group = [row for row in rows if row['context'] == context]
            for row in group:
                baseline = row['baseline']
                old_props = read(Path(baseline['props_path']))
                assert current == {key: value for key, value in old_props.items() if key != 'media_marker'}
                assert row['parameters'] == {key: value for key, value in baseline['request'].items() if key != 'prompt'}
                old_tokens = base.api('/tokenize', dict(content=baseline['prompt'], add_special=False, parse_special=True))['tokens']
                assert old_tokens == baseline['request']['prompt']
                tokens = base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
                assert len(tokens) + row['parameters']['n_predict'] < context, 'Do not cut source or change context'
                request = dict(row['parameters'], prompt=tokens)
                if 'request' in row:
                    assert row['request'] == request
                row.update(request=request, input_tokens=len(tokens), baseline_exact_runtime_verified=True)
            write(f'preflight_{len(runtime.starts)}_ctx{context}.json', dict(rows=group, props=props, args=args,
                calls=result['calls'], all_baseline_tokens_settings_props_exact=True))
            write('requests.json', rows)
            if len(runtime.starts) == 1:
                runtime.stop_server(process, args); process = None
                continue
            assert all(row.get('baseline_exact_runtime_verified') for row in rows)
            execution_freeze = dict(files={str(OUT / name): sha(OUT / name)
                for name in ['inputs.json', 'criteria.json', 'criteria_supplement_v2.json', 'decision_criteria_v3.json',
                             'freeze.json', 'release_preparation_v2.json']}, maximum_new_calls=5, original_contexts=[8192, 11264])
            if (EXEC / 'execution_freeze.json').exists():
                assert read(EXEC / 'execution_freeze.json') == execution_freeze
            else:
                write('execution_freeze.json', execution_freeze)
            for row in group:
                before = time.monotonic(); result['calls'] += 1
                record = dict(id=row['id'], context=context, input_tokens=row['input_tokens'], judgment_contract_pass=False)
                result['records'].append(record); write('result.json', result)
                try:
                    raw = base.call('/completion', row['request'])
                    path = EXEC / f"{row['id']}_response.json"; path.write_bytes(raw); response = json.loads(raw)
                    record.update(raw_sha256=sha(path), timings=response.get('timings'), stop_type=response.get('stop_type'),
                        truncated=response.get('truncated'), tokens_evaluated=response.get('tokens_evaluated'),
                        tokens_predicted=response.get('tokens_predicted'), generation_settings=response.get('generation_settings'),
                        tokens_cached=response.get('tokens_cached'))
                    assert response['stop_type'] == 'eos' and not response['truncated']
                    assert response['tokens_evaluated'] == row['input_tokens']
                    answer = json.loads('{' + response['content']); record['answer'] = answer
                    record['numeric_labels'] = {key: base.MAPPINGS['primary'].get(value.get('label'))
                                                for key, value in answer['judgments'].items()}
                    record['readable_labels'] = {key: base.MAPPINGS['primary'].get(prepared.ALIASES.get(value.get('label'), value.get('label')))
                                                for key, value in answer['judgments'].items()}
                    view = prepared.judgment_view(response['content'], row['cases'], row['canonical_views'])
                    record.update(judgment_contract_pass=True, judgment_view=view,
                        readable_labels={key: base.MAPPINGS['primary'].get(value) for key, value in view['normalized_labels'].items()})
                except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
                    record['error'] = repr(error)
                record['elapsed_s'] = time.monotonic() - before
                result['completion_elapsed_sum_s'] = sum(value.get('elapsed_s', 0) for value in result['records'])
                write('result.json', result)
                print(json.dumps(dict(id=record['id'], labels=record.get('readable_labels'),
                    judgment_contract=record['judgment_contract_pass'], error=record.get('error')), ensure_ascii=False), flush=True)
            runtime.stop_server(process, args); process = None
        assert result['calls'] == 5
        print('FIVE_COMPLETE; source/output semantic review pending; no retries', flush=True)
    except BaseException as error:
        write('driver_failure.json', dict(error=repr(error), new_calls=result['calls']))
        raise
    finally:
        if process:
            runtime.stop_server(process, args)
        write('resource_return.json', dict(stopped_owned_processes=runtime.stops, port11435_closed=not runtime.port_open(),
            ollama_models=runtime.ollama('/api/ps')['models'], driver_wall_s=time.monotonic() - started,
            finished_at_utc=runtime.utc(), new_calls=result['calls']))
        print('RESOURCE_RETURNED ' + json.dumps(read(EXEC / 'resource_return.json'), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', choices=['657'], required=True)
    parser.parse_args(); execute()
