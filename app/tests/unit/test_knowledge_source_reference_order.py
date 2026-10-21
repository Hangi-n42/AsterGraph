from copy import deepcopy

from app.knowledge.business_use import source_evidence_views


def row(block, quote, start, end, claim, precision='exact'):
    return dict(evidence=dict(block_id=block, source_version_id='v', parse_run_id='p',
        start_char=start, end_char=end, quote=quote, precision=precision), claim_ids=[claim])


def refs(views, claim):
    return [(view['id'], link['span'], link['precision'],
             view['text'][link['span'][0]-view['span'][0]:link['span'][1]-view['span'][0]])
            for view in views for link in view['claim_references'] if claim in link['claim_ids']]


def test_new_early_claim_cannot_move_an_existing_source_reference():
    rows = [row('a', 'alpha', 0, 5, 'old'), row('b', 'bravo', 0, 5, 'old')]
    original = deepcopy(rows)
    before, order = source_evidence_views(rows, [])
    new = row('b', 'brav', 0, 4, 'new')
    after, _ = source_evidence_views([new, *rows], order)
    assert rows == original
    assert refs(after, 'old') == refs(before, 'old')
    assert refs(after, 'new') == [('b', [0, 4], 'exact', 'brav')]
    assert [v['id'] for v in after] == ['a', 'b']


def test_bridging_source_views_preserves_old_reference_order_and_metadata():
    rows = [row('a', 'ef', 4, 6, 'old', 'chunk'), row('a', 'ab', 0, 2, 'old')]
    before, order = source_evidence_views(rows, [])
    after, _ = source_evidence_views([row('a', 'abcdefg', 0, 7, 'new'), *rows], order)
    assert refs(after, 'old') == refs(before, 'old')
    assert refs(after, 'new') == [('a', [0, 7], 'exact', 'abcdefg')]
    assert after[0]['text'] == 'abcdefg'


def test_previous_order_does_not_restore_deselected_evidence():
    rows = [row('a', 'alpha', 0, 5, 'old'), row('b', 'bravo', 0, 5, 'kept')]
    _, order = source_evidence_views(rows, [])
    after, current_order = source_evidence_views([rows[1]], order)
    assert refs(after, 'old') == []
    assert refs(after, 'kept') == [('b', [0, 5], 'exact', 'bravo')]
    assert len(current_order) == 1
