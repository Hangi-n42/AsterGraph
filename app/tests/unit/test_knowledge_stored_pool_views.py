"""Stored candidates retain their original extraction context in both product paths."""
from copy import deepcopy
from app.knowledge import autoschema,business_run
from app.knowledge.business_models import BusinessRunRequest
from app.tests.unit.test_knowledge_business import finish
from app.tests.unit.test_knowledge_business_checkpoint import completed_source


def test_reassess_and_resume_keep_original_capacity_views_without_generation(completed_source):
    service,parent,calls=completed_source
    view=deepcopy(parent['chunks'][0]);view['id']='saved-repair-view'
    parent['capacity_repair_views']={view['id']:view}
    parent['claims']=[autoschema.graph_record(view,'entity_relation',dict(Head='기관',Relation='접수',Tail='신청'),0)]
    parent['graph']=autoschema.graph(parent['claims'])
    with service.repository.connect() as db:service.repository.save(db,'runs',parent)
    before=deepcopy(parent)
    child=finish(service,service.start_business(BusinessRunRequest(source_version_ids=parent['input_version_ids'],
        reassess_run_id=parent['id'],repair=False,conceptualize=False))['run_id'])
    continued=finish(service,service.start_business(BusinessRunRequest(source_version_ids=parent['input_version_ids'],
        resume_run_id=child['id'],repair=False,conceptualize=False))['run_id'])
    for result in [child,continued]:
        assert result['capacity_repair_views']==parent['capacity_repair_views']
        assert result['claims']==parent['claims']
        assert business_run.source_chunks(result)[view['id']]==view
        assert 'source_checkpoint' not in result
    assert calls==[]
    child['capacity_repair_views'][view['id']]['blocks'][0]['text']='only this in-memory copy'
    assert parent==before
