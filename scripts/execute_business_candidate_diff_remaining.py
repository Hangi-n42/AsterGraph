"""Execute the released two-case existing B1 check using the unchanged B2 runner."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import prepare_business_candidate_diff_remaining as prepared
import compare_business_actual_proposal_pair as b2
import execute_business_candidate_diff_confirmation as runtime


def execute():
    out = prepared.OUT; execution = out / 'execution'
    assert not execution.exists(), 'One fixed run only'
    assert all(runtime.sha(Path(path)) == value for path, value in runtime.read(out / 'execution_release.json')['files'].items())
    b2.OUT = out; b2.check(); rows = runtime.read(out / 'inputs.json')
    assert len(rows) == 2 and all(row['context'] == 8192 for row in rows)
    execution.mkdir(); runtime.EXEC = execution; runtime.starts = []; runtime.stops = []
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
        runtime.write('resource_preflight.json', dict(active=active, ollama_models=models, port11435_open=runtime.port_open()))
        assert not active and not models and not runtime.port_open(), 'Resource conflict; no load'
        identity = runtime.read(Path(rows[0]['baseline']['runtime_path'])); before = time.monotonic()
        assert runtime.sha(Path(identity['engine_path'])) == identity['engine_sha256']
        assert runtime.sha(Path(identity['gguf_path'])) == identity['gguf_sha256']
        manifest = Path('/Users/hyeongi/.ollama/models/manifests/registry.ollama.ai/library/qwen3.8/27b-q4_K_M')
        tag = next(model for model in runtime.ollama('/api/tags')['models'] if model['name'] == 'qwen3.8:27b-q4_K_M')
        assert runtime.sha(manifest) == tag['digest'] == identity['tag_digest']
        assert any(layer['digest'] == 'sha256:' + identity['gguf_sha256'] for layer in runtime.read(manifest)['layers'])
        args = list(identity['args']); assert args[args.index('-c') + 1] == '8192'
        process = runtime.start_server(args, 'server_ctx8192.log'); runtime.wait_health(process)
        identity.update(verified_at_utc=runtime.utc(), tag=tag, hash_verification_s=time.monotonic() - before,
            driver_sha256=runtime.sha(Path(__file__)), args=args, phase='Existing B1 SC remaining failure confirmation')
        b2.write(out / 'runtime_identity.json', identity)
        b2.preflight()
        runtime.write('released_preflight.json', dict(requests_sha256=runtime.sha(out / 'requests.json'),
            release_sha256=runtime.sha(out / 'execution_release.json'), maximum_new_calls=2, baseline_tokens_settings_props_exact=True))
        b2.run()
        assert runtime.read(out / 'run/result.json')['calls'] == 2
    except BaseException as error:
        runtime.write('driver_failure.json', dict(error=repr(error), new_calls=runtime.read(out / 'run/result.json')['calls'] if (out / 'run/result.json').exists() else 0))
        raise
    finally:
        if process:
            runtime.stop_server(process, args)
        runtime.write('resource_return.json', dict(stopped_owned_processes=runtime.stops, port11435_closed=not runtime.port_open(),
            ollama_models=runtime.ollama('/api/ps')['models'], driver_wall_s=time.monotonic() - started,
            finished_at_utc=runtime.utc(), new_calls=runtime.read(out / 'run/result.json')['calls'] if (out / 'run/result.json').exists() else 0))
        print('RESOURCE_RETURNED ' + str(runtime.read(execution / 'resource_return.json')), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', choices=['657-SC'], required=True)
    parser.parse_args(); execute()
