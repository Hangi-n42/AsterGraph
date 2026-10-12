"use client";

import { useEffect, useState } from "react";
import { knowledgeRequest as request, knowledgeDate, knowledgeLabels, type KnowledgeScope } from "@/lib/knowledgeWorkbench";
import styles from "./KnowledgeWorkbench.module.css";

type Impact = { requirement_id: string; status: string; reason: string };
type ChangeView = { versions: { id: string; title?: string; supersedes_version_id?: string }[]; requirements: { id: string; question: string; status: string; revision: number }[]; records: { id: string; status: string; created_at?: string; before_version_id: string; after_version_id: string; diff?: { comparison: string; changes: { id: string; kind: string; before: unknown; after: unknown }[] }; impacts: Impact[] }[]; edit_impact?: { items?: Impact[]; related_requirement_ids?: string[]; candidate_requirement_ids?: string[]; pending_requirement_ids?: string[] } };
function sourceText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(v => typeof v === 'object' && v && 'text' in v ? String(v.text) : sourceText(v)).join('\n');
  return value == null ? '기록 없음' : JSON.stringify(value, null, 2);
}
export default function KnowledgeChanges({ scope, onOpen }: { scope: KnowledgeScope; onOpen?: () => void }) {
  const [view, setView] = useState<ChangeView | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    request<ChangeView>(`/workbench/changes?${new URLSearchParams({ kind: scope.kind, scope_id: scope.id })}`, { signal: abort.signal })
      .then(value => { if (!abort.signal.aborted) setView(value); })
      .catch(e => { if (!abort.signal.aborted) setError(e.message); });
    return () => abort.abort();
  }, [scope.kind, scope.id]);
  if (error) return <p role="alert" className={styles.error}>{error}</p>;
  if (!view) return <p role="status" className={styles.muted}>변경·재검토 기록을 확인하고 있습니다…</p>;
  if (onOpen) return <div className={styles.changeSummary}><button className={styles.textLink} onClick={onOpen}>원문 변경·영향 기록 {view.records.length}건 · 같은 출처의 재검토 필요 요구 {view.requirements.filter(r => r.status === 'needs_review').length}건 →</button><p className={styles.muted}>현재 선택한 자료 버전과 관련 출처의 저장 기록입니다.</p></div>;
  return <section className={styles.savedAnswers}><h3>원문 버전 변경과 영향</h3><p className={styles.muted}>저장된 비교·영향 결과만 읽습니다. 새 평가를 실행하지 않습니다.</p>
    {!view.records.length && <p className={styles.empty}>이 선택 범위에 연결된 원문 버전 비교·영향 결과가 없습니다.</p>}
    {view.records.map(r => <section key={r.id} className={styles.claim}><h4>{knowledgeDate(r.created_at)} · {knowledgeLabels[r.status] || r.status}</h4><p className={styles.muted}>원문 변경 전 {r.before_version_id} → 변경 후 {r.after_version_id}</p>{r.diff?.changes.map(c => <div key={c.id}><h4>변경 전</h4><p className={styles.prewrap}>{sourceText(c.before)}</p><h4>변경 후</h4><p className={styles.prewrap}>{sourceText(c.after)}</p></div>)}<h4>저장된 영향 판단</h4>{r.impacts.length ? r.impacts.map((i,n) => <p key={n}>{i.requirement_id} · {knowledgeLabels[i.status] || i.status} · {i.reason}</p>) : <p>영향 판단 미기록</p>}</section>)}
    {view.edit_impact && <section className={styles.claim}><h3>이 실행의 문장 수정 영향 기록</h3>{view.edit_impact.items?.length ? view.edit_impact.items.map((i,n) => <p key={n}>{i.requirement_id} · {knowledgeLabels[i.status] || i.status} · {i.reason}</p>) : <p>확정된 영향 판단이 저장되지 않았습니다.</p>}<p className={styles.muted}>관련 요구 {view.edit_impact.related_requirement_ids?.length ?? '미확인'}개 · 영향 후보 {view.edit_impact.candidate_requirement_ids?.length ?? '미확인'}개. 후보 수는 실제 영향 확정 수가 아닙니다.</p></section>}
    <h3>같은 출처에 연결된 업무 요구 · {view.requirements.length}건</h3><p className={styles.muted}>현재 원장의 상태입니다. 과거 승인이나 선택 실행의 검수 결과와 구분합니다.</p>{view.requirements.map(r => <div key={r.id} className={styles.claim}><p>{r.question}</p><span className={styles.badge}>{knowledgeLabels[r.status] || r.status}</span><span className={styles.muted}> · {r.id} · 요구 버전 {r.revision}</span></div>)}
    <details className={styles.diagnostics}><summary>선택한 원문 버전과 후속 관계</summary>{view.versions.map(v => <p key={v.id}>{v.title} · {v.id} · 이전 버전 {v.supersedes_version_id || '연결 기록 없음'}</p>)}</details>
  </section>;
}
