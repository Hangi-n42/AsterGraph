"use client";

import { useEffect, useState } from "react";
import { knowledgeRequest as request, knowledgeDate, knowledgeLabels, knowledgeVersionName, unchangedSourceFields, type KnowledgeScope, type KnowledgeVersion } from "@/lib/knowledgeWorkbench";
import styles from "./KnowledgeWorkbench.module.css";

type Impact = { requirement_id: string; status: string; reason: string };
type SourceDelta = { id?: string; kind?: string; key?: string[]; before: unknown; after: unknown; before_block_id?: string; after_block_id?: string; fields?: { field: string; before: unknown; after: unknown }[] };
type RebuildPlan = { id: string; status: string; created_at?: string; before_version: KnowledgeVersion; after_version: KnowledgeVersion; action_counts: Record<string, number>; source_comparison: Record<'before' | 'after', { status: string; blocks: { text: string }[]; reason?: string }>; requirement_discovery: { candidate_ids?: string[]; unselected_review_ids?: string[] }; execution_scopes: KnowledgeScope[]; review_scopes: KnowledgeScope[]; snapshots: KnowledgeScope[]; unavailable_run_ids: string[] };
type ChangeView = { versions: { id: string; title?: string; supersedes_version_id?: string }[]; requirements: { id: string; question: string; status: string; revision: number }[]; snapshot_review_requirement_ids: string[]; rebuild_plans?: RebuildPlan[]; records: { id: string; status: string; created_at?: string; before_version_id: string; after_version_id: string; before_version: KnowledgeVersion; after_version: KnowledgeVersion; diff?: { comparison: string; changes: SourceDelta[]; unchanged?: SourceDelta[] }; impacts: Impact[]; after_scopes: KnowledgeScope[] }[]; edit_impact?: { items?: Impact[]; related_requirement_ids?: string[]; candidate_requirement_ids?: string[]; pending_requirement_ids?: string[] } };
const rebuildActions: Record<string, string> = { preserve: '기존 지식 보존', rebuild_source: '변경 자료 재구축', rebind_row: '같은 행의 새 주소 연결', rebuild_row: '변경 행 재구축', add_row: '새 행 구축', remove: '변경 후 제외' };
function sourceText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(v => typeof v === 'object' && v && 'text' in v ? String(v.text) : sourceText(v)).join('\n');
  return value == null ? '기록 없음' : JSON.stringify(value, null, 2);
}
export default function KnowledgeChanges({ scope, onOpen, onOpenScope }: { scope: KnowledgeScope; onOpen?: () => void; onOpenScope?: (key: string) => void }) {
  const scopeKey = `${scope.kind}:${scope.id}`;
  const [view, setView] = useState<(ChangeView & { scope_key: string }) | null>(null);
  const [error, setError] = useState<{ scope_key: string; message: string } | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    request<ChangeView>(`/workbench/changes?${new URLSearchParams({ kind: scope.kind, scope_id: scope.id })}`, { signal: abort.signal })
      .then(value => { if (!abort.signal.aborted) { setView({ ...value, scope_key: scopeKey }); setError(null); } })
      .catch(e => { if (!abort.signal.aborted) setError({ scope_key: scopeKey, message: e.message }); });
    return () => abort.abort();
  }, [scope.kind, scope.id, scopeKey]);
  if (error?.scope_key === scopeKey) return <p role="alert" className={styles.error}>{error.message}</p>;
  if (!view || view.scope_key !== scopeKey) return <p role="status" className={styles.muted}>변경·재검토 기록을 확인하고 있습니다…</p>;
  const rebuilds = view.rebuild_plans || [];
  if (onOpen) return <div className={styles.changeSummary}><button className={styles.textLink} onClick={onOpen}>원문 변경·영향 기록 {view.records.length}건 · 부분 재구축 계획 {rebuilds.length}건 · {scope.kind === 'source_graph' ? `이 지식 버전의 변경 후 재검토 요구 ${view.snapshot_review_requirement_ids.length}건 · ` : ''}현재 원장의 재검토 필요 요구 {view.requirements.filter(r => r.status === 'needs_review').length}건 →</button><p className={styles.muted}>선택 지식 버전의 변경 제한과 현재 원장의 요구 상태를 구분합니다.</p></div>;
  return <section className={styles.savedAnswers}><h3>원문 버전 변경과 영향</h3><p className={styles.muted}>저장된 비교·영향 결과와 부분 재구축 이력을 읽습니다. 새 평가를 실행하지 않습니다.</p>
    {!view.records.length && !rebuilds.length && <p className={styles.empty}>이 선택 범위에 연결된 원문 버전 비교·영향 결과나 부분 재구축 계획이 없습니다.</p>}
    {rebuilds.map(plan => <section key={plan.id} className={styles.claim}>
      <h4>부분 재구축 계획 · {knowledgeDate(plan.created_at)}</h4>
      <p>변경 전: {knowledgeVersionName(plan.before_version)}<br />변경 후: {knowledgeVersionName(plan.after_version)}</p>
      <dl>{Object.entries(plan.action_counts).map(([action, count]) => <div key={action}><dt>{rebuildActions[action] || action}</dt><dd>{count}개</dd></div>)}</dl>
      <p className={styles.muted}>계획에 기록된 처리 대상 수입니다. 실제 실행 결과·의미 검수·사용 승인은 아래 기록에서 각각 확인하세요.</p>
      <details><summary>계획 당시 원문 비교</summary>{(['before', 'after'] as const).map(side => <div key={side}>
        <h4>{side === 'before' ? '변경 전' : '변경 후'}</h4>{plan.source_comparison[side].status === 'available'
          ? <pre className={styles.prewrap}>{sourceText(plan.source_comparison[side].blocks)}</pre>
          : <p className={styles.warning}>계획 당시 원문 확인 불가 · {plan.source_comparison[side].reason}</p>}
      </div>)}</details>
      <p>출처 연결에 따른 재검토 후보: {plan.requirement_discovery.candidate_ids?.map(id => view.requirements.find(r => r.id === id)?.question || id).join(' / ') || '기록 없음'}</p>
      <p className={styles.muted}>후보 연결은 업무 영향이나 요구 충족의 확정 판정이 아닙니다.</p>
      {([['execution_scopes', '재구축 실행'], ['review_scopes', '후속 검토·재검수'], ['snapshots', '별도 확정한 사용 버전']] as const).map(([key, label]) => <div key={key}>
        <h4>{label} · {plan[key].length}건</h4>{!plan[key].length && <p>연결된 저장 기록을 확인할 수 없습니다.</p>}
        {plan[key].map(s => <p key={`${s.kind}:${s.id}`}>{knowledgeDate(s.created_at)} · {knowledgeLabels[s.status] || s.status}{s.kind === 'source_graph' && ' · 별도 선택 기록'} {onOpenScope && <button className={styles.textLink} onClick={() => onOpenScope(`${s.kind}:${s.id}`)}>{label} 내용과 현재 상태 확인 →</button>}</p>)}
      </div>)}
      {!!plan.unavailable_run_ids.length && <p className={styles.warning}>계획과 실행·원문 버전의 연결을 확인할 수 없는 기록 {plan.unavailable_run_ids.length}건이 있습니다.</p>}
      <details className={styles.diagnostics}><summary>부분 재구축 계획 식별자</summary><p>{plan.id} · 저장 상태 {plan.status}</p><p>연결 확인 불가: {plan.unavailable_run_ids.join(' / ') || '없음'}</p></details>
    </section>)}
    {view.records.map(r => <section key={r.id} className={styles.claim}><h4>{knowledgeDate(r.created_at)} · {knowledgeLabels[r.status] || r.status}</h4><p>원문 변경 전: {knowledgeVersionName(r.before_version)}<br />변경 후: {knowledgeVersionName(r.after_version)}</p>{r.diff?.changes.map((c, n) => { const same = unchangedSourceFields(c.before, c.after); return <div key={c.id || n}><h4>변경된 원문 행 {c.key?.join(' · ')}</h4>{!!c.fields?.length && <dl>{c.fields.map(f => <div key={f.field}><dt>{f.field}</dt><dd>{sourceText(f.before)} → {sourceText(f.after)}</dd></div>)}</dl>}{same.length > 0 && <><h4>전후 같은 값 · {same.length}개 필드</h4><dl>{same.map(f => <div key={f.field}><dt>{f.field}</dt><dd>{sourceText(f.value)}</dd></div>)}</dl><p className={styles.muted}>값의 동일 여부와 업무 영향 판단은 별도입니다.</p></>}<details><summary>변경 전후 원문 전체</summary><h4>변경 전</h4><pre className={styles.prewrap}>{sourceText(c.before)}</pre><h4>변경 후</h4><pre className={styles.prewrap}>{sourceText(c.after)}</pre><p className={styles.muted}>원문 구간 {c.before_block_id || '미기록'} → {c.after_block_id || '미기록'}</p></details></div>; })}<h4>저장된 영향 판단</h4>{r.impacts.length ? r.impacts.map((i,n) => <div key={n}><p><strong>{view.requirements.find(q => q.id === i.requirement_id)?.question || i.requirement_id}</strong> · {knowledgeLabels[i.status] || i.status}</p><p>{i.reason}</p></div>) : <p>영향 판단 미기록</p>}
      {!!r.diff?.unchanged?.length && <details><summary>값이 유지된 원문 행 · {r.diff.unchanged.length}건</summary><p className={styles.muted}>저장된 원문 비교의 동일 기록입니다. 각 업무 요구의 영향 판단과 구분합니다.</p>{r.diff.unchanged.map((c,n) => <details key={c.key?.join(':') || n}><summary>원문 행 {c.key?.join(' · ') || n + 1}</summary><h4>변경 전</h4><pre className={styles.prewrap}>{sourceText(c.before)}</pre><h4>변경 후</h4><pre className={styles.prewrap}>{sourceText(c.after)}</pre></details>)}</details>}
      {!!r.after_scopes?.length && <><h4>변경 후 원문이 포함된 저장 결과</h4>{r.after_scopes.map(s => <p key={`${s.kind}:${s.id}`}>{s.version_files?.length ? s.version_files.map(knowledgeVersionName).join(' / ') : s.title} · {knowledgeDate(s.created_at)} · {knowledgeLabels[s.status] || s.status}{onOpenScope && <button className={styles.textLink} onClick={() => onOpenScope(`${s.kind}:${s.id}`)}>내용과 현재 상태 확인 →</button>}</p>)}</>}
      <details className={styles.diagnostics}><summary>원문 버전·변경 실행 식별자</summary><p>변경 실행 {r.id}</p><p>원문 변경 전 {r.before_version_id} → 변경 후 {r.after_version_id}</p><p>저장 비교 방식 {r.diff?.comparison || '미기록'}</p></details>
    </section>)}
    {view.edit_impact && <section className={styles.claim}><h3>이 실행의 문장 수정 영향 기록</h3>{view.edit_impact.items?.length ? view.edit_impact.items.map((i,n) => <p key={n}>{i.requirement_id} · {knowledgeLabels[i.status] || i.status} · {i.reason}</p>) : <p>확정된 영향 판단이 저장되지 않았습니다.</p>}<p className={styles.muted}>관련 요구 {view.edit_impact.related_requirement_ids?.length ?? '미확인'}개 · 영향 후보 {view.edit_impact.candidate_requirement_ids?.length ?? '미확인'}개. 후보 수는 실제 영향 확정 수가 아닙니다.</p></section>}
    <h3>선택 범위·저장 변경에 연결된 업무 요구 · {view.requirements.length}건</h3><p className={styles.muted}>선택 결과·변경 기록의 요구 ID 또는 출처 등록에 명시된 연결입니다. 현재 원장의 상태와 이 지식 버전의 변경 제한은 다릅니다.</p>{!view.requirements.length && <p>명시적으로 연결된 요구 기록을 확인할 수 없습니다. 업무 요구가 없다는 뜻은 아닙니다.</p>}{view.requirements.map(r => <div key={r.id} className={styles.claim}><p>{r.question}</p><span className={styles.badge}>{r.status === 'partial' ? '일부 미완료' : knowledgeLabels[r.status] || r.status}</span>{view.snapshot_review_requirement_ids.includes(r.id) && <p className={styles.warning}>이 지식 버전으로 답변하려면 원문 변경 후 재검토가 필요합니다.</p>}<span className={styles.muted}> · 요구 버전 {r.revision}</span></div>)}
    <details className={styles.diagnostics}><summary>선택한 원문 버전과 후속 관계</summary>{view.versions.map(v => <p key={v.id}>{v.title} · {v.id} · 이전 버전 {v.supersedes_version_id || '연결 기록 없음'}</p>)}</details>
  </section>;
}
