"""Explicit reference-only corrections of stored answers; no generation or approval."""
from copy import deepcopy
import json
from time import monotonic

from . import answer_links, autoschema, business_changes, business_run, business_use, concept_work
from .service import KnowledgeConflict, encode, utcnow


def correct(service, parent_run_id, *, expected_parent_fingerprint, actor, reason, citations, links):
    """Local operator entry point. Keep the producer/raw and all answer/source text fixed."""
    started = monotonic()
    if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
        raise ValueError('정정 주체와 이유가 필요합니다.')
    with service.lock, service.repository.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if service.closed or service.repository.has_active_runs(db):
            raise KnowledgeConflict('기존 실행 종료 후 정정하세요.')
        parent = service.repository.get(db, 'runs', parent_run_id)
        if concept_work.digest(parent) != expected_parent_fingerprint:
            raise KnowledgeConflict('저장 답변 버전이 바뀌었습니다. 다시 확인하세요.')
        if (parent.get('kind') != 'business_query' or parent.get('answer_status') != 'answered'
                or parent.get('status') != 'succeeded' or parent.get('query', {}).get('answer_mode') != 'synthesis'
                or parent.get('query', {}).get('source_citation_contract') != answer_links.CONTRACT
                or parent.get('answer_links', {}).get('status') == 'needs_review'
                or parent.get('answer_source_citations', {}).get('status') != 'recorded'):
            raise ValueError('현재 사용 가능한 저장 synthesis 답변과 정확한 원문 인용이 필요합니다.')
        answer = deepcopy(parent['answer'])
        if (not isinstance(citations, list) or any(not isinstance(c, str) for c in citations)
                or not set(citations) <= set(answer['citations']) or not citations):
            raise ValueError('원래 답변의 주장 참조만 유지·해제할 수 있습니다.')
        if not isinstance(links, list):
            raise ValueError('정정 후 연결 목록이 필요합니다.')
        answer['citations'] = deepcopy(citations)
        business_use.Answer.model_validate(answer)
        snapshot = service.repository.get(db, 'snapshots', parent['snapshot_id'])
        if (parent['query'].get('snapshot_id') != snapshot['id']
                or set(parent['input_version_ids']) != set(snapshot['source_versions'])):
            raise KnowledgeConflict('당시 원문·사용 버전이 일치하지 않습니다.')
        source = service.repository.get(db, 'runs', snapshot['run_id'])
        if (business_use.restricted_sources(db, parent['input_version_ids'])
                or business_changes.snapshot_invalidations(service, db, snapshot, source)):
            raise KnowledgeConflict('원문 사용 제한 또는 버전 변경 후에는 정정할 수 없습니다.')
        requirement_ids = set(parent['query'].get('requirement_ids', []))
        if not requirement_ids <= {r['id'] for r in snapshot['requirements']}:
            raise KnowledgeConflict('당시 선택 요구가 사용 버전에 없습니다.')
        for requirement in snapshot['requirements']:
            if requirement_ids and requirement['id'] not in requirement_ids:
                continue
            current = service.repository.get(db, 'requirements', requirement['id'])
            if current['revision'] != requirement['revision'] or current['status'] == 'needs_review':
                raise KnowledgeConflict('요구 변경 이후 재검토가 필요합니다.')
        producers = [u for u in parent['units'] if u.get('stage') == 'business_qa']
        if len(producers) != 1:
            raise ValueError('유일한 원래 QA 입력이 필요합니다.')
        messages = [m for m in producers[0]['messages'] if m.get('role') == 'user']
        if len(messages) != 1:
            raise ValueError('원래 QA 입력이 모호합니다.')
        provided = json.loads(messages[0]['content'])
        reverse = {v:k for k,v in (producers[0].get('reference_map') or {}).items()}
        claims = {c['id']:c for c in snapshot['claims']}
        input_ids = []
        for row in provided['context']:
            cid = reverse.get(row['id'], row['id'])
            claim = claims.get(cid)
            if (not claim or claim.get('review_status') != 'accepted'
                    or row['text'] != encode(business_run.compact_claim(claim))
                    or reverse.get(row['file_id'], row['file_id']) not in claim['source_version_ids']):
                raise KnowledgeConflict('생성 당시 주장본문·원문 버전과 현재 저장 버전이 다릅니다.')
            input_ids.append(cid)
        if len(input_ids) != len(set(input_ids)) or set(input_ids) != set(parent['provided_ids']):
            raise KnowledgeConflict('당시 제공 주장 범위가 일치하지 않습니다.')
        views = deepcopy(provided['source_evidence'])
        for view in views:
            for key in ('id', 'source_version_id', 'parse_run_id'):
                view[key] = reverse.get(view[key], view[key])
            ref = dict(block_id=view['id'], source_version_id=view['source_version_id'],
                parse_run_id=view['parse_run_id'], start_char=view['span'][0], end_char=view['span'][1], quote=view['text'])
            exact = business_run.exact_evidence([ref], snapshot['blocks'])[0]
            if any(exact[k] != ref[k] for k in ref):
                raise KnowledgeConflict('생성 당시 제공 원문 범위가 현재 저장 버전과 다릅니다.')
        quotes = parent['answer_source_citations']['citations']
        original_links = parent['answer_links']
        returned = []
        for qid in original_links.get('quote_declarations', []):
            lookup = original_links.get('quote_lookup', {}).get(qid, {})
            if lookup.get('status') != 'resolved':
                raise ValueError('미확정 원문 주소·ID를 이 정정으로 대체할 수 없습니다.')
            quote = quotes[lookup['citation_index']]
            if quote['address_status'] != 'matched' or qid not in quote.get('quote_ids', []):
                raise ValueError('원래 원문 인용의 고유한 주소가 필요합니다.')
            returned.append(dict(evidence_ref=quote['block_id'], quote=quote['quote'], quote_id=qid))
        answer.update(source_citations=returned, answer_links=deepcopy(links))
        output, metadata = answer_links.restore(answer, {})
        output['_answer_link_metadata'] = metadata
        child = deepcopy(parent)
        business_use.record_answer_source_citations(child, output, views, snapshot['blocks'])
        answer_links.record(child, output, parent['provided_ids'])
        if (child['answer_source_citations'] != parent['answer_source_citations']
                or child['answer_links']['status'] != 'recorded'):
            raise ValueError('원문 주소 또는 정정 연결이 유효하지 않습니다.')
        before_links = [v['declaration'] for v in original_links['links']]
        if citations == parent['answer']['citations'] and links == before_links:
            raise ValueError('변경한 참조가 없습니다.')
        request = dict(parent_run_id=parent_run_id, parent_fingerprint=expected_parent_fingerprint,
                       actor=actor.strip(), reason=reason.strip(), citations=citations, links=links)
        identifier = autoschema.identifier('answer_review', request)
        if db.execute('SELECT id FROM runs WHERE id=?', (identifier,)).fetchone():
            return service.repository.get(db, 'runs', identifier)
        producer = parent.get('answer_review') or {}
        receipt = dict(request=deepcopy(request), actor=request['actor'], reason=request['reason'],
            parent_run_id=parent_run_id, created_at=utcnow(), origin='explicit_reference_correction',
            authority='operator_instruction_not_semantic_or_use_approval', automatic_correction=False,
            human_approval=False, semantic_support='not_assessed', producer_units_inherited=True,
            producer_run_id=producer.get('producer_run_id', parent_run_id),
            producer_metrics=deepcopy(producer.get('producer_metrics', parent['metrics'])),
            changes=[dict(field='citations', before=deepcopy(parent['answer']['citations']), after=deepcopy(citations)),
                     dict(field='answer_links', before=deepcopy(before_links), after=deepcopy(links))])
        child['answer_links']['relation'] = 'reviewer_corrected'
        child.update(id=identifier, parent_run_id=parent_run_id, answer=output, answer_review=receipt,
            started_at=receipt['created_at'], finished_at=receipt['created_at'],
            metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=monotonic()-started),
            execution_boundary=dict(answer_contract=parent['answer_contract'],
                current_operation='explicit_answer_reference_correction',
                generation_parent_run_id=receipt['producer_run_id'], new_model_calls=0, approval_changed=False))
        db.execute('INSERT INTO runs VALUES(?,?)', (identifier, encode(child)))
        return child
