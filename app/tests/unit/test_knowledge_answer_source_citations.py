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
    assert use.source_citations_instruction(None) == ''
    assert use.source_citations_instruction('provided_source_quotes_v1') == use.SOURCE_CITATIONS_PROMPT
    with pytest.raises(ValueError):
        BusinessQuery(question='q', source_run_id='r', source_citation_contract='provided_source_quotes_v1')
