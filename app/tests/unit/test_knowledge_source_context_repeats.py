from collections import Counter
from copy import deepcopy
from weakref import ref
import gc

from bs4 import BeautifulSoup
import pytest

from app.knowledge import graph_retrieval as gr, source_reader


def context_fixture():
    blocks = [dict(id='parent', source_version_id='v1', parse_run_id='p1', text='조건',
                   locator=dict(element_path='h1:nth-of-type(1)', heading_level=1)),
              dict(id='note', source_version_id='v1', parse_run_id='p1', text='다만 제외',
                   locator=dict(element_path='table', row=0, column=0,
                                merged_span=dict(rows=2, columns=1), table_headers=['조건'])),
              *[dict(id=key, source_version_id='v1', parse_run_id='p1', text=key)
                for key in ['a', 'b', 'c']],
              dict(id='parent', source_version_id='v2', parse_run_id='other', text='다른 조건')]
    def candidate(key, version, block, parse='p1'):
        return dict(id=key, text=block, source_reference=dict(source_version_id=version,
            parse_run_id=parse, block_id=block, start_char=0, end_char=2))
    context = [candidate('first', 'v1', 'parent', 'p2'), candidate('second', 'v1', 'parent'),
               candidate('other', 'v2', 'parent', 'other'),
               *[candidate(key, 'v1', key) for key in ['a', 'b', 'c']]]
    bundles = [dict(blocks=[dict(blocks[0], context_only=True), dict(blocks[1], context_only=True),
                           dict(blocks[i], context_only=False)]) for i in [2, 3, 4]]
    return blocks, context, bundles


def test_context_lookup_keeps_first_match_parse_rule_span_and_support_order():
    blocks, context, bundles = context_fixture()
    original = deepcopy((blocks, bundles))
    rows = gr.source_context(blocks, context, {}, get_bundles=lambda: bundles)
    assert rows[0] == dict(context_id='first', supports_context_ids=['a', 'b', 'c'])
    assert rows[1]['text'] == '다만 제외' and rows[1]['parse_run_id'] == 'p1'
    assert rows[1]['supports_context_ids'] == ['a', 'b', 'c']
    assert rows[1]['locator']['merged_span'] == dict(rows=2, columns=1)
    assert rows[1]['locator']['table_headers'] == ['조건']
    assert (blocks, bundles) == original
    assert context[0]['locator']['heading_level'] == 1
    selected = [deepcopy(context[-1])]
    smaller = gr.source_context(blocks, selected, {}, get_bundles=lambda: bundles)
    assert smaller[0]['id'] == 'parent'
    assert all(row['supports_context_ids'] == ['c'] for row in smaller)
    smaller[0]['supports_context_ids'].append('changed')
    assert rows[0]['supports_context_ids'] == ['a', 'b', 'c']


@pytest.mark.parametrize('span', [[0, 2], (0, 2), [0, 1]])
def test_context_lookup_keeps_literal_span_comparison_and_false_first_id(span):
    blocks, context, bundles = context_fixture()
    for bundle in bundles:
        bundle['blocks'][0]['span'] = span
    context[0]['id'] = ''
    rows = gr.source_context(blocks, context, {}, get_bundles=lambda: bundles)
    assert rows[0]['id'] == 'parent' and not rows[0].get('context_id')
    assert rows[0]['span'] == span


@pytest.mark.parametrize('same_address', [False, True])
def test_context_lookup_does_not_read_spans_of_other_addresses(same_address):
    blocks, context, bundles = context_fixture()
    bad = dict(id='bad', source_reference=dict(source_version_id='v1',
        block_id='parent' if same_address else 'absent'))
    selected = [bad, context[-1]]
    if same_address:
        with pytest.raises(KeyError, match='start_char'):
            gr.source_context(blocks, selected, {}, get_bundles=lambda: bundles)
    else:
        assert gr.source_context(blocks, selected, {}, get_bundles=lambda: bundles)


def test_context_packet_defaults_are_computed_only_for_new_views(monkeypatch):
    blocks, context, bundles = context_fixture()
    packet, calls = gr.autoschema.source_packet, []
    def record(rows):
        calls.extend(row['id'] for row in rows)
        return packet(rows)
    monkeypatch.setattr(gr.autoschema, 'source_packet', record)
    gr.source_context(blocks, context, {}, get_bundles=lambda: bundles)
    # One packet plus reader_locator for the only unmatched context row, across three bundles.
    assert calls.count('note') == 2


HTML = '''<article><section><h2>조건</h2><p>본문</p><p>다만 제외</p>
<table><tr><th data-native-col="0" rowspan="2">기관</th></tr>
<tr><td data-native-col="1">위임장</td></tr></table></section></article>'''


def reader_fixture():
    paths = ['article > section > h2:nth-of-type(1)', 'article > section > p:nth-of-type(1)::text(0)',
             'article > section > p:nth-of-type(1)::text(1)', 'article > section > p',
             'article > ???', 'article > ???', 'article > absent',
             'article > section > table > tr:nth-of-type(1) > th']
    rows = [dict(id=str(i), text='원문 '+str(i),
                 locator=dict(element_path=path, block_order=i)) for i, path in enumerate(paths)]
    rows[-1]['locator'].update(row=0, column=0, merged_span=dict(rows=2, columns=1), table_headers=['기관'])
    body = dict(question='조건과 예외', context=rows,
                source_context=[dict(context_id='0', supports_context_ids=['1', '2'])])
    blocks = [dict(id='heading', text='조건', locator=dict(element_path=paths[0], block_order=0))]
    return body, blocks


def test_dom_selections_are_local_reused_and_restore_every_original_field():
    body, blocks = reader_fixture()
    before = deepcopy((body, blocks))
    soup = BeautifulSoup(HTML, 'html.parser')
    html_before = str(soup)
    select, calls = soup.select, Counter()
    def record(path):
        calls[path] += 1
        return select(path)
    soup.select = record
    result = source_reader.serialize(body, soup, blocks)
    assert source_reader.restore(result) == body
    assert (body, blocks) == before and str(soup) == html_before
    assert calls and max(calls.values()) == 1
    assert {row['reason'] for row in result['source_document']['unresolved']} == {
        'parser_path_not_verified_in_DOM', 'reference_only'}
    assert result['source_document']['headings'][0]['range'] == [0, None]
    source_reader.serialize(body, soup, blocks)
    assert max(calls.values()) == 2  # A new call repeats every lookup on this soup.


def test_dom_cache_does_not_survive_changed_soup_or_another_call():
    soup = BeautifulSoup('<article><p>조건</p></article>', 'html.parser')
    body = dict(context=[dict(id='one', text='조건', locator=dict(element_path='article > p'))], source_context=[])
    first = source_reader.serialize(body, soup, [])
    assert not first['source_document']['unresolved']
    soup.article.append(BeautifulSoup('<p>예외</p>', 'html.parser').p)
    changed = source_reader.serialize(body, soup, [])
    assert changed['source_document']['unresolved'] == [dict(row=0, reason='parser_path_not_verified_in_DOM')]
    assert source_reader.restore(changed) == body
    pointer = ref(soup)
    del soup
    gc.collect()
    assert pointer() is None


def test_dom_non_selector_failure_still_propagates():
    class BrokenSoup:
        def select(self, path):
            raise RuntimeError('DOM failure')
    body = dict(context=[dict(id='one', locator=dict(element_path='article'))], source_context=[])
    for _ in range(2):
        with pytest.raises(RuntimeError, match='DOM failure'):
            source_reader.serialize(body, BrokenSoup(), [])


@pytest.mark.parametrize('second_version', ['v1', 'v2'])
def test_reader_separates_same_block_paths_between_parse_and_version(tmp_path, monkeypatch, second_version):
    from app.knowledge.service import KnowledgeService
    soups = {('v1', 'p1'): BeautifulSoup('<article><p>조건</p></article>', 'html.parser'),
             (second_version, 'p2'): BeautifulSoup('<article><p>예외</p><p>주석</p></article>', 'html.parser')}
    loads = []
    def load(service, db, version, parse):
        loads.append((version, parse))
        return soups[version, parse], [], 'synthetic_complete_parse'
    monkeypatch.setattr(source_reader, 'load_html', load)
    body = dict(context=[dict(id=cid, text=text, locator=dict(element_path='article > p'),
        source_reference=dict(source_version_id=version, parse_run_id=parse, block_id='same-block'))
        for cid, version, parse, text in [('first', 'v1', 'p1', '조건'),
            ('second', second_version, 'p2', '예외')]], source_context=[])
    original = deepcopy(body)
    service = KnowledgeService(tmp_path/'knowledge.db')
    try:
        converted, provenance = source_reader.for_service(service, body)
        assert loads == [('v1', 'p1'), (second_version, 'p2')]
        assert not converted['source_documents'][0]['source_document']['unresolved']
        assert converted['source_documents'][1]['source_document']['unresolved'] == [
            dict(row=0, reason='parser_path_not_verified_in_DOM')]
        assert source_reader.restore_versions(converted) == body == original
        assert [(row['source_version_id'], row['parse_run_id']) for row in provenance] == loads
    finally:
        service.shutdown()
