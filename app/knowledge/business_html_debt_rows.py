"""Literal cells of the two-level KSIC-10 debt-ratio table; no applicability inference."""
from copy import deepcopy
import json,re

from . import autoschema,business_run

PROFILE = 'verified_html_debt_ratio_row_v1'
HEADERS = ['번호','업종(KSIC-10)','평균부채\n비율(%)','제한부채\n비율(%)','사업전환\n융자']
NOTES = ['*업종별 산업분류코드 중 하위코드 항목이 있을 경우 우선적용',
         '* 제한부채비율은 최소 200%, 최대 500% 이내',
         '* 한국은행 기업경영분석에 의한 최근 3개년 가중평균 부채비율']


def prepare(parent,targets,table,cell,persisted,version,parse_id,path):
    rows=table.find_all('tr',recursive=False)
    headers=[cell(0,c) for c in range(4)]+[cell(1,4)]
    if ([b['text'] for b,_ in headers]!=HEADERS
            or any(b['locator']['merged_span']!={'rows':2 if c<4 else 1,'columns':1} for c,(b,_) in enumerate(headers))
            or len(rows[0].find_all(['td','th'],recursive=False))!=5
            or len(rows[1].find_all(['td','th'],recursive=False))!=1):
        raise ValueError('unsupported_debt_ratio_headers_or_spans')
    blank=[c for c in rows[0].find_all(['td','th'],recursive=False) if c.get('data-native-col')=='4']
    if (len(blank)!=1 or blank[0].get_text('\n',strip=True)
            or int(blank[0].get('rowspan',1))!=1 or int(blank[0].get('colspan',1))!=1):
        raise ValueError('unsupported_debt_ratio_empty_header')
    item=table.find_parent('li')
    listing=item.parent if item else None
    siblings=listing.find_all('li',recursive=False) if listing and listing.name=='ul' else []
    section=table.find_parent('section')
    title=section.find('p',recursive=False) if section else None
    heading=section.find('h1',recursive=False) if section else None
    if (len(siblings)!=3 or siblings[0] is not item or not title or not heading
            or title.get_text('\n',strip=True)!='업종별 융자제한 부채비율'
            or heading.get_text('\n',strip=True)!='<별표 2>'
            or [''.join(item.find_all(string=True,recursive=False)).strip(),
                *[n.get_text('\n',strip=True) for n in siblings[1:]]]!=NOTES):
        raise ValueError('unsupported_debt_ratio_source_context')
    root=table
    while root.parent is not None:root=root.parent
    def context_ref(node,text):
        matches=[]
        for b in parent['blocks']:
            if b['source_version_id']!=version['id'] or b.get('parse_run_id')!=parse_id or b['text'].strip()!=text:
                continue
            location=b.get('locator',{}).get('element_path','')
            text_node=re.search(r'::text\((\d+)\)$',location)
            selector=re.sub(r'::text\(\d+\)$','',location)
            located=root.select(selector) if selector else []
            if len(located)==1 and located[0] is node:
                original_text=(str(node.find_all(string=True,recursive=False)[int(text_node[1])])
                               if text_node else node.get_text('\n',strip=True))
                if original_text==b['text']:matches.append(b)
        if len(matches)!=1:raise ValueError('debt_ratio_context_not_uniquely_located')
        b=matches[0];original=persisted.get(b['id'])
        if not original or any(original.get(k)!=b.get(k) for k in ('text','locator','source_version_id','parse_run_id')):
            raise ValueError('stored_parse_context_mismatch')
        ref=business_run.exact_evidence([dict(block_id=b['id'],quote=b['text'])],parent['blocks'])[0]
        return dict(ref,precision='verified_html_context',locator=deepcopy(b['locator']))
    notes=[dict(evidence=context_ref(node,text),structural_scope='same_source_list',application_state='unresolved')
           for node,text in zip(siblings,NOTES)]
    context=[context_ref(heading,'<별표 2>'),context_ref(title,'업종별 융자제한 부채비율')]
    mapping=dict(profile=PROFILE,source_version_id=version['id'],parse_run_id=parse_id,raw_sha256=version['sha256'],
        table_path=path,headers=[dict(field=name,evidence=deepcopy(ref)) for name,(_,ref) in zip(HEADERS,headers)],
        empty_header=dict(row=0,column=4,text='',block_id=None,merged_span=dict(rows=1,columns=1)),
        source_context=context,common_notes=notes,units={
            name:dict(state='explicit_in_header' if c<4 else 'unresolved',symbol='%' if c<4 else None,
                      evidence=deepcopy(headers[c][1])) for c,name in enumerate(HEADERS) if c>=2},
        semantic_status='unverified')
    mapping['id']=autoschema.identifier('table_mapping',mapping)
    claims,rejections=[],[]
    for target in targets:
        try:
            row=target['locator']['row']
            if target['locator'].get('column')!=1 or row<2:raise ValueError('select_debt_ratio_industry_cell_only')
            values=[cell(row,c) for c in range(5)]
            if (len(rows[row].find_all(['td','th'],recursive=False))!=5
                    or any(b['locator']['row']!=row or b['locator']['merged_span']!={'rows':1,'columns':1} for b,_ in values)):
                raise ValueError('unsupported_debt_ratio_body_merge')
            if not values[0][0]['text'].isdigit() or any(not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',b['text']) for b,_ in values[2:]):
                raise ValueError('unsupported_debt_ratio_literal_value')
            fields={name:b['text'] for name,(b,_) in zip(HEADERS,values)}
            field_sources={name:dict(value=deepcopy(ref),header=deepcopy(headers[c][1]))
                           for c,(name,(_,ref)) in enumerate(zip(HEADERS,values))}
            field_evidence={name:[deepcopy(ref),deepcopy(headers[c][1]),
                                  *[deepcopy(n['evidence']) for n in notes],*deepcopy(context)]
                            for c,(name,(_,ref)) in enumerate(zip(HEADERS,values))}
            evidence={ref['block_id']:ref for refs in field_evidence.values() for ref in refs}
            chunk=dict(id=autoschema.identifier('debt_row',[version['id'],parse_id,path,row]),
                       source_version_id=version['id'],blocks=[b for b,_ in values])
            claim=autoschema.graph_record(chunk,'structured_row',dict(Event=json.dumps(fields,ensure_ascii=False),fields=fields),0)
            claim.update(id=autoschema.identifier('claim',[PROFILE,version['id'],parse_id,path,row]),
                construction_method='direct_tabular_row',table_mapping=deepcopy(mapping),
                evidence=list(evidence.values()),field_sources=field_sources,field_evidence=field_evidence,
                literal_source=dict(source_version_id=version['id'],parse_run_id=parse_id,sha256=version['sha256'],
                    table_path=path,row=row,headers=HEADERS,profile=PROFILE,mapping_id=mapping['id'],
                    row_key={name:fields[name] for name in HEADERS[:2]}),
                qualifier_status='literal_cells_only; units_and_note_application_as_recorded; semantics_unverified')
            if any(c['id']==claim['id'] for c in claims):raise ValueError('duplicate_row_address')
            claims.append(claim)
        except (ValueError,KeyError,IndexError) as exc:
            rejections.append(dict(block_id=target['id'],reason=str(exc)))
    return claims,rejections


def annotate_graph(graph,claims):
    """Reuse structured-row/field nodes, with each field's own source references."""
    rows={c['id']:c for c in claims if c.get('table_mapping',{}).get('profile')==PROFILE}
    for node in graph['nodes']:
        claim=next((rows[i] for i in node.get('claim_ids',[]) if i in rows),None)
        if claim is not None:
            node['construction_method']=PROFILE
            node['evidence']=deepcopy(claim['field_evidence'].get(node.get('field'),claim['evidence']))
