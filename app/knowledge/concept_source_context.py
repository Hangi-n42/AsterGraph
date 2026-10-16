"""Opt-in, verified hierarchical table context; uncertain inputs retain their source."""
from copy import deepcopy
import re

from . import source_reader

VERSION = 'verified_table_rows_v1'


def references(value):
    if isinstance(value, dict):
        if 'block_id' in value:
            yield value
        for key, child in value.items():
            if key not in {'raw', 'chunk_evidence'}:
                yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def address(block, reason):
    return dict(block_id=block['id'], source_version_id=block['source_version_id'],
        parse_run_id=block.get('parse_run_id'), span=block.get('span'), reason=reason)


class Context:
    def __init__(self, service, parent):
        self.service = service
        self.parent = parent
        self.blocks = {b['id']: b for b in parent['blocks']}
        self.claims = {c['id']: c for c in parent['claims']}
        self.loaded = {}

    def select(self, target, selected_edges, groups):
        originals = {b['id']: b for _, blocks in groups for b in blocks}
        trace = dict(version=VERSION, status='retained', unresolved=[], added=[], excluded=[],
            kept=[address(b, 'original_scope_retained') for b in originals.values()],
            semantic_applicability='unapproved; DOM containment is structural only')

        def retain(reason):
            trace['unresolved'].append(reason)
            return groups, trace

        if target['kind'] != 'entity':
            return retain('initial_policy_requires_entity')
        cids = list(dict.fromkeys(target.get('claim_ids', []) + [e['claim_id'] for e in selected_edges]))
        trace['claim_ids'] = cids
        if not cids or any(cid not in self.claims for cid in cids):
            return retain('target_or_selected_neighbor_claim_unavailable')
        refs = [ref for cid in cids for ref in references(self.claims[cid])]
        if not refs or any(ref['block_id'] not in self.blocks for ref in refs):
            return retain('target_or_selected_neighbor_source_unavailable')
        seeds = {ref['block_id']: self.blocks[ref['block_id']] for ref in refs}
        trace['claim_evidence_block_ids'] = sorted(seeds)
        keys = {(b['source_version_id'], b.get('parse_run_id')) for b in seeds.values()}
        if len(keys) != 1 or not self.service:
            return retain('single_verified_source_parse_required')
        key = next(iter(keys))
        if key not in self.loaded:
            with self.service.repository.connect() as db:
                self.loaded[key] = source_reader.load_html(self.service, db, *key)
        soup, parsed, reason = self.loaded[key]
        trace['verification'] = dict(source_version_id=key[0], parse_run_id=key[1], status=reason)
        if reason != 'verified_raw_HTML_and_complete_parse_lineage':
            return retain(reason)
        if any(b.get('span') not in (None, [0, len(b['text'])]) or b['id'] not in self.blocks
               or b['text'] != self.blocks[b['id']]['text'] for b in originals.values()):
            return retain('partial_or_changed_source_view')
        for ref in refs:
            block = self.blocks[ref['block_id']]
            if (ref.get('source_version_id') != block['source_version_id'] or ref.get('parse_run_id') != block.get('parse_run_id')
                    or ref.get('start_char') is None or ref.get('end_char') is None
                    or block['text'][ref['start_char']:ref['end_char']] != ref.get('quote')):
                return retain('claim_source_address_not_verified')
        paths = {b.get('locator', {}).get('element_path') for b in seeds.values()}
        if len(paths) != 1 or None in paths or any('row' not in b.get('locator', {}) for b in seeds.values()):
            return retain('claim_evidence_not_one_table')
        path = next(iter(paths))
        try:
            tables = soup.select(path)
        except source_reader.SelectorSyntaxError:
            return retain('invalid_parser_path')
        if len(tables) != 1 or tables[0].name != 'table':
            return retain('table_path_not_unique')
        table = tables[0]
        section = table.parent
        if (section.name != 'section' or section.parent is None or section.parent.name not in {'article', 'main', 'body'}
                or len(section.find_all('table')) != 1 or table.find('caption') is not None):
            return retain('ambiguous_parent_or_multiple_tables_or_caption')
        prefix = path.rsplit(' > ', 1)[0]
        if soup.select(prefix) != [section]:
            return retain('section_path_not_verified')
        section_blocks = [b for b in parsed if b.get('locator', {}).get('element_path', '').startswith(prefix + ' > ')]
        if not section_blocks or any(b['id'] not in self.blocks or b['text'] != self.blocks[b['id']]['text']
                                     or b['locator'] != self.blocks[b['id']]['locator'] for b in section_blocks):
            return retain('complete_section_not_in_parent_scope')
        rows = table.find_all('tr')
        grid, cells = {}, {}
        for row_index, row in enumerate(rows):
            column = 0
            for cell in row.find_all(['td', 'th'], recursive=False):
                while (row_index, column) in grid:
                    column += 1
                try:
                    height, width = int(cell.get('rowspan', 1)), int(cell.get('colspan', 1))
                except ValueError:
                    return retain('invalid_table_span')
                if height < 1 or width != 1 or row_index + height > len(rows):
                    return retain('unsupported_table_span')
                origin = (row_index, column)
                cells[origin] = (cell, height)
                for index in range(row_index, row_index + height):
                    if (index, column) in grid:
                        return retain('overlapping_table_cells')
                    grid[index, column] = origin
                column += 1
        columns = sum(row == 0 for row, _ in cells)
        if (columns < 4 or len(rows) < 2 or any(cells[0, col][1] != 1 for col in range(columns))
                or any(set(col for row, col in grid if row == index) != set(range(columns)) for index in range(len(rows)))
                or any(cells[grid[index, col]][1] != 1 for index in range(1, len(rows)) for col in (columns-2, columns-1))
                or not any(height > 1 and col < columns-3 for (row, col), (_, height) in cells.items() if row > 0)
                or any(cell.name == 'th' for (row, _), (cell, _) in cells.items() if row > 0)):
            return retain('requires_flat_header_hierarchical_prefix_and_two_unmerged_terminal_columns')
        table_blocks = [b for b in section_blocks if b['locator']['element_path'] == path]
        by_cell = {}
        for block in table_blocks:
            loc = block['locator']; origin = (loc.get('row'), loc.get('column'))
            if origin not in cells or origin in by_cell:
                return retain('table_block_address_not_unique')
            cell, height = cells[origin]
            if loc.get('merged_span') != dict(rows=height, columns=1) or cell.get_text('\n', strip=True) != block['text']:
                return retain('table_cell_text_or_span_not_verified')
            by_cell[origin] = block
        if any(origin not in by_cell for origin, (cell, _) in cells.items() if cell.get_text('\n', strip=True)):
            return retain('incomplete_nonempty_table_parse')
        from .business_html_rows import HEADERS
        if columns != len(HEADERS) or [by_cell.get((0, col), {}).get('text') for col in range(columns)] != HEADERS:
            return retain('unsupported_classification_headers')
        item_column = HEADERS.index('품목명')
        trace['profile'] = dict(headers=list(HEADERS), item_column=item_column,
            terminal_columns=[HEADERS.index('분류코드'), HEADERS.index('업종명')])
        trace['reference_boundary'] = 'limited explicit markers in verified profile/section; no-marker is not proof of no semantic dependency'
        focus = set()
        for block in seeds.values():
            loc = block['locator']; origin = (loc['row'], loc['column'])
            if origin not in by_cell:
                return retain('evidence_cell_not_verified')
            if loc['column'] >= item_column and loc['row'] > 0:
                focus.add(grid[loc['row'], item_column])
        if len(focus) != 1:
            return retain('ambiguous_or_multiple_item_groups')
        item = next(iter(focus))
        focus_rows = set(range(item[0], item[0] + cells[item][1]))
        keep = {}; reasons = {}
        for origin, block in by_cell.items():
            row, col = origin; height = cells[origin][1]
            if row == 0 or set(range(row, row + height)) & focus_rows:
                keep[block['id']] = block
                reasons[block['id']] = 'table_header' if row == 0 else 'full_item_rows_with_merged_parent'
        headings = []
        for block in section_blocks:
            if block['locator']['element_path'] == path:
                continue
            locator = block['locator']; selector, marker, tail = locator['element_path'].partition('::text(')
            found = soup.select(selector)
            if len(found) != 1:
                return retain('section_context_path_not_unique')
            node = found[0]
            if node is not section and not any(ancestor is section for ancestor in node.parents):
                return retain('section_context_not_contained')
            try:
                text = str(list(node.children)[int(tail.rstrip(')'))]) if marker else node.get_text('\n', strip=True)
            except (ValueError, IndexError):
                return retain('section_text_slot_not_verified')
            if text != block['text']:
                return retain('section_context_text_not_verified')
            if re.fullmatch('h[1-6]', node.name):
                headings.append(block)
            keep[block['id']] = block
            reasons[block['id']] = 'source_heading_title_parent_or_note'
        own_refs = {ref for b in headings for ref in re.findall(r'별표\s*(\d+)', b['text'])}
        refs_found = {ref for b in keep.values() for ref in re.findall(r'별표\s*(\d+)', b['text'])}
        if not headings or not refs_found <= own_refs or any(re.search(r'제\s*\d+\s*조|별지|전항|각호', b['text']) for b in keep.values()):
            return retain('explicit_reference_or_heading_scope_unresolved')
        if not seeds.keys() <= keep.keys():
            return retain('target_or_selected_neighbor_evidence_outside_item')
        for bid, block in originals.items():
            if not block['locator']['element_path'].startswith(prefix + ' > '):
                keep[bid] = block; reasons[bid] = 'outside_focus_section_retained'
        selected = []
        for bid in sorted(keep, key=lambda bid: (keep[bid]['locator']['block_order'], bid)):
            block = deepcopy(keep[bid])
            if bid in originals:
                if 'context_only' in originals[bid]:
                    block['context_only'] = originals[bid]['context_only']
            else:
                block['context_only'] = True
            selected.append(block)
        trace.update(status='selected', kept=[address(b, reasons[b['id']]) for b in selected],
            added=[address(b, reasons[b['id']]) for b in selected if b['id'] not in originals],
            excluded=[address(b, 'outside_verified_item_rows; all_section_notes_retained') for bid, b in originals.items() if bid not in keep],
            item_rows=sorted(focus_rows), table_path=path,
            effect='context construction: row completion and note addition plus other-row exclusion; not pure token pruning')
        return [('verified_source_context', selected)], trace
