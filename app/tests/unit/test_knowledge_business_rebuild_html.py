import pytest

from app.knowledge import autoschema, business_rebuild_html
from app.knowledge.business_models import BusinessRunRequest
from app.knowledge.schemas import RunRequest, SourceRegistration
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business import finish


def parsed(service, body):
    identifier = service.register('controlled.html', ('<html><body><main id="root">'+body+'</main></body></html>').encode(),
        SourceRegistration(title='CONTROLLED 원문 구조 검사', publisher='검사', namespace='test',
                           selected_scope=dict(selector='#root')))['source_version_id']
    assert finish(service, service.start(RunRequest(source_version_ids=[identifier]))['run_id'])['status'] == 'succeeded'
    with service.repository.connect() as db:
        version = service.repository.get(db, 'versions', identifier)
        blocks = service.parse_blocks(db, version['latest_parse_run_id'], identifier)
    return identifier, blocks


def test_public_section_policy_retains_global_context_without_merging_local_targets(tmp_path):
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        identifier, blocks = parsed(service, '<h2>융자제한기업</h2><section id="tax"><p>① 세금을 체납중인 기업</p></section>'
            '<section id="closure"><ul><li><p>⑤ 휴‧폐업중인 기업.</p><p>단, 재해를 직접 원인으로 휴업중인 기업은 가동 중인 기업으로 간주하여 융자대상에 포함</p></li></ul></section>'
            '<p>항목별 적용예외는 사업별 융자계획에서 규정</p>')
        assert len(autoschema.chunks(blocks, 49152, 4096, 1000)) == 1
        request = BusinessRunRequest(source_version_ids=[identifier], source_unit_policy=business_rebuild_html.POLICY)
        with service.repository.connect() as db:
            chunks, structure = business_rebuild_html.source_chunks(service, db, blocks, request)
        assert len(chunks) == 2
        globals_ = set(structure['versions'][identifier]['global_context_block_ids'])
        assert len(globals_) == 2
        targets = []
        for chunk in chunks:
            assert globals_ <= {b['id'] for b in chunk['blocks'] if b['context_only']}
            target = {b['id'] for b in chunk['blocks'] if not b['context_only']}
            targets.append(target)
            assert not target.intersection(globals_)
            assert set(chunk['source_reference_map']) == {'b'+str(i+1) for i in range(len(chunk['blocks']))}
        assert not targets[0].intersection(targets[1])
        assert sorted(map(len, targets)) == [1, 2]
    finally:
        service.shutdown()


@pytest.mark.parametrize('body', [
    '<p>같은 문구</p><p>같은 문구</p>',
    '<section><p>같은 문구</p></section><section><p>같은 문구</p></section>',
    '<section id="same"><p>첫째</p></section><section id="same"><p>둘째</p></section>',
    '<section id="outer"><section id="inner"><p>새 주석</p></section></section>',
])
def test_flat_duplicate_or_nested_units_are_not_guessed_as_independent(tmp_path, body):
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        identifier, blocks = parsed(service, body)
        with service.repository.connect() as db, pytest.raises(ValueError, match='절'):
            business_rebuild_html.profile(service, db, identifier, blocks)
    finally:
        service.shutdown()


def test_equal_text_nodes_keep_distinct_structural_positions(tmp_path):
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        identifier, blocks = parsed(service, '<section id="unit"><p>같은 문구</p><p>같은 문구</p></section>')
        with service.repository.connect() as db:
            info = business_rebuild_html.profile(service, db, identifier, blocks)
        unit = info['units']['unit']
        assert len(unit['relative_blocks']) == len(set(unit['relative_blocks'].values())) == 2
        assert set(unit['relative_blocks']) == {'p:0', 'p:1'}
    finally:
        service.shutdown()


def test_unowned_new_note_is_read_by_every_local_unit_not_assigned_by_first_text_match(tmp_path):
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        identifier, blocks = parsed(service, '<section id="one"><p>본문</p></section>'
            '<section id="two"><p>다른 본문</p></section><p>부모가 불명확한 새 예외</p>')
        request = BusinessRunRequest(source_version_ids=[identifier], source_unit_policy=business_rebuild_html.POLICY)
        with service.repository.connect() as db:
            chunks, structure = business_rebuild_html.source_chunks(service, db, blocks, request)
        assert len(structure['versions'][identifier]['global_context_block_ids']) == 1
        assert all(any(b['text'] == '부모가 불명확한 새 예외' and b['context_only'] for b in c['blocks']) for c in chunks)
    finally:
        service.shutdown()


@pytest.mark.parametrize('href', ['#other', '#missing', 'https://example.invalid/other'])
def test_explicit_reference_outside_unit_cannot_silently_disappear(tmp_path, href):
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        identifier, blocks = parsed(service, '<section id="one"><p><a href="'+href+'">다른 조건 참조</a></p></section>'
            '<section id="other"><p>실제 추가 조건</p></section>')
        with service.repository.connect() as db, pytest.raises(ValueError, match='참조'):
            business_rebuild_html.profile(service, db, identifier, blocks)
    finally:
        service.shutdown()
