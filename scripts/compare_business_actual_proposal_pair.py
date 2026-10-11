"""B2: unchanged A judge on two actual, unapplied model edit proposals."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time

import compare_business_condition_contrast as prior
import compare_business_label_selection as base

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/knowledge/evaluations/business_actual_proposal_pair_20261011'
OLD = ROOT/'data/knowledge/evaluations/business_singleton_confirmation_20261011_execution'
PRODUCT = Path('/Users/hyeongi/.codex/worktrees/business-requirement-answer-flow/Civil-Complaints-System')
read,write,sha = base.read,base.write,base.sha


def prepare():
    assert not OUT.exists()
    originals=read(OLD/'requests.json')
    rows=[];files=[Path(__file__),OLD/'requests.json',OLD/'props.json',OLD/'runtime_identity.json']
    handoffs=[]
    for ident in ['SC03','SC04']:
        path=PRODUCT/'data/knowledge/evaluations/business_auto_finding_extension_20261011/actual'/f'{ident}_proposal_for_B2.json'
        handoff=read(path);old=next(r for r in originals if r['id']==ident+'_single')
        assert handoff['case_id']==ident and old['cases']['X']['raw']==handoff['before']
        case=old['cases']['X']
        assert case['source_parents']==handoff['source']['source_parents']
        for index,(old_block,source_block) in enumerate(zip(case['blocks'],handoff['source']['blocks'])):
            assert all(old_block[k]==source_block[k] for k in ['id','text','evidence_ref','source_version_id'])
            assert old_block['locator']['element_path']==source_block['dom_selector']
            assert old_block['locator']['block_order']==index
            canonical=old['canonical_views'][old_block['evidence_ref']]
            assert canonical['span']==[source_block['start_char'],source_block['end_char']]
            assert canonical['text']==source_block['text']
        assert len(case['blocks'])==8 and len(case['source_parents'])==6
        assert old['prompt']==prior.prompt(old['cases'])
        before=deepcopy(case);after=deepcopy(case);after.update(id=ident+'_actual_proposal',raw=handoff['after'])
        assert before['raw']!=after['raw']
        raw=OLD/(ident+'_single_response.json')
        parsed=prior.parse(read(raw)['content'],old['cases'],old['canonical_views'])
        baseline=dict(request_path=str(OLD/'requests.json'),response_path=str(raw),props_path=str(OLD/'props.json'),
                      runtime_path=str(OLD/'runtime_identity.json'),prompt=old['prompt'],request=old['request'],
                      answer=parsed['selected'],old_id=old['id'])
        params={k:v for k,v in old['request'].items() if k!='prompt'}
        for phase,cases,expected in [('after_single',dict(X=after),dict(X='supported')),
                                    ('joint',dict(X=before,Y=after),dict(X='unsupported',Y='supported'))]:
            prompt=prior.prompt(cases)
            payload=json.loads(prompt.split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
            assert set(payload)=={'context','candidates'}
            assert set(payload['context'])==set(case)-{'id','raw'}
            assert payload['context']['blocks']==case['blocks'] and payload['context']['source_parents']==case['source_parents']
            assert payload['candidates']=={k:c['raw'] for k,c in cases.items()}
            rows.append(dict(id=ident+'_'+phase,phase=phase,cases=cases,canonical_views=old['canonical_views'],
                             prompt=prompt,parameters=params,baseline=baseline,expected=expected))
        files.extend([path,raw]);handoffs.append(path)
    # Fix all four calls before seeing outputs: after baselines are necessary to isolate joint contribution.
    rows.sort(key=lambda r:(r['phase']=='joint',r['id']))
    assert all(r['parameters']==rows[0]['parameters'] for r in rows)
    OUT.mkdir();write(OUT/'inputs.json',rows)
    write(OUT/'criteria.json',dict(maximum_new_calls=4,before_single_reused_responses=2,after_single_new_calls=2,joint_new_calls=2,
        expected={r['id']:r['expected'] for r in rows},new_A_comparisons=0,A_cumulative=6,
        gate='All 6 new judgment occurrences, after normal preservation, source-grounded reasons, U/C, exact differences/error locations/evidence and output contracts pass. No prompt retry.',
        source_reason_checks=dict(SC03='Source requires prior approval for field-trip applicants, not all visitors. Before U; after matches the stated audience and wording. Do not infer exemption outside the audience.',
                                 SC04='Source permits cancellation before session start, not mandatory cancellation. Before U; after supported. No-show automatic cancellation does not explicitly refute this prior-time duty.'),
        contribution='Compare joint before to exact reused before singleton; joint after to newly fixed after singleton. After is not assumed correct because it was proposed.',
        exposure='SC03/SC04 are exposed AI-authored evaluation candidates. After is actual native model proposal, not stored/applied.',
        exclusions=['B1 diff/warning or alias/deletion contract repair','c47 rerun','edit reason/gold/provenance in judge input',
                    'new candidates or source','product writes','model/prompt retries','new independent A mechanism']))
    frozen=OUT/'frozen_code';frozen.mkdir()
    dependencies=[Path(__file__),Path(prior.__file__),Path(base.__file__),Path(prior.previous.__file__),
                  Path(prior.previous.previous.__file__),Path(prior.previous.previous.refs.__file__),
                  ROOT/'scripts/compare_business_modality_spans.py',ROOT/'scripts/compare_business_nli.py',
                  ROOT/'app/knowledge/business_run.py']
    for p in dependencies:
        dest=frozen/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    for p in handoffs:
        dest=OUT/'handoffs'/p.name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(p.read_bytes())
    files.extend(dependencies);files.extend(p for p in OUT.rglob('*') if p.is_file())
    write(OUT/'prepared.json',dict(files={str(p):sha(p) for p in dict.fromkeys(files)},calls=0,
        research_head='8cfb57f0ccd98bc64e1bd9e6729ffca0c6659ed6',criteria_sha256=sha(OUT/'criteria.json')))
    print('Frozen actual unapplied proposals; before2 reused, after2 singleton and joint2 fixed new calls')


def check():
    assert all(sha(Path(p))==h for p,h in read(OUT/'prepared.json')['files'].items())


def preflight():
    check();props=base.api('/props');rows=read(OUT/'inputs.json')
    for row in rows:
        old=row['baseline'];old_props=read(Path(old['props_path']))
        assert {k:v for k,v in props.items() if k!='media_marker'}=={k:v for k,v in old_props.items() if k!='media_marker'}
        tokens=base.api('/tokenize',dict(content=old['prompt'],add_special=False,parse_special=True))['tokens']
        assert dict(row['parameters'],prompt=tokens)==old['request']
        tokens=base.api('/tokenize',dict(content=row['prompt'],add_special=False,parse_special=True))['tokens']
        assert len(tokens)+row['parameters']['n_predict']<8192
        row.update(input_tokens=len(tokens),request=dict(row['parameters'],prompt=tokens),baseline_token_ids_verified=True)
    write(OUT/'requests.json',rows);write(OUT/'props.json',props)
    write(OUT/'freeze.json',dict(files={str(OUT/n):sha(OUT/n) for n in ['prepared.json','requests.json','props.json','runtime_identity.json']}))
    print('Native/tokenizer/settings reuse verified',[(r['id'],r['input_tokens']) for r in rows],flush=True)


def run():
    check();assert all(sha(Path(p))==h for p,h in read(OUT/'freeze.json')['files'].items())
    assert base.api('/props')==read(OUT/'props.json')
    dest=OUT/'run';dest.mkdir();result=dict(calls=0,reused_calls=2,records=[],semantic_review='pending',product_adoption=False)
    started=time.monotonic()
    for row in read(OUT/'requests.json'):
        record=dict(id=row['id'],input_tokens=row['input_tokens'],contract_pass=False)
        result['records'].append(record);result['calls']+=1;write(dest/'result.json',result);before=time.monotonic()
        try:
            raw=base.call('/completion',row['request']);path=dest/f"{row['id']}_response.json";path.write_bytes(raw);response=json.loads(raw)
            record.update(raw_sha256=sha(path),timings=response.get('timings'),stop_type=response.get('stop_type'),truncated=response.get('truncated'),
                          tokens_evaluated=response.get('tokens_evaluated'),tokens_predicted=response.get('tokens_predicted'),tokens_cached=response.get('tokens_cached'))
            if response.get('stop_type')!='eos' or response.get('truncated'):raise ValueError('incomplete_generation')
            record['answer']=json.loads('{'+response['content'])
            record['labels']={k:base.MAPPINGS['primary'].get(v.get('label')) for k,v in record['answer']['judgments'].items()}
            record['label_pass']=record['labels']==row['expected']
            record['restored']=prior.parse(response['content'],row['cases'],row['canonical_views']);record['contract_pass']=True
        except (OSError,ValueError,KeyError,TypeError,AssertionError) as error:record['error']=repr(error)
        record['elapsed_s']=time.monotonic()-before;result['completion_driver_s']=time.monotonic()-started;write(dest/'result.json',result)
        print(record['id'],record.get('labels'),record['contract_pass'],flush=True)
    print('Fixed B2 bundle complete; source/output audit pending; no retries',flush=True)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('mode',choices=['prepare','preflight','run'])
    globals()[cli.parse_args().mode]()
