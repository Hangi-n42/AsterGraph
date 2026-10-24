"""Resume a saved mandatory-input capacity failure without repeating retrieval."""
from copy import deepcopy
import json
from time import monotonic

from . import autoschema, business_run, business_use, concept_work
from .business_models import BusinessQuery
from .service import KnowledgeConflict, encode, utcnow


def start(service, parent_id, request):
    started = monotonic()
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        parent = service.repository.get(db, 'runs', parent_id)
        fingerprint = concept_work.digest(parent)
        identifier = autoschema.identifier('query_capacity_resume', [fingerprint, request.model_dump()])
        existing = db.execute('SELECT payload FROM runs WHERE id=?', (identifier,)).fetchone()
        if existing:
            return dict(run_id=identifier, status='already_recorded', duplicate_request=True)
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('다른 실행이 종료된 뒤 답변을 이어가세요.')
        if fingerprint != request.expected_parent_fingerprint:
            raise KnowledgeConflict('검토한 검색 실패 기록이 변경됐습니다.')
        assembly = parent.get('evidence_assembly') or {}
        query = BusinessQuery.model_validate(parent['query'])
        if (parent.get('kind') != 'business_query' or parent['status'] != 'failed'
                or parent.get('error') != 'mandatory_capacity' or parent.get('context_mode') != 'graph'
                or assembly.get('failure_kind') != 'mandatory_capacity' or not query.evidence_union
                or query.answer_mode != 'synthesis' or query.source_run_id or query.requirement_ids):
            raise ValueError('저장된 그래프 종합 질문의 필수 입력 용량 실패만 이어갈 수 있습니다.')
        if request.context_tokens <= parent['recipe']['options']['context_tokens']:
            raise ValueError('이전보다 큰 QA 문맥 한도를 명시하세요.')
        snapshot = service.repository.get(db, 'snapshots', query.snapshot_id)
        if concept_work.digest(snapshot) != request.expected_snapshot_fingerprint:
            raise KnowledgeConflict('사용 지식 버전이 변경됐습니다.')
        original = service.repository.get(db, 'runs', snapshot['run_id'])
        from .business_changes import snapshot_invalidations
        corrections = [event for row in db.execute('SELECT payload FROM snapshot_events')
                       if (event := json.loads(row['payload'])).get('snapshot_id') == query.snapshot_id
                       and event.get('event') == 'business_correction']
        if (corrections or snapshot_invalidations(service, db, snapshot, original)
                or business_use.restricted_sources(db, snapshot['source_versions'])):
            raise KnowledgeConflict('원문 또는 근거의 변경·사용 제한을 먼저 검토하세요.')
        requirements = [service.repository.get(db, 'requirements', r['id']) for r in snapshot['requirements']]
        if any(r['revision'] != saved['revision'] or r['status'] == 'needs_review'
               for r, saved in zip(requirements, snapshot['requirements'])):
            raise KnowledgeConflict('업무 요구 변경 이후 재검수가 필요합니다.')
        units = parent['units']
        if (not units or any(u['stage'] != 'graph_retrieval_filter' or u['status'] != 'succeeded'
                or u.get('error') or not concept_work.complete(u)
                or u.get('requested_limits') != u.get('executed_limits')
                or u['executed_limits']['context_tokens'] != parent['recipe']['options']['context_tokens']
                for u in units)):
            raise ValueError('완료된 관계 선택 결과가 필요합니다.')
        rejected = assembly['rejected_input']
        hits = rejected['hits']
        if [h['block_id'] for h in hits] != assembly['mandatory_claim_ids']:
            raise ValueError('저장된 필수 근거 순서가 다릅니다.')
        candidates = [dict(id=c['id'], text=encode(business_run.compact_claim(c)),
                           file_id=c['source_version_ids'][0], source_group=c['source_version_ids'][0])
                      for c in snapshot['claims']]
        baseline = hits[:len(assembly['baseline_claim_ids'])]
        if [h['block_id'] for h in baseline] != assembly['baseline_claim_ids']:
            raise ValueError('저장된 기본 근거 순서가 다릅니다.')
        base_state = business_use.graph_qa_input(snapshot, original, parent['recipe'], query, candidates, baseline, [])[0]
        state, body, schema, references = business_use.graph_qa_input(
            snapshot, original, parent['recipe'], query, candidates, hits, base_state['source_reference_order'])
        packet = business_run.json_request(parent, 'business_qa', business_use.SYNTHESIS_PROMPT
            + business_use.REVIEWED_MEANINGS_PROMPT + business_use.source_citations_instruction(query.source_citation_contract),
            body, schema, reference_map=references)
        if (packet != rejected['request'] or state != rejected['state']
                or concept_work.digest(packet) != request.expected_packet_fingerprint):
            raise KnowledgeConflict('현재 제품이 복원한 필수 입력이 저장된 요청과 다릅니다.')
        identity = business_run.ModelClient(parent['recipe']['generation']).identities(
            {'review': parent['recipe']['models']['review']}, {'review': request.context_tokens})
        if identity['review'] != parent['model_identity']['review']:
            raise KnowledgeConflict('저장된 답변 모델의 식별자가 변경됐습니다.')
        run = deepcopy(parent)
        run.update(id=identifier, parent_run_id=parent_id, status='running', units=[],
                   started_at=utcnow(), finished_at=None, metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0),
                   preserved_retrieval_units=deepcopy(units), **state)
        for key in ('error', 'answer', 'answer_status', 'reusable_units', 'parent_recipe', 'parent_model_identity'):
            run.pop(key, None)
        run['recipe']['options']['qa_context_tokens'] = request.context_tokens
        run['capacity_resume'] = dict(parent_run_id=parent_id, parent_fingerprint=fingerprint,
            snapshot_fingerprint=request.expected_snapshot_fingerprint, packet_fingerprint=concept_work.digest(packet),
            mandatory_claim_ids=deepcopy(assembly['mandatory_claim_ids']), optional_additions=0,
            selector_context_tokens=parent['recipe']['options']['context_tokens'],
            QA_context_tokens=request.context_tokens, retrieval_repeated=False, request=request.model_dump())
        run['execution_boundary']['capacity_resume'] = deepcopy(run['capacity_resume'])
        run['retrieval_concept_hints'] = {}
        db.execute('INSERT INTO runs VALUES(?,?)', (identifier, encode(run)))
    limitations = [dict(requirement_id=rid, status=a['status'], gaps=(a.get('source') or {}).get('gaps', []))
                   for rid, a in snapshot['assessments'].items() if a['status'] != 'satisfied']
    output = business_run.json_call(service, run, 'business_qa', business_use.SYNTHESIS_PROMPT
        + business_use.REVIEWED_MEANINGS_PROMPT + business_use.source_citations_instruction(query.source_citation_contract),
        body, schema, reference_map=references)
    return business_use.finish_query(service, run, query, snapshot, requirements, output, hits,
                                    body['source_evidence'], limitations, started)
