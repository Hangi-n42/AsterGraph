from copy import deepcopy
import pytest

from app.knowledge import source_capacity_repair
from app.tests.unit.test_knowledge_business_scope import block


def source():
    body = block('body', '대상 원문')
    header = block('header', '원문의 필수 제목')
    chunk = dict(id='chunk', blocks=[body], source_version_id=body['source_version_id'])
    ref = dict(block_id=header['id'], source_version_id=header['source_version_id'],
               parse_run_id=header['parse_run_id'], quote=header['text'], locator=header['locator'], span=None)
    groups = [dict(id='view', included_views=[dict(block_id='header', span=None), dict(block_id='body', span=None)],
                   target_views=[dict(block_id='body', span=None)])]
    return chunk, header, ref, groups


def test_canonical_context_is_explicit_and_keeps_original_source_fields():
    chunk, header, ref, groups = source(); before = deepcopy(chunk)
    result = source_capacity_repair.views(chunk, groups, [], [ref], [header])[0]
    assert result['blocks'] == [dict(header, context_only=True), dict(chunk['blocks'][0], context_only=False)]
    assert result['source_reference_map'] == {'b1': dict(block_id='header', span=None), 'b2': dict(block_id='body', span=None)}
    assert chunk == before


@pytest.mark.parametrize('field,value', [
    ('source_version_id', 'other'), ('parse_run_id', 'other'), ('quote', '발명한 제목'),
    ('locator', {'row': 100}), ('span', [0, 2]),
])
def test_canonical_context_rejects_changed_identity_text_locator_or_slice(field, value):
    chunk, header, ref, groups = source()
    ref[field] = value
    with pytest.raises(AssertionError):
        source_capacity_repair.views(chunk, groups, [], [ref], [header])


def test_canonical_context_cannot_be_added_without_a_split_or_silently_omitted():
    chunk, header, ref, groups = source()
    with pytest.raises(AssertionError): source_capacity_repair.views(chunk, None, [], [ref], [header])
    groups[0]['included_views'] = groups[0]['included_views'][1:]
    with pytest.raises(AssertionError): source_capacity_repair.views(chunk, groups, [], [ref], [header])
