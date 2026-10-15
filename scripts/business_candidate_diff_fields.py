"""Candidate character spans, including absent string paths in unequal arrays."""
import difflib
from itertools import combinations

from compare_business_candidate_text_diff import NOTE
from compare_business_modality_spans import raw_fields


def character_diff(candidates):
    pairs=[]
    for x,y in combinations(candidates,2):
        left,right=dict(raw_fields(candidates[x])),dict(raw_fields(candidates[y]))
        fields,identical=[],[]
        for field in dict.fromkeys([*left,*right]):
            exists={x:field in left,y:field in right}
            a,b=left.get(field,''),right.get(field,'')
            if all(exists.values()) and a==b:
                identical.append(field);continue
            segments=[dict(op=op,**{x:[i,j,a[i:j]],y:[k,l,b[k:l]]})
                      for op,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes()]
            item=dict(field=field,segments=segments)
            if not all(exists.values()):item['string_path_present']=exists
            fields.append(item)
        pairs.append(dict(candidates=[x,y],identical_string_fields=identical,fields=fields))
    return dict(offsets='Python Unicode code points, [start,end)',interpretation_note=NOTE,pairs=pairs)
