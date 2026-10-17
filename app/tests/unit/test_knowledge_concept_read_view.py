"""One explicit product child view; retrieval/generation are local stubs only."""
from copy import deepcopy
import json

import numpy as np
import pytest
from pydantic import ValidationError

from app.knowledge import business_concepts, business_use, business_run, graph_retrieval
from app.knowledge.business_models import BusinessQuery, ConceptRunRequest
from app.tests.unit.test_knowledge_concept_source_map_entrypoints import environment, pool, store


def setup(environment):
    service,requests=environment
    parent=pool('v');targets=[n for n in parent['graph']['nodes'] if n['kind']=='entity']
    parent['concepts']=[dict(id='old'+str(i),target=deepcopy(t),concepts=['old'+str(i)],status='accepted',
        relation='has_concept',approved_is_a=False) for i,t in enumerate(targets)]
    store(service,parent)
    child=business_concepts.start(service,ConceptRunRequest(parent_run_id=parent['id'],target_ids=[targets[0]['id']],neighbor_mode='plain'))
    assert child['status']=='succeeded'
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)',('untouched',json.dumps(dict(id='untouched',concepts=parent['concepts']))))
    return service,requests,parent,child


def test_explicit_single_child_replaces_only_its_target_without_mutating_saved_data(environment):
    service,_,parent,child=setup(environment)
    with service.repository.connect() as db:
        before={table:db.execute('SELECT payload FROM '+table+' ORDER BY id').fetchall() for table in ['runs','snapshots']}
        view,meta=business_use.concept_read_view(service,db,parent,child['id'])
        assert view[-1]==child['concepts'][0] and view[0]==parent['concepts'][1]
        assert len(view)==len(parent['concepts']) and meta['concept_run_id']==child['id']
        assert meta['parent_and_snapshot_persisted'] is False
        view[-1]['target']['label']='view-only'
        after={table:db.execute('SELECT payload FROM '+table+' ORDER BY id').fetchall() for table in ['runs','snapshots']}
        assert [tuple(r) for r in before['runs']]==[tuple(r) for r in after['runs']]
        assert [tuple(r) for r in before['snapshots']]==[tuple(r) for r in after['snapshots']]
    assert child['concepts'][0]['target']['label']!='view-only'


@pytest.mark.parametrize('fault',['parent','versions','fingerprint','active','target','binding','approved','reviewed','incomplete','work','changed_source','stale_parent_graph'])
def test_incompatible_child_or_current_source_is_rejected_before_consumption(environment,fault):
    service,requests,parent,child=setup(environment);count=len(requests)
    if fault=='parent':child['parent_run_id']='elsewhere'
    elif fault=='versions':child['input_version_ids']=['other']
    elif fault=='fingerprint':child['graph_fingerprint']='stale'
    elif fault=='active':child['status']='running'
    elif fault=='target':child['concepts'][0]['target']['claim_ids']=[]
    elif fault=='binding':child['concept_bindings'][0]['target_id']='other'
    elif fault=='approved':child['concepts'][0]['approved_is_a']=True
    elif fault=='reviewed':child['concepts'][0]['status']='accepted'
    elif fault=='incomplete':child['units'][0]['response']['done']=False
    elif fault=='work':next(iter(child['concept_work'].values()))['fingerprint']='wrong'
    elif fault=='changed_source':parent['blocks'][0]['text']+=' changed'
    else:parent['claims'][0]['raw']['Relation']='changed'
    with service.repository.connect() as db:
        service.repository.save(db,'runs',child)
        with pytest.raises(ValueError):business_use.concept_read_view(service,db,parent,child['id'])
    assert len(requests)==count


def test_snapshot_query_cannot_select_source_child():
    with pytest.raises(ValidationError):BusinessQuery(snapshot_id='s',concept_run_id='child',question='q')


@pytest.mark.parametrize('explicit',[False,True])
def test_product_source_query_consumes_only_explicit_child_and_keeps_other_targets(environment,monkeypatch,explicit):
    service,_,parent,child=setup(environment)
    before_parent=deepcopy(parent);before_child=deepcopy(child);captured=[];stages=[]
    original=graph_retrieval.build
    def inspect(snapshot,variant):
        captured.append(deepcopy(snapshot['concepts']))
        return original(snapshot,variant)
    monkeypatch.setattr(graph_retrieval,'build',inspect)
    monkeypatch.setattr(graph_retrieval,'embed',lambda texts, *, service=None:np.asarray([[1.,.5] for _ in texts]))
    def call(service,run,stage,instruction,context,schema,**kwargs):
        stages.append(stage)
        if stage=='graph_retrieval_filter':return dict(selected_ids=[context['candidate_facts'][0]['id']])
        assert stage=='business_qa'
        assert 'has_concept' not in json.dumps(context['context'])
        return dict(answer='fixture source answer',choice=None,citations=[context['context'][0]['id']],limitations=[])
    monkeypatch.setattr(business_run,'json_call',call)
    query=BusinessQuery(source_run_id=parent['id'],concept_run_id=child['id'] if explicit else None,question='fixture',limit=1)
    result=business_use.query(service,query)
    assert result['status']=='answered' and stages==['graph_retrieval_filter','business_qa']
    assert captured and all(c[0 if not explicit else -1]['concepts']==(parent['concepts'][0]['concepts'] if not explicit else child['concepts'][0]['concepts']) for c in captured)
    assert all(parent['concepts'][1] in c for c in captured)
    with service.repository.connect() as db:
        assert service.repository.get(db,'runs',parent['id'])==before_parent
        assert service.repository.get(db,'runs',child['id'])==before_child
        saved=service.repository.get(db,'runs',result['run_id'])
        assert json.loads(db.execute('SELECT payload FROM snapshots WHERE id=?',('untouched',)).fetchone()[0])['concepts']==parent['concepts']
    if explicit:
        assert saved['concept_view']['concept_run_id']==result['concept_run_id']==child['id']
        assert saved['concept_view']['states']=='unreviewed; has_concept; approved_is_a=false'
    else:
        assert 'concept_view' not in saved and 'concept_run_id' not in result
