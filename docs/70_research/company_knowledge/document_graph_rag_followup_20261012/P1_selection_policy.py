"""One fixed, source-blind rule for explicitly numbered request coverage."""
import re

def numbered_question_parts(question):
    markers = list(re.finditer(r'(?<!\d)(\d+)\.(?!\d)', question))
    if len(markers) < 2 or [int(m.group(1)) for m in markers] != list(range(1, len(markers)+1)):
        return []
    parts = [question[m.end():markers[i+1].start() if i+1 < len(markers) else len(question)].strip()
             for i, m in enumerate(markers)]
    return parts if all(parts) else []

def interleave_rankings(original, item_rankings):
    by_id = {row['block_id']: row for row in original}
    groups = [original, *item_rankings]
    result, seen = [], set()
    for position in range(max(map(len, groups))):
        for number, rows in enumerate(groups):
            if position < len(rows) and rows[position]['block_id'] not in seen:
                cid = rows[position]['block_id']
                seen.add(cid)
                result.append(dict(by_id[cid], query_group=number, query_group_rank=position+1))
    return result
