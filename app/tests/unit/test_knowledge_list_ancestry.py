"""Declared list ancestry is stricter than the context retained for reading."""
from copy import deepcopy
import json

import pytest

from app.knowledge import autoschema, business_changes, business_run
from app.knowledge.business_models import CandidateSourceReview
from app.knowledge.schemas import RunRequest, SourceRegistration
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business import finish
from app.tests.unit.test_knowledge_business_local_review import local_run
from app.tests.unit.test_knowledge_chunks_candidates import block, focus_chunk


@pytest.fixture
def parsed_lists(tmp_path):
    service = KnowledgeService(tmp_path/'knowledge.db')
    html = ('<main id="root"><ul><li><p>기본 제한</p><p>단, 예외</p>'
            '<ul><li><p>하위 업무</p></li></ul></li><li><p>다른 항목</p></li></ul></main>')
    try:
        vid = service.register('lists.html', html.encode(), SourceRegistration(
            title='구조 검사 자료', publisher='검사', namespace='test', selected_scope=dict(selector='#root')))['source_version_id']
        parsed = finish(service, service.start(RunRequest(source_version_ids=[vid]))['run_id'])
        assert parsed['status'] == 'succeeded'
        with service.repository.connect() as db:
            version = service.repository.get(db, 'versions', vid)
            blocks = service.parse_blocks(db, version['latest_parse_run_id'], vid)
        yield blocks
    finally:
        service.shutdown()


def expected_parents(blocks):
    ids = {b['text']:b['id'] for b in blocks}
    return [dict(block_id=ids['하위 업무'], parent_block_ids=[ids['기본 제한'], ids['단, 예외']])]


def test_json_request_excludes_same_li_cycles_from_actual_parser(parsed_lists):
    run = local_run();run['blocks'] = parsed_lists
    request = business_run.json_request(run, 'candidate_source_review', '', dict(blocks=parsed_lists), CandidateSourceReview)
    payload = json.loads(request['messages'][-1]['content'])
    mapping = request['reference_map']
    expected = [dict(block_id=mapping[row['block_id']], parent_block_ids=[mapping[p] for p in row['parent_block_ids']])
                for row in expected_parents(parsed_lists)]
    assert payload['source_parents'] == expected


def test_change_impact_uses_same_strict_ancestry(parsed_lists, monkeypatch):
    captured = []
    monkeypatch.setattr(business_changes, 'stored_dependencies', lambda *args: ([], parsed_lists))
    def call(service, run, stage, instruction, context, schema):
        captured.append(context['source_parents'])
        return dict(items=[])
    monkeypatch.setattr(business_run, 'json_call', call)
    result, valid = business_changes.review_impacts(None, {}, [], dict(changes=[]), {}, [])
    assert valid and result == dict(items=[])
    assert captured == [expected_parents(parsed_lists)]


@pytest.mark.parametrize('suffix', [' > p:2', ' > span:2', '::text(2)', ''])
def test_same_list_item_text_paragraph_and_span_are_not_ancestors(suffix):
    path = 'section > ul:1 > li:1'
    candidates = [block('text', '조건', path+'::text(0)'), block('p', '본문', path+' > p:1'),
                  block('span', '설명', path+' > span:1')]
    target = block('target', '항목', path+suffix)
    assert autoschema.strict_list_parents(target, candidates) == []


@pytest.mark.parametrize('fault', [None, 'version', 'parse', 'other_li', 'prefix'])
def test_strict_nested_list_owner_preserves_carriers_and_rejects_other_scope(fault):
    path = 'section > ul:1 > li:1'
    candidates = [block('text', '조건', path+'::text(0)'), block('p', '본문', path+' > p:1'),
                  block('span', '설명', path+' > span:1')]
    target_path = path+' > ul:1 > li:1 > p:1'
    if fault == 'other_li': target_path = 'section > ul:1 > li:2 > ul:1 > li:1 > p:1'
    if fault == 'prefix': target_path = 'section > ul:1 > li:10 > ul:1 > li:1 > p:1'
    target = block('target', '하위 항목', target_path,
                   version='other' if fault == 'version' else 'v1', parse='other' if fault == 'parse' else 'p1')
    saved = deepcopy([target, candidates])
    assert autoschema.strict_list_parents(target, candidates) == ([] if fault else candidates)
    assert [target, candidates] == saved


def test_reading_context_keeps_same_li_rule_and_exception(parsed_lists):
    saved = deepcopy(parsed_lists)
    chunks = autoschema.chunks(parsed_lists, 49152, 4096, target_chars=1)
    ids = {b['text']:b['id'] for b in parsed_lists}
    for text in ['기본 제한', '단, 예외']:
        selected = focus_chunk(chunks, ids[text])
        assert {ids['기본 제한'], ids['단, 예외']} <= {b['id'] for b in selected['blocks']}
        assert next(b for b in selected['blocks'] if b['id'] == ids[text])['context_only'] is False
    assert parsed_lists == saved
