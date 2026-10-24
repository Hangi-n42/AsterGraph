"use client";

import { useEffect, useState } from "react";
import { knowledgeRequest as request, knowledgeDate, relationLabel, knowledgeVersionName, hasUsageRecords, type KnowledgeScope, type KnowledgeClaim, type KnowledgeUsage, type KnowledgeVersion } from "@/lib/knowledgeWorkbench";
import { KnowledgeUsageDetails } from "./KnowledgeUsage";
import KnowledgeAnswerSources, { type AnswerSourceCitations, type AnswerLinks, type AnswerLinkClaims } from "./KnowledgeAnswerSources";
import styles from "./KnowledgeWorkbench.module.css";

type AnswerRow = { id: string; question: string; retrieval: string; status: string; finished_at?: string };
type StoredConsumer = { original_run_id: string; original_unit_id: string; original_status?: string; status?: string; semantic_status: string; human_approval: boolean; records: { status: string }[]; not_consumed?: { status: string }[] };
type AnswerReview = { status?: string; actor?: string; reason?: string; created_at?: string; parent_run_id?: string; producer_run_id?: string; producer_metrics?: Record<string, unknown>; changes?: unknown };
type AnswerDetail = { answer_review?: AnswerReview; condition_consumer?: StoredConsumer; timing_consumer?: StoredConsumer; source_citations?: AnswerSourceCitations; answer_links?: AnswerLinks; answer_link_claims?: AnswerLinkClaims; id: string; retrieval: string; question: string; note: string; status: string; source_run_id?: string; snapshot_id?: string; used_version_ids: string[]; used_versions: KnowledgeVersion[]; requirement_ids: string[]; answer_mode?: string; current_usage: KnowledgeUsage; answer: { answer?: string; citations?: string[]; limitations?: string[] }; evidence: { id: string; cited: boolean; provided: boolean; retrieved: boolean; claim_ids: string[]; statement?: string; evidence: KnowledgeClaim['evidence']; fallback_text?: string }[]; graph_links: { id: string; relation: string }[]; recorded_links: { id: string; text?: string; status?: string; concept_hint: boolean }[]; recorded_edge_count: number; fallback?: string; metrics?: Record<string, unknown> };
export default function KnowledgeStoredAnswers({ scope, onExplore, initialAnswerId = "" }: { scope: KnowledgeScope; onExplore: (id: string) => void; initialAnswerId?: string }) {
  const [items, setItems] = useState<AnswerRow[] | null>(null);
  const [selected, setSelected] = useState(initialAnswerId);
  const [detail, setDetail] = useState<AnswerDetail | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const abort = new AbortController();
    const params = new URLSearchParams({ kind: scope.kind, scope_id: scope.id });
    if (selected) params.set('answer_id', selected);
    request<{ items: AnswerRow[]; detail: AnswerDetail | null }>(`/workbench/answers?${params}`, { signal: abort.signal })
      .then(value => { if (value.detail && (!hasUsageRecords(value.detail.current_usage) || !Array.isArray(value.detail.used_versions) || !Array.isArray(value.detail.used_version_ids) || !Array.isArray(value.detail.requirement_ids))) throw new Error('저장 답변의 당시 버전·현재 사용 상태 연결을 읽지 못했습니다.'); if (!abort.signal.aborted) { setItems(value.items); setDetail(value.detail); setError(""); } })
      .catch(e => { if (!abort.signal.aborted) setError(e.message); })
      .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [scope.kind, scope.id, selected]);
  const matches = (items || []).filter(r => r.question.includes(query));
  const explicit = detail?.answer_mode === "source_list_comparison";
  const review = detail?.answer_review;
  const reviewBlocked = detail?.status === "needs_review" || detail?.source_citations?.status === "needs_review" || detail?.answer_links?.status === "needs_review";
  return <div className={styles.savedAnswers}>
    <h2>저장된 질문과 답변</h2><p className={styles.muted}>{items === null ? "현재 선택한 저장 범위의 답변 수를 확인하고 있습니다." : `현재 선택한 저장 범위에 연결된 ${items.length}건입니다.`} 조회는 모델을 실행하지 않습니다.</p>
    <label className={styles.answerFilter}>저장 질문 찾기<input value={query} onChange={e => setQuery(e.target.value)} placeholder="질문의 단어로 찾기" /></label>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {loading && <p role="status">저장 답변을 읽고 있습니다…</p>}
    {!loading && !matches.length && <p className={styles.empty}>이 범위와 검색어에 연결된 저장 답변이 없습니다.</p>}
    <ul className={styles.answerList}>{matches.map(row => <li key={row.id}><button aria-pressed={selected === row.id} onClick={() => { setSelected(row.id); setDetail(null); setLoading(true); }}><strong>{row.question}</strong><span className={styles.muted}>{row.retrieval === 'hipporag2' ? '그래프 검색' : row.retrieval === 'hybrid' ? '하이브리드 검색' : row.retrieval === 'hybrid_graph' ? 'Hybrid+graph (과거 모드)' : row.retrieval === 'explicit_sources' ? '명시적 원문 목록 대조 · 저장 결과' : row.retrieval} · {knowledgeDate(row.finished_at)} · 저장됨</span></button></li>)}</ul>
    {detail && <article className={styles.answerDetail}><p className={styles.warning}>{detail.note}</p>{detail.retrieval === "hybrid_graph" && <p className={styles.warning}>과거 Hybrid+graph 답변입니다. 신규 실행은 종료되었으며 당시 답변과 인용을 그대로 조회합니다.</p>}<h3>당시 사용한 버전</h3><p>{detail.source_run_id ? '미승인 추출 실행의 원문 QA' : detail.snapshot_id ? '질문에서 직접 지정한 출처 지식 버전' : '사용한 저장 범위 미확인'}</p><p>당시 원문 {detail.used_versions.map(knowledgeVersionName).join(' · ') || '버전 기록 없음'}</p><p>당시 선택 요구 {detail.requirement_ids.map(id => detail.current_usage.requirements.find(r => r.id === id)?.question || '요구 이름 연결 미확인').join(' · ') || '별도 선택 기록 없음'}</p><KnowledgeUsageDetails view={detail.current_usage} selectedClaimIds={detail.evidence.filter(e => e.cited).flatMap(e => e.claim_ids)} /><h3>저장 질문</h3><p className={styles.prewrap}>{detail.question}</p><h3>저장 답변</h3><p className={styles.prewrap}>{detail.answer.answer || '답변 본문이 저장되지 않았습니다.'}</p>
      {!!detail.answer.limitations?.length && <ul>{detail.answer.limitations.map((v, i) => <li key={i}>{v}</li>)}</ul>}
      {explicit && <><p>명시적 원문 목록과 저장 조건·시점을 대조한 결과입니다. 이 소비 실행은 모델·검색을 실행하지 않았습니다.</p>
        {[['조건', detail.condition_consumer], ['시점', detail.timing_consumer]].map(([label, value]) => {
          const consumer = value as StoredConsumer | undefined;
          return consumer && <details key={label as string}><summary>저장 {label as string} 연결 상태 · 의미 미검증</summary>
            <p>원래 생산 실행 {consumer.original_run_id} · 단계 {consumer.original_unit_id}</p>
            <p>원래 생산 실행 상태: {consumer.original_status || '이 소비 기록에는 미기록'} · 소비 상태: {consumer.status || '항목별 기록'}</p>
            <p>의미 검증: {consumer.semantic_status} · 사람 승인: {consumer.human_approval ? '기록 있음' : '없음'}</p>
            <ul>{Array.from(new Set(consumer.records.map(r => r.status))).map(status => <li key={status}>{status} · {consumer.records.filter(r => r.status === status).length}개</li>)}</ul>
            {!!consumer.not_consumed?.length && <p>미소비 기록 {consumer.not_consumed.length}개 · not_consumed_not_absence</p>}
            <p>미확인·미소비 기록은 조건이 없다는 뜻이 아닙니다. 원래 생산 상태와 이번 소비 상태는 별도입니다.</p>
          </details>;
        })}</>}
      {review && <section className={styles.warning}>
        <h3>저장 답변의 명시적 참조 정정</h3>
        {reviewBlocked || review.status === "needs_review" ? <p>재검토 필요 상태에서는 정정 상세를 표시하지 않습니다.</p> : <>
          <p>정정 주체: {review.actor} · {knowledgeDate(review.created_at || "")}</p><p>이유: {review.reason}</p>
          <p>모델 자동 교정·독립 사람 검수·새 사용 승인이 아닙니다. 원본문·한계·원문 인용은 유지했습니다. 이번 정정의 새 모델 호출은 0회입니다.</p>
          <button className={styles.secondary} onClick={() => { if (review.parent_run_id) { setSelected(review.parent_run_id); setDetail(null); setLoading(true); } }}>정정 전 답변과 원래 생성 기록 보기</button>
          <details><summary>정정 전후 참조와 원래 생성 비용</summary><p>원래 생성 실행 {review.producer_run_id}</p><pre>{JSON.stringify({ changes: review.changes, producer_metrics: review.producer_metrics }, null, 2)}</pre></details>
        </>}
      </section>}
      <KnowledgeAnswerSources record={detail.source_citations} links={detail.answer_links} claimBodies={detail.answer_link_claims} claimEvidence={detail.evidence} />
      <h3>기존 인용 ID의 근거 · {detail.evidence.filter(e => e.cited).length}개</h3>
      <p className={styles.muted}>{explicit ? '아래는 목록 대조 결과에 연결된 원문 범위입니다.' : '아래는 각 주장에 기록된 원문 범위입니다.'} 주소 범위는 문장별 의미 지지 판정이 아닙니다.</p>
      {detail.evidence.filter(e => e.cited).map((entry, i) => <section key={entry.id} className={styles.evidence}>
        <h4>인용 {i + 1}</h4>{entry.statement && <p>{entry.statement}</p>}
        {entry.evidence.map((e, j) => <div key={j}>
          <p className={styles.sourceTitle}>{e.source_title || '출처 이름 미기록'}</p>
          <p className={styles.muted}>원문 파일 · {e.version_file ? knowledgeVersionName(e.version_file) : '버전 연결 미기록'}</p>
          <p className={styles.muted}>{e.precision === 'chunk' ? '넓은 문맥 근거 (chunk)' : e.precision === 'exact_unverified_meaning' ? '기록된 원문 범위 · 의미 지지 미검증 (exact_unverified_meaning)' : e.precision === 'exact' ? '기록된 원문 범위 (exact)' : '근거 정밀도 미기록·미확정'}</p>
          <p className={styles.muted}>{typeof e.start_char === 'number' && Number.isInteger(e.start_char) && e.start_char >= 0 && typeof e.end_char === 'number' && Number.isInteger(e.end_char) && e.end_char > e.start_char ? `블록 내 문자 [${e.start_char}, ${e.end_char})` : '문자 범위 미기록·미확정'}</p>
          <details><summary>기록된 원문 위치·버전</summary><p>원문 버전 {e.source_version_id || '미기록'} · 원문 처리 기록 {e.parse_run_id || '미기록'}</p><p>구간 {e.block_id || '미기록'}</p></details>
          <blockquote>{e.quote}</blockquote>
          <details><summary>주변 원문 · 주장 근거 범위와 별도</summary><p className={styles.prewrap}>{e.block_text || '원문 구간 미기록'}</p><p>주변 원문 위치 정보</p><pre>{JSON.stringify(e.locator, null, 2)}</pre></details>
        </div>)}
        {!entry.evidence.length && <><p className={styles.warning}>이 인용 ID의 정확한 원문 위치 연결을 확인할 수 없습니다.</p><p className={styles.prewrap}>{entry.fallback_text || '저장 텍스트 없음'}</p></>}
        {entry.claim_ids.map(id => <button key={id} className={styles.secondary} onClick={() => onExplore(id)}>연결된 저장 주장 확인</button>)}
      </section>)}
      <details className={styles.contextEvidence}><summary>인용하지 않은 조회·제공 근거 · {detail.evidence.filter(e => !e.cited).length}개</summary><p className={styles.muted}>답변에 사용된 인용과 구분합니다. 제공됐다는 사실만으로 답변 근거로 승인된 것은 아닙니다.</p>{detail.evidence.filter(e => !e.cited).map(e => <div key={e.id}><p>{explicit ? '명시적 목록 대조에 연결된 원문 참조' : <>{e.provided ? '모델에 제공됨' : '검색 조회만 확인'} · {e.retrieved ? '검색 결과에 포함' : '검색 결과 목록에는 없음'}</>}</p><blockquote>{e.evidence.map(v => v.quote).join('\n') || e.fallback_text || '본문 미기록'}</blockquote></div>)}</details>
      {!explicit && <details className={styles.contextEvidence}><summary>저장된 그래프 검색 연결</summary><p>선택 관계 ID {detail.recorded_edge_count}개 · 현재 저장 그래프와 일치하는 관계 {detail.graph_links.length}개</p>{detail.graph_links.map(e => <button key={e.id} className={styles.secondary} onClick={() => onExplore(e.id)}>{relationLabel(e.relation)} 관계 확인</button>)}<ul>{detail.recorded_links.map(e => <li key={e.id}><p>{e.text?.replace(" has_concept ", " → 자동 개념 후보 → ") || "관계 내용 미기록"}</p><p className={styles.muted}>{e.concept_hint ? "당시 검색에 사용한 미승인 개념 연결 · 사실 관계나 답변 근거 승인이 아님" : `당시 저장 상태: ${e.status || "미기록"}`}</p></li>)}</ul><p className={styles.muted}>연속된 탐색 경로는 기록에서 확인되지 않아 그리지 않습니다.</p>{detail.fallback && <p>기록된 대체 검색: {detail.fallback}</p>}</details>}
      <details className={styles.diagnostics}><summary>진단 · 당시 실행 기록</summary><p>답변 실행 {detail.id}</p><p>당시 출처 지식 버전 {detail.snapshot_id || "없음"} · 추출 실행 {detail.source_run_id || "없음"}</p><p>당시 원문 버전 {detail.used_version_ids.join(" · ") || "미기록"} · 선택 요구 {detail.requirement_ids.join(" · ") || "별도 선택 없음"}</p><p>당시 응답 검사 상태 {detail.status} · 의미 정확성 판정과 별도</p><pre>{JSON.stringify(detail.metrics, null, 2)}</pre></details>
    </article>}
  </div>;
}
