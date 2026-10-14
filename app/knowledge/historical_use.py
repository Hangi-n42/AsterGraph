"""Common source-answer contract for retrieved historical consultation records."""
from copy import deepcopy
from time import monotonic
from typing import Literal
from uuid import uuid4

from pydantic import Field, create_model

from . import business_run
from .business_use import SourceAnswer
from .service import utcnow


def answer(service, question, context, recipe, identity, instruction, *, source_cap=16384):
    started = monotonic()
    selected = {row['id'] for row in context}
    if len(selected) != len(context):
        raise ValueError('Repeated historical context IDs')
    run = dict(id=uuid4().hex, kind='business_query', status='running', units=[],
        recipe=deepcopy(recipe), model_identity=deepcopy(identity),
        metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0),
        started_at=utcnow(), finished_at=None, query=dict(question=question, choices=[]),
        answer_basis='past_consultation_records_not_official_rules',
        answer_contract='source-unique-provided-citations-lossless-dedup-v3',
        required_context_ids=[], answer_items=[])
    with service.lock, service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], business_run.encode(run)))
    size = (len(business_run.encode(dict(context=context, source_context=[])).encode()) + 1) // 2
    run['source_context_budget'] = dict(limit=source_cap, estimate_tokens=size,
        method='utf8_bytes/2', exact=False, within_limit=size <= source_cap)
    if not context or size > source_cap:
        status = 'unverified' if not context else 'input_capacity'
        run.update(status='partial' if not context else 'failed', answer=None,
            answer_status=status, finished_at=utcnow(), provided_ids=sorted(selected))
        business_run.save(service, run)
        return dict(run_id=run['id'], status=status, answer=None, qa_model_called=False)
    references = {row['id']: f'q{i+1}' for i, row in enumerate(context)}
    response_type = create_model('ContextAnswer', __base__=SourceAnswer,
        citations=(list[Literal[tuple(references)]], Field(max_length=len(context),
            json_schema_extra={'uniqueItems': True})))
    output = business_run.json_call(service, run, 'business_qa', instruction,
        dict(question=question, choices=[], context=context, source_context=[],
            source_versions={}, source_evidence={}, requirement_limitations=[]),
        response_type, reference_map=references)
    raw_ids = ((run['units'][-1].get('response') or {}).get('parsed') or {}).get('citations', [])
    if output and isinstance(raw_ids, list) and all(isinstance(v, str) for v in raw_ids):
        run['citation_normalization'] = dict(kind='stable_dedup_only',
            removed_duplicates=len(raw_ids)-len(set(raw_ids)))
    status = 'answered'
    if not output or not set(output['citations']) <= selected or (output['answer'] and not output['citations']):
        status = 'unverified'
    run.update(status='succeeded' if status == 'answered' else 'partial',
        finished_at=utcnow(), answer=output, answer_status=status, provided_ids=sorted(selected))
    run['metrics']['elapsed_s'] = monotonic() - started
    business_run.save(service, run)
    return dict(run_id=run['id'], status=status, answer=output,
        answer_basis=run['answer_basis'], source_context_budget=run['source_context_budget'])
