"""Lossless record serialization with verified DOM containment; no semantic links."""
from copy import deepcopy
import re
from soupsieve.util import SelectorSyntaxError


def serialize(body, soup, source_blocks):
    original = deepcopy(body)
    context = original.pop('context')
    required = original.pop('source_context')
    records, originals, context_rows, source_rows, paths, roots, unresolved = [], [], [], [], {}, [], []
    nodes = {}
    selections = {}

    def select(path):
        if soup is None:
            return []
        if path not in selections:
            try:
                selections[path] = soup.select(path)
            except SelectorSyntaxError:
                selections[path] = []
        return selections[path]

    def node_path(path):
        selector, marker, tail = path.partition('::text(')
        suffix = marker + tail if marker else ''
        pieces = selector.split(' > ')
        prefixes = [' > '.join(pieces[:i+1]) for i in range(len(pieces))]
        located = [select(prefix) for prefix in prefixes]
        if any(len(items) != 1 for items in located):
            return None, suffix
        if any(located[i][0].parent is not located[i-1][0] for i in range(1, len(located))):
            return None, suffix
        parent = None
        for prefix, piece, selected in zip(prefixes, pieces, located):
            if prefix not in paths:
                number = len(paths)
                paths[prefix] = number
                entry = dict(node=number, selector=piece, records=[])
                nodes[number] = (entry, selected[0])
                (roots if parent is None else nodes[parent][0].setdefault('children', [])).append(entry)
            parent = paths[prefix]
        return parent, suffix

    for target, rows in ((context_rows, context), (source_rows, required)):
        for row in rows:
            if row in originals:
                target.append(originals.index(row))
                continue
            index = len(records)
            target.append(index)
            record = deepcopy(row)
            originals.append(deepcopy(row))
            records.append(record)
            locator = record.get('locator', {})
            path = locator.get('element_path')
            if not path:
                unresolved.append(dict(row=index, reason='reference_only' if 'context_id' in record else 'no_parser_path'))
                continue
            number, suffix = node_path(path)
            if number is None:
                unresolved.append(dict(row=index, reason='parser_path_not_verified_in_DOM'))
                continue
            locator.pop('element_path')
            locator['dom_node'] = number
            if suffix:
                locator['text_slot'] = suffix
            nodes[number][0]['records'].append(index)

    def order_tree(entries):
        entries.sort(key=lambda e: next(i for i, child in enumerate(nodes[e['node']][1].parent.children)
            if child is nodes[e['node']][1]))
        for entry in entries:
            if entry.get('children'):
                order_tree(entry['children'])
            if not entry['records']:
                entry.pop('records')
    order_tree(roots)

    levels = []
    for block in source_blocks:
        loc = block.get('locator', {})
        path = loc.get('element_path', '')
        match = re.search(r'(?:^| > )h([1-6]):', path)
        if match and isinstance(loc.get('block_order'), int):
            selected = select(path.split('::text(')[0])
            if len(selected) == 1 and selected[0].name == 'h' + match[1]:
                levels.append((loc['block_order'], int(match[1])))
    levels.sort()
    headings = []
    for index, record in enumerate(records):
        loc = record.get('locator', {})
        number = loc.get('dom_node')
        if number is None:
            continue
        node = nodes[number][1]
        if node.name in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
            start, level = loc.get('block_order'), int(node.name[1])
            if (start, level) not in levels:
                unresolved.append(dict(row=index, reason='heading_range_not_verified'))
                continue
            end = next((order for order, depth in levels if order > start and depth <= level), None)
            members = [i for i, r in enumerate(records) if isinstance(r.get('locator', {}).get('block_order'), int)
                and start <= r['locator']['block_order'] and (end is None or r['locator']['block_order'] < end)]
            headings.append(dict(row=index, level=level, range=[start, end], records=members))
        if 'row' in loc:
            table = node if node.name == 'table' else node.find_parent('table')
            rows = table.find_all('tr', recursive=False) if table else []
            row, column = loc['row'], loc['column']
            cells = rows[row].find_all(['td', 'th'], recursive=False) if 0 <= row < len(rows) else []
            cell = next((c for c in cells if int(c.get('data-native-col', -1)) == column), None)
            span = loc.get('merged_span', dict(rows=1, columns=1))
            if cell is None or int(cell.get('rowspan', 1)) != span['rows'] or int(cell.get('colspan', 1)) != span['columns']:
                unresolved.append(dict(row=index, reason='table_coordinates_not_verified'))
    attached = set()
    for entry, _ in nodes.values():
        if entry.get('records'):
            attached.update(entry['records'])
            entry['records'] = [dict(input_row=i, **records[i]) for i in entry['records']]
    for entry, _ in nodes.values():
        entry.pop('node')
        for record in entry.get('records', []):
            record.get('locator', {}).pop('dom_node', None)
    document = dict(tree=roots, unlocated_records=[dict(input_row=i, **record)
        for i, record in enumerate(records) if i not in attached], context_rows=context_rows,
        source_context_rows=source_rows, headings=headings, unresolved=unresolved)
    result = dict(original, source_document=document)
    return result


def restore(body):
    original = deepcopy(body)
    document = original.pop('source_document')
    records = {}
    def keep(row, path=None):
        value = deepcopy(row)
        index = value.pop('input_row')
        if path is not None:
            locator = value['locator']
            locator['element_path'] = path + locator.pop('text_slot', '')
        records[index] = value
    def walk(entries, prefix=''):
        for entry in entries:
            path = (prefix + ' > ' if prefix else '') + entry['selector']
            for row in entry.get('records', []):
                keep(row, path)
            walk(entry.get('children', []), path)
    walk(document['tree'])
    for row in document['unlocated_records']:
        keep(row)
    original['context'] = [records[i] for i in document['context_rows']]
    original['source_context'] = [records[i] for i in document['source_context_rows']]
    return original


FORMAT = ('source_document.tree는 확인된 원문 DOM 포함 관계이며 각 위치의 records에서 본문을 직접 읽는다. '
    '각 record의 소속 tree 가지와 text_slot으로 원래 element_path를 복원한다. '
    'context_rows와 source_context_rows는 input_row로 원래 두 배열을 복원한다. '
    'headings는 제공된 제목의 실제 level/range이고 표의 row/column/merged_span은 record locator에 보존되어 있다. '
    'supports_context_ids는 기존 참고구간 연결로서 DOM 부모가 아니다. '
    'unlocated_records는 원래 참조 기록이고 unresolved는 표현하지 못한 구조다. '
    'citations는 context_rows에 해당하는 기존 context id만 쓴다. ')


def load_html(service, db, version_id, parse_id):
    """Common immutable HTML/complete-parse lookup; performs no model request."""
    from hashlib import sha256
    from bs4 import BeautifulSoup
    soup = None; blocks = []; reason = 'unrecorded_version_or_parse'
    if version_id and parse_id:
        try:
            version = service.repository.get(db, 'versions', version_id)
            parse = service.repository.get(db, 'runs', parse_id)
        except KeyError:
            reason = 'unavailable_version_or_parse'
        else:
            if version['format'] == 'html' and parse['kind'] == 'parse' and version_id in parse['input_version_ids']:
                path = service.raw_path(version)
                try:
                    raw = path.read_bytes()
                except OSError:
                    reason = 'unavailable_raw_HTML'
                else:
                    if sha256(raw).hexdigest() != version['sha256']:
                        reason = 'raw_version_hash_mismatch'
                    else:
                        try:
                            soup = BeautifulSoup(raw.decode('utf-8-sig'), 'html.parser')
                        except UnicodeDecodeError:
                            reason = 'unsupported_HTML_encoding'
                        else:
                            units = service.parse_units(db, parse, version_id)
                            complete = bool(units) and all(u['status'] == 'succeeded' for u, _ in units)
                            blocks = service.parse_blocks(db, parse_id, version_id) if complete else []
                            reason = ('verified_raw_HTML_and_complete_parse_lineage' if complete else
                                'verified_raw_HTML_incomplete_parse_no_heading_ranges')
            else:
                reason = 'unsupported_format_or_parse_lineage'
    return soup, blocks, reason


def for_service(service, body):
    """Use the recorded raw version and parse lineage, keeping unknown records intact."""
    context = body['context']; source_context = body['source_context']
    refs = {r['id']: r.get('source_reference', {}) for r in context}
    def key(row):
        ref = row.get('source_reference', row)
        if 'context_id' in row:
            ref = refs.get(row['context_id'], ref)
        return ref.get('source_version_id'), ref.get('parse_run_id')
    keys = list(dict.fromkeys(key(r) for r in context + source_context))
    loaded = {}; provenance = []
    with service.repository.connect() as db:
        for version_id, parse_id in keys:
            soup, blocks, reason = load_html(service, db, version_id, parse_id)
            loaded[version_id, parse_id] = soup, blocks
            provenance.append(dict(source_version_id=version_id, parse_run_id=parse_id, status=reason))
    if len(keys) == 1:
        soup, blocks = loaded[keys[0]]
        if soup is None:
            return deepcopy(body), provenance
        converted = serialize(body, soup, blocks)
    else:
        converted = {k:deepcopy(v) for k,v in body.items() if k not in {'context', 'source_context'}}
        documents = []
        for version_id, parse_id in keys:
            context_indices = [i for i,r in enumerate(context) if key(r) == (version_id, parse_id)]
            source_indices = [i for i,r in enumerate(source_context) if key(r) == (version_id, parse_id)]
            rows = dict(context=[context[i] for i in context_indices], source_context=[source_context[i] for i in source_indices])
            soup, blocks = loaded[version_id, parse_id]
            document = serialize(rows, soup, blocks)['source_document']
            documents.append(dict(source_version_id=version_id, parse_run_id=parse_id,
                context_input_rows=context_indices, source_context_input_rows=source_indices, source_document=document))
        converted['source_documents'] = documents
    assert restore_versions(converted) == body
    return converted, provenance


def restore_versions(body):
    if 'source_document' in body:
        return restore(body)
    if 'source_documents' not in body:
        return deepcopy(body)
    original = deepcopy(body); documents = original.pop('source_documents')
    context = {}; source_context = {}
    for document in documents:
        rows = restore(dict(source_document=document['source_document']))
        context.update(zip(document['context_input_rows'], rows['context']))
        source_context.update(zip(document['source_context_input_rows'], rows['source_context']))
    original['context'] = [context[i] for i in range(len(context))]
    original['source_context'] = [source_context[i] for i in range(len(source_context))]
    return original
