"""Lossless literal lists, not ingredient equivalence, necessity, or approval."""
import re

from .business_run import exact_evidence

VERSION = 'literal-source-list-v1'
UNITS = ('kg', 'mg', 'g', 'mL', 'ml', 'L', 'l', '개', '모', '컵', '큰술', '작은술', '뿌리', '장', '인분')
NUMBER = r'(?:\d+/\d+|\d+(?:\.\d+)?)'
AMOUNT = NUMBER + r'\s*(?:' + '|'.join(sorted(UNITS, key=len, reverse=True)) + r')(?![A-Za-z가-힣])|약간(?!\S)'
QUANTITY = re.compile(r'(?<!\S)(?:' + AMOUNT + ')')
SUFFIX = re.compile(r'(?:' + AMOUNT + r')(?:\s*\([^()]*\))*\s*')
PREAMBLE = re.compile(r'\s*(?:재료소개(?:\s+|$))?(?:재료량\s*\([^()\n]*\)(?:\s+|$))?')


def parse_field(evidence, blocks):
    """Only the frozen explicit-quantity grammar can establish a name boundary."""
    field = exact_evidence([evidence], blocks)[0]
    text = field['quote']
    base = field['start_char']
    def ref(a, b):
        return {**{k: field[k] for k in ('source_version_id', 'parse_run_id', 'block_id')},
                'start_char': base+a, 'end_char': base+b, 'quote': text[a:b], 'precision': 'exact'}
    result = dict(version=VERSION, field=field, parts=[], items=[], issues=[],
                  condition_state='unreviewed', exception_state='unreviewed', necessity='not_inferred')
    stack, depths, commas = [], [], []
    pairs = {')': '(', ']': '[', '}': '{'}
    for i, char in enumerate(text):
        depths.append(len(stack))
        if char in '\"\'':
            result['issues'].append(dict(offset=i, reason='quoted_syntax_not_supported'))
        if char in '([{':
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                result['issues'].append(dict(offset=i, reason='unbalanced_brackets'))
        elif char == ',' and not stack:
            commas.append(i)
    if stack:
        result['issues'].append(dict(reason='unclosed_brackets'))
    if result['issues']:
        result.update(status='unresolved', parts=[dict(role='unresolved', evidence=ref(0, len(text)))],
                      roundtrip_exact=True)
        return result
    start = PREAMBLE.match(text).end()
    if start:
        result['parts'].append(dict(role='preamble', evidence=ref(0, start)))
    for end in [*[i for i in commas if i >= start], len(text)]:
        if end > start:
            result['parts'].append(dict(role='entry', evidence=ref(start, end)))
        matches = [m for m in QUANTITY.finditer(text, start, end) if depths[m.start()] == 0]
        issue = None
        if len(matches) != 1:
            issue = 'ambiguous_or_missing_quantity_boundary'
        else:
            quantity_start = matches[0].start()
            name_start = start + len(text[start:quantity_start])-len(text[start:quantity_start].lstrip())
            name_end = start + len(text[start:quantity_start].rstrip())
            quantity_end = start + len(text[start:end].rstrip())
            if name_start == name_end or not SUFFIX.fullmatch(text[quantity_start:end]):
                issue = 'empty_name_or_unsupported_quantity_suffix'
            else:
                result['items'].append(dict(entry=ref(start, end), name=ref(name_start, name_end),
                                            quantity=ref(quantity_start, quantity_end)))
        if issue:
            result['issues'].append(dict(span=[start, end], reason=issue))
        if end < len(text):
            result['parts'].append(dict(role='separator', evidence=ref(end, end+1)))
        start = end+1
    result['roundtrip_exact'] = ''.join(p['evidence']['quote'] for p in result['parts']) == text
    result['status'] = 'ready' if result['roundtrip_exact'] and not result['issues'] else 'unresolved'
    return result


def compare_lists(left, right):
    """Exact Unicode names only; keep every occurrence and its original source."""
    result = dict(version=VERSION, relation='literal_name_in_both_lists_not_necessity',
                  condition_state='unreviewed', exception_state='unreviewed')
    if any(row['status'] != 'ready' for row in (left, right)):
        return dict(result, status='unresolved', common=None, only=None)
    groups = []
    for row in (left, right):
        names = {}
        for item in row['items']:
            names.setdefault(item['name']['quote'], []).append(item)
        groups.append(names)
    return dict(result, status='ready', common=[dict(name=name, occurrences=[items, groups[1][name]])
        for name, items in groups[0].items() if name in groups[1]],
        only=[[dict(name=name, occurrences=items) for name, items in group.items() if name not in groups[1-i]]
              for i, group in enumerate(groups)])
