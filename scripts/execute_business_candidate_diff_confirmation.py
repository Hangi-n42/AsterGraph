"""Execute the frozen NIE paired comparison once; no product writes or retries."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import compare_business_label_selection as base
import compare_business_condition_contrast as legacy
from check_business_candidate_diff_contract import ALIASES,technical_view

OUT=ROOT/'data/knowledge/evaluations/business_candidate_diff_confirmation_20261011'
EXEC=OUT/'execution'
read,sha=base.read,base.sha

def write(name,value):
    (EXEC/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def utc():return datetime.now(timezone.utc).isoformat()

def ollama(path):
    with urllib.request.urlopen('http://127.0.0.1:11434'+path,timeout=10) as response:return json.load(response)

def port_open():
    with socket.socket() as client:
        client.settimeout(1);return client.connect_ex(('127.0.0.1',11435))==0

def check_prepared():
    manifest=read(OUT/'preservation_manifest.json')
    assert all(sha(OUT/path)==value for path,value in manifest['files'].items())
    assert all(sha(ROOT/path)==value for path,value in read(OUT/'freeze_manifest.json')['code'].items())

def start_server(args,name):
    log=(EXEC/name).open('wb')
    server=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT)
    starts.append(dict(pid=server.pid,args=args,owned=True,started_at_utc=utc()))
    write('server_starts.json',starts)
    return server

def wait_health(server):
    deadline=time.monotonic()+90
    while True:
        if server.poll() is not None:raise RuntimeError('owned server exited before health')
        try:base.api('/health');return
        except OSError:
            if time.monotonic()>deadline:raise TimeoutError('owned server health timeout')
            time.sleep(.5)

def stop_server(server,args):
    stop=dict(owned_pid=server.pid,checked_at_utc=utc())
    if server.poll() is None:
        command=subprocess.check_output(['ps','-p',str(server.pid),'-o','command='],text=True).strip()
        stop['owned_command_verified']=command==' '.join(args)
        assert stop['owned_command_verified']
        server.send_signal(signal.SIGTERM)
        try:server.wait(timeout=20)
        except subprocess.TimeoutExpired:
            server.kill();server.wait(timeout=10);stop['forced_kill']=True
    stop.update(exit_code=server.returncode,finished_at_utc=utc(),port11435_closed=not port_open())
    stops.append(stop);write('owned_server_stops.json',stops)

def run(rows):
    check_prepared()
    assert all(sha(Path(path))==value for path,value in read(EXEC/'execution_freeze.json')['files'].items())
    assert base.api('/props')==read(EXEC/'props.json')
    dest=EXEC/'run';dest.mkdir()
    result=dict(calls=0,reused_calls=0,records=[],semantic_review='pending',product_adoption=False)
    began=time.monotonic()
    for row in rows:
        record=dict(id=row['id'],condition=row['condition'],input_tokens=row['input_tokens'],
                    legacy_contract_pass=False,technical_contract_pass=False)
        result['records'].append(record);result['calls']+=1;write('run/result.json',result)
        before=time.monotonic()
        try:
            raw=base.call('/completion',row['request'])
            path=dest/f"{row['id']}_response.json";path.write_bytes(raw);response=json.loads(raw)
            record.update(raw_sha256=sha(path),timings=response.get('timings'),stop_type=response.get('stop_type'),
                truncated=response.get('truncated'),tokens_evaluated=response.get('tokens_evaluated'),
                tokens_predicted=response.get('tokens_predicted'),tokens_cached=response.get('tokens_cached'))
            record['answer']=json.loads('{'+response['content'])
            mapping=base.MAPPINGS['primary']
            record['labels']={k:mapping.get(ALIASES.get(v.get('label'),v.get('label'))) for k,v in record['answer']['judgments'].items()}
            record['label_pass']=record['labels']==row['expected']
            if response.get('stop_type')!='eos' or response.get('truncated'):raise ValueError('incomplete_generation')
            assert response['tokens_evaluated']==row['input_tokens']
            try:
                record['legacy_parsed']=legacy.parse(response['content'],row['cases'],row['canonical_views'])
                record['legacy_contract_pass']=True
            except (ValueError,KeyError,TypeError,AssertionError) as error:record['legacy_error']=repr(error)
            try:
                record['technical_parsed']=technical_view(response['content'],row['cases'],row['canonical_views'])
                record['technical_contract_pass']=True
            except (ValueError,KeyError,TypeError,AssertionError) as error:record['technical_error']=repr(error)
        except (OSError,ValueError,KeyError,TypeError,AssertionError) as error:record['execution_error']=repr(error)
        record['elapsed_s']=time.monotonic()-before
        result['completion_driver_s']=time.monotonic()-began;write('run/result.json',result)
        print(json.dumps(dict(id=record['id'],labels=record.get('labels'),legacy=record['legacy_contract_pass'],
                              technical=record['technical_contract_pass']),ensure_ascii=False),flush=True)
    print('FIXED_SIX_COMPLETE; semantic source/output review pending; no retries',flush=True)

if __name__=='__main__':
    assert not EXEC.exists()
    EXEC.mkdir();starts=[];stops=[];process=None;args=None;began=time.monotonic()
    try:
        check_prepared();rows=read(OUT/'inputs.json')
        assert len(rows)==6 and all(r['parameters']==rows[0]['parameters'] for r in rows)
        active=[]
        for line in subprocess.check_output(['ps','-axo','pid,ppid,command'],text=True).splitlines()[1:]:
            pieces=line.strip().split(None,2)
            if len(pieces)<3 or int(pieces[0])==os.getpid() or '/bin/zsh -' in pieces[2]:continue
            if re.search(r'llama-server|llama-cli|ollama runner|mlx.*server|run_business',pieces[2],re.I):active.append(line)
        models=ollama('/api/ps')['models']
        write('resource_preflight.json',dict(active_known_model_processes=active,ollama_models=models,
            port11435_open=port_open(),checked_at_utc=utc()))
        assert not active and not models and not port_open(),'model resource conflict; no completion'
        identity=read(OUT/'runtime_reference.json');hash_began=time.monotonic()
        assert sha(Path(identity['engine_path']))==identity['engine_sha256']
        assert sha(Path(identity['gguf_path']))==identity['gguf_sha256']
        tag=next(m for m in ollama('/api/tags')['models'] if m['name']=='qwen3.8:27b-q4_K_M')
        manifest=Path('/Users/hyeongi/.ollama/models/manifests/registry.ollama.ai/library/qwen3.8/27b-q4_K_M')
        assert sha(manifest)==tag['digest']==identity['tag_manifest_sha256']
        assert any(layer['digest']=='sha256:'+identity['gguf_sha256'] for layer in read(manifest)['layers'])
        identity.update(verified_at_utc=utc(),hash_verification_s=time.monotonic()-hash_began,tag=tag,
                        driver_sha256=sha(Path(__file__)),new_source_responses_reused=0)
        args=list(identity['args']);process=start_server(args,'server_ctx8192.log');wait_health(process)
        for row in rows:
            payload=json.loads(row['prompt'].split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
            assert set(payload)==({'context','candidates','candidate_text_diff'} if row['condition']=='diff' else {'context','candidates'})
            assert all(set(v)=={'Event','Entity'} for v in payload['candidates'].values())
            assert len(payload['context']['blocks'])==40 and len(payload['context']['source_parents'])==8
            tokens=base.api('/tokenize',dict(content=row['prompt'],add_special=False,parse_special=True))['tokens']
            row.update(input_tokens=len(tokens),request=dict(row['parameters'],prompt=tokens))
        required=max(r['input_tokens']+r['parameters']['n_predict']+1 for r in rows)
        context=8192 if required<=8192 else math.ceil(required/512)*512
        write('context_decision.json',dict(original_ctx=8192,required=required,final_ctx=context,
            baseline_diff_same_ctx=True,output_tokens=2048,all_required_source_preserved=True,new_completion_calls=0,
            measured=[dict(id=r['id'],input_tokens=r['input_tokens'],input_plus_output=r['input_tokens']+2048) for r in rows],
            rule='Keep8192 if input+2048<8192; otherwise smallest multiple of512 above max input+2048. Fix before any completion.',decided_at_utc=utc()))
        if context!=8192:
            stop_server(process,args);process=None
            args[args.index('-c')+1]=str(context)
            process=start_server(args,f'server_ctx{context}.log');wait_health(process)
            for row in rows:
                assert base.api('/tokenize',dict(content=row['prompt'],add_special=False,parse_special=True))['tokens']==row['request']['prompt']
        props=base.api('/props');assert props['default_generation_settings']['n_ctx']==context and props['total_slots']==1
        assert all(r['input_tokens']+2048<context for r in rows)
        identity.update(args=args,final_context=context,same_runtime_for_baseline_and_diff=True)
        write('runtime_identity.json',identity);write('requests.json',rows);write('props.json',props)
        frozen=EXEC/'frozen_code';frozen.mkdir()
        (frozen/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
        files=[OUT/'inputs.json',OUT/'criteria.json',OUT/'freeze_manifest.json',OUT/'preservation_manifest.json',
               EXEC/'context_decision.json',EXEC/'runtime_identity.json',EXEC/'requests.json',EXEC/'props.json',Path(__file__)]
        files.extend(ROOT/path for path in read(OUT/'freeze_manifest.json')['code'])
        write('execution_freeze.json',dict(files={str(p):sha(p) for p in files},new_calls=0,maximum_calls=6,
            context_fixed_before_first_completion=True,context=context,semantic_input_gold=False))
        print('PREFLIGHT_READY '+json.dumps(dict(context=context,required=required,counts=[(r['id'],r['input_tokens']) for r in rows]),ensure_ascii=False),flush=True)
        print('WAITING_FOR_RUN: complete paired settings recorded; enter RUN or STOP',flush=True)
        if input().strip()!='RUN':raise RuntimeError('execution not released')
        write('execution_release.json',dict(at_utc=utc(),context=context,authorized_fixed_calls=6))
        run(rows)
    except BaseException as error:
        write('driver_failure.json',dict(error=repr(error),new_calls=read(EXEC/'run/result.json')['calls'] if (EXEC/'run/result.json').exists() else 0))
        raise
    finally:
        if process:stop_server(process,args)
        write('resource_return.json',dict(stopped_owned_processes=stops,port11435_closed=not port_open(),
            ollama_models=ollama('/api/ps')['models'],driver_wall_s=time.monotonic()-began,finished_at_utc=utc()))
        print('RESOURCE_RETURNED '+json.dumps(read(EXEC/'resource_return.json'),ensure_ascii=False),flush=True)
