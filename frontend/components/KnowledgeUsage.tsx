"use client";

import { useEffect, useState } from "react";
import { knowledgeRequest, knowledgeDate, knowledgeLabels, knowledgeVersionName, hasUsageRecords, type KnowledgeScope, type KnowledgeUsage } from "@/lib/knowledgeWorkbench";
import styles from "./KnowledgeWorkbench.module.css";

const requirementStatus = (value?: string) => value === 'partial' ? '일부 미완료' : knowledgeLabels[value || 'unknown'] || value;
const reviewReason: Record<string, string> = { own_source_review_pending_or_not_supported: '자기 원문 검수 미완료 또는 미지지', stale_assessment: '검수 대상 버전 변경', unresolved_claim_support: '주장의 원문 지지 미확정', confirmed_expression_error: '표현 오류 확인', confirmed_error_or_refutation: '오류 또는 원문 반박 확인', unresolved_meaning_not_false: '의미 미확정', normal_meaning_preservation_conflict: '정상 의미 보존 충돌', meaning_dependency_blocked: '관련 의미 판단 제한', normal_meaning_preservation_unconfirmed: '기존 정상 의미 보존 미확인', whole_claim_support_unconfirmed: '주장 전체의 원문 지지 미확인', corrected_in_new_run: '후속 실행에서 수정된 주장', candidate_changed_since_publication: '검토안 게시 이후 후보 변경' };

export function KnowledgeUsageDetails({ view, selectedClaimIds = [], onOpenScope }: { view: KnowledgeUsage; selectedClaimIds?: string[]; onOpenScope?: (key: string) => void }) {
  if (!hasUsageRecords(view)) return <p role="alert" className={styles.error}>사용 상태 응답의 필수 버전·검토 기록을 읽지 못했습니다. 새로고침해 다시 확인하세요.</p>;
  const policy = view.scope.kind === 'run' ? '자동 추출 · 미승인' : view.activation === 'explicit_query_only' ? '질문에서 직접 지정하는 버전' : '사용 정책 미확인';
  const selectedExcluded = selectedClaimIds.filter(id => view.excluded_claim_ids.includes(id));
  return <details className={styles.diagnostics}>
    <summary>사용 버전·검토 상태 · {policy}{view.invalidations.length ? ' · 변경 후 제외 기록 있음' : ''}{view.source_restrictions.length ? ' · 원문 사용 제한 있음' : ''}</summary>
    <p>일반 활성 지식 버전: {view.active_snapshot_id ? '활성 선택 기록 있음' : '없음'}</p>
    {view.scope.kind === 'source_graph' ? <><p>{policy}. 일반 활성 지식과 별도로 관리됩니다.</p><p>선택 기록: {view.actor || '결정자 미기록'} · {view.reason || '사유 미기록'}</p></> : <p>이 자동 추출 실행의 원문 QA와 검토된 출처 지식 활용은 별도입니다.</p>}
    <p className={styles.muted}>조회 {knowledgeDate(view.status_checked_at)} · 사용 상태 이력 버전 {view.status_revision}</p>
    <h3>선택한 원문 버전</h3>{view.version_files.map((v, i) => <p key={v.id || i}>{knowledgeVersionName(v)}</p>)}
    {view.missing_version_ids.length > 0 && <p className={styles.warning}>원문 버전 {view.missing_version_ids.length}건의 원장 연결을 확인할 수 없습니다.</p>}
    <p>현재 원문 사용 제한: {view.source_restrictions.length ? view.source_restrictions.map(r => knowledgeLabels[r.state] || r.state).join(' / ') : '저장된 제한 없음'}</p>
    <h3>업무 요구의 저장 결과와 현재 상태</h3>
    {!view.requirements.length && <p>이 범위에 저장된 업무 요구가 없습니다.</p>}
    {view.requirements.map(r => <div key={r.id} className={styles.claim}><strong>{r.question || r.id}</strong><p>이 버전의 검토: {requirementStatus(r.recorded_status)} · 현재 요구: {requirementStatus(r.current_status)}</p><p>저장 요구 버전 {r.recorded_revision ?? '미기록'} → 현재 {r.current_revision ?? '미확인'}</p>{r.source_change_requires_review && <p className={styles.warning}>이 지식 버전으로 이 요구에 답하려면 원문 변경 후 재검토가 필요합니다.</p>}{!r.revision_matches && <p className={styles.warning}>요구 버전 일치가 확인되지 않아 현재 요구의 근거로 확정할 수 없습니다.</p>}{r.current_status === 'needs_review' && <p className={styles.warning}>현재 요구가 재검토 필요 상태입니다.</p>}</div>)}
    {view.invalidations.length > 0 && <p className={styles.warning}>변경 기록에 따라 주장 {view.excluded_claim_ids.length}개·원문 구간 {view.excluded_block_ids.length}개를 이 버전의 질의에서 제외합니다. 영향받은 요구의 답변은 재검토가 필요하며, 다른 요구도 해당 요청의 버전·사용 제한을 확인합니다.</p>}
    {selectedExcluded.length > 0 && <p className={styles.warning}>선택 항목에 변경 후 제외된 주장 {selectedExcluded.length}개가 있습니다.</p>}
    {view.review && <p>현재 변경안의 후보 자격 검사 통과 {view.review.eligible_ids.length}개 · 부적격 사유 기록 {Object.keys(view.review.blocks).length}개 · 별도 원문 직접 대조 대상 {view.review.explicit_review_ids.length}개. 승인에는 원문·요구 변경 제한도 적용됩니다. 이 수는 승인·활성화 또는 업무 요구 전체 충족을 뜻하지 않습니다.</p>}
    {selectedClaimIds.filter(id => view.review?.blocks[id]).map(id => <p key={id} className={styles.warning}>선택 주장의 검토 제한: {view.review!.blocks[id].map(reason => reviewReason[reason] || '기타 제한 사유 · 아래 기록 확인').join(' · ')}</p>)}
    <p className={styles.muted}>실제 활용은 선택한 요구·답변 방식·원문 사용 제한에 따라 판단됩니다. 제한이 없다는 표시만으로 의미 정확성이나 전체 요구 충족이 확정되지 않습니다.</p>
    {!!view.linked_snapshots.length && <><h3>이 추출 실행의 검토 선택 버전</h3>{view.linked_snapshots.map(s => <p key={s.id}>{s.reason || '사유 미기록'} · {knowledgeDate(s.created_at)}{onOpenScope && <button className={styles.textLink} onClick={() => onOpenScope(`source_graph:${s.id}`)}>버전과 현재 상태 확인 →</button>}</p>)}</>}
    <details><summary>원문·실행·검토·제외 기록 식별자</summary><p>일반 활성 버전 {view.active_snapshot_id || '없음'}</p><p>선택한 출처 지식 버전 {view.snapshot_id || '없음'}</p><p>원문 버전 {view.version_ids.join(' · ') || '미기록'}</p><p>추출 실행 {view.run_id || '미기록'}</p><pre>{JSON.stringify({ source_restrictions: view.source_restrictions, invalidations: view.invalidations, review: view.review }, null, 2)}</pre></details>
  </details>;
}

export default function KnowledgeUsageState({ scope, reload, selectedClaimIds, onOpenScope }: { scope: KnowledgeScope; reload: number; selectedClaimIds: string[]; onOpenScope: (key: string) => void }) {
  const [view, setView] = useState<KnowledgeUsage | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    knowledgeRequest<KnowledgeUsage>(`/workbench/usage?${new URLSearchParams({ kind: scope.kind, scope_id: scope.id })}`, { signal: abort.signal })
      .then(value => { if (!hasUsageRecords(value)) throw new Error('사용 상태 응답에 필수 버전·검토 기록이 없습니다.'); if (!abort.signal.aborted) { setView(value); setError(""); } })
      .catch(e => { if (!abort.signal.aborted) setError(e.message); });
    return () => abort.abort();
  }, [scope.kind, scope.id, reload]);
  if (error) return <p role="alert" className={styles.error}>현재 사용 상태 조회 실패: {error}</p>;
  if (!view || view.scope.kind !== scope.kind || view.scope.id !== scope.id) return <p role="status" className={styles.muted}>선택한 버전의 현재 사용·검토 상태를 확인하고 있습니다…</p>;
  return <KnowledgeUsageDetails view={view} selectedClaimIds={selectedClaimIds} onOpenScope={onOpenScope} />;
}
