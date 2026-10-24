"""Explicit reference correction fixtures, never model or independent-human quality evidence."""
from copy import deepcopy
import json
import sqlite3
import threading

import pytest

from app.knowledge import answer_review, answer_links, business_use as use, business_run, concept_work, workbench
from app.knowledge.service import KnowledgeService, KnowledgeConflict, encode
from app.generation.model_client import ModelClient


@pytest.fixture
def stored(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path/'knowledge.db')
    def forbidden(*a, **k): pytest.fail('No model, count, search or background execution')
    monkeypatch.setattr(ModelClient,'generate',forbidden)
    monkeypatch.setattr(business_run,'call',forbidden)
    monkeypatch.setattr(business_run,'request_budget',forbidden)
    monkeypatch.setattr(service.executor,'submit',forbidden)
    view = dict(id='block',source_version_id='version',parse_run_id='parse',span=[0,18],text='원문 확인 사실. 다른 사실.')
    view['span'][1] = len(view['text'])
    claims = [dict(id=cid,role='event_entity',raw=dict(Event=text,Entity=[]),statement=text,
        source_version_ids=['version'],review_status='accepted',semantic_status='unknown',evidence=[])
        for cid,text in [('direct','원문 확인 사실'),('unrelated','다른 사실')]]
    snapshot = dict(id='snapshot',kind='source_graph',run_id='source-run',source_versions={'version':{}},
        claims=claims,blocks=[view],concepts=[],requirements=[dict(id='req',revision=1)],assessments={})
    source = dict(id='source-run',kind='business',status='cancelled',units=[],claims=claims,blocks=[view])
    context = [dict(id=c['id'],text=encode(business_run.compact_claim(c)),file_id='version') for c in claims]
    model, refs = use.answer_references(context,[view],source_citation_contract=answer_links.CONTRACT)
    query = dict(snapshot_id='snapshot',question='질문',answer_mode='synthesis',requirement_ids=[],source_citation_contract=answer_links.CONTRACT)
    parent = dict(id='parent',kind='business_query',status='succeeded',answer_status='answered',snapshot_id='snapshot',query=query,
        input_version_ids=['version'],provided_ids=['direct','unrelated'],answer_contract=use.ANSWER_CONTRACT,
        metrics=dict(llm_calls=1,model_total_s=2,elapsed_s=3),recipe=dict(options={}))
    packet = business_run.json_request(parent,'business_qa','기존 지시',dict(question='질문',context=context,source_evidence=[view]),model,reference_map=refs)
    raw = dict(answer='직접 사실 설명. 참고 설명.',choice=None,citations=['q1','q2'],limitations=['제공 자료에서 이유 확인 불가'],
        source_citations=[dict(quote_id='sq_original',evidence_ref='b1',quote='원문 확인 사실')],answer_links=[
        dict(target='answer',anchor='직접 사실 설명',claim_refs=['q1'],quote_refs=['sq_original']),
        dict(target='answer',anchor='참고 설명',claim_refs=['q2'],quote_refs=['sq_original']),
        dict(target='limitations',anchor='제공 자료에서 이유 확인 불가',claim_refs=['q2'],quote_refs=['sq_original'])])
    output, meta = answer_links.restore(raw,{v:k for k,v in packet['reference_map'].items()})
    output['_answer_link_metadata'] = meta
    use.record_answer_source_citations(parent,output,[view],[view]);answer_links.record(parent,output,parent['provided_ids'])
    parent['answer'] = output
    parent['units'] = [dict(id='producer',stage='business_qa',status='succeeded',messages=packet['messages'],
        reference_map=packet['reference_map'],response=dict(parsed=raw,text=encode(raw)))]
    with service.repository.connect() as db:
        for table,item in [('runs',source),('runs',parent),('snapshots',snapshot),('requirements',dict(id='req',revision=1,status='unknown'))]:
            db.execute('INSERT INTO '+table+' VALUES(?,?)',(item['id'],encode(item)))
    try: yield service,parent,snapshot
    finally: service.shutdown()


def request(parent):
    links = [deepcopy(v['declaration']) for v in parent['answer_links']['links'][:2]]
    links[1]['claim_refs'] = []
    return dict(expected_parent_fingerprint=concept_work.digest(parent),actor='사용자 지시에 따른 Codex 명시 정정',
                reason='참조만 명시 정정',citations=['direct'],links=links)


def test_reference_only_child_is_idempotent_and_retains_producer_and_quotes(stored):
    service,parent,snapshot = stored
    child = answer_review.correct(service,'parent',**request(parent))
    repeated = answer_review.correct(service,'parent',**request(parent))
    assert repeated == child and child['id']!='parent'
    assert child['answer']['answer']==parent['answer']['answer'] and child['answer']['limitations']==parent['answer']['limitations']
    assert child['answer_source_citations']==parent['answer_source_citations'] and child['units']==parent['units']
    assert child['answer']['citations']==['direct'] and child['answer_links']['links'][1]['declaration']['claim_refs']==[]
    assert child['answer_links']['relation']=='reviewer_corrected' and child['answer_links']['semantic_support']=='not_assessed'
    assert child['metrics']['llm_calls']==child['metrics']['model_total_s']==0
    assert child['metrics']['elapsed_s']>0
    assert child['answer_review']['producer_metrics']==parent['metrics'] and not child['answer_review']['human_approval']
    with service.repository.connect() as db:
        assert service.repository.get(db,'runs','parent')==parent
        assert service.repository.get(db,'snapshots','snapshot')==snapshot
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==3


@pytest.mark.parametrize('fault', ['stale','new_claim','new_quote','bad_anchor','duplicate','noop'])
def test_invalid_correction_never_changes_a_stored_row(stored,fault):
    service,parent,_ = stored
    args = request(parent)
    if fault=='stale': args['expected_parent_fingerprint']='old'
    if fault=='new_claim': args['citations']=['not-in-previous-answer']
    if fault=='new_quote': args['links'][0]['quote_refs']=['not-recorded']
    if fault=='bad_anchor': args['links'][0]['anchor']='없는 구절'
    if fault=='duplicate': args['citations']=['direct','direct']
    if fault=='noop': args.update(citations=parent['answer']['citations'],links=[v['declaration'] for v in parent['answer_links']['links']])
    with pytest.raises((KnowledgeConflict,ValueError)): answer_review.correct(service,'parent',**args)
    with service.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==2
        assert service.repository.get(db,'runs','parent')==parent


@pytest.mark.parametrize('fault', ['restricted','requirement','selection','source','parent_gate'])
def test_current_versions_and_use_gates_are_preserved(stored,monkeypatch,fault):
    service,parent,snapshot = stored
    if fault=='restricted': monkeypatch.setattr(use,'restricted_sources',lambda *a:[dict(state='restricted')])
    with service.repository.connect() as db:
        if fault=='requirement': service.repository.save(db,'requirements',dict(id='req',revision=2,status='unknown'))
        if fault=='selection':
            parent['query']['requirement_ids']=['missing'];service.repository.save(db,'runs',parent)
        if fault=='parent_gate':
            parent['answer_status']='needs_review';service.repository.save(db,'runs',parent)
        if fault=='source':
            snapshot['blocks'][0]['text']='변경된 원문'
            db.execute('UPDATE snapshots SET payload=? WHERE id=?',(encode(snapshot),'snapshot'))
    with pytest.raises((KnowledgeConflict,ValueError)): answer_review.correct(service,'parent',**request(parent))
    with service.repository.connect() as db: assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==2


def test_competing_committed_parent_change_is_checked_after_writer_lock(stored):
    service,parent,_ = stored
    errors=[];started=threading.Event()
    def correct():
        started.set()
        try: answer_review.correct(service,'parent',**request(parent))
        except Exception as exc: errors.append(exc)
    with sqlite3.connect(service.repository.path) as other:
        other.execute('BEGIN IMMEDIATE')
        changed=deepcopy(parent);changed['concurrent_revision']='changed'
        other.execute('UPDATE runs SET payload=? WHERE id=?',(encode(changed),'parent'))
        thread=threading.Thread(target=correct);thread.start();assert started.wait(1)
    thread.join(5)
    assert not thread.is_alive() and len(errors)==1 and isinstance(errors[0],KnowledgeConflict)
    with service.repository.connect() as db: assert db.execute('SELECT count(*) FROM runs').fetchone()[0]==2


def test_workbench_hides_correction_receipt_when_answer_requires_review(stored,monkeypatch):
    service,parent,snapshot = stored
    child=answer_review.correct(service,'parent',**request(parent))
    monkeypatch.setattr(workbench,'_scope',lambda *a:(snapshot,dict(edges=[]),{},{}))
    monkeypatch.setattr(workbench,'usage',lambda *a:{})
    visible=workbench.answers(service,'source_graph','snapshot',child['id'])['detail']
    assert visible['answer_review']==child['answer_review']
    child['answer_status']='needs_review';child['answer']=None
    child['answer_source_citations'].update(status='needs_review',citations=[]);answer_links.withhold(child)
    with service.repository.connect() as db: service.repository.save(db,'runs',child)
    hidden=workbench.answers(service,'source_graph','snapshot',child['id'])['detail']
    assert hidden['answer_review']==dict(status='needs_review') and hidden['answer_link_claims']==dict(status='needs_review',claims={})
    assert child['units']==parent['units']
