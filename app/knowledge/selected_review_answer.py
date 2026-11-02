"""Bind diagnostic final review to unchanged claims in an existing use snapshot."""
from copy import deepcopy

from . import autoschema, business_run, business_review, business_selected_review as final
from . import required_unit_selection as selection, question_inspection
from .source_meanings import remap

CONTRACT = 'selected-review-existing-snapshot-answer-v1-experimental'
INSTRUCTION = ('\nselected_requirement_review는 동일 질문·원문·저장 표현을 대조한 이전 모델 검수다. '
    '새 원문 사실이나 사용 승인이 아니며 오류 가능성이 있다. 검색된 context와 source_evidence로 다시 대조하여 새 답변을 작성한다. '
    '확인된 속성의 일치·차이와 자료만으로 확정하지 못하는 판단을 구분한다. '
    '검수 문장을 원문으로 인용하지 말고 실제 제공 원문을 인용한다. 다른 버전이나 다른 속성의 결론으로 확대하지 않는다.')


def bind(run, snapshot, request):
    spec = request.selected_review
    records = [r for r in run.get('selected_business_reviews', []) if r['review_unit_id'] == spec.unit_id]
    if len(records) != 1:
        raise ValueError('selected_review_result_unavailable')
    saved = records[0]
    unit = next((u for u in run['units'] if business_review.response_unit_id(dict(units=[u])) == spec.unit_id), None)
    if not unit or unit.get('status') != 'succeeded' or not (unit.get('response') or {}).get('parsed'):
        raise ValueError('selected_review_native_response_unavailable')
    items = saved['items']
    ids = {i['item_id'] for i in items}
    requirements = [r for r in run['requirements'] if r['question'] == request.question
        and {i['id'] for i in question_inspection.public_items(run, r)} == ids]
    if len(requirements) != 1:
        raise ValueError('selected_review_question_changed')
    requirement = requirements[0]
    published = next((r for r in snapshot['requirements'] if r['id'] == requirement['id']), None)
    fields = ('id', 'revision', 'question', 'criterion', 'target', 'situation', 'period', 'source_ids')
    if not published or any(published.get(k) != requirement.get(k) for k in fields):
        raise ValueError('selected_review_requirement_changed')
    receipt = run['selected_request_source']['application_history'][-1]
    scope = selection.bound_targets(run['selected_request_source'], receipt['source_property_catalog'])
    by_id = {b['id']: b for b in run['blocks']}
    blocks = [by_id[k] for k in run['request_reference_review']['block_ids']]
    context = final.packet(run, requirement, scope, blocks, contract=saved['contract'])
    expected = business_run.json_request(run, 'requirement_representation', final.instruction(saved['contract']), context, final.output_type(context))
    if any(unit.get(k) != expected[k] for k in ('messages', 'schema', 'reference_map')):
        raise ValueError('selected_review_request_changed')
    raw = remap(unit['response']['parsed'], {v: k for k, v in (unit.get('reference_map') or {}).items()})
    consumed = final.consume(raw, context)
    if any(saved.get(k) != v for k, v in consumed.items()) or consumed['overall'] != 'sufficient_in_scope':
        raise ValueError('selected_review_result_changed_or_unresolved')
    claims = {c['id']: c for c in run['claims']}
    accepted = {c['id']: c for c in snapshot['claims']}
    published_blocks = {b['id']: b for b in snapshot['blocks']}
    required = sorted({b['claim_id'] for o in context['source_observations'] for b in o['expression_bindings']})
    for cid in required:
        claim = accepted.get(cid)
        # Approval adds review_status; every substantive stored field must still match.
        if (not claim or claim.get('review_status') != 'accepted'
                or {k:v for k,v in claim.items() if k != 'review_status'} !=
                   {k:v for k,v in claims[cid].items() if k != 'review_status'}):
            raise ValueError('selected_review_snapshot_claim_changed: ' + cid)
    for block in blocks:
        version = block['source_version_id']
        if (version not in snapshot['source_versions'] or published_blocks.get(block['id']) != block
                or snapshot['source_versions'][version].get('sha256') != run['sources'][version].get('sha256')):
            raise ValueError('selected_review_snapshot_source_changed: ' + version)
    return dict(contract=CONTRACT, review_run_id=run['id'], final_review_unit_id=spec.unit_id,
        source_review_unit_id=saved['source_review_unit_id'], snapshot_id=snapshot['id'],
        question=request.question, public_answer_items=deepcopy(context['public_answer_items']),
        findings=deepcopy(raw['items']), source_observations=deepcopy(context['source_observations']),
        required_claim_ids=required,
        snapshot_claim_versions={cid: autoschema.identifier('claim', accepted[cid]) for cid in required},
        snapshot_fingerprint=autoschema.identifier('snapshot', snapshot),
        review_fingerprint=autoschema.identifier('selected_review', saved),
        authority='diagnostic_model_review_not_source_fact_or_use_approval')


def load(service, db, request, snapshot):
    if request.selected_review is None:
        return None
    return bind(service.repository.get(db, 'runs', request.selected_review.run_id), snapshot, request)


def review_scope_refs(context):
    if context is None:
        return {}
    return {f'rv_{item_id}_{index + 1}': dict(item_id=item_id, finding_index=index)
        for item_id, item in context['findings'].items()
        for index, finding in enumerate(item['findings']) if finding['status'] == 'undetermined'}


def review_scopes(context, selected):
    """Expose the recorded premises of a bounded judgment, never certify absence."""
    if not context or not set(context['required_claim_ids']) <= set(selected):
        return {}
    observations = {o['target_id']: o for o in context['source_observations']}
    scopes = {}
    for ref, address in review_scope_refs(context).items():
        finding = context['findings'][address['item_id']]['findings'][address['finding_index']]
        ids = finding['source_result_ids']
        if not ids or any(i not in observations for i in ids):
            continue
        scopes[ref] = dict(**address, **deepcopy(finding),
            **{k: context[k] for k in ('snapshot_id', 'review_run_id', 'final_review_unit_id',
                'source_review_unit_id', 'review_fingerprint', 'snapshot_fingerprint')},
            scope='selected_source_observations_only', semantic_support='not_assessed',
            premises=[{k: deepcopy(observations[i][k]) for k in ('target_id', 'represented_content',
                'evidence', 'expression_bindings', 'condition_references', 'condition_state')} for i in ids])
    return scopes


def answer_context(context, selected, citation_contract=None):
    if context is None:
        return {}
    if not set(context['required_claim_ids']) <= set(selected):
        raise ValueError('selected_review_required_claim_not_delivered')
    from .answer_links import REVIEW_CONTRACT
    return dict(selected_requirement_review=deepcopy(context),
        **(dict(review_scope_refs=review_scope_refs(context)) if citation_contract == REVIEW_CONTRACT else {}))
