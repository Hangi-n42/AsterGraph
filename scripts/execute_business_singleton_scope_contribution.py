"""Run the allocated eight NIE singleton requests once, then release owned resources."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import prepare_business_singleton_scope_contribution as prep
import execute_business_candidate_diff_confirmation as transport

base,prior=prep.base,prep.prior
OUT=prep.OUT;EXEC=OUT/'execution'
read,sha=base.read,base.sha
transport.EXEC=EXEC
transport.starts=[];transport.stops=[]
write=transport.write


def check():
    frozen=read(OUT/'prepared.json')
    assert all(sha(Path(p))==v for p,v in {**frozen['files'],**frozen['code']}.items())


def complete(rows):
    result=dict(calls=0,reused_calls=3,records=[],semantic_review='pending',product_adoption=False)
    began=time.monotonic()
    for row in rows:
        check()
        record=dict(id=row['id'],strict_contract_pass=False,input_tokens=row['input_tokens'])
        result['records'].append(record);result['calls']+=1;write('run/result.json',result)
        before=time.monotonic()
        try:
            raw=base.call('/completion',row['request'])
            path=EXEC/'run'/f"{row['id']}_response.json";path.write_bytes(raw);response=json.loads(raw)
            record.update(raw_sha256=sha(path),timings=response.get('timings'),stop_type=response.get('stop_type'),
                truncated=response.get('truncated'),tokens_evaluated=response.get('tokens_evaluated'),
                tokens_predicted=response.get('tokens_predicted'),tokens_cached=response.get('tokens_cached'))
            assert response['stop_type']=='eos' and not response['truncated']
            assert response['tokens_evaluated']==row['input_tokens']
            assert response['tokens_predicted']==len(response['tokens'])
            for key in ['seed','temperature','top_k','top_p','min_p','repeat_penalty','presence_penalty','frequency_penalty','n_predict']:
                assert response['generation_settings'][key]==row['parameters'][key]
            assert response['generation_settings']==read(Path(read(OUT/'baselines.json')[0]['response']))['generation_settings']
            record['answer']=json.loads('{'+response['content'],object_pairs_hook=prior.previous.previous.strict_object)
            record['labels']={k:base.MAPPINGS['primary'].get(v.get('label')) for k,v in record['answer'].get('judgments',{}).items()}
            record['label_pass']=record['labels']==row['expected']
            try:
                record['parsed']=prior.parse(response['content'],row['cases'],row['canonical_views'])
                record['strict_contract_pass']=True
            except (ValueError,KeyError,TypeError,AssertionError) as error:record['contract_error']=repr(error)
        except (OSError,ValueError,KeyError,TypeError,AssertionError) as error:record['execution_error']=repr(error)
        record['elapsed_s']=time.monotonic()-before;result['completion_driver_s']=time.monotonic()-began
        write('run/result.json',result)
        print(json.dumps(dict(id=record['id'],labels=record.get('labels'),strict=record['strict_contract_pass'],
            error=record.get('execution_error')),ensure_ascii=False),flush=True)


if __name__=='__main__':
    assert not EXEC.exists();EXEC.mkdir();process=None;args=None;began=time.monotonic()
    try:
        check();rows=read(OUT/'inputs.json');assert len(rows)==8
        active=[]
        for line in subprocess.check_output(['ps','-axo','pid,ppid,command'],text=True).splitlines()[1:]:
            parts=line.strip().split(None,2)
            if len(parts)<3 or int(parts[0])==os.getpid() or '/bin/zsh -' in parts[2]:continue
            if re.search(r'llama-server|llama-cli|ollama runner|mlx.*server|run_business',parts[2],re.I):active.append(line)
        models=transport.ollama('/api/ps')['models']
        write('resource_preflight.json',dict(active_known_model_processes=active,ollama_models=models,
            port11435_open=transport.port_open(),checked_at_utc=transport.utc()))
        assert not active and not models and not transport.port_open(),'resource conflict; no model start'
        identity=read(OUT/'runtime_reference.json');hash_began=time.monotonic()
        assert sha(Path(identity['engine_path']))==identity['engine_sha256']
        assert sha(Path(identity['gguf_path']))==identity['gguf_sha256']
        tag=next(m for m in transport.ollama('/api/tags')['models'] if m['name']=='qwen3.8:27b-q4_K_M')
        manifest=Path('/Users/hyeongi/.ollama/models/manifests/registry.ollama.ai/library/qwen3.8/27b-q4_K_M')
        assert sha(manifest)==tag['digest']==identity['tag_manifest_sha256']
        identity.update(verified_at_utc=transport.utc(),hash_verification_s=time.monotonic()-hash_began,
            driver_sha256=sha(Path(__file__)),same_runtime_as_saved_NIE_joint=True,same_runtime_as_c47_8192=False)
        args=list(identity['args']);assert args[args.index('-c')+1]=='11264'
        process=transport.start_server(args,'server_ctx11264.log');transport.wait_health(process)
        props=base.api('/props');old_props=read(prep.OLD/'execution/props.json')
        assert {k:v for k,v in props.items() if k!='media_marker'}=={k:v for k,v in old_props.items() if k!='media_marker'}
        assert props['total_slots']==1 and props['default_generation_settings']['n_ctx']==11264
        for saved in read(OUT/'baselines.json'):
            tokens=base.api('/tokenize',dict(content=saved['prompt'],add_special=False,parse_special=True))['tokens']
            assert saved['request']==dict(rows[0]['parameters'],prompt=tokens)
        for row in rows:
            tokens=base.api('/tokenize',dict(content=row['prompt'],add_special=False,parse_special=True))['tokens']
            assert len(tokens)+2048<11264,'source exceeds fixed context; no truncation or restart'
            row.update(input_tokens=len(tokens),request=dict(row['parameters'],prompt=tokens))
        write('requests.json',rows);write('runtime_identity.json',identity);write('props.json',props)
        write('execution_freeze.json',dict(files={str(p):sha(p) for p in [EXEC/'requests.json',EXEC/'runtime_identity.json',EXEC/'props.json',OUT/'prepared.json']},maximum_calls=8,new_calls=0,context_fixed=11264))
        print('PREFLIGHT_READY '+json.dumps(dict(input_tokens=[r['input_tokens'] for r in rows],context=11264)),flush=True)
        print('WAITING_FOR_RUN; enter RUN or STOP',flush=True)
        if input().strip()!='RUN':raise RuntimeError('execution not released')
        write('execution_release.json',dict(at_utc=transport.utc(),authorized_fixed_calls=8))
        assert all(sha(Path(p))==v for p,v in read(EXEC/'execution_freeze.json')['files'].items())
        (EXEC/'run').mkdir();complete(rows)
    except BaseException as error:
        write('driver_failure.json',dict(error=repr(error),new_calls=read(EXEC/'run/result.json')['calls'] if (EXEC/'run/result.json').exists() else 0));raise
    finally:
        if process:transport.stop_server(process,args)
        write('resource_return.json',dict(stopped_owned_processes=transport.stops,port11435_closed=not transport.port_open(),
            ollama_models=transport.ollama('/api/ps')['models'],driver_wall_s=time.monotonic()-began,finished_at_utc=transport.utc()))
        print('RESOURCE_RETURNED '+json.dumps(read(EXEC/'resource_return.json'),ensure_ascii=False),flush=True)
