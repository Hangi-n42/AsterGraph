"""Preserve a completed extraction subset without re-chunking or retrying failures."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from . import autoschema, business_concepts, business_run
from .service import KnowledgeConflict, encode, utcnow


def start(service, parent_run_id, *, block_ids, chunk_ids, reason, stop_new_requests_at):
    deadline = datetime.fromisoformat(stop_new_requests_at)
    if not reason.strip() or deadline.tzinfo is None:
        raise ValueError('원문 선택 이유와 시간대가 있는 요청 중단 시각이 필요합니다.')
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('기존 실행 종료 후 완료 추출 풀을 연결하세요.')
        parent = service.repository.get(db, 'runs', parent_run_id)
        if parent.get('kind') != 'business' or parent.get('requirements') or parent.get('assessments'):
            raise ValueError('요구 평가가 없는 종료된 원문 추출 실행만 연결할 수 있습니다.')
        if parent['recipe']['version'] != autoschema.VERSION or parent['recipe']['scope_contract'] != autoschema.SCOPE_CONTRACT:
            raise ValueError('현재 추출 계약과 부모 실행이 다릅니다.')
        selected_blocks, selected_chunks = set(block_ids), set(chunk_ids)
        if (not selected_blocks or not selected_chunks or len(selected_blocks) != len(block_ids)
                or len(selected_chunks) != len(chunk_ids)
                or not selected_blocks <= {b['id'] for b in parent['blocks']}
                or not selected_chunks <= {c['id'] for c in parent['chunks']}):
            raise ValueError('부모 실행의 고유 원문 블록과 추출 단위를 선택하세요.')
        chunks = deepcopy([c for c in parent['chunks'] if c['id'] in selected_chunks])
        if any(b['id'] not in selected_blocks for c in chunks for b in c['blocks']):
            raise ValueError('기존 추출 단위의 대상과 필수 부모 문맥을 원문 풀에 모두 보존하세요.')
        units = deepcopy([u for u in parent['units'] if u.get('source_chunk_id') in selected_chunks])
        if any(u['status'] in {'queued', 'running'} for u in units):
            raise ValueError('진행 중 응답은 재사용할 수 없습니다.')
        for unit in units:
            chunk = next(c for c in chunks if c['id'] == unit['source_chunk_id'])
            if unit['stage'] in autoschema.ROLES and (
                    unit['messages'] != business_run.extraction_messages(parent, chunk, unit['stage'])
                    or unit['schema'] != autoschema.extraction_schema(unit['stage'])
                    or unit['reference_map'] != chunk['source_reference_map']):
                raise ValueError('원문·프롬프트·출력 계약이 기존 응답과 다릅니다.')
            unit.update(reused_from=dict(run_id=parent_run_id, unit_id=unit['id'], original_status=unit['status']),
                        id=uuid4().hex, materialized_at=utcnow(), reuse_reason='preserved_completed_source_record; not_a_new_model_call')
        run = deepcopy(parent)
        run.update(id=uuid4().hex, status='queued', parent_run_id=parent_run_id, units=units,
            blocks=deepcopy([b for b in parent['blocks'] if b['id'] in selected_blocks]), chunks=chunks,
            claims=deepcopy([c for c in parent['claims'] if c['chunk_id'] in selected_chunks]),
            concepts=[], assessments=[], repairs=[], analysis_units=[], inspection_units=[], reusable_units=[],
            reusable_chunk_ids=[], started_at=None, finished_at=None,
            metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0,
                         preserved_provider_responses=sum(bool((u.get('response') or {}).get('raw_response')) for u in units)))
        for key in ('changeset_id', 'error', 'counts', 'extraction_complete', 'parent_recipe', 'parent_model_identity'):
            run.pop(key, None)
        run['extraction_rejections'] = deepcopy([r for r in parent.get('extraction_rejections', [])
                                                 if r['chunk_id'] in selected_chunks])
        run['recipe']['options'].update(block_ids=list(block_ids), selection_reason=reason, conceptualize=True, repair=False)
        run['graph'] = autoschema.graph(run['claims'], run['blocks'])
        targets = [item['target'] for item in business_concepts.prepare(
            run, autoschema.concept_targets(run['graph']), run['recipe']['options']['neighbor_mode'], service=service)]
        target_block_ids = {b['id'] for c in chunks for b in c['blocks'] if not b.get('context_only')}
        run['stored_pool'] = dict(parent_run_id=parent_run_id, source_hash=autoschema.identifier('source', run['blocks']),
            claims_hash=autoschema.identifier('claims', run['claims']), graph_hash=autoschema.identifier('graph', run['graph']),
            construction_recipe=deepcopy(parent['recipe']), construction_model_identity=deepcopy(parent['model_identity']))
        run['source_projection'] = dict(reason=reason, parent_run_id=parent_run_id,
            extraction_chunk_ids=[c['id'] for c in chunks], source_block_ids=[b['id'] for b in run['blocks']],
            blocks_without_selected_extraction_target=[b['id'] for b in run['blocks'] if b['id'] not in target_block_ids],
            preserved_failures=[u['reused_from'] for u in units if u['status'] != 'succeeded'],
            unattempted_extraction=[dict(chunk_id=c['id'], stage=stage) for c in chunks
                for stage in [*autoschema.ROLES, 'direct_definitions']
                if not any(u.get('source_chunk_id') == c['id'] and u['stage'] == stage for u in units)],
            planned_concept_target_ids=[t['id'] for t in targets], reused_concepts=0,
            stop_new_requests_at=deadline.astimezone(timezone.utc).isoformat(),
            approved=False, questions_used=False, semantic_repairs=False)
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    service.executor.submit(business_run.execute, service, run['id'])
    return dict(run_id=run['id'], status='queued', concept_targets=len(targets))
