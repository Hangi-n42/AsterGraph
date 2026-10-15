"""Prepare B1 fresh confirmation only; no product/native model call."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import compare_business_condition_contrast as prior
import compare_business_label_selection as base
import compare_business_candidate_text_diff as v1
from business_candidate_diff_fields import character_diff

OUT=ROOT/'data/knowledge/evaluations/business_candidate_diff_confirmation_20261011'
AUTHOR=Path('/private/tmp/business_fresh_confirmation_20261011_author')
REVIEWER=Path('/private/tmp/business_fresh_confirmation_20261011_reviewer')
read,write,sha=base.read,base.write,base.sha
GROUPS=[('normal_detail',['NIE-C01','NIE-C08']),('permission_place',['NIE-C02','NIE-C03','NIE-C04']),
        ('equipment_scope',['NIE-C05','NIE-C06','NIE-C07'])]
LABELS={'S':'supported','U':'unsupported','C':'contradicted'}


def source_views(source):
    blocks=[];views={};parents=[]
    for n,block in enumerate(source['blocks']):
        ident=block['block_id'];text=block['text'];marker=f'[{ident}]\n'
        assert source['source_text'].count(marker)==1
        start=source['source_text'].index(marker)+len(marker)
        assert source['source_text'][start:start+len(text)]==text
        ref=f'e{n+1}'
        blocks.append(dict(id=ident,text=text,evidence_ref=ref,source_version_id='v1',parent_id=block['parent_id']))
        views[ref]=dict(id=ident,evidence_id=ident,source_version_id='v1',parse_run_id='archived_full_dom_extraction_20261011',
            unit_id=source['document_id'],order=n,text=text,source_id=source['document_id'],span=[start,start+len(text)],
            locator=dict(format='html',selector='div.sub-useGuide',element_path=f'archived_block[{n}]',block_order=n,
                         normalized_text_marker=marker,parent_id=block['parent_id']))
    for section in source['sections']:
        parents.append(dict(id=section['section_id'],parent_id=section['parent_id'],title=section['heading'],
                            block_ids=[b['block_id'] for b in source['blocks'] if b['parent_id']==section['section_id']]))
    # Preserve table merge attributes and each cell's decoded text separately from flattened rows.
    spans=[]
    def cells(node,block_id,path=()):
        if not isinstance(node,dict):return
        attrs=node.get('attrs',{})
        if any(k in attrs for k in ['rowspan','colspan']):
            def text(value):
                if isinstance(value,str):return value
                return ''.join(text(v) for v in value.get('children',[]))
            spans.append(dict(block_id=block_id,path=list(path),tag=node['tag'],
                              attributes={k:attrs[k] for k in ['rowspan','colspan'] if k in attrs},text=text(node)))
        for i,v in enumerate(node.get('children',[])):cells(v,block_id,path+(i,))
    for b in source['blocks']:cells(b['html_tree'],b['block_id'])
    context=dict(blocks=blocks,source_parents=parents,source_versions=[dict(id='v1',source_id=source['document_id'],
        title=source['title'],url=source['url'],sha256=source['raw_html_sha256'],dates=[])],
        source_structure=dict(table_spans=spans,external_link_bodies_provided=False,image_pixels_provided=False))
    return context,views


if __name__=='__main__':
    assert not OUT.exists()
    source=read(AUTHOR/'revision_v2/blind_packet_v2/source.json')
    packet=read(AUTHOR/'revision_v2/blind_packet_v2/candidates.json')
    gold=read(AUTHOR/'revision_v2/gold_v2.json')
    independent=read(REVIEWER/'independent_v2.json')
    comparison=read(REVIEWER/'comparison_v2.json')
    candidates={r['candidate_id']:{k:r[k] for k in ['Event','Entity']} for r in packet['candidates']}
    expected={r['candidate_id']:LABELS[r['label']] for r in gold['answers']}
    reviewer={r['candidate_id']:LABELS[r['label']] for r in independent['candidate_reviews']}
    assert expected==reviewer and len(candidates)==8
    assert sha(REVIEWER/'independent.json')=='9af0176070ecfd8c26f3fcd739e130d6827f508750203894b20f9cb4c9a32e0f'
    assert sha(REVIEWER/'independent_v2.json')=='de258e8e9887fe5a93cb94759ba054d9aeebb4e7a7abe625454aa776afe87e63'
    before=read(AUTHOR/'blind_packet/candidates.json')['candidates'];after=packet['candidates']
    assert [a['candidate_id'] for a,b in zip(after,before) if a!=b]==['NIE-C08']
    assert sha(AUTHOR/'blind_packet/source.json')==sha(AUTHOR/'revision_v2/blind_packet_v2/source.json')
    context,views=source_views(source)
    # Use exact transport parameters from the executed fixed request.
    old=read(ROOT/'data/knowledge/evaluations/business_singleton_confirmation_20261011_execution/requests.json')[0]
    params={k:v for k,v in old['request'].items() if k!='prompt'}
    rows=[]
    for group,ids in GROUPS:
        cases={key:dict(id=ident,raw=candidates[ident],**deepcopy(context)) for key,ident in zip(['X','Y','Z'],ids)}
        baseline=prior.prompt(cases)
        prefix,tail=baseline.split('<|im_start|>user\n',1);body,suffix=tail.split('<|im_end|>',1)
        payload=json.loads(body);diff=character_diff(payload['candidates'])
        treatment=prefix+'<|im_start|>user\n'+json.dumps(dict(payload,candidate_text_diff=diff),ensure_ascii=False)+'<|im_end|>'+suffix
        recovered=json.loads(treatment.split('<|im_start|>user\n')[1].split('<|im_end|>')[0]);recovered.pop('candidate_text_diff')
        assert recovered==payload and prefix==treatment.split('<|im_start|>user\n')[0]
        for condition,prompt in [('baseline',baseline),('diff',treatment)]:
            rows.append(dict(id=group+'_'+condition,group=group,condition=condition,cases=cases,canonical_views=views,
                prompt=prompt,parameters=params,expected={key:expected[c['id']] for key,c in cases.items()}))
    rows.sort(key=lambda r:(r['condition']=='diff',[g for g,_ in GROUPS].index(r['group'])))
    # Existing equal-path B1 cases must retain exactly the frozen annotation object.
    for old_row in read(v1.OUT/'inputs.json'):
        raw={k:v['raw'] for k,v in old_row['cases'].items()}
        assert character_diff(raw)==v1.character_diff(raw)
    OUT.mkdir();write(OUT/'inputs.json',rows)
    write(OUT/'preparation_failure_receipt.json',dict(
        original_failure="AssertionError at source_views: assert source['source_text'].count(text)==1",
        failed_before_output_directory_creation=True,new_model_calls=0,
        repeated_block_counts={b['block_id']:source['source_text'].count(b['text']) for b in source['blocks']
                               if source['source_text'].count(b['text'])!=1},
        repair='Unique archived block marker followed by exact unchanged block text; no global-first-phrase choice.',
        unchanged=['Full source','Candidates','Gold','Grouping','Semantic instructions'],semantic_improvement=False))
    write(OUT/'criteria.json',dict(product_model_calls=0,execution_authorized=False,maximum_new_calls=6,reused_responses=0,
        groups=GROUPS,unique_candidates=8,judgment_occurrences_per_condition=8,baseline_and_diff_occurrences=16,
        normal_unique_candidates=4,error_unique_candidates=4,all_normal_claims_preserved=True,
        gate='Diff: all 8 labels, all four normals, U/C/gaps, differences, exact locations/evidence, no added completeness/exemption/prohibition and new technical output contract pass. Compare all baseline results separately; do not change gold or retry.',
        expected={r['id']:r['expected'] for r in rows},technical_contract='Identical fixed literal aliases and uniquely input-verified typed empty spans for both baseline and diff; legacy contract failures also recorded.',
        parser='check_business_candidate_diff_contract.technical_view',new_original_B1_success=False,original_B1_gate_pass=False,
        candidate_revision='Only C08 changed before any product model call for hypothesis fit; v1 source/candidates/gold/blind judgments preserved.',
        string_path_extension='Unequal Entity lengths preserved. Missing versus empty path explicitly distinguished; no source interpretation.',
        source_full_text_chars=len(source['source_text']),source_blocks=len(source['blocks']),source_parents=len(source['sections']),
        source_address_scope='Archived extracted source normalized-text spans, not an existing company DB parse or source version.',
        token_runtime_preflight='Pending resource handoff; require complete input plus output2048 below ctx8192. No source truncation to pass.',
        limitations=['Same GPT-6 Astra in separate fresh author/reviewer contexts, not human validation or different-model verification.',
                    'Bounded saved-path absence before acquisition is not all-chat/deleted/pretraining non-exposure.',
                    'No product model output grading by author/reviewer. No local/native load or execution during preparation.']))
    shutil.copytree(AUTHOR,OUT/'author');shutil.copytree(REVIEWER,OUT/'reviewer')
    code=[Path(__file__),ROOT/'scripts/business_candidate_diff_fields.py',ROOT/'scripts/check_business_candidate_diff_contract.py',
          ROOT/'scripts/compare_business_candidate_text_diff.py',ROOT/'scripts/compare_business_condition_contrast.py',
          ROOT/'scripts/compare_business_label_selection.py',ROOT/'scripts/compare_business_explicit_opposition.py',
          ROOT/'scripts/compare_business_candidate_contrast.py',ROOT/'scripts/compare_business_joint_contrast.py',
          ROOT/'scripts/compare_business_modality_spans.py',ROOT/'scripts/compare_business_nli.py',ROOT/'app/knowledge/business_run.py']
    for p in code:
        dest=OUT/'frozen_code'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    files={str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file()}
    write(OUT/'freeze_manifest.json',dict(files=files,calls=0,model_resources_used=False,
        unchanged_original_B1=True,code={str(p.relative_to(ROOT)):sha(p) for p in code},
        runtime_reference=str(ROOT/'data/knowledge/evaluations/business_singleton_confirmation_20261011_execution/runtime_identity.json')))
    print(json.dumps(dict(prepared=str(OUT),source_blocks=len(source['blocks']),unique_candidates=8,fixed_requests=6,product_model_calls=0,token_preflight='pending'),ensure_ascii=False))
