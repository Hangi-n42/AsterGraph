"""Fixed policy, model-free reader-input comparison; no evaluator is consumed."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from app.knowledge import graph_retrieval as gr, autoschema
from app.knowledge.discovery_profile import FrozenIndex
from P1_selection_policy import numbered_question_parts, interleave_rankings

ROOT = Path('/Users/hyeongi/.codex/worktrees/document-graph-rag-comparison/Civil-Complaints-System')
BASE = ROOT/'data/knowledge/evaluations/document_graph_rag_20261012/presentation_20261012/qa'
OUT = Path('/private/tmp/rag-followup-20261012')
digest = lambda v: hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
pool = json.loads((BASE/'source_passage_pool.json').read_text())
source = json.loads((OUT/'source_snapshot_readonly.json').read_text())
blocks = source['blocks']
gr.reader_locator = lambda block: autoschema.source_packet([block])[0].get('locator',{})
candidates = gr.passage_candidates(pool)
first = json.loads((BASE/'presentation_exploratory/ACT501070_B.json').read_text())
texts = first['run']['passage_index']['texts']
assert digest(texts) == '75bc2ec8519c6445e59c955e911d44919edbbdd5b501681eef383e9b6c7a0ddd'
question = first['request']['question']
parts = numbered_question_parts(question)
assert len(parts)==2 and all(part in question for part in parts)
index = FrozenIndex([dict(id=p['id'],file_id=p['evidence']['source_version_id'],text=texts[p['id']]) for p in pool.values()],preserve_numbers=True)
item_rankings = [index.rank(part,set(pool)) for part in parts]
policy = dict(version='literal-numbered-requests-round-robin-v1', ordered_groups=['original_arm_ranking','verbatim_request1_bm25','verbatim_request2_bm25'],
    rule='one row per rank position per group; skip already seen passage IDs; then existing exact source-bundle redundancy selection',
    selected_limit=12, source_budget=16384, policy_code_sha256=hashlib.sha256((OUT/'P1_selection_policy.py').read_bytes()).hexdigest(),
    gold_or_required_evidence_used=False, prompt_rewriting=False, new_model_calls=0)
(OUT/'P1_policy_frozen_before_selection.json').write_text(json.dumps(policy,ensure_ascii=False,indent=2)+'\n')
receipt=dict(policy=policy,question_sha256=hashlib.sha256(question.encode()).hexdigest(),parts=parts,arms={},new_model_calls=0,P2_native_location_changes=False)
for arm in ['B','C']:
    row=json.loads((BASE/f'presentation_exploratory/ACT501070_{arm}.json').read_text());r=row['run'];options=r['recipe']['options']
    original=[dict(block_id=h['id'],file_id=h['evidence']['source_version_id'],score=h['score'],selection_reason=row['request']['retrieval']) for h in r['graph_retrieval']['ranked_passages']]
    old_hits,old_trace=gr.select_passages(candidates,original,blocks,options,12)
    assert old_hits==r['retrieval'],arm+' baseline selection replay differs'
    merged=interleave_rankings(original,item_rankings)
    hits,trace=gr.select_passages(candidates,merged,blocks,options,12)
    selected={h['block_id'] for h in hits}
    context=[{k:v for k,v in c.items() if k!='linked_claim_ids'} for c in deepcopy(candidates) if c['id'] in selected]
    source_context=gr.source_context(blocks,context,options)
    body=dict(context=context,source_context=source_context)
    estimate=(len(json.dumps(body,ensure_ascii=False).encode())+1)//2
    assert all('block_order' not in c.get('locator',{}) and 'element_path' not in c.get('locator',{}) for c in context+source_context)
    receipt['arms'][arm]=dict(selected=hits,trace=trace,body=body,reader_source_sha256=digest(body),source_context_budget_estimate=estimate,
        within_original_source_budget=estimate<=16384,baseline_selected_exactly_replayed=True)
    print(arm,'new selected source texts:',[pool[h['block_id']]['text'] for h in hits],flush=True)
    print(arm,'budget',estimate,'of16384',flush=True)
(OUT/'P1_offline_selection.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
for q in ['SUP01','SUP03','SUP02']:
    row=json.loads((BASE/f'presentation_exploratory/{q}_B.json').read_text())
    assert not numbered_question_parts(row['request']['question'])
print('Normal controls have no numbered request split; unchanged ranking and context policy. No QA, query-embedding or edge-filter calls.')
