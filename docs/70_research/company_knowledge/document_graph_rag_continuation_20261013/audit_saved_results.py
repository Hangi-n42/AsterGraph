"""Audit saved P3/P4 records without model calls or evaluator-driven inputs."""
import hashlib
import json
from pathlib import Path

ROOT = Path('/Users/hyeongi/.codex/worktrees/document-graph-rag-comparison/Civil-Complaints-System')
DATA = ROOT / 'data/knowledge/evaluations/document_graph_rag_continuation_v1'
OUTPUT = Path('/private/tmp/rag-continuation-diagnostic/final_audit.json')
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
digest = lambda v: hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

phases = {
    'P3_selection': [DATA / 'P3' / f'ACT501070_{a}_selection.json' for a in 'BC'],
    'P3_current_baseline': [DATA / 'P3_current_baseline' / f'ACT501070_{a}_qa.json' for a in 'BC'],
    'P3_selected_QA': [DATA / 'P3' / f'ACT501070_{a}_qa.json' for a in 'BC'],
    'P4_target': [DATA / 'P4' / f'SUP02_{a}_qa.json' for a in 'BC'],
    'P4_normal_controls': [DATA / 'P4' / f'SUP0{i}_{a}_qa.json' for i in [1, 3] for a in 'BC'],
    'P4_gap_current_baseline': [DATA / 'P4_current_baseline' / 'ACT501108_B_qa.json'],
    'P4_gap_bundle': [DATA / 'P4_gap_B' / 'ACT501108_B_qa.json'],
}

def summed(rows, key):
    values = [r[key] for r in rows]
    return sum(values) if all(v is not None for v in values) else None

results = {}
all_native = []
for phase, paths in phases.items():
    rows = []
    phase_native = []
    for path in paths:
        saved = read(path)
        run = saved['run']
        native, reused = [], []
        for unit in run['units']:
            response = unit.get('response')
            if not response:
                continue
            if unit.get('reused_from'):
                reused.append(dict(id=unit['id'], stage=unit['stage'], reused_from=unit['reused_from']))
                continue
            raw = response.get('raw_response', {})
            record = dict(run_id=run['id'], unit_id=unit['id'], stage=unit['stage'],
                status=unit['status'], failure_kind=response.get('failure_kind'),
                done_reason=response.get('done_reason'), input_tokens=response.get('prompt_eval_count'),
                output_tokens=response.get('eval_count'), request_elapsed_s=response.get('elapsed_s'),
                provider_cached_input_tokens=raw.get('prompt_eval_cached_count'),
                provider_load_duration_ns=raw.get('load_duration'),
                raw_response_sha256=digest(raw), messages_sha256=digest(unit['messages']),
                schema_sha256=digest(unit['schema']), input_budget=unit.get('input_budget'),
                executed_limits=unit.get('executed_limits'))
            native.append(record)
        assert len(native) == 1, (phase, path, len(native))
        assert run['metrics']['llm_calls'] == 1
        if phase == 'P3_selected_QA':
            assert len(reused) == 1 and reused[0]['stage'] == 'source_passage_selection'
        else:
            assert not reused
        row = dict(case=saved['case'], file=str(path.relative_to(ROOT)), sha256=sha(path),
            run_id=run['id'], run_status=run['status'], result=saved.get('result'),
            outer_elapsed_s=saved['elapsed_s'], service_elapsed_s=run['metrics'].get('elapsed_s'),
            source_context_budget=run.get('source_context_budget'), native=native, exact_reused_units=reused,
            retrieval_reuse=run.get('retrieval_reuse'), contract_sha256=saved['contract_sha256'])
        if 'source_selection' in run:
            row['source_selection'] = run['source_selection']
        rows.append(row)
        phase_native.extend(native)
    all_native.extend(phase_native)
    results[phase] = dict(rows=rows, native_calls=len(phase_native),
        input_tokens=summed(phase_native, 'input_tokens'), output_tokens=summed(phase_native, 'output_tokens'),
        request_elapsed_s=summed(phase_native, 'request_elapsed_s'),
        outer_elapsed_s=sum(r['outer_elapsed_s'] for r in rows),
        provider_cached_input_tokens=summed(phase_native, 'provider_cached_input_tokens'),
        exact_reused_units=sum(len(r['exact_reused_units']) for r in rows))

assert len(all_native) == 14
assert all(r['status'] == 'succeeded' and r['failure_kind'] is None for r in all_native)
guard = read(ROOT / 'docs/70_research/company_knowledge/document_graph_rag_followup_20261012/preservation_manifest.json')['original_guard']
checks = [dict(**row, current_sha256=sha(Path(row['path']))) for row in guard['files']]
assert len(checks) == 16 and all(r['current_sha256'] == r['sha256'] for r in checks)
contracts = {}
for scope in ['P3', 'P3_current_baseline', 'P3_controls', 'P4', 'P4_current_baseline', 'P4_gap_B']:
    path = DATA / scope / 'input_contract.json'
    c = read(path)
    contracts[scope] = dict(path=str(path.relative_to(ROOT)), sha256=sha(path),
        cases={key: {k: v for k, v in value.items() if not k.endswith('_request')} for key, value in c['cases'].items()},
        driver_sha256=c['driver_sha256'], model_digest=c['model_digest'], code=c['code'])
path = DATA / 'P3/qa_contract_after_selection.json'
contracts['P3_QA_after_selection'] = dict(path=str(path.relative_to(ROOT)), sha256=sha(path))
output = dict(version='p3-p4-saved-native-audit-v1', start_head='ade0185c5de6ca14e4ddfd872c4af57bf5ce534b',
    phase_costs=results, total=dict(native_calls=len(all_native), input_tokens=summed(all_native, 'input_tokens'),
        output_tokens=summed(all_native, 'output_tokens'), request_elapsed_s=summed(all_native, 'request_elapsed_s'),
        provider_cached_input_tokens=summed(all_native, 'provider_cached_input_tokens'),
        exact_reused_selector_units=2, model_failures=0, model_retries=0,
        new_search_calls=0, new_embedding_calls=0, new_edge_filter_calls=0),
    original_guard=checks, contracts=contracts, P3_decision='rejected_by_coordinator',
    P4_decision='default_and_product_opt_in_on_hold; frozen_research_only',
    control_C_not_executed=read(DATA / 'P4_current_baseline/ACT501108_C_prepare_failure.json')['result'],
    limitations=['Development-exposed fixed cases; no generalization or graph superiority claim.',
        'Provider-reported cache and durations are observations, not independent causal controls.',
        'Capture termination and source-capacity preflight are not native model failures.',
        'This audit computes receipts; semantic decisions require direct source/output comparison.'])
OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: {x: v for x, v in row.items() if x != 'rows'} for k, row in results.items()}, ensure_ascii=False))
print('TOTAL', json.dumps(output['total'], ensure_ascii=False))
print('AUDIT', str(OUTPUT), sha(OUTPUT))
