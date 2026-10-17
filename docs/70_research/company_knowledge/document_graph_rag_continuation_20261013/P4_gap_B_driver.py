"""P3/P4 product-boundary capture and guarded local execution; evaluator files excluded."""
import argparse
from copy import deepcopy
from dataclasses import asdict
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from app.generation.model_client import ModelClient
from app.knowledge import business_run, business_use, graph_retrieval as gr
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService, utcnow

ROOT=Path('/Users/hyeongi/.codex/worktrees/document-graph-rag-comparison/Civil-Complaints-System')
BASE=ROOT/'data/knowledge/evaluations/document_graph_rag_20261012/presentation_20261012'
PREVIOUS=ROOT/'data/knowledge/evaluations/document_graph_rag_followup_20261012/P2_native_locations_v1'
OUT=ROOT/'data/knowledge/evaluations/document_graph_rag_continuation_v1'
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
digest=lambda v:hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def normalize(request):
    row=asdict(request);row.pop('request_id');return row

parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','selection','qa'])
parser.add_argument('variant',choices=['P3','P4']);parser.add_argument('cases',nargs='+');args=parser.parse_args()
allowed={f'{q}_{a}' for q in (['ACT501070','SUP01','SUP02','SUP03'] if args.variant=='P3' else ['SUP02','SUP01','SUP03','ACT501108']) for a in ['B','C']}
assert set(args.cases)<=allowed
folder=OUT/(args.variant+'_gap_B');folder.mkdir(parents=True,exist_ok=True)
build=read(BASE/'source_build_manifest.json');execution=read(BASE/'qa/execution_manifest.json')
baseline=None;captured=None;frozen=None;current=None;reusable=None
original_select=gr.select_passages

class Captured(Exception):pass

def load_case(name):
    path=PREVIOUS/(name+'.json') if (PREVIOUS/(name+'.json')).exists() else BASE/'qa/presentation_exploratory'/(name+'.json')
    row=read(path)
    if 'request' not in row:row['request']=deepcopy(row['run']['query'])
    row['_baseline_path']=str(path)
    return row

def request_for(row):
    request=BusinessQuery.model_validate(row['request'])
    request.source_selection='listwise' if args.variant=='P3' else 'ranked'
    request.source_context_format='separate' if args.variant=='P3' else 'native_bundle'
    return request

def reuse_ranking(service,run,snapshot,request):
    old=BusinessQuery.model_validate(baseline['request']).model_dump()
    now=request.model_dump();old.pop('source_selection');old.pop('source_context_format');now.pop('source_selection');now.pop('source_context_format')
    assert now==old and snapshot['id']=='run:'+execution['source_run_id']
    run['graph_retrieval']=deepcopy(baseline['run']['graph_retrieval']);run['passage_index']=deepcopy(baseline['run']['passage_index'])
    run['retrieval_reuse']=dict(baseline_run_id=baseline['run']['id'],new_search_calls=0,new_embedding_calls=0,new_edge_filter_calls=0)
    if reusable:
        run.update(reusable_units=deepcopy(reusable['units']),parent_recipe=reusable['recipe'],
                   parent_model_identity=reusable['model_identity'],parent_run_id=reusable['id'])
    return [dict(block_id=h['id'],file_id=h['evidence']['source_version_id'],score=h['score'],selection_reason=request.retrieval)
            for h in baseline['run']['graph_retrieval']['ranked_passages']]

def selection(candidates,ranked,blocks,options,limit):
    if args.variant=='P4':return deepcopy(baseline['run']['retrieval']),deepcopy(baseline['run']['passage_selection'])
    return original_select(candidates,ranked,blocks,options,limit)
gr.retrieve=reuse_ranking;gr.select_passages=selection

class CaptureClient:
    def __init__(self,config):assert config==baseline['run']['recipe']['generation']
    async def generate(self,request,cancelled=None):
        global captured
        captured=normalize(request);raise Captured()

class GuardedClient(ModelClient):
    async def generate(self,request,cancelled=None):
        global captured
        if args.mode=='selection' and request.stage=='business_qa':
            captured=normalize(request);raise Captured()
        expected=frozen['cases'][current]['selection_request' if args.mode=='selection' else 'qa_request']
        assert normalize(request)==expected,'Unfrozen request'
        assert request.model=='qwen3.8:27b-q4_K_M' and request.temperature==0 and request.think is False
        return await super().generate(request,cancelled)

def last_run(service,request):
    with service.repository.connect() as db:
        rows=[json.loads(row['payload']) for row in db.execute('SELECT payload FROM runs')]
    return next(row for row in reversed(rows) if row.get('query')==request.model_dump())

def close_capture(service,run):
    run.update(status='failed',finished_at=utcnow(),error='input_capture_no_QA_call')
    if run['units'] and not run['units'][-1].get('response'):
        run['units'][-1].update(status='failed',error='input_capture_no_model_call')
    business_run.save(service,run)

if args.mode=='prepare':
    assert not (folder/'input_contract.json').exists(),'Frozen contract already exists'
    with sqlite3.connect(Path(build['database']).as_uri()+'?mode=ro',uri=True) as src:
        source=json.loads(src.execute('SELECT payload FROM runs WHERE id=?',(execution['source_run_id'],)).fetchone()[0])
        assert digest(source)==execution['source_run_sha256']
        if not (folder/'knowledge.db').exists():
            with sqlite3.connect(folder/'knowledge.db') as dst:src.backup(dst)
    service=KnowledgeService(folder/'knowledge.db');business_run.ModelClient=CaptureClient
    frozen=dict(version='bounded-listwise-v1' if args.variant=='P3' else 'lossless-native-bundle-v1',created_at=utcnow(),cases={},
        source_run_id=execution['source_run_id'],source_run_sha256=execution['source_run_sha256'],
        original_DB_sha256=sha(build['database']),model_digest='25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e',
        code={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'app/knowledge/business_models.py',ROOT/'app/knowledge/graph_retrieval.py',ROOT/'app/knowledge/business_use.py',ROOT/'app/knowledge/business_run.py',ROOT/'app/generation/model_client.py']},
        driver_sha256=sha(__file__),source_cap=16384,selected_limit=12,pool_multiplier=5,model_calls_before_freeze=0,
        independence='P3 uses separate; P4 uses ranked',baseline_scope='stored baseline responses; P3 ACT baseline predates native locator restoration, so QA attribution must be stated separately')
    for current in args.cases:
        baseline=load_case(current);request=request_for(baseline);captured=None
        result=None
        with service.repository.connect() as db:
            previous=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM runs')]
        previous=[r for r in previous if r.get('query')==request.model_dump() and r.get('units')
                  and not r['units'][-1].get('response')]
        if previous:
            assert len(previous)==1
            run=previous[0];u=run['units'][-1];limits=u['requested_limits'];conf=u['request_configuration']
            captured=dict(stage=u['stage'],model=conf['model'],messages=u['messages'],schema=u['schema'],
                max_tokens=limits['max_tokens'],context_tokens=limits['context_tokens'],temperature=conf['temperature'],
                think=limits['think'],timeout=conf['timeout'])
        else:
            try:result=business_use.query(service,request,context_mode=baseline['run']['context_mode'])
            except Captured:pass
            run=last_run(service,request)
        if captured is None:
            write(folder/(current+'_prepare_failure.json'),dict(result=result,run=run))
            raise RuntimeError('Preparation failed before capture; inspect explicit failure record')
        oldunit=next(u for u in baseline['run']['units'] if u['stage']=='business_qa')
        field='selection_request' if args.variant=='P3' else 'qa_request'
        frozen['cases'][current]={field:captured,field+'_sha256':digest(captured),'baseline_file':baseline['_baseline_path'],
            'baseline_sha256':sha(baseline['_baseline_path']),'baseline_run_id':baseline['run']['id'],'prepare_run_id':run['id']}
        if args.variant=='P3':
            assert len(run['source_selection']['pool_ids'])==60
            assert run['source_selection']['pool_ids']==[r['id'] for r in baseline['run']['graph_retrieval']['ranked_passages'][:60]]
            assert json.loads(captured['messages'][1]['content'])['question']==request.question
            frozen['cases'][current]['input_budget']=dict(estimate_tokens=business_run.request_tokens(
                captured['messages'],captured['schema'],captured['max_tokens']),method='utf8_bytes/2+output+1000',exact=False)
        else:
            assert captured['schema']==oldunit['schema']
            old=json.loads(read(OUT/'P4_current_baseline/ACT501108_B_frozen_request.json')['messages'][1]['content']);new=json.loads(captured['messages'][1]['content']);bundle=new.pop('source_bundle')
            new['context']=[bundle['blocks'][i] for i in bundle['context_rows']]
            new['source_context']=[bundle['blocks'][i] for i in bundle['source_context_rows']]
            assert new==old,'P4 non-lossless input conversion'
            frozen['cases'][current]['source_budget']=run['source_context_budget']
        close_capture(service,run)
        write(folder/(current+'_frozen_request.json'),captured)
        print(current,field,digest(captured),'budget',frozen['cases'][current].get('source_budget') or frozen['cases'][current].get('input_budget'),flush=True)
    write(folder/'input_contract.json',frozen);service.shutdown();print('CONTRACT',sha(folder/'input_contract.json'),flush=True)
else:
    contract_path=folder/('qa_contract_after_selection.json' if args.variant=='P3' and args.mode=='qa' else 'input_contract.json')
    frozen=read(contract_path);assert sha(__file__)==frozen['driver_sha256']
    assert sha(build['database'])==frozen['original_DB_sha256']
    for name,expected in frozen['code'].items():assert sha(ROOT/name)==expected
    lock=Path(build['inference_lock']).open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    identity=ModelClient(load_case(args.cases[0])['run']['recipe']['generation']).identities({'review':'qwen3.8:27b-q4_K_M'},{'review':49152})
    assert identity['review']['digest']==frozen['model_digest']
    service=KnowledgeService(folder/'knowledge.db');business_run.ModelClient=GuardedClient
    for current in args.cases:
        assert current in frozen['cases'];suffix='_selection' if args.mode=='selection' else '_qa';target=folder/(current+suffix+'.json');assert not target.exists(),'No unchanged retry'
        baseline=load_case(current);assert sha(baseline['_baseline_path'])==frozen['cases'][current]['baseline_sha256']
        request=request_for(baseline);captured=None;result=None;reusable=None
        if args.variant=='P3' and args.mode=='qa':reusable=read(folder/(current+'_selection.json'))['run']
        started=time.monotonic()
        try:result=business_use.query(service,request,context_mode=baseline['run']['context_mode'])
        except Captured:pass
        run=last_run(service,request)
        if captured:
            assert args.variant=='P3' and args.mode=='selection'
            frozen['cases'][current]['qa_request']=captured;frozen['cases'][current]['qa_request_sha256']=digest(captured)
            close_capture(service,run)
            write(folder/(current+'_qa_frozen_request.json'),captured)
        write(target,dict(case=current,variant=args.variant,phase=args.mode,result=result,run=run,elapsed_s=time.monotonic()-started,
            baseline_run_id=baseline['run']['id'],contract_sha256=sha(contract_path),qa_was_executed=args.mode=='qa'))
        print(current,args.mode,'saved',run['id'],run['status'],flush=True)
    if args.variant=='P3' and args.mode=='selection':write(folder/'qa_contract_after_selection.json',frozen)
    service.shutdown();fcntl.flock(lock,fcntl.LOCK_UN)
