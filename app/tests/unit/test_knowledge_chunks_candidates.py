from copy import deepcopy

import pytest

from app.knowledge import autoschema


def block(key, text, path=None, *, version='v1', parse='p1', **locator):
    if path is not None:
        locator['element_path'] = path
    return dict(id=key, text=text, source_version_id=version, parse_run_id=parse, locator=locator)


def chunk_blocks():
    table = 'section > table:nth-of-type(1)'
    parent = 'section > ul:nth-of-type(1) > li:nth-of-type(1)'
    return [block('heading', '상위 조건', 'section > h1:nth-of-type(1)', heading_level=1),
        block('header', '기관 / 조건', table, row=0, column=0, table_headers=['기관', '조건']),
        block('merged', '같은 이름', table, row=1, column=0, merged_span=dict(rows=3, columns=1)),
        block('row-one', '첫 행', table, row=1, column=1),
        block('row-two', '같은 이름', table, row=2, column=1),
        block('row-peer', '제12조 및 별표 참조', table, row=2, column=2),
        block('implicit-merge', '상위 병합', table, merged_span=dict(rows=4, columns=1)),
        block('other-table', '다른 표 머리글', 'section > table:nth-of-type(2)', row=0, column=0),
        block('list-parent', '신청자 조건', parent+'::text(0)'),
        block('list-base', '기본 신청', parent+' > ul:nth-of-type(1) > li:nth-of-type(1)'),
        block('list-note', '다만 예외는 별표 참조', parent+' > ul:nth-of-type(1) > li:nth-of-type(2)'),
        block('long', '기본 절차.\n\n다만 제외 경우.\n\n'*100,
              parent+' > ul:nth-of-type(1) > li:nth-of-type(3)')]


def focus_chunk(chunks, key):
    return next(chunk for chunk in chunks if any(row['id'] == key and not row.get('context_only')
                                                for row in chunk['blocks']))


def test_table_candidates_keep_headers_rowspan_and_nonrow_candidates_in_source_order():
    blocks = chunk_blocks()
    before = deepcopy(blocks)
    chunks = autoschema.chunks(blocks, 49152, 4096, target_chars=1)
    selected = focus_chunk(chunks, 'row-two')
    assert [row['id'] for row in selected['blocks']] == [
        'heading', 'header', 'merged', 'row-two', 'row-peer', 'implicit-merge']
    assert next(row for row in selected['blocks'] if row['id'] == 'merged')['locator']['merged_span']['rows'] == 3
    assert next(row for row in selected['blocks'] if row['id'] == 'header')['locator']['table_headers'] == ['기관', '조건']
    assert '별표' in selected['text'] and blocks == before
    selected['blocks'][0]['locator']['heading_level'] = 6
    assert blocks == before


def test_list_notes_keep_parent_base_and_exception_without_root_path_expansion():
    blocks = chunk_blocks()
    chunks = autoschema.chunks(blocks, 49152, 4096, target_chars=1)
    selected = focus_chunk(chunks, 'list-note')
    ids = {row['id'] for row in selected['blocks']}
    assert {'heading', 'list-parent', 'list-base', 'list-note'} <= ids
    assert not {'header', 'other-table'} & ids
    root = [block('root', '본문', 'section'), block('note', '다만 제외', 'section > p:nth-of-type(1)')]
    chunks = autoschema.chunks(root, 49152, 4096, target_chars=1)
    assert [row['id'] for row in focus_chunk(chunks, 'root')['blocks']] == ['root']


@pytest.mark.parametrize('target', [1, 1000])
def test_same_version_reappearing_starts_a_new_candidate_group(target):
    table = 'table'
    blocks = [block('old-header', '이전 머리글', table, row=0, column=0),
              block('old-row', '동일 이름', table, row=1, column=0),
              block('middle', '다른 출처', version='v2'),
              block('new-header', '새 머리글', table, parse='p3', row=0, column=0),
              block('new-row', '동일 이름', table, parse='p3', row=1, column=0)]
    chunks = autoschema.chunks(blocks, 49152, 4096, target_chars=target)
    selected = focus_chunk(chunks, 'new-row')
    assert {row['id'] for row in selected['blocks']} == {'new-header', 'new-row'}
    assert all(row['parse_run_id'] == 'p3' for row in selected['blocks'])
    versions = [chunk['source_version_id'] for chunk in chunks]
    assert [vid for i,vid in enumerate(versions) if i == 0 or vid != versions[i-1]] == ['v1', 'v2', 'v1']
    assert next(i for i,c in enumerate(chunks) if c['source_version_id'] == 'v2') < chunks.index(selected)


def test_missing_and_empty_table_paths_stay_distinct():
    blocks = [block('missing', '경로 누락', row=0, column=0),
              block('empty', '빈 경로 머리글', '', row=0, column=0),
              block('focus', '행', '', row=1, column=0)]
    selected = focus_chunk(autoschema.chunks(blocks, 49152, 4096, target_chars=1), 'focus')
    assert [row['id'] for row in selected['blocks']] == ['empty', 'focus']


@pytest.mark.parametrize('target', [1, 1000])
def test_capacity_continuations_empty_and_failure_contracts(target):
    blocks = chunk_blocks()
    before = deepcopy(blocks)
    chunks = autoschema.chunks(blocks, 2800, 256, target_chars=target)
    assert any(row.get('continuation_bundle') for chunk in chunks for row in chunk['blocks'])
    assert any('다만' in chunk['text'] for chunk in chunks)
    assert blocks == before and autoschema.chunks([], 2800, 256, target_chars=target) == []
    with pytest.raises(ValueError, match='No input capacity'):
        autoschema.chunks(blocks, 1000, 4096, target_chars=target)
    with pytest.raises(ValueError, match='positive Unicode'):
        autoschema.chunks(blocks, 49152, 4096, target_chars=0)
