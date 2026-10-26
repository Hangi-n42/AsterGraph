"""Local identity, renderer, fallback and final-guard tests with a small byte BPE fixture."""
from copy import deepcopy
from hashlib import sha256
import json

import httpx
import pytest
from tokenizers.pre_tokenizers import ByteLevel

from app.generation import model_input_budget as counter
from app.knowledge import business_run


@pytest.fixture
def local(tmp_path):
    store = tmp_path / 'models'; (store/'blobs').mkdir(parents=True); (store/'manifests').mkdir()
    def put(data):
        digest = sha256(data).hexdigest(); path = store/'blobs'/('sha256-'+digest); path.write_bytes(data)
        return dict(digest='sha256:'+digest, size=len(data)), path
    config, _ = put(json.dumps(dict(renderer='qwen3.8', model_format='gguf')).encode())
    model, path = put(b'GGUFbyte-bpe-test')
    model['mediaType']='application/vnd.ollama.image.model'
    manifest = json.dumps(dict(config=config,layers=[model])).encode(); digest=sha256(manifest).hexdigest()
    (store/'manifests'/'fixture').write_bytes(manifest)
    words=sorted(ByteLevel.alphabet())+['<|im_start|>','<|im_end|>']
    meta={'tokenizer.ggml.model':'gpt2','tokenizer.ggml.pre':'qwen35','tokenizer.ggml.add_bos_token':False,
        'tokenizer.ggml.tokens':words,'tokenizer.ggml.token_type':[1]*256+[3,3],'tokenizer.ggml.merges':[]}
    shown=dict(template='{{ .Prompt }}',parameters='',modelfile=f'FROM {path}\nRENDERER qwen3.8\nPARSER qwen3.5\n',
               details=dict(format='gguf'),model_info=meta)
    state=dict(version='0.40.3',digest=digest,shown=shown,verbose_reads=0)
    def handler(req):
        if req.url.path=='/api/version':value=dict(version=state['version'])
        elif req.url.path=='/api/tags':value=dict(models=[dict(name='fixture:local',digest=state['digest'])])
        elif req.url.path=='/api/show':
            state['verbose_reads']+=int(json.loads(req.content).get('verbose',False));value=state['shown']
        else:raise AssertionError('No inference endpoint is allowed')
        return httpx.Response(200,json=value)
    transport=httpx.MockTransport(handler)
    config=dict(provider='ollama',endpoint='http://127.0.0.1:11434')
    messages=[dict(role='system',content='규칙'),dict(role='user',content='질문')]
    actual_count=counter.count
    def measure(**kw):
        args=dict(config=config,model='fixture:local',identity=dict(digest=state['digest']),messages=messages,schema={'type':'object'},think=False,transport=transport);args.update(kw)
        return actual_count(**args)
    return state,measure,messages,config,path


def test_native_prefix_unicode_and_separate_schema_reserve(local):
    state,measure,messages,_,_=local
    messages[0]['content']='\u2000 규칙 \x85';messages[1]['content']='\u3000e\u0301 한글 123\u00a0'
    result,error=measure();assert error is None
    prompt='<|im_start|>system\n규칙<|im_end|>\n<|im_start|>user\ne\u0301 한글 123<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
    assert result['prompt_sha256']==sha256(prompt.encode()).hexdigest()
    assert result['prompt_tokens']==len(prompt.encode())-3*(len('<|im_start|>')-1)-2*(len('<|im_end|>')-1)
    assert result['schema_serialized_tokens']==len('{"type":"object"}')
    assert result['prompt_exact'] and result['content_addresses_verified']
    assert result['schema_reserve_is_separate_grammar_not_observed_prompt']
    assert state['verbose_reads']==1


@pytest.mark.parametrize('change',[{'think':True},{'think':None},
    {'messages':[1,dict(role='user',content='q')]},
    {'messages':['system',dict(role='user',content='q')]},
    {'messages':[None,dict(role='user',content='q')]},
    {'messages':[dict(role='user',content='only user')]},
    {'messages':[dict(role='system',content='s'),dict(role='user',content='q'),dict(role='assistant',content='a')]},
    {'messages':[dict(role='developer',content='s'),dict(role='user',content='q')]},
    {'messages':[dict(role='system',content='s'),dict(role='user',content='q',images=['x'])]},
    {'messages':[dict(role='system',content='s'),dict(role='user',content='q',tool_calls=[])]},
    {'messages':[dict(role='system',content='s'),dict(role='user',content=' \n')]},
    {'messages':[dict(role='system',content='s'),dict(role='user',content='<|im_start|>')]},
    {'messages':[dict(role='system',content='s'),dict(role='user',content='<tool_response>x</tool_response>')]}])
def test_unsupported_message_contract_falls_back(local,change):
    _,measure,_,_,_=local;assert measure(**change)[0] is None


def test_empty_system_is_omitted_and_go_control_trim_is_not_python_strip(local):
    _,measure,messages,_,_=local;messages[0]['content']=' \n';messages[1]['content']='\x1cq\x1f'
    result,error=measure(schema=None);assert error is None
    prompt='<|im_start|>user\n\x1cq\x1f<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
    assert result['prompt_sha256']==sha256(prompt.encode()).hexdigest() and result['schema_reserve_tokens']==0


def test_metadata_or_identity_change_cannot_reuse_previous_counter(local):
    state,measure,_,_,_=local;assert measure()[0]
    assert measure()[0] and state['verbose_reads']==1
    state['shown']['parameters']='temperature 0'
    assert measure()[0] and state['verbose_reads']==2
    state['shown']['template']='{{ .Messages }}'
    assert measure()[0] is None
    state['shown']['template']='{{ .Prompt }}';state['version']='0.40.4'
    assert measure()[0] is None
    state['version']='0.40.3';assert measure(identity={'digest':'0'*64})[0] is None
    state['shown']['modelfile']=state['shown']['modelfile'].replace('RENDERER qwen3.8','RENDERER unknown')
    assert measure()[0] is None


def test_changed_content_address_is_reverified(local):
    _,measure,_,_,path=local;assert measure()[0]
    path.write_bytes(b'GGUFtampered-test')
    result,error=measure();assert result is None and error=='local_blob_digest_mismatch'


def test_changed_manifest_gets_a_new_tokenizer_cache_entry(local):
    state,measure,_,_,path=local;assert measure()[0]
    manifest=next((path.parent.parent/'manifests').iterdir())
    value=json.loads(manifest.read_bytes());value['revision']=2
    data=json.dumps(value).encode();manifest.write_bytes(data);state['digest']=sha256(data).hexdigest()
    assert measure()[0] and state['verbose_reads']==2


@pytest.mark.parametrize('endpoint',['https://127.0.0.1:11434','http://example.com',
    'http://user:secret@127.0.0.1:11434','http://127.0.0.1:11434/v1'])
def test_nonlocal_or_different_transport_wrapper_falls_back(local,endpoint):
    _,measure,_,_,_=local
    assert measure(config=dict(provider='ollama',endpoint=endpoint))[0] is None


def test_missing_manifest_or_unknown_tokenizer_falls_back(local):
    state,measure,_,_,path=local
    state['shown']['model_info']['tokenizer.ggml.pre']='unverified'
    assert measure()[0] is None
    state['shown']['model_info']['tokenizer.ggml.pre']='qwen35'
    next((path.parent.parent/'manifests').iterdir()).unlink()
    assert measure()[0] is None


def test_preflight_and_final_product_call_share_budget_and_enforce_overflow(local,monkeypatch):
    state,measure,messages,config,_=local
    def measured(config,model,identity,messages,schema,think):
        return measure(config=config,model=model,identity=identity,messages=messages,schema=schema,think=think)
    monkeypatch.setattr(counter,'count',measured)
    run=dict(id='fixture-run',recipe=dict(generation=config,models=dict(draft='fixture:local',review='fixture:local'),
        options=dict(context_tokens=49152,review_tokens=8192,extraction_tokens=8192,think=False,timeout=1800)),
        model_identity=dict(review=dict(digest=state['digest'])),units=[],metrics=dict(llm_calls=0,model_total_s=0))
    budget=business_run.request_budget(run,messages,{'type':'object'},8192)
    run['recipe']['options']['context_tokens']=budget['estimate_tokens']
    calls=[]
    class Client:
        def __init__(self,*args):pass
        async def generate(self,request,cancelled):
            calls.append(request);return dict(failure_kind=None,elapsed_s=0,parsed={})
    monkeypatch.setattr(business_run,'ModelClient',Client);monkeypatch.setattr(business_run,'save',lambda *a:None)
    assert business_run.call(None,run,'business_qa',messages,{'type':'object'},review=True,max_tokens=8192)
    assert run['units'][-1]['input_budget']==budget and len(calls)==1
    run=deepcopy(run);run['units']=[];run['recipe']['options']['context_tokens']-=1
    assert business_run.call(None,run,'business_qa',messages,{'type':'object'},review=True,max_tokens=8192) is None
    assert run['units'][-1]['error']=='input_capacity' and len(calls)==1


def test_unverified_contract_keeps_original_conservative_estimate(monkeypatch):
    monkeypatch.setattr(counter,'count',lambda *a:(None,'unsupported'))
    messages=[dict(role='user',content='question')]
    run=dict(recipe=dict(options=dict(think=False),models={},generation={}))
    result=business_run.request_budget(run,messages,None,8192)
    assert result['estimate_tokens']==business_run.request_tokens(messages,None,8192)
    assert result['method']=='utf8_bytes/2+output+1000' and result['fallback_reason']=='unsupported'


@pytest.mark.parametrize("version", ["0.40.3", "0.40.6", "0.40.10", "0.40.11"])
def test_verified_engine_versions_keep_their_renderer_contract(local, version):
    state, measure, _, _, _ = local
    state["version"] = version
    result, error = measure()
    assert error is None
    assert result["renderer_contract"].endswith(version)


def test_unverified_engine_version_is_still_rejected(local):
    state, measure, _, _, _ = local
    state['version'] = '0.40.12'
    assert measure() == (None, 'unsupported_engine_version')


@pytest.mark.parametrize('scheme',['never','first','always','unknown',''])
def test_new_metaspace_metadata_cannot_silently_change_the_qwen35_counter(local,scheme):
    state,measure,_,_,_=local
    state['version']='0.40.11'
    state['shown']['model_info']['tokenizer.ggml.metaspace.prepend_scheme']=scheme
    result,error=measure()
    assert bool(result)==(scheme=='never')
    assert error==(None if scheme=='never' else 'unsupported_tokenizer_contract')
