"""New-search defaults only: no model, database, or historical-query mutation."""
import pytest
from pydantic import ValidationError

from app.knowledge.business_models import BusinessQuery
from app.knowledge.business_use import resolve_query_defaults

DEFAULTS = dict(candidate_contract='r2_g1_w1', evidence_union='ranked_preserved_claims_v2',
                source_citation_contract='provided_source_quote_links_v1')


def test_omission_and_explicit_null_remain_distinct():
    omitted = BusinessQuery(snapshot_id='s', question='q')
    effective, changed = resolve_query_defaults(omitted, 'graph')
    assert {k: getattr(effective, k) for k in DEFAULTS} == DEFAULTS
    assert changed == list(DEFAULTS)
    assert all(getattr(omitted, k) is None for k in DEFAULTS)
    baseline = BusinessQuery(snapshot_id='s', question='q', **dict.fromkeys(DEFAULTS))
    assert resolve_query_defaults(baseline, 'graph') == (baseline, [])


def test_partial_override_and_quote_v1_are_preserved():
    request = BusinessQuery(snapshot_id='s', question='q', evidence_union=None,
                            source_citation_contract='provided_source_quotes_v1')
    effective, changed = resolve_query_defaults(request, 'graph')
    assert changed == ['candidate_contract']
    assert effective.candidate_contract == DEFAULTS['candidate_contract']
    assert effective.evidence_union is None
    assert effective.source_citation_contract == 'provided_source_quotes_v1'


@pytest.mark.parametrize('change,context', [
    ({'source_run_id': 'r', 'snapshot_id': None}, 'graph'),
    ({'source_run_id': 'r', 'snapshot_id': None, 'retrieval': 'hybrid'}, 'graph'),
    ({'source_run_id': 'r', 'snapshot_id': None, 'retrieval': 'hybrid_graph'}, 'graph'),
    ({'retrieval': 'bm25'}, 'graph'), ({'retrieval': 'dense'}, 'graph'),
    ({'graph_variant': 'entity'}, 'graph'), ({'graph_variant': 'entity_event'}, 'graph'),
    ({'requirement_ids': ['r']}, 'graph'), ({'answer_mode': 'source_quotes'}, 'graph'),
    ({'answer_mode': 'reviewed_items', 'answer_items': [dict(id='i', requirement_id='r',
        requirement_revision=1, field='question', request_quote='q')]}, 'graph'),
    ({'retrieval': 'bm25'}, 'document'),
])
def test_other_modes_do_not_receive_defaults(change, context):
    request = BusinessQuery(**dict(dict(snapshot_id='s', question='q'), **change))
    assert resolve_query_defaults(request, context) == (request, [])


@pytest.mark.parametrize('field', ['candidate_contract', 'evidence_union'])
def test_explicit_unsupported_contract_is_rejected(field):
    with pytest.raises(ValidationError):
        BusinessQuery(snapshot_id='s', question='q', retrieval='bm25', **{field: DEFAULTS[field]})


def test_loading_historical_query_never_applies_new_defaults():
    historical = dict(snapshot_id='s', question='old query')
    loaded = BusinessQuery.model_validate(historical)
    assert all(getattr(loaded, k) is None for k in DEFAULTS)
    assert historical == dict(snapshot_id='s', question='old query')
