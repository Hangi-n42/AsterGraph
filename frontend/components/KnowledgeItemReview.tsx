"use client";

import { useEffect, useRef, useState } from "react";
import { EventEditor, type Change } from "./KnowledgeBusiness";
import { knowledgeRequest as request, knowledgeLabels, type KnowledgeDetail } from "@/lib/knowledgeWorkbench";
import styles from "./KnowledgeWorkbench.module.css";

type Saved = { id: string; status: string; changeset_id?: string; selected_id?: string; error?: string; llm_calls?: number; recheck_status?: string; changes: { before: string; after: string; entities: string[] }[] };
export default function KnowledgeItemReview({ detail, onOpenSaved }: { detail: KnowledgeDetail; onOpenSaved: (runId: string, selectedId?: string) => void }) {
  const [change, setChange] = useState<Change | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState("");
  const [saved, setSaved] = useState<Saved | null>(null);
  const receipt = useRef<HTMLDivElement>(null);
  useEffect(() => { if (runId) { receipt.current?.focus(); receipt.current?.scrollIntoView({ block: "start" }); } }, [runId]);
  const pending = useRef(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const abort = new AbortController(); controller.current = abort;
    if (detail.changeset_id) request<Change>(`/business/changes/${detail.changeset_id}`, { signal: abort.signal })
      .then(value => { if (!abort.signal.aborted) setChange(value); })
      .catch(e => { if (!abort.signal.aborted) setError(e.message); });
    return () => abort.abort();
  }, [detail.changeset_id]);
  useEffect(() => {
    if (!runId) return;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const value = await request<Saved>(`/workbench/review?run_id=${runId}`, { signal: abort.signal });
        if (abort.signal.aborted) return;
        setSaved(value);
        if (['queued', 'running', 'cancel_requested'].includes(value.status)) timer = setTimeout(refresh, 4000);
      } catch (e) { if (!abort.signal.aborted) setError((e as Error).message); }
    }
    refresh();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [runId]);
  if (!detail.claims.some(c => c.editable) || !detail.changeset_id) return <p className={styles.warning}>이 선택은 현재 직접 문장 수정 대상이 아닙니다. 지원되는 업무 내용 문장과 변경 묶음이 있는 저장 결과를 선택하세요.</p>;
  return <section className={styles.itemReview} aria-label="선택 항목 직접 수정">
    <h3>선택한 업무 내용 수정</h3>
    <p className={styles.muted}>이 선택에 연결된 문장만 불러옵니다. 수정 저장 시 기존 계약에 따라 로컬 모델 재검수가 시작됩니다. 저장·재검수·승인·사용 버전 반영은 별도입니다.</p>
    {error && <div role="alert" className={styles.error}>{error}<p>입력 내용은 이 화면에 유지됩니다. 버전 충돌이면 입력을 보관한 뒤 현재 저장 결과를 다시 여세요.</p></div>}
    {change && !runId && <EventEditor initiallyOpen busy={busy} change={{ ...change, candidates: change.candidates.filter(c => detail.claims.some(v => v.id === c.id && v.editable)) }} onSubmit={async value => {
      if (pending.current) return;
      pending.current = true; setBusy(true); setError("");
      try {
        const result = await request<{ run_id: string }>(`/business/changes/${change.id}/edits`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value), signal: controller.current?.signal });
        if (!controller.current?.signal.aborted) setRunId(result.run_id);
      } catch (e) { if (!controller.current?.signal.aborted) setError((e as Error).message); }
      finally { pending.current = false; setBusy(false); }
    }} />}
    {!change && !error && <p role="status">편집할 현재 버전을 읽고 있습니다…</p>}
    {runId && <div ref={receipt} tabIndex={-1} role="status" className={styles.savedReview}><h3>수정 저장됨 · {saved ? knowledgeLabels[saved.status] || saved.status : '재검수 상태 확인 중'}</h3><p>아직 승인 또는 사용 버전 반영을 실행하지 않았습니다.</p>{saved?.error && <p className={styles.warning}>재검수 실패: {saved.error}</p>}{saved?.changes.map((c, i) => <div key={i}><h4>변경 전</h4><p>{c.before}</p><h4>변경 후</h4><p>{c.after}</p><p className={styles.muted}>유지된 연결 대상: {c.entities.join(' / ')}</p></div>)}<button className={styles.primary} onClick={() => onOpenSaved(runId, saved?.selected_id)}>저장 결과 열기</button><details className={styles.diagnostics}><summary>저장·재검수 기록</summary><p>실행 {runId}</p><p>재검수 {saved?.recheck_status || '미기록'} · 모델 호출 {saved?.llm_calls ?? '미확인'}</p></details></div>}
  </section>;
}
