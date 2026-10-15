"""Literal rows from explicitly supported HTML table profiles."""
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4
import json,re

from bs4 import BeautifulSoup

from . import autoschema,business_run,business_use,business_html_debt_rows
from .service import KnowledgeConflict,encode,utcnow

METHOD = 'verified_html_classification_row_v1'
HEADERS = ['테마','분야','품목명','분류코드','업종명']


def prepare(service,parent,block_ids):
    if len(block_ids)!=len(set(block_ids)):
        raise ValueError('동일 원문 주소를 중복 선택할 수 없습니다.')
    originals={b['id']:b for b in parent['blocks']}
    selected=[originals[i] for i in block_ids]
    groups={};claims=[];rejections=[]
    for b in selected:
        loc=b.get('locator',{})
        key=(b['source_version_id'],b.get('parse_run_id'),loc.get('element_path'))
        groups.setdefault(key,[]).append(b)
    for (version_id,parse_id,path),targets in groups.items():
        try:
            with service.repository.connect() as db:
                version=service.repository.get(db,'versions',version_id)
                parse=service.repository.get(db,'runs',parse_id)
                recorded=service.parse_blocks(db,parse_id,version_id)
            if version['format']!='html' or parse['kind']!='parse' or version_id not in parse['input_version_ids']:
                raise ValueError('unsupported_source_or_parse')
            raw=service.raw_path(version).read_bytes()
            if sha256(raw).hexdigest()!=version['sha256']:
                raise ValueError('raw_source_hash_mismatch')
            soup=BeautifulSoup(raw.decode('utf-8-sig'),'html.parser');tables=soup.select(path or '')
            if len(tables)!=1 or tables[0].name!='table':
                raise ValueError('table_not_uniquely_located')
            table=tables[0];rows=table.find_all('tr',recursive=False)
            cells=[b for b in parent['blocks'] if b['source_version_id']==version_id and b.get('parse_run_id')==parse_id
                   and b.get('locator',{}).get('element_path')==path and 'row' in b['locator']]
            persisted={b['id']:b for b in recorded}
            def cell(row,column):
                owners=[b for b in cells if b['locator']['column']==column
                        and b['locator']['row']<=row<b['locator']['row']+b['locator']['merged_span']['rows']]
                if len(owners)!=1:raise ValueError('cell_owner_not_unique')
                b=owners[0];loc=b['locator'];original=persisted.get(b['id'])
                if not original or any(original.get(k)!=b.get(k) for k in ('text','locator','source_version_id','parse_run_id')):
                    raise ValueError('stored_parse_cell_mismatch')
                physical=[c for c in rows[loc['row']].find_all(['td','th'],recursive=False)
                          if int(c.get('data-native-col',-1))==column]
                span=loc['merged_span']
                if (len(physical)!=1 or span['columns']!=1 or physical[0].get_text('\n',strip=True)!=b['text']
                        or int(physical[0].get('rowspan',1))!=span['rows'] or int(physical[0].get('colspan',1))!=span['columns']):
                    raise ValueError('DOM_cell_text_or_span_mismatch')
                ref=business_run.exact_evidence([dict(block_id=b['id'],quote=b['text'])],parent['blocks'])[0]
                return b,dict(ref,precision='verified_html_cell',locator=deepcopy(loc))
            if cell(0,0)[0]['text']=='번호':
                added,rejected=business_html_debt_rows.prepare(parent,targets,table,cell,persisted,version,parse_id,path)
                claims.extend(added);rejections.extend(rejected)
                continue
            headers=[cell(0,c) for c in range(5)]
            if [b['text'] for b,_ in headers]!=HEADERS or len(rows[0].find_all(['td','th'],recursive=False))!=5:
                raise ValueError('unsupported_classification_headers')
            for target in targets:
                try:
                    loc=target['locator'];row=loc['row']
                    if loc.get('column')!=3 or row==0:raise ValueError('select_code_cell_only')
                    values=[cell(row,c) for c in range(5)]
                    if not re.fullmatch(r'[0-9]{5}',values[3][0]['text']):raise ValueError('multi_item_code_cell_not_supported')
                    fields={name:b['text'] for name,(b,_) in zip(HEADERS,values)}
                    field_sources={};field_evidence={};evidence={}
                    for column,name in enumerate(HEADERS):
                        ancestors=[ref for b,ref in values[:min(column,3)] if b['locator']['merged_span']['rows']>1]
                        refs=[values[column][1],headers[column][1],*ancestors]
                        field_sources[name]=dict(value=values[column][1],header=headers[column][1],parents=ancestors)
                        field_evidence[name]=deepcopy(refs)
                        for ref in refs:evidence[ref['block_id']]=ref
                    chunk=dict(id=autoschema.identifier('html_row',[version_id,parse_id,path,row]),source_version_id=version_id,
                               blocks=[values[c][0] for c in range(5)])
                    claim=autoschema.graph_record(chunk,'structured_row',dict(Event=json.dumps(fields,ensure_ascii=False),fields=fields),0)
                    claim['id']=autoschema.identifier('claim',[METHOD,version_id,parse_id,path,row])
                    claim.update(construction_method=METHOD,evidence=list(evidence.values()),field_sources=field_sources,
                        field_evidence=field_evidence,literal_source=dict(source_version_id=version_id,parse_run_id=parse_id,
                            sha256=version['sha256'],table_path=path,row=row,headers=HEADERS),
                        qualifier_status='literal_cells_only; applicability_and_semantics_unverified')
                    if any(c['id']==claim['id'] for c in claims):raise ValueError('duplicate_row_address')
                    claims.append(claim)
                except (ValueError,KeyError,IndexError) as exc:
                    rejections.append(dict(block_id=target['id'],reason=str(exc)))
        except (ValueError,KeyError,IndexError,OSError,UnicodeError) as exc:
            rejections.extend(dict(block_id=b['id'],reason=str(exc)) for b in targets)
    return claims,rejections


def store(service,request):
    with service.lock,service.repository.connect() as db:
        if service.closed or any(json.loads(r['payload'])['status'] in {'queued','running','cancel_requested'} for r in db.execute('SELECT payload FROM runs')):
            raise KnowledgeConflict('기존 실행 종료 후 원문 행을 저장하세요.')
        parent=service.repository.get(db,'runs',request.parent_run_id)
        if parent.get('kind')!='business' or parent.get('requirements'):
            raise ValueError('종료된 원문 구축 실행을 선택하세요.')
    claims,rejections=prepare(service,parent,request.block_ids)
    added,reused=[],[]
    for claim in claims:
        location=lambda c:tuple(c.get('literal_source',{}).get(k) for k in ('source_version_id','parse_run_id','table_path','row'))
        existing=[c for c in parent['claims'] if c.get('construction_method')==claim['construction_method']
                  and location(c)==location(claim)]
        if existing:
            if len(existing)!=1 or any(existing[0].get(k)!=claim.get(k) for k in ('raw','evidence','field_sources','field_evidence','literal_source','table_mapping')):
                rejections.append(dict(claim_id=claim['id'],reason='existing_row_content_conflict'))
            else:reused.append(existing[0]['id'])
        else:added.append(claim)
    profiles=sorted({c.get('table_mapping',{}).get('profile',c['construction_method']) for c in claims})
    run=deepcopy(parent);run.update(id=uuid4().hex,parent_run_id=parent['id'],status='partial',started_at=utcnow(),finished_at=utcnow(),
        metrics=dict(llm_calls=0,model_total_s=0,elapsed_s=0),
        html_literal_rows=dict(method=profiles[0] if len(profiles)==1 else METHOD,profiles=profiles,
            selected_block_ids=request.block_ids,added_claim_ids=[c['id'] for c in added],reused_claim_ids=reused,
            rejections=rejections,model_calls=0,semantic_quality_approved=False,original_claims_preserved=len(parent['claims'])))
    run['claims'].extend(added)
    delta=autoschema.graph(added)
    business_html_debt_rows.annotate_graph(delta,added)
    for key in ('nodes','edges'):
        existing_ids={v['id'] for v in run['graph'][key]}
        run['graph'][key].extend(v for v in delta[key] if v['id'] not in existing_ids)
    with service.lock,service.repository.connect() as db:db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
    run['changeset_id']=business_use.publish(service,run)['id'];business_run.save(service,run)
    return dict(run_id=run['id'],changeset_id=run['changeset_id'],status=run['status'],stored_rows=len(added),reused_rows=len(reused),rejections=rejections,model_calls=0)
