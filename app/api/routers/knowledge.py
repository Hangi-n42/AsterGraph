"""Current source, business knowledge and workbench endpoints."""
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError

from app.api.error_utils import error_response, make_request_id, now_iso
from app.core.config import settings
from app.core.exceptions import GenerationError
from app.knowledge.service import KnowledgeConflict, KnowledgeService
from app.knowledge.repository import VersionConflict
from app.knowledge.schemas import RunRequest, SourceRegistration, AvailabilityRequest
from app.knowledge import availability as usage_status
from app.knowledge import business_store, business_use
from app.knowledge.business_models import RequirementInput, BusinessRunRequest, BusinessDecision, BusinessEventEdit, BusinessQuery, ChangeRequest, ConceptRunRequest, HtmlLiteralRowsRequest, BusinessAnswerRecheck, BusinessParticipantResume, SourceRebuildPlanRequest
from app.knowledge.business_models import ConceptPreservationRequest, ConceptMaterializationRequest, QueryCapacityResume, InterpretationEditRequest, StoredRequirementLink


class KnowledgeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            if not settings.KNOWLEDGE_ENABLED:
                return error_response(request_id=make_request_id(), error_code='KNOWLEDGE_DISABLED',
                                      message='회사 지식 기능이 비활성화되어 있습니다.', status_code=503)
            try:
                return await original(request)
            except GenerationError as exc:
                return error_response(request_id=make_request_id(), error_code=exc.code, message=str(exc))
            except KeyError:
                return error_response(request_id=make_request_id(), error_code='NOT_FOUND', message='등록 항목을 찾을 수 없습니다.', status_code=404)
            except VersionConflict as exc:
                return error_response(request_id=make_request_id(), error_code='VERSION_CONFLICT', message=str(exc), status_code=409)
            except KnowledgeConflict as exc:
                return error_response(request_id=make_request_id(), error_code='RUN_BUSY', message=str(exc), status_code=409)
            except (ValueError, ValidationError, RequestValidationError) as exc:
                return error_response(request_id=make_request_id(), error_code='VALIDATION_ERROR', message=str(exc), status_code=422)
        return handler


router = APIRouter(prefix='/knowledge', tags=['knowledge'], route_class=KnowledgeRoute)


class KnowledgeResponse(BaseModel):
    success: bool = True
    request_id: str
    timestamp: str
    data: dict[str, Any]


def result(data):
    return dict(success=True, request_id=make_request_id(), timestamp=now_iso(), data=data)


@lru_cache(maxsize=1)
def get_knowledge_service():
    return KnowledgeService(settings.KNOWLEDGE_DB_PATH)


def shutdown_knowledge_service():
    if get_knowledge_service.cache_info().currsize:
        get_knowledge_service().shutdown()
        get_knowledge_service.cache_clear()


@router.post('/sources', response_model=KnowledgeResponse)
def register(file: UploadFile = File(...), metadata: str = Form(...), service=Depends(get_knowledge_service)):
    try:
        registration = SourceRegistration.model_validate_json(metadata)
        return result(service.register(file.filename, file.file.read(), registration))
    finally:
        file.file.close()


@router.get('/sources', response_model=KnowledgeResponse)
def sources(source_id: str | None = None, service=Depends(get_knowledge_service)):
    return result(service.sources(source_id))


@router.get('/sources/{source_id}/versions/{version_id}', response_model=KnowledgeResponse)
def version(source_id: str, version_id: str, service=Depends(get_knowledge_service)):
    return result(service.version(source_id, version_id))


@router.get('/sources/{source_id}/versions/{version_id}/raw')
def raw(source_id: str, version_id: str, service=Depends(get_knowledge_service)):
    value = service.version(source_id, version_id)['version']
    return FileResponse(service.raw_path(value), filename=value['filename'])


@router.get('/sources/{source_id}/versions/{version_id}/blocks', response_model=KnowledgeResponse)
def blocks(source_id: str, version_id: str, service=Depends(get_knowledge_service)):
    return result(service.blocks(source_id, version_id))


@router.get('/evidence/{evidence_id}', response_model=KnowledgeResponse)
def evidence(evidence_id: str, run_id: str | None = None, service=Depends(get_knowledge_service)):
    if run_id:
        raise ValueError('이전 온톨로지 발견 실행의 문맥 조회는 보존 브랜치에서 지원합니다.')
    return result(service.evidence(evidence_id))


@router.post('/runs', response_model=KnowledgeResponse)
def start(request: RunRequest, service=Depends(get_knowledge_service)):
    return result(service.start(request))


@router.put('/requirements/{requirement_id}', response_model=KnowledgeResponse)
def put_requirement(requirement_id: str, request: RequirementInput, service=Depends(get_knowledge_service)):
    if request.id != requirement_id:
        raise ValueError('요구 ID가 일치하지 않습니다.')
    return result(business_store.put_requirement(service, request))


@router.get('/requirements', response_model=KnowledgeResponse)
def requirements(service=Depends(get_knowledge_service)):
    return result(business_store.requirements(service))


@router.post('/business/runs', response_model=KnowledgeResponse)
def start_business(request: BusinessRunRequest, service=Depends(get_knowledge_service)):
    return result(service.start_business(request))


@router.get('/business/source-concept-preservations/{parent_run_id}', response_model=KnowledgeResponse)
def source_concept_preservation_preview(parent_run_id: str, service=Depends(get_knowledge_service)):
    from app.knowledge.business_concepts import source_preservation
    return result(source_preservation(service, parent_run_id))


@router.post('/business/source-concept-preservations', response_model=KnowledgeResponse)
def source_concept_preservation(request: ConceptPreservationRequest, service=Depends(get_knowledge_service)):
    from app.knowledge.business_concepts import source_preservation
    return result(source_preservation(service, request.parent_run_id, request=request))


@router.get('/business/concept-view-materializations', response_model=KnowledgeResponse)
def concept_materialization_preview(parent_run_id: str, concept_run_id: str, service=Depends(get_knowledge_service)):
    from app.knowledge.business_concepts import materialize_view
    return result(materialize_view(service, parent_run_id, concept_run_id))


@router.post('/business/concept-view-materializations', response_model=KnowledgeResponse)
def concept_materialization(request: ConceptMaterializationRequest, service=Depends(get_knowledge_service)):
    from app.knowledge.business_concepts import materialize_view
    return result(materialize_view(service, request.parent_run_id, request.concept_run_id, request=request))


@router.post('/business/concepts', response_model=KnowledgeResponse)
def business_concepts(request: ConceptRunRequest, service=Depends(get_knowledge_service)):
    from app.knowledge.business_concepts import start
    return result(start(service, request))


@router.post('/business/html-rows', response_model=KnowledgeResponse)
def business_html_rows(request: HtmlLiteralRowsRequest, service=Depends(get_knowledge_service)):
    return result(service.store_business_html_rows(request))


@router.get('/business/runs', response_model=KnowledgeResponse)
def business_runs(service=Depends(get_knowledge_service)):
    import json
    with service.repository.connect() as db:
        items = [dict(id=r['id'], status=r['status'], started_at=r.get('started_at'),
                      questions=[q['question'] for q in r['requirements']])
                 for row in db.execute('SELECT payload FROM runs ORDER BY rowid DESC')
                 if (r := json.loads(row['payload'])).get('kind') == 'business']
    return result(dict(items=items))


@router.get('/business/changes/{changeset_id}', response_model=KnowledgeResponse)
def business_change(changeset_id: str, service=Depends(get_knowledge_service)):
    return result(business_use.change_view(service, changeset_id))


@router.post('/business/runs/{run_id}/publish-candidates', response_model=KnowledgeResponse)
def publish_business_candidates(run_id: str, service=Depends(get_knowledge_service)):
    return result(business_use.publish_terminal_candidates(service, run_id))


@router.post('/business/changes/{changeset_id}/decisions', response_model=KnowledgeResponse)
def business_decision(changeset_id: str, request: BusinessDecision, service=Depends(get_knowledge_service)):
    return result(business_use.decide(service, changeset_id, request))


@router.post('/business/changes/{changeset_id}/edits', response_model=KnowledgeResponse)
def business_edit(changeset_id: str, request: BusinessEventEdit, service=Depends(get_knowledge_service)):
    from app.knowledge.business_edit import start
    return result(start(service, changeset_id, request))


@router.post('/business/changes/{changeset_id}/interpretation-edits', response_model=KnowledgeResponse)
def business_interpretation_edit(changeset_id: str, request: InterpretationEditRequest, service=Depends(get_knowledge_service)):
    from app.knowledge.interpretation_edit import start
    return result(start(service, changeset_id, request))


@router.get('/business/snapshots', response_model=KnowledgeResponse)
def business_snapshots(service=Depends(get_knowledge_service)):
    return result(business_use.snapshots(service))


@router.post('/business/search', response_model=KnowledgeResponse)
def business_search(request: BusinessQuery, service=Depends(get_knowledge_service)):
    return result(business_use.query(service, request))


@router.post('/business/runs/{run_id}/capacity-resumes', response_model=KnowledgeResponse)
def business_capacity_resume(run_id: str, request: QueryCapacityResume, service=Depends(get_knowledge_service)):
    from app.knowledge.query_capacity_resume import start
    return result(start(service, run_id, request))


@router.post('/business/runs/{run_id}/requirement-links', response_model=KnowledgeResponse)
def business_requirement_link(run_id: str, request: StoredRequirementLink, service=Depends(get_knowledge_service)):
    return result(business_store.link_stored_requirement(service, run_id, request))


@router.post('/business/runs/{run_id}/answer-rechecks', response_model=KnowledgeResponse)
def business_answer_recheck(run_id: str, request: BusinessAnswerRecheck, service=Depends(get_knowledge_service)):
    from app.knowledge.business_feedback import start
    return result(start(service, run_id, request))


@router.post('/business/runs/{run_id}/participant-resumptions', response_model=KnowledgeResponse)
def business_participant_resume(run_id: str, request: BusinessParticipantResume, service=Depends(get_knowledge_service)):
    from app.knowledge.business_participant_resume import start
    return result(start(service, run_id, request.repair_id))


@router.post('/business/changes', response_model=KnowledgeResponse)
def business_version_change(request: ChangeRequest, service=Depends(get_knowledge_service)):
    from app.knowledge.business_changes import analyze
    return result(analyze(service, request))


@router.post('/business/source-rebuild-plans', response_model=KnowledgeResponse)
def business_source_rebuild_plan(request: SourceRebuildPlanRequest, service=Depends(get_knowledge_service)):
    from app.knowledge.business_rebuild import plan
    return result(plan(service, request))


@router.get('/runs/{run_id}', response_model=KnowledgeResponse)
def run(run_id: str, service=Depends(get_knowledge_service)):
    return result(service.run(run_id))


@router.post('/runs/{run_id}/cancel', response_model=KnowledgeResponse)
def cancel(run_id: str, service=Depends(get_knowledge_service)):
    return result(service.cancel(run_id))


@router.get('/availability', response_model=KnowledgeResponse)
def availability(type: str, id: str, service=Depends(get_knowledge_service)):
    return result(usage_status.availability(service, type, id))


@router.post('/availability', response_model=KnowledgeResponse)
def set_availability(request: AvailabilityRequest, service=Depends(get_knowledge_service)):
    return result(usage_status.set_availability(service, request))


@router.get('/workbench/scopes', response_model=KnowledgeResponse)
def workbench_scopes(service=Depends(get_knowledge_service)):
    from app.knowledge import workbench
    return result(workbench.catalog(service))


@router.get('/workbench/review', response_model=KnowledgeResponse)
def workbench_review(run_id: str, service=Depends(get_knowledge_service)):
    from app.knowledge import workbench
    return result(workbench.review_status(service, run_id))


@router.get('/workbench/usage', response_model=KnowledgeResponse)
def workbench_usage(kind: str, scope_id: str, service=Depends(get_knowledge_service)):
    from app.knowledge import workbench
    return result(workbench.usage(service, kind, scope_id))


@router.get('/workbench/answers', response_model=KnowledgeResponse)
def workbench_answers(kind: str, scope_id: str, answer_id: str | None = None, service=Depends(get_knowledge_service)):
    from app.knowledge import workbench
    return result(workbench.answers(service, kind, scope_id, answer_id))


@router.get('/workbench/changes', response_model=KnowledgeResponse)
def workbench_changes(kind: str, scope_id: str, service=Depends(get_knowledge_service)):
    from app.knowledge import workbench
    return result(workbench.changes(service, kind, scope_id))


@router.get('/workbench/explore', response_model=KnowledgeResponse)
def workbench_explore(kind: str, scope_id: str, q: str = '', selected_id: str | None = None,
                      item_kind: str = 'all', offset: int = 0, limit: int = 40,
                      relation_type: str = '', direction: str = 'both', source_id: str = '',
                      review_state: str = '', depth: int = 1, graph_root: str = '',
                      service=Depends(get_knowledge_service)):
    from app.knowledge import workbench
    return result(workbench.explore(service, kind, scope_id, q=q, selected_id=selected_id,
                                   item_kind=item_kind, offset=offset, limit=limit, relation_type=relation_type,
                                   direction=direction, source_id=source_id, review_state=review_state, depth=depth, graph_root=graph_root))
