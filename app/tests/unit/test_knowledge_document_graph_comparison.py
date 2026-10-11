from copy import deepcopy
import json

import numpy as np
import pytest

from app.knowledge import autoschema, business_run, business_use, graph_retrieval as gr
from app.knowledge.business_models import BusinessQuery, BusinessRunRequest
from app.knowledge.service import KnowledgeService
from app.knowledge.schemas import RunRequest, SourceRegistration
from app.tests.unit.test_knowledge_business import finish
from app.tests.unit.test_knowledge_graph_retrieval import snapshot


def test_source_pool_is_fixed_before_extraction_and_covers_partial_quotes():
    s = snapshot()
    s['include_unlinked_blocks'] = True
    for block in s['blocks']:
        block['parse_run_id'] = 'p'
    s['blocks'][0]['text'] = '앞 조건. 원문 0. 인용되지 않은 뒤 예외.'
    s['claims'][0]['evidence'][0].update(start_char=6, end_char=10, quote='원문 0')
    empty = dict(s, claims=[], concepts=[])
    before = gr.build(empty, 'full')[2]
    after = gr.build(s, 'full')[2]
    assert {pid: (p['text'], p['evidence']) for pid, p in before.items()} == {
        pid: (p['text'], p['evidence']) for pid, p in after.items()}
    p = next(p for p in after.values() if p['evidence']['block_id'] == 'b0')
    assert p['text'] == s['blocks'][0]['text'] and p['claim_ids'] == ['c0']
    assert s['claims'][0]['evidence'][0]['quote'] == '원문 0'


@pytest.mark.parametrize('retrieval', ['hybrid', 'hipporag2'])
def test_source_reader_shared_context_budget_and_no_forced_gold(tmp_path, monkeypatch, retrieval):
    s = snapshot()
    s['blocks'][0]['text'] = '신청 기간 원문 0'
    original = dict(id='origin', kind='business', status='succeeded', units=[], model_identity={},
        recipe=dict(options=dict(context_tokens=49152, review_tokens=4096)),
        sources=s['source_versions'], blocks=s['blocks'], claims=s['claims'], concepts=s['concepts'])
    original_before = deepcopy(original)
    service = KnowledgeService(tmp_path/'knowledge.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(original)))
    monkeypatch.setattr(gr, 'embed', lambda texts: np.asarray([[1., .5] for _ in texts]))
    stages = []
    def call(service, run, stage, instruction, context, schema, **kwargs):
        stages.append(stage)
        if stage == 'graph_retrieval_filter':
            return dict(selected_ids=[context['candidate_facts'][0]['id']])
        assert not run['required_context_ids'] and 'reviewed_meanings' not in context
        assert 'public_requirements' not in context
        return dict(answer='원문 답변', choice=None, citations=[context['context'][0]['id']], limitations=[])
    monkeypatch.setattr(business_run, 'json_call', call)
    try:
        request = BusinessQuery(source_run_id='origin', question='신청', retrieval=retrieval,
            limit=2, source_context_tokens=4096)
        result = business_use.query(service, request)
        assert result['status'] == 'answered'
        assert stages == (['business_qa'] if retrieval == 'hybrid' else ['graph_retrieval_filter', 'business_qa'])
        run = service.run(result['run_id'])
        assert run['source_context_budget']['within_limit']
        if retrieval == 'hybrid':
            assert run['graph_retrieval']['hybrid']['rrf_k'] == 60
            assert run['graph_retrieval']['hybrid']['bm25_ranking']
            assert not run['graph_retrieval']['selected_edge_ids']
        stages.clear()
        request.source_context_tokens = 1
        result = business_use.query(service, request)
        assert result['status'] == 'input_capacity' and 'business_qa' not in stages
        assert service.run(result['run_id'])['source_context_budget']['within_limit'] is False
        with service.repository.connect() as db:
            assert service.repository.get(db, 'runs', 'origin') == original_before
    finally:
        service.shutdown()


def test_source_only_build_needs_no_question():
    request = BusinessRunRequest(source_version_ids=['v'], repair=False)
    assert request.requirement_ids == [] and request.answer_items == []


def test_source_only_service_finishes_without_requirement_or_approval(tmp_path, monkeypatch):
    stages = []
    class Client:
        def __init__(self, *_): pass
        def identities(self, models, _): return models
        async def generate(self, request, cancelled=None):
            stages.append(request.stage)
            parsed = {'definitions': []} if request.stage == 'direct_definitions' else []
            return dict(parsed=parsed, text=json.dumps(parsed), failure_kind=None, elapsed_s=.001)
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        vid = service.register('source.txt', '원문 자료를 보존한다.'.encode(),
            SourceRegistration(title='자료', publisher='기관', namespace='test'))['source_version_id']
        finish(service, service.start(RunRequest(source_version_ids=[vid]))['run_id'])
        run = finish(service, service.start_business(BusinessRunRequest(source_version_ids=[vid], repair=False))['run_id'])
        assert run['status'] == 'succeeded', run.get('error')
        assert stages == [*autoschema.ROLES, 'direct_definitions']
        assert run['requirements'] == run['assessments'] == run['repairs'] == []
        assert run['conceptualization_scope'] == 'all'
        with service.repository.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0
    finally:
        service.shutdown()


def test_nested_table_keeps_list_parent_paragraph():
    parent = dict(id='parent', source_version_id='v', text='이 조건에 해당하는 경우에만 다음 표를 적용한다.',
                  locator=dict(element_path='article > ul:1 > li:1 > p:1'))
    cell = dict(id='cell', source_version_id='v', text='지원 대상',
                locator=dict(element_path='article > ul:1 > li:1 > table:1', row=1, column=0))
    chunks = autoschema.chunks([parent, cell], 8192, 512, 1)
    target = next(c for c in chunks if any(b['id']=='cell' and not b.get('context_only') for b in c['blocks']))
    assert any(b['id']=='parent' and b.get('context_only') for b in target['blocks'])
