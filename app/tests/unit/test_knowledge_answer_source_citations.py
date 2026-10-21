"""Source-address contract fixtures; not model-selected or semantic support evidence."""
from copy import deepcopy

import pytest

from app.knowledge import business_use as use
from app.knowledge.business_models import BusinessQuery


QUOTE = '상품 무게: 0.5kg'  # Literal quotation already present in the saved retail source.


def source(text=QUOTE, start=0, version='v', parse='p'):
    return dict(id='b', text=text, span=[start, start + len(text)],
                source_version_id=version, parse_run_id=parse, claim_references=[dict(claim_ids=['other'])])


def answer():
    return dict(answer='기존 답변', choice=None, citations=['kept'], limitations=['기존 미확정'])


def record(rows=None, views=None, blocks=None):
    run, output = {}, answer()
    if rows is not None:
        output['source_citations'] = rows
    use.record_answer_source_citations(run, output, views or [source()], blocks or [source()])
    assert output == answer()  # A source-address error never discards the normal answer/claim citations.
    return run['answer_source_citations']


def test_missing_and_explicit_empty_are_distinct():
    assert record()['status'] == 'not_recorded'
    empty = record([])
    assert empty['status'] == 'recorded' and empty['citations'] == []
    assert empty['semantic_support'] == 'not_assessed' and empty['answer_binding'] == 'global'


def test_unique_quote_retains_absolute_identity_without_promoting_parent_claims():
    views = [source(start=10)]
    blocks = [source('x' * 10 + QUOTE)]
    before = deepcopy((views, blocks))
    saved = record([dict(evidence_ref='b', quote=QUOTE)], views, blocks)
    assert saved['status'] == 'recorded'
    ref = saved['citations'][0]
    assert (ref['source_version_id'], ref['parse_run_id'], ref['block_id']) == ('v', 'p', 'b')
    assert (ref['start_char'], ref['end_char']) == (10, 10 + len(QUOTE))
    assert 'claim_ids' not in ref and 'claim_references' not in ref
    assert (views, blocks) == before


def test_repeated_text_is_unresolved_even_for_overlapping_occurrences():
    for text, quote in [(QUOTE + ' / ' + QUOTE, QUOTE), ('aaa', 'aa')]:
        saved = record([dict(evidence_ref='b', quote=quote)], [source(text)], [source(text)])
        assert saved['status'] == 'unresolved'
        assert saved['citations'][0]['address_status'] == 'unresolved'
        assert 'start_char' not in saved['citations'][0]


def test_same_position_from_overlapping_views_and_repeated_records_counts_once():
    views = [source(), source(QUOTE[3:], start=3)]
    item = dict(evidence_ref='b', quote=QUOTE)
    saved = record([item, item], views)
    assert saved['status'] == 'recorded' and len(saved['citations']) == 1
    assert saved['duplicates_removed'] == 1


@pytest.mark.parametrize('version,parse', [('wrong', 'p'), ('v', 'wrong'), ('v', None)])
def test_wrong_or_missing_source_identity_is_unresolved(version, parse):
    saved = record([dict(evidence_ref='b', quote=QUOTE)], [source(version=version, parse=parse)])
    assert saved['status'] == 'unresolved'


def test_unregistered_and_outside_provided_ranges_do_not_replace_valid_records():
    rows = [dict(evidence_ref='missing', quote=QUOTE), dict(evidence_ref='b', quote=QUOTE)]
    saved = record(rows)
    assert saved['status'] == 'unresolved'
    assert [r['address_status'] for r in saved['citations']] == ['unresolved', 'matched']
    outside = record([dict(evidence_ref='b', quote=QUOTE)], [source(QUOTE[:4])])
    assert outside['status'] == 'unresolved'


def test_same_text_in_distinct_parse_identities_does_not_pick_the_first():
    saved = record([dict(evidence_ref='b', quote=QUOTE)],
        [source(), source(parse='p2')], [source(), source(parse='p2')])
    assert saved['status'] == 'unresolved'


def test_default_request_schema_stays_unchanged_and_source_contract_is_explicit():
    context = [dict(id='c', text='원래 주장')]
    old, refs = use.answer_references(context, [source()])
    default, default_refs = use.answer_references(context, [source()], source_citation_contract=None)
    assert old.model_json_schema() == default.model_json_schema() and refs == default_refs
    assert 'source_citations' not in default.model_json_schema()['properties']
    enabled, _ = use.answer_references(context, [source()], source_citation_contract='provided_source_quotes_v1')
    assert 'source_citations' in enabled.model_json_schema()['required']
    assert use.SOURCE_CITATIONS_PROMPT not in use.SYNTHESIS_PROMPT + use.REVIEWED_MEANINGS_PROMPT
    with pytest.raises(ValueError):
        BusinessQuery(question='q', source_run_id='r', source_citation_contract='provided_source_quotes_v1')


@pytest.mark.parametrize('enabled', [False, True])
def test_union_preview_includes_the_same_explicit_source_instruction(monkeypatch, enabled):
    class StopBeforeBudget(Exception):
        pass
    seen = []
    def packet(run, stage, instruction, *args, **kwargs):
        seen.append(instruction)
        raise StopBeforeBudget
    monkeypatch.setattr(use, 'graph_qa_input', lambda *a: ({}, {}, use.Answer, {}))
    monkeypatch.setattr(use.business_run, 'json_request', packet)
    request = BusinessQuery(question='q', snapshot_id='s', evidence_union='ranked_preserved_claims_v2',
        source_citation_contract='provided_source_quotes_v1' if enabled else None)
    run = dict(recipe={}, graph_retrieval=dict(selected_factual_claim_ids=[], ranked_passages=[]))
    with pytest.raises(StopBeforeBudget):
        use.preserved_graph_hits(run, {}, {}, request, [], [dict(block_id='c')])
    assert seen == [use.SYNTHESIS_PROMPT + use.REVIEWED_MEANINGS_PROMPT + (
        use.SOURCE_CITATIONS_PROMPT if enabled else '')]


def test_existing_publication_gate_withholds_new_quotes_but_preserves_raw_record(tmp_path, monkeypatch):
    from app.tests.unit.test_knowledge_evidence_preservation import fixture_service, data
    service, client, _ = fixture_service(tmp_path, monkeypatch)
    blocked = []
    def retrieve(service, run, snapshot, request):
        run['graph_retrieval'] = dict(contract='explicit_fixture_no_search')
        return deepcopy(data()[3])
    def response(service, run, stage, instruction, context, output_type, **kwargs):
        source = context['source_evidence'][0]
        output = dict(answer='보존된 정상 내용', choice=None, citations=[context['context'][0]['id']], limitations=[],
            source_citations=[dict(evidence_ref=source['id'], quote=source['text'])])
        run['units'].append(dict(id='explicit-fixture', stage=stage, status='succeeded',
            response=dict(parsed=deepcopy(output))))
        blocked.append(dict(source_version_id=source['source_version_id'], state='restricted'))
        return output
    monkeypatch.setattr(use, 'restricted_sources', lambda *a: blocked)
    monkeypatch.setattr(use.business_run, 'json_call', response)
    monkeypatch.setattr(use, 'concept_hints', lambda *a: {})
    from app.knowledge import graph_retrieval
    monkeypatch.setattr(graph_retrieval, 'retrieve', retrieve)
    try:
        reply = client.post('/api/v1/knowledge/business/search', json=dict(snapshot_id='s', question='계약 차단 검사',
            source_citation_contract='provided_source_quotes_v1')).json()['data']
        assert reply['status'] == 'needs_review' and reply['answer'] is None
        assert reply['source_citations']['status'] == 'needs_review' and reply['source_citations']['citations'] == []
        saved = client.get('/api/v1/knowledge/runs/'+reply['run_id']).json()['data']
        assert saved['answer'] is None and saved['answer_source_citations'] == reply['source_citations']
        assert saved['units'][0]['response']['parsed']['source_citations'][0]['quote']
    finally:
        service.executor.shutdown(wait=True)
