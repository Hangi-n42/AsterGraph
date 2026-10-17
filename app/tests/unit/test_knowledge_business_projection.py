from copy import deepcopy
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.knowledge import autoschema, business_run
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business import finish


def parent_run():
    blocks = [dict(id='b'+str(i), text=text, source_version_id='v', parse_run_id='p', order=i, locator={})
              for i, text in enumerate(['원문 조건과 예외', '미추출 별표 원문'])]
    chunks = autoschema.chunks(blocks[:1], 49152, 8192)
    chunk = chunks[0]
    claims = [autoschema.graph_record(chunk, role, raw, 0) for role, raw in [
        ('entity_relation', dict(Head='기업', Relation='신청한다', Tail='자금')),
        ('event_entity', dict(Event='신청', Entity=['기업'])),
        ('event_relation', dict(Head='신청', Relation='선행한다', Tail='심사'))]]
    parent = dict(id='parent', kind='business', status='cancelled', blocks=blocks, chunks=chunks,
        claims=claims, graph=dict(nodes=[], edges=[]), concepts=[], requirements=[], assessments=[], repairs=[],
        units=[], input_version_ids=['v'], sources={'v':dict(title='원문')}, model_identity={},
        recipe=dict(version=autoschema.VERSION, scope_contract=autoschema.SCOPE_CONTRACT,
                    generation=dict(provider='ollama'),models=dict(draft='fixture',review='fixture'),
                    options=dict(context_tokens=49152, extraction_tokens=8192, concept_tokens=512,
                        review_tokens=4096, neighbor_mode='plain', conceptualize=True, repair=False, answer_items=[])))
    for role in autoschema.ROLES:
        parent['units'].append(dict(id=role, stage=role, source_chunk_id=chunk['id'], status='succeeded', error=None,
            messages=business_run.extraction_messages(parent, chunk, role), schema=autoschema.extraction_schema(role),
            reference_map=chunk['source_reference_map'], response=dict(parsed=[], raw_response={'saved':True})))
    parent['units'].append(dict(id='failed-definition', stage='direct_definitions',source_chunk_id=chunk['id'],
        status='failed', error='truncated', response=dict(failure_kind='truncated',raw_response={'saved':True})))
    return parent


@pytest.mark.parametrize('past_deadline', [False, True, 'after_first'])
def test_projection_preserves_source_failures_and_all_concept_kinds(tmp_path, monkeypatch, past_deadline):
    parent = parent_run(); before = deepcopy(parent)
    service = KnowledgeService(tmp_path/'projection.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('parent', json.dumps(parent)))
    calls = []
    def call(service, run, stage, messages, **kwargs):
        assert stage.startswith('concept_') and kwargs['max_tokens']==512
        calls.append(stage)
        if past_deadline == 'after_first':
            run['source_projection']['stop_new_requests_at']='2000-01-01T00:00:00+00:00'
        run['units'].append(dict(id=str(len(calls)),stage=stage,status='succeeded',
            response=dict(text='개념',done=True,done_reason='stop',failure_kind=None)))
        business_run.save(service, run)
        return dict(text='개념')
    monkeypatch.setattr(business_run, 'call', call)
    monkeypatch.setattr(business_run, 'ModelClient', lambda *a: SimpleNamespace())
    try:
        result = service.project_business_source('parent', block_ids=['b0','b1'],
            chunk_ids=[parent['chunks'][0]['id']], reason='원문 업무 범위',
            stop_new_requests_at=(datetime.now(timezone.utc)+timedelta(hours=-1 if past_deadline is True else 1)).isoformat())
        run = finish(service,result['run_id'])
        assert run['status']=='partial',run.get('error')
        assert run['blocks']==parent['blocks'] and run['chunks']==parent['chunks']
        assert run['claims']==parent['claims']
        with service.repository.connect() as db:
            assert service.repository.get(db,'runs','parent')==before
        assert run['source_projection']['blocks_without_selected_extraction_target']==['b1']
        assert run['units'][3]['error']=='truncated' and run['units'][3]['reused_from']['unit_id']=='failed-definition'
        assert run['conceptualization_scope']=='all'
        if past_deadline is True:
            assert calls==[] and run['source_projection']['stop_reason']=='new_request_deadline'
            assert len(run['source_projection']['unattempted_concept_target_ids'])==result['concept_targets']
        elif past_deadline == 'after_first':
            assert len(calls)==len(run['concepts'])==1
            assert run['source_projection']['stop_reason']=='new_request_deadline'
            assert len(run['source_projection']['unattempted_concept_target_ids'])==result['concept_targets']-1
        else:
            assert set(calls)=={'concept_entity','concept_event','concept_relation'}
            assert len(calls)==result['concept_targets'] and not run['source_projection']['unattempted_concept_target_ids']
    finally:
        service.shutdown()


def test_projection_rejects_removed_parent_context_and_changed_prompt(tmp_path):
    parent=parent_run();service=KnowledgeService(tmp_path/'projection.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('parent', json.dumps(parent)))
    kwargs=dict(chunk_ids=[parent['chunks'][0]['id']],reason='업무 범위',stop_new_requests_at='2099-01-01T00:00:00+00:00')
    try:
        with pytest.raises(ValueError,match='부모 문맥'):
            service.project_business_source('parent',block_ids=['b1'],**kwargs)
        parent['units'][0]['messages'][0]['content']+=' changed'
        with service.repository.connect() as db:service.repository.save(db,'runs',parent)
        with pytest.raises(ValueError,match='프롬프트'):
            service.project_business_source('parent',block_ids=['b0','b1'],**kwargs)
        with service.repository.connect() as db:assert db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]==1
    finally:
        service.shutdown()
