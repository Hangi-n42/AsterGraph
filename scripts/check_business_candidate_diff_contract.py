"""Offline proposed transport contract; keeps frozen model outputs unchanged."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import compare_business_candidate_text_diff as b1
from business_candidate_diff_fields import character_diff

ALIASES={'supported':'1','unsupported':'2','contradicted':'3'}


def technical_view(content,cases,canonical):
    answer=json.loads('{'+content,object_pairs_hook=b1.prior.previous.previous.strict_object)
    adapted=deepcopy(answer);changes=[]
    for candidate,row in adapted['judgments'].items():
        if row['label'] in ALIASES:
            old=row['label'];row['label']=ALIASES[old]
            changes.append(dict(kind='fixed_literal_alias',candidate=candidate,before=old,after=row['label']))
    judgments_only=deepcopy(adapted);judgments_only['differences']=[]
    parsed=b1.prior.parse(json.dumps(judgments_only,ensure_ascii=False)[1:],cases,canonical)
    diff=character_diff({k:c['raw'] for k,c in cases.items()})
    addresses=[]
    for d in adapted['differences']:
        ids=set(d)-{'dimensions','reason'}
        if not {'dimensions','reason'}<=set(d) or not 2<=len(ids)<=len(cases) or not ids<=set(cases):
            raise ValueError('difference_candidates')
        if not isinstance(d['dimensions'],list) or not d['dimensions'] or any(v not in b1.prior.DIMENSIONS for v in d['dimensions']):
            raise ValueError('difference_dimensions')
        if not isinstance(d['reason'],str) or not d['reason'].strip():raise ValueError('difference_reason')
        for ident in ids:
            ref=d[ident]
            if not isinstance(ref,dict) or set(ref)!={'field','quote'}:raise ValueError('reference_schema')
            if ref['quote']:
                b1.prior.previous.previous.refs.exact(ref,cases[ident],candidate=True)
                text=cases[ident]['raw'][ref['field']];start=text.index(ref['quote'])
                addresses.append(dict(candidate=ident,field=ref['field'],span=[start,start+len(ref['quote'])],kind='nonempty_model_quote'))
                continue
            if ref['quote']!='' or len(ids)!=2:raise ValueError('unsupported_empty_reference')
            other=next(iter(ids-{ident}));opposite=d[other]
            if opposite['field']!=ref['field'] or not opposite['quote']:raise ValueError('missing_deletion_counterpart')
            b1.prior.previous.previous.refs.exact(opposite,cases[other],candidate=True)
            matches=[]
            for pair in diff['pairs']:
                if set(pair['candidates'])!=ids:continue
                for field in pair['fields']:
                    if field['field']!='raw.'+ref['field']:continue
                    for segment in field['segments']:
                        if segment['op'] in {'insert','delete'} and segment[ident][2]=='' and segment[other][2]==opposite['quote']:
                            matches.append(segment[ident][:2])
            if len(matches)!=1 or matches[0][0]!=matches[0][1]:raise ValueError('unverified_or_ambiguous_empty_point')
            text=cases[ident]['raw'][ref['field']];start,end=matches[0]
            if not isinstance(text,str) or not 0<=start==end<=len(text):raise ValueError('empty_point_bounds')
            addresses.append(dict(candidate=ident,field=ref['field'],quote='',span=[start,end],kind='server_verified_deletion_point',
                counterpart=other,provenance='exact full counterpart quote and unique opcode from unchanged input candidates'))
            changes.append(dict(kind='typed_empty_span',candidate=ident,field=ref['field'],span=[start,end],original_quote_preserved=True))
    return dict(technical_contract_pass=True,changes=changes,difference_addresses=addresses,
                canonical_address_verified=parsed['canonical_address_verified'],source_reason_not_corrected=True)


if __name__=='__main__':
    out=b1.OUT;rows=b1.read(out/'inputs.json');results=[]
    paths=[out/'run/result.json']+[out/'run'/f"{r['id']}_response.json" for r in rows]
    paths += [Path(r['baseline']['response_path']) for r in rows]
    hashes={str(p):b1.sha(p) for p in paths}
    for row in rows:
        for treatment,path in [('baseline',Path(row['baseline']['response_path'])),('B1',out/'run'/f"{row['id']}_response.json")]:
            result=technical_view(b1.read(path)['content'],row['cases'],row['canonical_views'])
            results.append(dict(id=row['id'],treatment=treatment,raw_sha256=b1.sha(path),**result))
    assert all(b1.sha(Path(p))==h for p,h in hashes.items())
    b1.write(out/'technical_contract_spec.json',dict(version='offline-proposal-v1',aliases=ALIASES,
        empty_reference='Retain empty quote; add typed zero-width coordinates only when same field, nonempty unique counterpart quote and exactly one full insert/delete opcode match unchanged input candidates.',
        invalid=['Unknown aliases','Non-string fields','Two empty quotes','Three-way empty reference','Unmatched/ambiguous/partial opcode','Different fields','Changed input'],
        unchanged=['Original schema failures/gate','Raw bytes','Labels semantic meaning','Reasons','Evidence','Error spans','Prompt/model settings'],
        product_implementation=False,new_prompt_instructions=False))
    b1.write(out/'technical_contract_check.json',dict(records=results,new_model_calls=0,
        stored_response_checks=8,original_gate_pass=False,new_technical_contract_only=True,
        reason_failure_still_present='condition.Y',raw_hashes_verified_unchanged=hashes))
    print('Offline proposed transport contract: 8/8 saved outputs; original gate stays false; condition reason unchanged')
