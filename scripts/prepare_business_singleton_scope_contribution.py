"""Freeze all eight exposed NIE singleton inputs; no model or product writes."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import compare_business_condition_contrast as prior
import compare_business_label_selection as base

OLD=ROOT/'data/knowledge/evaluations/business_candidate_diff_confirmation_20261011'
OUT=ROOT/'data/knowledge/evaluations/business_singleton_scope_contribution_20261011'
read,write,sha=base.read,base.write,base.sha


def packet():
    saved=read(OLD/'execution/requests.json')
    baseline=[r for r in saved if r['condition']=='baseline']
    assert len(baseline)==3
    results={r['id']:r for r in read(OLD/'execution/run/result.json')['records']}
    rows=[];reused=[]
    for row in baseline:
        assert prior.prompt(row['cases'])==row['prompt']
        assert row['parameters']==baseline[0]['parameters']
        response=OLD/'execution/run'/f"{row['id']}_response.json"
        assert sha(response)==results[row['id']]['raw_sha256']
        assert json.loads('{'+read(response)['content'])==results[row['id']]['answer']
        reused.append(dict(id=row['id'],cases=row['cases'],canonical_views=row['canonical_views'],
            prompt=row['prompt'],request=row['request'],expected=row['expected'],response=str(response),
            response_sha256=sha(response),result=results[row['id']]))
        for key,case in row['cases'].items():
            cases={'X':deepcopy(case)}
            prompt=prior.prompt(cases)
            payload=json.loads(prompt.split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
            original=json.loads(row['prompt'].split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
            assert payload==dict(context=original['context'],candidates={'X':case['raw']})
            assert len(payload['context']['blocks'])==40 and len(payload['context']['source_parents'])==8
            assert set(payload)=={'context','candidates'} and set(case['raw'])=={'Event','Entity'}
            rows.append(dict(id=case['id']+'_single',condition='singleton',cases=cases,
                canonical_views=row['canonical_views'],prompt=prompt,parameters=row['parameters'],
                expected={'X':row['expected'][key]},baseline_id=row['id'],baseline_key=key))
    assert len(rows)==8 and len({r['cases']['X']['id'] for r in rows})==8
    assert [r['expected']['X'] for r in rows].count('supported')==4
    assert [r['expected']['X'] for r in rows].count('unsupported')==2
    assert [r['expected']['X'] for r in rows].count('contradicted')==2
    prefix=os.path.commonprefix([r['prompt'] for r in baseline])
    assert all(r['prompt'].startswith(prefix) for r in rows)
    tokens=[r['request']['prompt'] for r in baseline]
    shared=next((i for i,v in enumerate(zip(*tokens)) if len(set(v))!=1),min(map(len,tokens)))
    identity=read(OLD/'execution/runtime_identity.json')
    assert identity['args'][identity['args'].index('-c')+1]=='11264'
    scope=dict(context=11264,original_c47_context=8192,output_limit=2048,
        saved_joint_shared_input_token_prefix=shared,shared_text_tail=prefix[-80:],
        prefix_scope='Full system/context plus candidate JSON header and common Event prefix; not source-only token count.',
        singleton_exact_tokens='pending native preflight after allocated resources',
        observable_features=['full supplied source and parents','exact archived source addresses',
            'input token budget in fixed tokenizer/context','actual string field and unique quote for error address'],
        semantic_routing_rule=False,document_id_or_gold_exception=False)
    return rows,reused,identity,scope


def selfcheck():
    rows,reused,identity,scope=packet()
    case=rows[0]['cases']['X'];view=rows[0]['canonical_views']
    answer=dict(differences=[],judgments=dict(X=dict(label='1',error_fields=[],error_spans=[],evidence=['e1'],reason='계약 검사')))
    prior.parse(json.dumps(answer,ensure_ascii=False)[1:],{'X':case},view)
    for spans in [[dict(field='Entity',quote=case['raw']['Entity'][0])],[dict(field='Event',quote='없는 구절')]]:
        bad=deepcopy(answer);bad['judgments']['X'].update(label='2',error_fields=[spans[0]['field']],error_spans=spans)
        try:prior.parse(json.dumps(bad,ensure_ascii=False)[1:],{'X':case},view)
        except (ValueError,KeyError,TypeError,AssertionError):pass
        else:raise AssertionError('invalid error address accepted')
    print('Eight unchanged full-source inputs, three exact saved baselines, gold isolation and strict address checks passed')


if __name__=='__main__':
    if sys.argv[1:] == ['selfcheck']:selfcheck();sys.exit()
    assert not sys.argv[1:] and not OUT.exists()
    rows,reused,identity,scope=packet();OUT.mkdir()
    write(OUT/'inputs.json',rows);write(OUT/'baselines.json',reused)
    write(OUT/'runtime_reference.json',identity);write(OUT/'scope.json',scope)
    write(OUT/'criteria.json',dict(maximum_new_calls=8,reused_joint_calls=3,unique_candidates=8,
        expected={r['id']:r['expected'] for r in rows},normal_candidates=4,U_candidates=2,C_candidates=2,
        gate='All 8 labels, 4 normals, U/C distinction, actual Event error locations, exact source evidence, source-valid reasons and strict whole contracts pass. Failures/unknown remain denominator; no retry or post-hoc contract relaxation.',
        contribution='Compare each singleton against its exact saved joint judgment; separate label/reason/location/contract improvement, regression, same and unknown. Joint success already known; no novel-source or B1 causal gain claim.',
        product_adoption=False,adoption_limit='Exposed diagnostic only. Adoption still requires outside-development errors/normals and useful actual correction evidence.',
        A_cumulative=6,new_A_number=False,source_or_candidates_authored=0,models_loaded=0,new_model_calls=0,
        runtime='NIE ctx11264 matched to stored joint. Not the complete c47 ctx8192 configuration.',
        changed='Other candidate members removed; current candidate remapped to X, including former Y/Z. System/context/raw/parameters/parser unchanged. Cardinality plus role-ID package, not pure isolated cardinality causality.'))
    files=[OLD/'execution/requests.json',OLD/'execution/run/result.json',OLD/'execution/props.json',
           OLD/'execution/runtime_identity.json',OLD/'execution/runtime_metadata_errata.json']
    files += [Path(r['response']) for r in reused]
    files += [OUT/name for name in ['inputs.json','baselines.json','criteria.json','scope.json','runtime_reference.json']]
    code=[Path(__file__),ROOT/'scripts/execute_business_singleton_scope_contribution.py']
    code += [ROOT/path for path in read(OLD/'freeze_manifest.json')['code']]
    write(OUT/'prepared.json',dict(files={str(p):sha(p) for p in files},code={str(p):sha(p) for p in code},new_model_calls=0))
    print(json.dumps(dict(prepared=str(OUT),requests=8,reused=3,scope=scope),ensure_ascii=False))
