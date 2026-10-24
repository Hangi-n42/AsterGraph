"use client";

import { useEffect, useRef, useState } from "react";
import KnowledgeStoredAnswers from "./KnowledgeStoredAnswers";
import { knowledgeDate, knowledgeLabels, type KnowledgeScope } from "@/lib/knowledgeWorkbench";
import styles from "./KnowledgeWorkbench.module.css";

type Request = <T>(path: string, init?: RequestInit) => Promise<T>;
type Snapshot = { id: string; run_id: string; reason: string; created_at: string; counts: { claims: number } };
type Result = { run_id?: string; status: string; answer?: { answer: string } | null; limitations?: (string | { requirement_id: string; status: string; gaps: string[] })[] };
const statuses: Record<string, string> = { answered: "답변 생성·의미 정확성 확인 필요", needs_review: "현재 사용 상태가 바뀌어 재검토가 필요합니다.", no_reviewed_claims: "사용할 승인 지식이 없습니다.", retrieval_failed: "근거 검색 실패", input_capacity: "답변 입력 용량 초과", unverified: "답변 확인 미완료" };

export function businessSearchRequest(snapshotId: string, question: string, retrieval: string, configuration = retrieval === "hipporag2" ? "preserved" : "baseline") {
  if (!snapshotId || !question.trim()) throw new Error("출처 지식 버전과 질문을 선택하세요.");
  if (!["hipporag2", "bm25", "dense"].includes(retrieval)) throw new Error("이 버전에서 지원하지 않는 검색 방식입니다.");
  if (!["baseline", "preserved"].includes(configuration) || configuration === "preserved" && retrieval !== "hipporag2") throw new Error("근거 확장은 개념·관계 연결 검색에서만 선택하세요.");
  return { snapshot_id: snapshotId, question: question.trim(), retrieval, graph_variant: "full", answer_mode: "synthesis",
    ...(configuration === "baseline" ? { candidate_contract: null, evidence_union: null, source_citation_contract: "provided_source_quote_links_v1" } : {}) };
}

export default function KnowledgeSearch({ request, scope, onOpenScope, onExplore }: {
  request: Request; scope: KnowledgeScope | null; onOpenScope: (key: string) => void; onExplore: (id: string) => void;
}) {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [retrieval, setRetrieval] = useState("hipporag2");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [configuration, setConfiguration] = useState("preserved");
  const inFlight = useRef(false);
  const alive = useRef(true);
  const snapshot = scope?.kind === "source_graph" ? snapshots.find(s => s.id === scope.id) : undefined;

  useEffect(() => {
    alive.current = true;
    const abort = new AbortController();
    request<{ items: Snapshot[] }>("/business/snapshots", { signal: abort.signal })
      .then(value => { if (!abort.signal.aborted) setSnapshots(value.items); })
      .catch(e => { if (!abort.signal.aborted) setError(e.message); })
      .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => { alive.current = false; abort.abort(); };
  }, [request]);

  async function search() {
    if (inFlight.current || !snapshot) return;
    inFlight.current = true; setBusy(true); setError(""); setResult(null);
    try {
      const value = await request<Result>("/business/search", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(businessSearchRequest(snapshot.id, query, retrieval, configuration)) });
      if (alive.current) setResult(value);
    } catch (e) { if (alive.current) setError((e as Error).message); }
    finally { inFlight.current = false; if (alive.current) setBusy(false); }
  }

  return <section className={styles.savedAnswers}>
    <h2>출처 지식 버전으로 새 질문</h2>
    <p className={styles.muted}>명시적으로 선택한 저장 버전을 사용합니다. 검색과 답변은 질문 제출 시에만 실행하며, 답변 생성이 업무 요구 충족이나 의미 정확성을 보증하지 않습니다.</p>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {loading && <p role="status">사용할 출처 지식 버전을 읽고 있습니다…</p>}
    <form onSubmit={e => { e.preventDefault(); void search(); }}>
      <fieldset disabled={loading || busy} className={styles.searchFields}>
        <label>사용할 출처 지식 버전<select aria-label="사용할 출처 지식 버전" value={snapshot?.id || ""} onChange={e => onOpenScope(`source_graph:${e.target.value}`)}>
          <option value="" disabled>상단 범위와 함께 사용할 저장 버전을 선택하세요</option>
          {snapshots.map(s => <option key={s.id} value={s.id}>{s.reason || "출처 지식"} · {knowledgeDate(s.created_at)} · 주장 {s.counts.claims}개</option>)}
        </select></label>
        {snapshot && <p className={styles.muted}>{snapshot.reason}</p>}
        {!loading && !snapshots.length && <p className={styles.empty}>저장된 출처 지식 버전이 없습니다. 검토·승인 뒤 생성한 버전으로 질문할 수 있습니다.</p>}
        {!loading && snapshots.length > 0 && !snapshot && <p className={styles.warning}>현재 상단의 범위는 사용 가능한 출처 지식 버전이 아닙니다. 다른 버전으로 자동 대체하지 않습니다.</p>}
        <label>근거 찾기<select aria-label="근거 찾기" value={retrieval} onChange={e => { setRetrieval(e.target.value); setConfiguration(e.target.value === "hipporag2" ? "preserved" : "baseline"); setResult(null); }}>
          <option value="hipporag2">개념·관계 연결 검색</option><option value="bm25">단어 검색 (BM25)</option><option value="dense">임베딩 검색</option>
        </select></label>
        {retrieval === "hipporag2" && <label>검색 구성<select aria-label="검색 구성" value={configuration} onChange={e => { setConfiguration(e.target.value); setResult(null); }}>
          <option value="baseline">이전 구성 (비교용)</option><option value="preserved">근거 보존·확장</option>
        </select></label>}
        {configuration === "preserved" && <p className={styles.warning}>선택한 사실과 추가 근거를 입력 예산 안에서 보존합니다. 새 질문의 검색·답변 품질은 검증 중이며, 원문과 조건을 확인해야 합니다.</p>}
        <label>질문<textarea aria-label="질문" rows={3} required maxLength={4000} value={query} onChange={e => { setQuery(e.target.value); setResult(null); }} /></label>
        <button className={styles.primary} disabled={!snapshot || !query.trim()}>검색하고 답변 생성</button>
      </fieldset>
    </form>
    {busy && <p role="status">선택한 버전에서 검색·답변을 실행하고 있습니다…</p>}
    {result && <div role="status"><p>{statuses[result.status] || result.status}</p>{result.limitations?.map((v, i) => <p key={i}>{typeof v === "string" ? v : [v.requirement_id, knowledgeLabels[v.status] || v.status, ...v.gaps].join(" · ")}</p>)}</div>}
    {result?.run_id && scope && <KnowledgeStoredAnswers key={result.run_id} scope={scope} initialAnswerId={result.run_id} onExplore={onExplore} />}
  </section>;
}
