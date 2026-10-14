import json

import pytest

from app.knowledge import business_run, historical_use
from app.knowledge.service import KnowledgeService


RECIPE = dict(generation={'provider': 'ollama'}, models={'review': 'fixed-review'},
    options=dict(review_tokens=4096, context_tokens=49152, think=False, timeout=1800))
CONTEXT = [dict(id='past-MSS-001', text='과거 상담 원문', source_kind='past_MSS_consultation')]


@pytest.mark.parametrize('answer,citations,status', [
    ('원문 답변', ['q1'], 'answered'),
    ('원문 답변', ['q1', 'q1'], 'answered'),
    ('원문 답변', ['outside'], 'unverified'),
    ('원문 답변', [], 'unverified'),
    ('', ['q1'], 'unverified'),
    ('   ', ['q1'], 'unverified'),
])
def test_real_ledger_and_source_answer_boundary(tmp_path, monkeypatch, answer, citations, status):
    requests = []
    class Client:
        def __init__(self, *_): pass
        async def generate(self, request, cancelled=None):
            assert cancelled() is False
            requests.append(request)
            parsed = dict(answer=answer, choice=None, citations=citations, limitations=[])
            return dict(parsed=parsed, text=json.dumps(parsed), failure_kind=None, elapsed_s=.01)
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    service = KnowledgeService(tmp_path/'knowledge.db')
    original = dict(id='preserved', kind='business_query', status='succeeded', units=[])
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('preserved', json.dumps(original)))
    try:
        result = historical_use.answer(service, '질문', CONTEXT, RECIPE, {'review': 'fixed'}, '공통 지시')
        assert result['status'] == status
        run = service.run(result['run_id'])
        assert run['answer_status'] == status
        assert run['status'] == ('succeeded' if status == 'answered' else 'partial')
        assert run['metrics']['llm_calls'] == 1 and len(requests) == 1
        req = requests[0]
        assert req.stage == 'business_qa' and req.model == 'fixed-review'
        assert req.max_tokens == 4096 and req.context_tokens == 49152
        assert req.messages[0]['content'] == '공통 지시'
        assert json.loads(req.messages[1]['content'])['context'][0]['id'] == 'q1'
        assert req.schema['properties']['citations']['items']['const'] == 'q1'
        assert run['units'][0]['reference_map'] == {'past-MSS-001': 'q1'}
        if status == 'answered':
            assert run['answer']['citations'] == ['past-MSS-001']
            assert run['citation_normalization']['removed_duplicates'] == len(citations)-1
        elif (citations and not answer.strip()) or 'outside' in citations:
            assert run['units'][0]['status'] == 'failed'
            assert run['units'][0]['error'].startswith('schema_error:')
        with service.repository.connect() as db:
            assert service.repository.get(db, 'runs', 'preserved') == original
    finally:
        service.shutdown()
    reopened = KnowledgeService(tmp_path/'knowledge.db')
    try:
        assert reopened.run(result['run_id'])['answer_status'] == status
    finally:
        reopened.shutdown()


@pytest.mark.parametrize('context,cap,status', [([], 16384, 'unverified'), (CONTEXT, 1, 'input_capacity')])
def test_capacity_and_empty_context_make_no_model_call(tmp_path, monkeypatch, context, cap, status):
    class Client:
        def __init__(self, *_):
            pytest.fail('Model client must not be constructed')
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        result = historical_use.answer(service, '질문', context, RECIPE, {}, '지시', source_cap=cap)
        assert result['status'] == status and result['qa_model_called'] is False
        run = service.run(result['run_id'])
        assert run['metrics']['llm_calls'] == 0 and not run['units']
    finally:
        service.shutdown()
