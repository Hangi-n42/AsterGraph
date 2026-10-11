"""Read saved native receipts and emit a local execution audit; never run models."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib, json, sqlite3, subprocess

P = Path(__file__).resolve().parent
W = P.parents[4]
Q = P / 'qa/presentation_exploratory'
load = lambda p: json.loads(Path(p).read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
digest = lambda v: hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
dt = datetime.fromisoformat
kst = lambda t: dt(t).astimezone(ZoneInfo('Asia/Seoul')).isoformat()
git = lambda *args: subprocess.check_output(['git', *args], cwd=W, text=True).strip()
status = load(P / 'qa_continuation_status.json')
assert status['phase'] == 'presentation_qa_finished', status
assert not (P / 'execution_cost_audit.json').exists()
assert not (P / 'execution_cost_audit.md').exists()
build_manifest = load(P / 'source_build_manifest.json')
continuation = load(P / 'qa_continuation_manifest.json')
execution = load(P / 'qa/execution_manifest.json')
snapshot = load(P / 'qa/snapshot_connection.json')
build = load(P / 'build_run.json')
ledger = load(Q / 'execution_ledger.json')
checked = []
for manifest in (build_manifest, continuation):
    for row in manifest['files']:
        actual = sha(row['path'])
        checked.append(dict(path=row['path'], expected=row['sha256'], actual=actual, passed=actual == row['sha256']))
assert all(r['passed'] for r in checked)
for path, expected in [(execution['settings_manifest'], execution['settings_sha256']),
                       (execution['questions_only'], execution['questions_sha256']),
                       (P / 'run_presentation_qa.py', execution['qa_driver_sha256']),
                       (execution['deadline_adapter'], execution['deadline_adapter_sha256']),
                       (P / 'source_build_manifest.json', snapshot['parent_source_build_manifest_sha256'])]:
    assert sha(path) == expected, path
with sqlite3.connect(Path(build_manifest['database']).as_uri() + '?mode=ro', uri=True) as db:
    source = json.loads(db.execute('SELECT payload FROM runs WHERE id=?', (execution['source_run_id'],)).fetchone()[0])
assert digest(source) == execution['source_run_sha256'] == snapshot['source_run_sha256']
pool = load(P / 'qa/source_passage_pool.json')
assert digest({k: dict(text=v['text'], evidence=v['evidence']) for k, v in pool.items()}) == snapshot['source_pool_sha256']
cache = load(Q / 'embedding_cache.json')
assert sha(Q / 'embedding_cache.npz') == cache['npz_sha256']
assert cache['source_run_sha256'] == execution['source_run_sha256']
head = git('rev-parse', 'HEAD')
remote = git('ls-remote', 'origin', 'refs/heads/feature/document-graph-rag-comparison')
assert head == build_manifest['git_head'] == remote.split()[0]
assert ledger['planned_attempts'] == 12 and len(ledger['items']) == 12
assert len(list(Q.glob('*_pair_ready.json'))) == 6


def native_unit(u):
    r = u.get('response') or {}
    raw = r.get('raw_response') or {}
    out = dict(id=u['id'], stage=u['stage'], status=u['status'], error=u.get('error'),
               started_at=u.get('started_at'), finished_at=u.get('finished_at'),
               provider_response=bool(raw), input_budget=u.get('input_budget'),
               requested_limits=u.get('requested_limits'), executed_limits=u.get('executed_limits'))
    if raw:
        out.update(input_tokens=r.get('prompt_eval_count'), output_tokens=r.get('eval_count'),
                   usage_source=r.get('usage_source'), client_elapsed_s=r.get('elapsed_s'),
                   model=r.get('model'), failure_kind=r.get('failure_kind'),
                   done_reason=r.get('done_reason'), provider_cached_input_tokens=raw.get('prompt_eval_cached_count'))
        for key in ('total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration'):
            out['provider_' + key + '_s'] = raw[key] / 1e9 if raw.get(key) is not None else None
    return out


def costs(units):
    native = [u for u in units if u['provider_response']]
    result = dict(records=len(units), provider_responses=len(native), statuses=dict(Counter(u['status'] for u in units)))
    for key in ('input_tokens', 'output_tokens', 'client_elapsed_s', 'provider_total_duration_s',
                'provider_load_duration_s', 'provider_prompt_eval_duration_s', 'provider_eval_duration_s'):
        vals = [u.get(key) for u in native]
        result[key] = sum(vals) if all(v is not None for v in vals) else None
    return result

items, embedding_calls, stages = [], [], defaultdict(list)
for qid in execution['question_order']:
    for arm in ('B', 'C'):
        row = next(r for r in ledger['items'] if r['question_id'] == qid and r['arm'] == arm)
        assert row['status'] == 'response_returned_not_semantically_validated', row
        path = Q / row['result_file']
        x = load(path)
        run = x['run']
        g = run['graph_retrieval']
        units = [native_unit(u) for u in run['units']]
        assert x['comparison_contract'] == 'passed'
        assert digest(run['passage_index']['texts']) == execution['passage_index_sha256']
        assert run['required_context_ids'] == [] and run['query']['requirement_ids'] == []
        assert run['query']['question'] == x['request']['question']
        assert x['actual_provider_responses'] == sum(u['provider_response'] for u in units)
        for u in units:
            stages[(arm, u['stage'])].append(u)
        embeds = []
        for call in x['embedding_calls']:
            kind = 'query_embedding' if call['count'] == 1 else ('shared_passage_initialization' if call['count'] == 3371 else 'c_edge_initialization')
            if kind == 'c_edge_initialization':
                assert call['count'] == 1446 and arm == 'C'
            record = dict(question_id=qid, arm=arm, kind=kind, **call)
            embeds.append(record)
            embedding_calls.append(record)
        graph = {k: g.get(k) for k in ('contract', 'nodes', 'edges', 'passages', 'concept_nodes', 'index_cache_hit',
                 'edge_index_cache_hit', 'index_elapsed_s', 'elapsed_s', 'fallback', 'alpha', 'passage_weight')}
        graph.update(candidate_edge_count=len(g.get('candidate_edge_ids', [])),
                     selected_edge_count=len(g.get('selected_edge_ids', [])), seed_node_count=len(g.get('seed_node_scores', {})),
                     selected_edge_ids=g.get('selected_edge_ids', []), seed_node_ids=list(g.get('seed_node_scores', {})))
        graph['graph_propagation_executed'] = arm == 'C' and bool(graph['seed_node_count'])
        item = dict(question_id=qid, arm=arm, raw_file=str(path), raw_file_sha256=sha(path),
                    original_split=x['original_split'], status=x['execution_outcome'], product_status=x['product_status'],
                    exception=x['exception'], comparison_contract=x['comparison_contract'],
                    started_at=run['started_at'], finished_at=run['finished_at'], observed_at=x['observed_at'],
                    outer_elapsed_s=x['elapsed_s'], product_metrics=run['metrics'],
                    deadline_admission_skips=x['deadline_admission_skips'], graph_retrieval=graph,
                    embeddings=embeds, units=units, native_cost=costs(units))
        assert item['native_cost']['input_tokens'] is not None and item['native_cost']['output_tokens'] is not None
        items.append(item)
assert len(embedding_calls) == len(cache['actual_embedding_calls'])
assert sorted((x['count'], x['input_sha256'], x['elapsed_s']) for x in embedding_calls) == sorted((x['count'], x['input_sha256'], x['elapsed_s']) for x in cache['actual_embedding_calls'])
source_units = [native_unit(u) for u in source['units']]
reused = [native_unit(u) for u in source['units'] if u.get('reused_from')]
fresh = [native_unit(u) for u in source['units'] if not u.get('reused_from')]
start = min(dt(x['started_at']) for x in items)
finish = max(dt(x['finished_at']) for x in items)
arm_totals = {}
for arm in ('B', 'C'):
    xs = [x for x in items if x['arm'] == arm]
    arm_totals[arm] = dict(attempts=len(xs), outer_elapsed_s=sum(x['outer_elapsed_s'] for x in xs),
                          native_cost=costs([u for x in xs for u in x['units']]),
                          graph_retrieval_elapsed_s=sum(x['graph_retrieval']['elapsed_s'] for x in xs),
                          index_elapsed_s=sum(x['graph_retrieval']['index_elapsed_s'] for x in xs),
                          query_embedding_elapsed_s=sum(e['elapsed_s'] for e in embedding_calls if e['arm'] == arm and e['kind'] == 'query_embedding'),
                          deadline_admission_skips=sum(x['deadline_admission_skips'] for x in xs))
initializations = [e for e in embedding_calls if e['kind'] != 'query_embedding']
qa_span = (finish - start).total_seconds()
outer_sum = sum(x['outer_elapsed_s'] for x in items)
audit = dict(version='presentation-execution-cost-audit-v1', audited_at=datetime.now(timezone.utc).isoformat(),
    scope='six pre-exposed exploratory question pairs; emergency_partial_build; execution and cost only; no semantic grading',
    units='seconds; provider-reported token counts; durations converted from provider nanoseconds',
    completion=status, ledger_statuses=dict(Counter(r['status'] for r in ledger['items'])),
    question_order=execution['question_order'],
    timing=dict(first_query_started_at=start.isoformat(), last_query_finished_at=finish.isoformat(),
                qa_run_timestamp_span_s=qa_span, sum_outer_query_elapsed_s=outer_sum,
                span_minus_outer_elapsed_s=qa_span-outer_sum,
                note='Outer timings cover business_use.query. Timestamp span includes between-query recording and model-state reads. Small boundary differences prevent exact attribution of the residual.'),
    arm_totals=arm_totals,
    stage_totals=[dict(arm=a, stage=s, **costs(us)) for (a,s),us in stages.items()],
    initializations=initializations, all_embedding_calls=embedding_calls, items=items,
    graph_execution=dict(c_graph_propagation_count=sum(x['graph_retrieval']['graph_propagation_executed'] for x in items),
                         c_fallbacks=[dict(question_id=x['question_id'], fallback=x['graph_retrieval']['fallback']) for x in items if x['arm']=='C' and x['graph_retrieval']['fallback']]),
    source_build=dict(started_at=source['started_at'], finished_at=source['finished_at'],
        timestamp_wall_s=(dt(source['finished_at'])-dt(source['started_at'])).total_seconds(),
        product_metrics=source['metrics'], reused_extraction_cost=costs(reused), new_concept_cost=costs(fresh),
        fresh_failures=[u for u in fresh if u['status']!='succeeded'],
        unattempted_concepts=snapshot['unattempted_concepts'], unextracted_appendix_blocks=2996,
        additional_extraction_calls=0, graph_completed=False,
        note='Reused extraction costs belong to the selected 52 historical records; they are not new calls or the total historical experimental expenditure.'),
    snapshot_connection=snapshot,
    integrity=dict(local_head=head, remote_head=remote.split()[0], remote_ref=remote.split()[1],
        git_status_porcelain=git('status','--porcelain'), source_build_file_entries=len(build_manifest['files']),
        continuation_file_entries=len(continuation['files']), checked_entries=len(checked),
        unique_checked_paths=len({r['path'] for r in checked}), checks=checked,
        source_run_database_sha256=digest(source), source_pool_sha256=snapshot['source_pool_sha256'],
        passage_index_sha256=execution['passage_index_sha256'], questions_sha256=execution['questions_sha256'],
        settings_sha256=execution['settings_sha256'], cache_npz_sha256=cache['npz_sha256'],
        source_build_manifest_sha256=sha(P/'source_build_manifest.json'),
        qa_continuation_manifest_sha256=sha(P/'qa_continuation_manifest.json'),
        pair_receipts=[dict(path=str(p),sha256=sha(p)) for p in sorted(Q.glob('*_pair_ready.json'))]),
    exclusions=['semantic correctness and scoring', 'full graph completion', 'A baseline', 'original final 26 questions',
                'monetary cost, power and peak memory', 'total historical experiment expenditure'],
    timing_code_references=['app/knowledge/graph_retrieval.py:278-380','presentation_20261012/run_presentation_qa.py:119-129'])
(P/'execution_cost_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')

fmt = lambda n: f'{n:,.3f}' if n is not None else '미기록'
integer = lambda n: f'{n:,}' if n is not None else '미기록'
lines = [
'# 발표용 B/C 실행 및 비용 감사', '',
f"감사 시각: {kst(audit['audited_at'])}. 대상: 사전 노출 탐색 질문 6개, B/C 12회, `emergency_partial_build`.", '',
'6쌍의 원본 응답 저장과 실행 계약 검사가 완료됐다. 이 문서는 호출·시간·토큰·그래프 사용·동결 무결성만 다룬다. `answered`는 응답 반환 상태이며 의미 정확도나 채점 결과가 아니다.', '',
'## 실행 완료와 실제 시간', '',
f"질의 run의 시작·종료 기록 기준으로 {kst(start.isoformat())}부터 {kst(finish.isoformat())}까지 {fmt(qa_span)}초({qa_span/60:.2f}분)가 경과했다. 12회 외부 측정 시간의 합은 {fmt(outer_sum)}초다. 둘의 차이 {fmt(qa_span-outer_sum)}초에는 질의 사이 저장 및 모델 상태 조회 등이 포함되며, 타이머 경계가 달라 각 작업의 시간으로 정확히 분해할 수 없다.", '',
'| 방식 | 완료 요청 | Native 응답 | 입력 토큰 | 출력 토큰 | 호출 측정 합계 초 | 질의 외부 측정 합계 초 |',
'|---|---:|---:|---:|---:|---:|---:|']
for arm,t in arm_totals.items():
    c=t['native_cost'];lines.append(f"| {arm} | {t['attempts']} | {c['provider_responses']} | {integer(c['input_tokens'])} | {integer(c['output_tokens'])} | {fmt(c['client_elapsed_s'])} | {fmt(t['outer_elapsed_s'])} |")
lines += ['', 'B는 질문마다 답변 호출 1회, C는 관계 선택과 답변 호출 각 1회를 실행했다. QA 실패·미시도·마감에 따른 신규 요청 차단은 모두 0건이다. 비교 계약 검사는 12/12 통과했다.', '',
'## 공통 초기화와 C 전용 초기화', '',
'| 포함된 요청 | 비용 구분 | 임베딩 대상 수 | 임베딩 측정 초 | 같은 요청의 인덱스 준비 전체 초 |',
'|---|---|---:|---:|---:|']
for e in initializations:
    item=next(x for x in items if x['question_id']==e['question_id'] and x['arm']==e['arm'])
    label='B/C 공통 passage 최초 임베딩' if e['kind']=='shared_passage_initialization' else 'C 전용 edge 최초 임베딩'
    lines.append(f"| {e['question_id']}-{e['arm']} | {label} | {e['count']:,} | {fmt(e['elapsed_s'])} | {fmt(item['graph_retrieval']['index_elapsed_s'])} |")
lines += ['',
'공통 passage 캐시는 첫 B에서 생성되어 이후 11회에 재사용됐다. C의 edge 캐시는 첫 C에서 생성되어 이후 C 5회에 재사용됐다. 첫 임베딩 측정에는 임베딩 함수 내부 초기화가 포함되며, 모델 로드만의 시간은 따로 계측하지 않았다. `index_elapsed_s`는 그래프 구성·검색 텍스트 준비·캐시 처리·필요한 임베딩까지 포함한다. 임베딩 시간과 인덱스 준비 시간을 더하면 중복 계산이다.', '',
'질문 임베딩은 12회 별도로 실행됐다. B 합계 '+fmt(arm_totals['B']['query_embedding_elapsed_s'])+'초, C 합계 '+fmt(arm_totals['C']['query_embedding_elapsed_s'])+'초다. 초기 비용을 뺀 값을 별도 측정한 warm 성능으로 제시하지 않는다.', '',
'## 요청별 측정', '',
'| 질문 | 방식 | 외부 측정 초 | 검색 전체 초 | 인덱스 준비 초 | Native 호출 초 | 입력 토큰 | 출력 토큰 |',
'|---|---|---:|---:|---:|---:|---:|---:|']
for x in items:
    g=x['graph_retrieval'];c=x['native_cost'];lines.append(f"| {x['question_id']} | {x['arm']} | {fmt(x['outer_elapsed_s'])} | {fmt(g['elapsed_s'])} | {fmt(g['index_elapsed_s'])} | {fmt(c['client_elapsed_s'])} | {integer(c['input_tokens'])} | {integer(c['output_tokens'])} |")
lines += ['',
'검색 전체 시간은 인덱스 준비와 질문 임베딩을 포함하고, C에서는 관계 선택 native 호출도 포함한다. Native 호출 합계에는 관계 선택과 답변이 포함되므로 검색 시간에 그대로 더하지 않는다. 외부 시간은 `business_use.query` 호출 구간이며, 검색·모델 외 원문 구성 및 저장 등의 작업도 포함한다. 각 질문의 원문 입력량과 출력량이 달라 순수 검색 알고리즘 속도 비교로 해석할 수 없다.', '',
'## Native 단계별 토큰과 시간', '',
'| 방식·단계 | 응답 수 | 입력 토큰 | 출력 토큰 | 클라이언트 측정 초 | Provider 전체 초 | 로드 초 | 입력 평가 초 | 출력 생성 초 |',
'|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for c in audit['stage_totals']:
    lines.append('| '+c['arm']+' '+c['stage']+' | '+str(c['provider_responses'])+' | '+integer(c['input_tokens'])+' | '+integer(c['output_tokens'])+' | '+' | '.join(fmt(c[k]) for k in ['client_elapsed_s','provider_total_duration_s','provider_load_duration_s','provider_prompt_eval_duration_s','provider_eval_duration_s'])+' |')
lines += ['',
'토큰은 Ollama의 `prompt_eval_count`와 `eval_count`를 그대로 합산했다. 입력 예산 추정치와 구분한다. Provider 시간은 raw response의 나노초 값을 초로 변환했으며, 클라이언트 측정 시간과 범위가 다르다. 전체 시간과 내부 단계 시간은 중첩되며, 차액을 특정 작업 비용으로 단정하지 않는다.', '',
'## C의 실제 그래프 사용', '',
'| 질문 | 후보 edge | 선택 edge | seed node | 그래프 전파 실행 | fallback |',
'|---|---:|---:|---:|---|---|']
for x in items:
    if x['arm']!='C':continue
    g=x['graph_retrieval'];lines.append(f"| {x['question_id']} | {g['candidate_edge_count']} | {g['selected_edge_count']} | {g['seed_node_count']} | {'예' if g['graph_propagation_executed'] else '아니요'} | {g['fallback'] or '없음'} |")
lines += ['',
f"C의 seed가 있는 그래프 전파는 {audit['graph_execution']['c_graph_propagation_count']}/6회, fallback은 {len(audit['graph_execution']['c_fallbacks'])}회다. 저장 trace와 `rank`의 seed 조건으로 실행 경로를 확인했다. 이는 선택 관계의 의미 정확성이나 그래프의 답변 개선 효과를 입증하지 않는다.", '',
'스냅샷은 검색 passage 3,371개, 임베딩 대상 edge fact 1,446개다. 검색 그래프 trace는 node 4,129개, graph edge 2,022개, concept node 501개를 기록했다. edge fact와 검색 그래프의 edge 수는 서로 다른 계수다. B에도 공통 스냅샷 구성 정보가 기록되지만 B의 순위는 BM25·dense RRF이며 그래프 전파를 실행하지 않는다.', '',
'## 구축 비용과 남은 실패', '',
f"발표용 개념화 run은 {kst(source['started_at'])}부터 {kst(source['finished_at'])}까지 {fmt(audit['source_build']['timestamp_wall_s'])}초가 걸렸다. 신규 추출 호출은 0회다.", '',
'| 비용 범위 | 기록 수 | Native 응답 | 입력 토큰 | 출력 토큰 | 클라이언트 호출 합계 초 |',
'|---|---:|---:|---:|---:|---:|']
for label,c in [('재사용한 기존 추출 13개 chunk',costs(reused)),('발표 범위 신규 개념화',costs(fresh))]:
    lines.append(f"| {label} | {c['records']} | {c['provider_responses']} | {integer(c['input_tokens'])} | {integer(c['output_tokens'])} | {fmt(c['client_elapsed_s'])} |")
lines += ['',
'기존 추출은 성공 46건과 truncated 실패 6건을 그대로 보존했다. 이 52개 기록의 비용은 기존에 지출한 선택 범위 비용으로, 이번 신규 호출 비용이나 전체 과거 실험 비용이 아니다.', '',
'개념화 289개 대상 중 288개는 native 응답을 받았고, 1개는 `input_capacity`로 호출 전에 실패했다. 해당 입력 예산 추정치는 98,825로 설정 context 49,152를 초과했다. 개념화 미시도는 0개지만 별표 원문 2,996개 block은 추출되지 않았다. 따라서 3,364개 원문 block 전체의 검색 가능성과 그래프 구축 완료는 구분해야 하며 `graph_completed=false`를 유지한다.', '',
'## 동결 무결성', '',
f"구축 manifest {len(build_manifest['files'])}개 항목과 QA continuation manifest {len(continuation['files'])}개 항목, 총 {len(checked)}개 파일 검사를 통과했다. 질문·설정·driver·deadline adapter·공통 passage index·저장 cache·read-only DB의 source run 해시도 일치했다. 12회 모두 같은 passage index를 사용했다.", '',
f"로컬 HEAD와 원격 `feature/document-graph-rag-comparison` HEAD는 `{head}`로 같다. 검사 시 tracked/untracked Git 상태 출력은 비어 있었다. 감사 결과는 gitignored 로컬 파일로 저장하며 이 감사 보고서는 커밋하지 않았다.", '',
'| 대상 | SHA-256 또는 Git HEAD |', '|---|---|']
for label,key in [('Source run','source_run_database_sha256'),('Passage index','passage_index_sha256'),('질문','questions_sha256'),('설정','settings_sha256'),('Source build manifest','source_build_manifest_sha256'),('QA continuation manifest','qa_continuation_manifest_sha256'),('Embedding cache','cache_npz_sha256')]:
    lines.append(f"| {label} | `{audit['integrity'][key]}` |")
lines += ['', '## 근거 파일과 해석 범위', '',
'원본 질문별 응답과 usage는 [QA 기록 디렉터리]('+str(Q)+'), 구축 연결은 [snapshot_connection.json]('+str(P/'qa/snapshot_connection.json')+'), 정확한 수치·단계별 기록·검사 목록은 [execution_cost_audit.json]('+str(P/'execution_cost_audit.json')+')에 있다. [집계 스크립트]('+str(Path(__file__).resolve())+')는 저장 파일과 read-only SQLite만 읽고 모델을 호출하지 않는다.', '',
'이 결과는 사전 노출된 탐색 6문항과 부분 구축 범위에 한정된다. 의미 채점, A 방식, 원래 final 26문항, 완성 그래프 비교, 금액·전력·최대 메모리는 포함하지 않는다. 의미 채점과 발표 결론은 총괄 보고서에서 별도로 판단한다.', '',
'다음 단계는 총괄의 의미 평가 및 발표 보고서와 이 실행 감사의 수치를 대조하는 것이다. 현재 사용자 결정이 필요한 사항 없음.', '']
(P/'execution_cost_audit.md').write_text('\n'.join(lines))
print(json.dumps(dict(report=str(P/'execution_cost_audit.md'),json=str(P/'execution_cost_audit.json'),
                     timing=audit['timing'],arm_totals=arm_totals,graph_execution=audit['graph_execution'],
                     checked_entries=len(checked),local_head=head,remote_head=remote.split()[0]),ensure_ascii=False,indent=2))
