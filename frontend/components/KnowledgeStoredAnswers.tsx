"use client";

import { useEffect, useState } from "react";
import { knowledgeRequest as request, knowledgeDate, relationLabel, knowledgeVersionName, hasUsageRecords, type KnowledgeScope, type KnowledgeClaim, type KnowledgeUsage, type KnowledgeVersion } from "@/lib/knowledgeWorkbench";
import { KnowledgeUsageDetails } from "./KnowledgeUsage";
import KnowledgeAnswerSources, { type AnswerSourceCitations } from "./KnowledgeAnswerSources";
import styles from "./KnowledgeWorkbench.module.css";

type AnswerRow = { id: string; question: string; retrieval: string; status: string; finished_at?: string };
type AnswerDetail = { source_citations?: AnswerSourceCitations; id: string; question: string; note: string; status: string; source_run_id?: string; snapshot_id?: string; used_version_ids: string[]; used_versions: KnowledgeVersion[]; requirement_ids: string[]; answer_mode?: string; current_usage: KnowledgeUsage; answer: { answer?: string; citations?: string[]; limitations?: string[] }; evidence: { id: string; cited: boolean; provided: boolean; retrieved: boolean; claim_ids: string[]; statement?: string; evidence: KnowledgeClaim['evidence']; fallback_text?: string }[]; graph_links: { id: string; relation: string }[]; recorded_links: { id: string; text?: string; status?: string; concept_hint: boolean }[]; recorded_edge_count: number; fallback?: string; metrics?: Record<string, unknown> };
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
  return <div className={styles.savedAnswers}>
    <h2>저장된 질문과 답변</h2><p className={styles.muted}>{items === null ? "현재 선택한 저장 범위의 답변 수를 확인하고 있습니다." : `현재 선택한 저장 범위에 연결된 ${items.length}건입니다.`} 조회는 모델을 실행하지 않습니다.</p>
    <label className={styles.answerFilter}>저장 질문 찾기<input value={query} onChange={e => setQuery(e.target.value)} placeholder="질문의 단어로 찾기" /></label>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {loading && <p role="status">저장 답변을 읽고 있습니다…</p>}
    {!loading && !matches.length && <p className={styles.empty}>이 범위와 검색어에 연결된 저장 답변이 없습니다.</p>}
    <ul className={styles.answerList}>{matches.map(row => <li key={row.id}><button aria-pressed={selected === row.id} onClick={() => { setSelected(row.id); setDetail(null); setLoading(true); }}><strong>{row.question}</strong><span className={styles.muted}>{row.retrieval === 'hipporag2' ? '그래프 검색' : row.retrieval === 'hybrid' ? '하이브리드 검색' : row.retrieval} · {knowledgeDate(row.finished_at)} · 저장됨</span></button></li>)}</ul>
    {detail && <article className={styles.answerDetail}><p className={styles.warning}>{detail.note}</p><h3>당시 사용한 버전</h3><p>{detail.source_run_id ? '미승인 추출 실행의 원문 QA' : detail.snapshot_id ? '질문에서 직접 지정한 출처 지식 버전' : '사용한 저장 범위 미확인'}</p><p>당시 원문 {detail.used_versions.map(knowledgeVersionName).join(' · ') || '버전 기록 없음'}</p><p>당시 선택 요구 {detail.requirement_ids.map(id => detail.current_usage.requirements.find(r => r.id === id)?.question || '요구 이름 연결 미확인').join(' · ') || '별도 선택 기록 없음'}</p><KnowledgeUsageDetails view={detail.current_usage} selectedClaimIds={detail.evidence.filter(e => e.cited).flatMap(e => e.claim_ids)} /><h3>저장 질문</h3><p className={styles.prewrap}>{detail.question}</p><h3>저장 답변</h3><p className={styles.prewrap}>{detail.answer.answer || '답변 본문이 저장되지 않았습니다.'}</p>
      {!!detail.answer.limitations?.length && <ul>{detail.answer.limitations.map((v, i) => <li key={i}>{v}</li>)}</ul>}
      <KnowledgeAnswerSources record={detail.source_citations} />
      <h3>기존 인용 ID의 근거 · {detail.evidence.filter(e => e.cited).length}개</h3>
      <p className={styles.muted}>아래는 각 주장에 기록된 원문 범위입니다. 주소 범위는 문장별 의미 지지 판정이 아닙니다.</p>
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
      <details className={styles.contextEvidence}><summary>인용하지 않은 조회·제공 근거 · {detail.evidence.filter(e => !e.cited).length}개</summary><p className={styles.muted}>답변에 사용된 인용과 구분합니다. 제공됐다는 사실만으로 답변 근거로 승인된 것은 아닙니다.</p>{detail.evidence.filter(e => !e.cited).map(e => <div key={e.id}><p>{e.provided ? '모델에 제공됨' : '검색 조회만 확인'} · {e.retrieved ? '검색 결과에 포함' : '검색 결과 목록에는 없음'}</p><blockquote>{e.evidence.map(v => v.quote).join('\n') || e.fallback_text || '본문 미기록'}</blockquote></div>)}</details>
      <details className={styles.contextEvidence}><summary>저장된 그래프 검색 연결</summary><p>선택 관계 ID {detail.recorded_edge_count}개 · 현재 저장 그래프와 일치하는 관계 {detail.graph_links.length}개</p>{detail.graph_links.map(e => <button key={e.id} className={styles.secondary} onClick={() => onExplore(e.id)}>{relationLabel(e.relation)} 관계 확인</button>)}<ul>{detail.recorded_links.map(e => <li key={e.id}><p>{e.text?.replace(" has_concept ", " → 자동 개념 후보 → ") || "관계 내용 미기록"}</p><p className={styles.muted}>{e.concept_hint ? "당시 검색에 사용한 미승인 개념 연결 · 사실 관계나 답변 근거 승인이 아님" : `당시 저장 상태: ${e.status || "미기록"}`}</p></li>)}</ul><p className={styles.muted}>연속된 탐색 경로는 기록에서 확인되지 않아 그리지 않습니다.</p>{detail.fallback && <p>기록된 대체 검색: {detail.fallback}</p>}</details>
      <details className={styles.diagnostics}><summary>진단 · 당시 실행 기록</summary><p>답변 실행 {detail.id}</p><p>당시 출처 지식 버전 {detail.snapshot_id || "없음"} · 추출 실행 {detail.source_run_id || "없음"}</p><p>당시 원문 버전 {detail.used_version_ids.join(" · ") || "미기록"} · 선택 요구 {detail.requirement_ids.join(" · ") || "별도 선택 없음"}</p><p>당시 응답 검사 상태 {detail.status} · 의미 정확성 판정과 별도</p><pre>{JSON.stringify(detail.metrics, null, 2)}</pre></details>
    </article>}
  </div>;
}
