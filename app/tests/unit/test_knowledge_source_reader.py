from copy import deepcopy

from bs4 import BeautifulSoup

from app.knowledge import source_reader
from app.knowledge.service import KnowledgeService
from app.knowledge.schemas import RunRequest, SourceRegistration
from app.tests.unit.test_knowledge_business import finish


def test_equal_siblings_follow_actual_dom_order_and_restore_input_order():
    soup = BeautifulSoup('<article><p>동일</p><p>동일</p></article>', 'html.parser')
    first = dict(id='first', text='동일', locator=dict(element_path='article > p:nth-of-type(1)'))
    second = dict(id='second', text='동일', locator=dict(element_path='article > p:nth-of-type(2)'))
    body = dict(question='질문', context=[second, first], source_context=[])
    converted = source_reader.serialize(body, soup, [])
    children = converted['source_document']['tree'][0]['children']
    assert [r['id'] for child in children for r in child['records']] == ['first', 'second']
    assert source_reader.restore(converted) == body


def test_invalid_path_keeps_original_record_without_guessing_parent():
    body = dict(context=[dict(id='p', text='원문', locator=dict(element_path='article > ???'))],
        source_context=[dict(context_id='p', supports_context_ids=['p'])])
    converted = source_reader.serialize(body, BeautifulSoup('<article>원문</article>', 'html.parser'), [])
    assert not converted['source_document']['tree']
    assert len(converted['source_document']['unlocated_records']) == 2
    assert source_reader.restore(converted) == body


def source(service, name, text):
    vid = service.register(name+'.html', ('<article id="source"><h1>제목</h1><p>'+text+'</p></article>').encode(),
        SourceRegistration(title=name, publisher='기관', namespace='test', selected_scope={'selector':'#source'}))['source_version_id']
    parsed = finish(service, service.start(RunRequest(source_version_ids=[vid]))['run_id'])
    with service.repository.connect() as db:
        blocks = service.parse_blocks(db, parsed['id'], vid)
    row = blocks[-1]
    return dict(id='context:'+vid, text=row['text'], locator=deepcopy(row['locator']),
        source_reference=dict(source_version_id=vid, parse_run_id=parsed['id'], block_id=row['id'])), parsed, blocks


def test_multiple_versions_with_identical_paths_stay_in_separate_documents(tmp_path):
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        first, _, _ = source(service, '하나', '첫 원문')
        second, _, _ = source(service, '둘', '다른 원문')
        body = dict(question='질문', context=[second, first], source_context=[])
        converted, provenance = source_reader.for_service(service, body)
        assert len(converted['source_documents']) == 2
        assert len({d['source_version_id'] for d in converted['source_documents']}) == 2
        assert source_reader.restore_versions(converted) == body
        assert all(p['status'] == 'verified_raw_HTML_and_complete_parse_lineage' for p in provenance)
    finally:
        service.shutdown()


def test_raw_hash_mismatch_preserves_flat_input(tmp_path):
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        row, _, _ = source(service, '원문', '보존할 원문')
        with service.repository.connect() as db:
            version = service.repository.get(db, 'versions', row['source_reference']['source_version_id'])
        service.raw_path(version).write_text('<article>다른 내용</article>')
        body = dict(context=[row], source_context=[])
        converted, provenance = source_reader.for_service(service, body)
        assert converted == body
        assert provenance[0]['status'] == 'raw_version_hash_mismatch'
    finally:
        service.shutdown()


def test_incomplete_parse_does_not_assert_heading_range(tmp_path):
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        row, parsed, blocks = source(service, '부분', '본문')
        heading = blocks[0]
        row.update(text=heading['text'], locator=deepcopy(heading['locator']))
        row['source_reference']['block_id'] = heading['id']
        with service.repository.connect() as db:
            parsed['units'][0]['status'] = 'failed'
            service.repository.save(db, 'runs', parsed)
        body = dict(context=[row], source_context=[])
        converted, provenance = source_reader.for_service(service, body)
        assert converted['source_document']['headings'] == []
        assert any(r['reason'] == 'heading_range_not_verified' for r in converted['source_document']['unresolved'])
        assert provenance[0]['status'] == 'verified_raw_HTML_incomplete_parse_no_heading_ranges'
        assert source_reader.restore_versions(converted) == body
    finally:
        service.shutdown()
