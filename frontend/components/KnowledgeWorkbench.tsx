"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import AppSidebar from "./AppSidebar";
import KnowledgeChanges from "./KnowledgeChanges";
import KnowledgeUsageState from "./KnowledgeUsage";
import KnowledgeStoredAnswers from "./KnowledgeStoredAnswers";
import KnowledgeItemReview from "./KnowledgeItemReview";
import KnowledgeGraph from "./KnowledgeGraph";
import KnowledgeExtraction from "./KnowledgeExtraction";
import KnowledgeSources from "./KnowledgeSources";
import KnowledgeBusiness from "./KnowledgeBusiness";
import KnowledgeOntology from "./KnowledgeOntology";
import KnowledgeSnapshots from "./KnowledgeSnapshots";
import KnowledgeSearch from "./KnowledgeSearch";
import { knowledgeRequest as request, knowledgeLabels as labels, knowledgeDate, knowledgeVersionName, qualifier, relationLabel, itemLabel, type KnowledgeCatalog, type KnowledgeView, type KnowledgeDetail, type KnowledgeClaim } from "@/lib/knowledgeWorkbench";
import styles from "./KnowledgeWorkbench.module.css";

type Area = "overview" | "sources" | "explore" | "review" | "search";
const areas: [Area, string][] = [["overview", "현황"], ["sources", "자료"], ["explore", "지식 탐색"], ["review", "검토 / 변경"], ["search", "검색 / 답변"]];
type SourceItem = { source: { id: string; title: string }; versions: { id: string; format: string; processing_status?: string }[] };

function ClaimDetail({ claim, single, editable }: { claim: KnowledgeClaim; single: boolean; editable: boolean }) {
  const [expanded, setExpanded] = useState(single);
  const content = <div className={styles.claimContent}>
      {claim.extraction_error && <p role="note" className={styles.warning}>추출 오류 기록: {claim.extraction_error}</p>}
      <h3>조건 · 예외 · 기간</h3>
      {claim.meanings.length > 0 ? claim.meanings.map((meaning, i) => {
        const fields = [['conditions', '조건'], ['exceptions', '예외'], ['time', '기간 / 시점'], ['references', '참조']] as const;
        const absent = fields.filter(([key]) => typeof meaning[key] === 'object' && meaning[key] !== null && (meaning[key] as { state?: string }).state === 'absent');
        const present = fields.filter(field => !absent.includes(field));
        return <div key={i} className={styles.meaning}>
          {!!present.length && <><p className={styles.muted}>자동 해석 {i + 1} · 저장된 조건</p><dl>{present.map(([key, title]) => <div key={key}><dt>{title}</dt><dd>{qualifier(meaning[key])}</dd></div>)}</dl></>}
          {!!absent.length && <details className={styles.absentQualifiers}><summary>{absent.map(([, title]) => title).join('·')} 없음으로 자동 기록</summary><dl>{absent.map(([key, title]) => <div key={key}><dt>{title}</dt><dd>{qualifier(meaning[key])}</dd></div>)}</dl></details>}
        </div>;
      }) : <dl><div><dt>조건</dt><dd>{claim.conditions?.length ? claim.conditions.join("\n") : "별도 정리되지 않음 · 아래 원문 확인"}</dd></div><div><dt>예외</dt><dd>{claim.exceptions?.length ? claim.exceptions.join("\n") : "별도 정리되지 않음 · 아래 원문 확인"}</dd></div><div><dt>기간</dt><dd>{claim.period || "기록 없음"}</dd></div></dl>}
      <h3>원문과 위치</h3>
      {!claim.evidence.length && <p className={styles.warning}>저장된 원문 근거가 없습니다.</p>}
      {claim.evidence.map((e, i) => <div key={`${e.block_id}:${i}`} className={styles.evidence}>
        <p className={styles.sourceTitle}>{e.source_title || "출처 이름 미기록"}</p>
        <p className={styles.muted}>원문 파일 · {e.version_file ? knowledgeVersionName(e.version_file) : '버전 연결 미기록'}</p>
        <p className={styles.muted}>{e.context_only || e.precision === "chunk" ? "문맥 근거 · 직접 근거와 구분" : "저장 발췌 · 위치 기록 확인"}</p>
        <blockquote>{e.quote || "발췌 미기록"}</blockquote>
        <details><summary>원문 구간과 위치 보기</summary><p className={styles.prewrap}>{e.block_text || "원문 구간 미기록"}</p><dl>{Object.entries(e.locator || {}).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{String(v)}</dd></div>)}</dl></details>
      </div>)}
      <p className={styles.muted}>{claim.editable && editable ? "문장 부분 수정 지원 대상 · 저장 후 재검수와 승인은 별도입니다." : "이 유형은 읽기와 이력 확인을 지원합니다."}</p>
    </div>;
  if (single) return <><span className={styles.badge}>{labels[claim.review_status || 'unrecorded'] || claim.review_status}</span>{content}<details className={styles.claimDisclosure}><summary>저장 문장 전체</summary><p>{claim.statement}</p></details></>;
  return <details className={styles.claimDisclosure} open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
    <summary><span className={styles.badge}>{labels[claim.review_status || 'unrecorded'] || claim.review_status}</span><strong>{claim.statement}</strong><span className={styles.muted}>조건과 원문 {claim.evidence.length}건 {expanded ? '접기' : '보기'}</span></summary>
    {expanded && content}
  </details>;
}

export function KnowledgeSelection({ detail, onSelect, onReview }: { detail: KnowledgeDetail | null; onSelect: (id: string) => void; onReview?: () => void }) {
  if (!detail) return <div className={styles.empty}><h3>확인할 대상을 선택하세요</h3><p>원문, 조건과 연결된 관계를 이곳에서 확인합니다.</p></div>;
  return <div className={styles.detailBody}>
    <div className={styles.eyebrow}>{labels[detail.item.kind] || detail.item.kind}</div>
    <h2 tabIndex={-1}>{itemLabel(detail.item)}</h2>
    {detail.item.kind === "relation" && <p className={styles.relationDirection}>{detail.item.head_label}<span aria-label="연결 방향"> → </span>{detail.item.tail_label}</p>}
    {detail.item.kind === "concept" && <p className={styles.warning}>자동 개념 후보: {detail.item.concepts?.join(" · ") || "저장 후보 없음"}. 승인된 온톨로지가 아닙니다.</p>}
    {!!detail.relations.length && <details className={styles.connectionDisclosure} open={detail.claims.length > 1}><summary>직접 연결된 관계 · {detail.relations.length}</summary><ul className={styles.connections}>{detail.relations.map(e => <li key={e.id}><button onClick={() => onSelect(e.id)}>{e.head_label}<span>{relationLabel(e.relation)} →</span>{e.tail_label}</button></li>)}</ul></details>}
    {detail.claims.length > 1 && <h3>연결된 주장 · {detail.claims.length}</h3>}
    {detail.claims.length > 1 && <p className={styles.muted}>확인할 주장 또는 연결 관계를 선택해 조건과 원문을 펼치세요.</p>}
    {detail.claims.length === 0 && <p>이 대상에 연결된 주장 기록이 없습니다.</p>}
    {detail.claims.map(claim => <ClaimDetail key={claim.id} claim={claim} single={detail.claims.length === 1} editable={!!detail.changeset_id} />)}
    {!!detail.history.length && <section><h3>저장된 변경 전후</h3>{detail.history.map(h => <div key={h.id}><p>{h.actor} · {h.reason}</p>{h.changes.map((c, i) => <div key={i}><p>변경 전: {c.before || "기록 없음"}</p><p>변경 후: {c.after || "기록 없음"}</p></div>)}<p className={styles.muted}>재검수 기록: {h.status ? labels[h.status] || h.status : "미기록"}</p></div>)}</section>}
    {onReview && <div className={styles.selectionAction}><button className={styles.primary} onClick={onReview}>이 항목 검토하기</button><p className={styles.muted}>저장·재검수·승인은 별도 단계입니다.</p></div>}
    <details className={styles.diagnostics}><summary>진단 · 식별자와 변경 이력</summary><p>항목 {detail.item.id}</p><p>저장 표시값 {detail.item.label}</p><p>실행 {detail.run_id || "미기록"}</p><p>변경 묶음 {detail.changeset_id || "없음"}</p>{detail.history.length ? <pre>{JSON.stringify(detail.history, null, 2)}</pre> : <p>이 항목의 저장된 수정 이력이 없습니다.</p>}</details>
  </div>;
}

export default function KnowledgeWorkbench() {
  const [answerTool, setAnswerTool] = useState("stored");
  const [area, setArea] = useState<Area>("overview");
  const [catalog, setCatalog] = useState<KnowledgeCatalog | null>(null);
  const [scopeKey, setScopeKey] = useState("");
  const [view, setView] = useState<KnowledgeView | null>(null);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [itemKind, setItemKind] = useState("all");
  const [selectedId, setSelectedId] = useState("");
  const [offset, setOffset] = useState(0);
  const [tool, setTool] = useState("selection");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [graphRoot, setGraphRoot] = useState("");
  const [graphMode, setGraphMode] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [relationType, setRelationType] = useState("");
  const [direction, setDirection] = useState("both");
  const [sourceId, setSourceId] = useState("");
  const [reviewState, setReviewState] = useState("");
  const [depth, setDepth] = useState(1);
  const [mobileDetail, setMobileDetail] = useState(false);
  const explorePanel = useRef<HTMLElement>(null);
  const detailPanel = useRef<HTMLElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const scope = catalog?.scopes.find(s => `${s.kind}:${s.id}` === scopeKey);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([request<KnowledgeCatalog>("/workbench/scopes", { signal: controller.signal }), request<{ items: SourceItem[] }>("/sources", { signal: controller.signal })]).then(([next, docs]) => {
      if (controller.signal.aborted) return;
      setCatalog(next); setSources(docs.items); setScopeKey(previous => previous || (next.scopes[0] ? `${next.scopes[0].kind}:${next.scopes[0].id}` : ""));
      if (!next.scopes.length) setLoading(false);
    }).catch(e => { if (!controller.signal.aborted) { setError(e.message); setLoading(false); } });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => {
    if (!scope) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ kind: scope.kind, scope_id: scope.id, q: submitted, item_kind: itemKind, offset: String(offset), relation_type: relationType, direction, source_id: sourceId, review_state: reviewState, depth: String(depth), graph_root: graphRoot });
    if (selectedId) params.set("selected_id", selectedId);
    request<KnowledgeView>(`/workbench/explore?${params}`, { signal: controller.signal }).then(next => {
      if (!controller.signal.aborted) { setView(next); setError(""); }
    }).catch(e => { if (!controller.signal.aborted) setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [scope, selectedId, itemKind, submitted, offset, reload, relationType, direction, sourceId, reviewState, depth, graphRoot]);
  const select = useCallback((id: string, keyboard = true) => { setSelectedId(id); setView(v => v ? { ...v, detail: null } : v); setLoading(true); setInspectorOpen(true); setMobileDetail(keyboard); }, []);
  useEffect(() => { if (view?.detail && mobileDetail) detailPanel.current?.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true }); }, [view?.detail, mobileDetail]);
  useEffect(() => { heading.current?.focus(); }, [area]);
  function navigate(next: Area) { setArea(next); setTool("selection"); }
  function changeScope(key: string) { setScopeKey(key); setInspectorOpen(false); setAnswerTool("stored"); setGraphRoot(""); setRelationType(""); setDirection("both"); setSourceId(""); setReviewState(""); setDepth(1); setSelectedId(""); setView(null); setQuery(""); setSubmitted(""); setOffset(0); setTool("selection"); setMobileDetail(false); setLoading(true); }
  function showList(kind = "all") { setGraphMode(false); setSubmitted(""); setQuery(""); setSelectedId(""); setRelationType(""); setReviewState(""); setSourceId(""); setItemKind(kind); setOffset(0); setLoading(true); navigate("explore"); setMobileDetail(false); }
  const counts = view?.counts;

  return <div className={styles.shell} data-focus={focusMode && area === "explore" && graphMode}>
    <AppSidebar activeMenu="knowledge" />
    <main className={styles.main} data-graph={area === "explore" && graphMode}><details className={styles.mobileMenu}><summary>전체 메뉴</summary><nav aria-label="전체 메뉴"><Link href="/">민원 선택</Link><Link href="/workbench">처리 워크벤치</Link><Link href="/admin">관리자 통계</Link><Link href="/intelligence">민원 인텔리전스</Link></nav></details>
      <header className={styles.header}><div><h1 ref={heading} tabIndex={-1}>회사 지식</h1></div><button className={styles.secondary} onClick={() => { setLoading(true); setReload(v => v + 1); }}>새로고침</button></header>
      <nav aria-label="회사 지식 작업" className={styles.navigation}>{areas.map(([id, name]) => <button key={id} aria-current={area === id ? "page" : undefined} onClick={() => navigate(id)}>{name}</button>)}</nav>
      <section className={styles.scopeBar} aria-label="현재 탐색 범위">
        <label>자료와 저장 버전<select value={scopeKey} disabled={!catalog?.scopes.length} onChange={e => changeScope(e.target.value)}><option value="" disabled>{catalog?.scopes.length ? "저장 결과 선택" : "탐색할 업무 저장 결과 없음"}</option>{catalog?.scopes.map(s => <option key={`${s.kind}:${s.id}`} value={`${s.kind}:${s.id}`}>{s.version_files?.length ? s.version_files.map(knowledgeVersionName).join(' / ') : s.title} · {knowledgeDate(s.created_at)} · {labels[s.status] || s.status}</option>)}</select></label>
        <div className={styles.scopeState}><span className={styles.badge}>{scope?.data_label || "등록 자료와 검토 도구를 확인하세요"}</span>{scope && <span>{labels[scope.status] || scope.status} · {knowledgeDate(scope.created_at)}</span>}</div>
        {scope && <KnowledgeUsageState key={scopeKey} scope={scope} reload={reload} selectedClaimIds={view?.scope.id === scope.id && view.scope.kind === scope.kind ? view.detail?.claims.map(c => c.id) || [] : []} onOpenScope={key => { changeScope(key); navigate('overview'); }} />}
      </section>
      {error && <div className={styles.error} role="alert">{error} <button onClick={() => { setLoading(true); setReload(v => v + 1); }}>다시 읽기</button></div>}
      {loading && <p role="status" className={styles.loading}>선택한 저장 결과를 읽는 중입니다…</p>}
      {area === "overview" && <section className={styles.panel}>
        <div className={styles.panelHeader}><div><p className={styles.eyebrow}>선택 범위 현황</p><h2>{scope?.title || "자료에서 시작하세요"}</h2></div><button className={styles.primary} onClick={() => showList()} disabled={!view}>지식 탐색하기</button></div>
        {!view ? <div className={styles.empty}><p>{loading ? "현황을 확인하고 있습니다." : "자동 추출 업무 결과가 없습니다. 등록 자료와 기존 검토 지식은 각 작업에서 확인할 수 있습니다."}</p><button className={styles.secondary} onClick={() => navigate("sources")}>자료 보기</button></div> : <>
          <div className={styles.metrics}>{[['대상', counts?.nodes, 'node'], ['관계', counts?.relations, 'relation'], ['자료', counts?.sources, 'sources']].map(([label, n, action]) => <button key={String(label)} onClick={() => action === 'sources' ? navigate('sources') : showList(String(action))}><span>{String(label)}</span><strong>{n == null ? "미확인" : Number(n).toLocaleString()}</strong><span>목록 보기 →</span></button>)}</div>
          <p className={styles.muted}>{view.count_policy}</p>
          <div className={styles.overviewRows}><div><h3>원문 처리</h3><p>원문 구간 {counts?.blocks.toLocaleString()}개 · 자료 버전 {counts?.versions}개</p></div><div><h3><button className={styles.textLink} onClick={() => showList("claim")}>추출과 검토 →</button></h3><p>주장 {counts?.claims}개 · 추출 오류 또는 대체 기록 {counts?.excluded_claims}개</p><p className={styles.muted}>{Object.entries(counts?.claim_review || {}).map(([state, n]) => `${labels[state] || state} ${n}개`).join(' · ')}</p></div><div><h3><button className={styles.textLink} onClick={() => showList("concept")}>개념화 기록 →</button></h3><p>대상 기록 {counts?.concepts}개 · 실패 기록 {counts?.failed_concepts}개</p><p className={styles.muted}>자동 개념화 기록입니다. 승인된 온톨로지 수가 아닙니다.</p></div></div>
          {scope && <KnowledgeChanges key={scopeKey} scope={scope} onOpen={() => { navigate("review"); setTool("changes"); }} />}
          {view.scope.graph_available === false && <p className={styles.warning}>저장된 그래프가 없습니다. 대상·관계 전체 수는 미확인입니다.</p>}
          {view.scope.partial && <p className={styles.warning}>일부 구축된 결과입니다. 검색 가능한 원문과 추출된 그래프의 범위가 다를 수 있습니다.</p>}
          <details className={styles.diagnostics}><summary>범위 식별자와 집계 기준</summary><p>{view.scope.kind} · {view.scope.id}</p><p>자료 버전 {view.scope.version_ids?.join(' / ') || '미기록'}</p><p>같은 이름도 저장 ID가 다르면 별도 대상입니다. 실행 간 지식을 합산하지 않았습니다.</p></details>
        </>}
      </section>}
      {area === "sources" && <div className={styles.legacy}><KnowledgeSources key={scopeKey} versionIds={view?.scope.version_ids} /></div>}
      {area === "explore" && <section ref={explorePanel} className={`${styles.panel} ${graphMode ? styles.graphWorkspace : ""}`}>
        <div className={styles.panelHeader}><h2>{graphMode ? "지식 지도" : "대상과 관계 찾기"}</h2><div className={styles.viewSwitch}><button aria-pressed={!graphMode} onClick={() => setGraphMode(false)}>목록</button><button aria-pressed={graphMode} onClick={() => { setGraphRoot(selectedId); setGraphMode(true); setInspectorOpen(!!selectedId); }}>그래프</button>{graphMode && <><button aria-pressed={focusMode} onClick={() => setFocusMode(v => !v)}>{focusMode ? "기본 화면" : "집중 보기"}</button><button aria-expanded={inspectorOpen} disabled={!selectedId} onClick={() => { setInspectorOpen(v => !v); setMobileDetail(true); }}>선택 상세</button></>}<span className={styles.muted}>검색 일치 {view?.filtered_count ?? '미확인'}개</span></div></div>
        <form className={styles.filters} onSubmit={e => { e.preventDefault(); setSubmitted(query); setGraphRoot(""); setSelectedId(""); setDepth(1); setOffset(0); setLoading(true); setMobileDetail(false); }}><label>이름 또는 관계<input value={query} onChange={e => setQuery(e.target.value)} placeholder="확인할 업무나 대상을 검색하세요" /></label><label>항목 종류<select value={itemKind} onChange={e => { setItemKind(e.target.value); setOffset(0); setLoading(true); }}><option value="all">전체</option><option value="node">대상과 업무 내용</option><option value="entity">대상</option><option value="event">업무 내용</option><option value="relation">관계</option><option value="claim">검토 대상 주장</option><option value="concept">자동 개념화 기록</option></select></label><button className={styles.primary} disabled={!scope}>찾기</button></form>
        <details className={styles.filterDetails}><summary>연결 필터 · 관계 / 방향 / 출처 / 검토 상태</summary><div className={styles.filters}>
          <label>관계 종류<select value={relationType} onChange={e => { setRelationType(e.target.value); setOffset(0); setLoading(true); }}><option value="">전체 관계</option>{view?.filters.relation_types.map(v => <option key={v} value={v}>{relationLabel(v)}</option>)}</select></label>
          <label>이웃 방향<select value={direction} onChange={e => { setDirection(e.target.value); setLoading(true); }}><option value="both">양방향</option><option value="out">선택에서 나가는 연결</option><option value="in">선택으로 들어오는 연결</option></select></label>
          <label>출처<select value={sourceId} onChange={e => { setSourceId(e.target.value); setOffset(0); setLoading(true); }}><option value="">전체 출처</option>{view?.filters.sources.map(v => <option key={v.id} value={v.id}>{v.title}</option>)}</select></label>
          <label>검토 상태<select value={reviewState} onChange={e => { setReviewState(e.target.value); setOffset(0); setLoading(true); }}><option value="">전체 상태</option>{view?.filters.review_states.map(v => <option key={v} value={v}>{labels[v] || v}</option>)}</select></label>
        </div></details>
        <div className={styles.mobileSwitch}><button aria-pressed={!mobileDetail} onClick={() => setMobileDetail(false)}>목록</button><button aria-pressed={mobileDetail} onClick={() => setMobileDetail(true)} disabled={!selectedId}>선택 상세</button></div>
        <div className={styles.split} data-detail={mobileDetail} data-graph={graphMode} data-inspector={inspectorOpen}><div className={styles.listPane}>
          {graphMode && view ? <KnowledgeGraph key={scopeKey} graph={view.graph} selectedId={selectedId} rootId={graphRoot} dataLabel={view.scope.data_label} onSelect={select} busy={loading} onFocus={() => { setGraphRoot(selectedId); setDepth(1); setLoading(true); }} onExpand={() => { setDepth(d => Math.min(3, d + 1)); setLoading(true); }} onReset={() => { setGraphRoot(""); setSelectedId(""); setDepth(1); setLoading(true); setMobileDetail(false); }} /> : <>
          {view?.items.length === 0 && <div className={styles.empty}>현재 조건에 맞는 항목이 없습니다. 검색어와 종류를 확인하세요.</div>}
          <ul className={styles.itemList}>{view?.items.map(item => <li key={item.id}><button aria-pressed={selectedId === item.id} onClick={() => select(item.id)}><span className={styles.eyebrow}>{labels[item.kind] || item.kind}</span><strong>{itemLabel(item)}</strong>{item.disambiguation && <span>구분 근거: {item.disambiguation}</span>}{item.state && <span>{labels[item.state] || item.state}{item.issue ? " · 오류 기록 있음" : ""}</span>}{item.kind === 'relation' && <span>{item.head_label} → {item.tail_label}</span>}</button></li>)}</ul>
          {!!view?.filtered_count && <div className={styles.pagination}><button disabled={offset === 0 || loading} onClick={() => { setOffset(Math.max(0, offset - 40)); setLoading(true); }}>이전</button><span>{offset + 1}–{Math.min(offset + 40, view.filtered_count)} / {view.filtered_count}</span><button disabled={offset + 40 >= view.filtered_count || loading} onClick={() => { setOffset(offset + 40); setLoading(true); }}>다음</button></div>}
        </>}
        </div><aside ref={detailPanel} className={styles.detailPane} aria-label="선택 항목 상세">{graphMode && <div className={styles.inspectorHeader}><span>선택 항목</span><button aria-label="선택 상세 닫기" onClick={() => { setInspectorOpen(false); setMobileDetail(false); }}>×</button></div>}{loading && selectedId ? <p className={styles.empty}>선택한 항목을 읽고 있습니다…</p> : <KnowledgeSelection key={selectedId} detail={view?.detail || null} onSelect={select} onReview={() => navigate('review')} />}</aside></div>
      </section>}
      {area === "review" && <section className={styles.panel}>
        <div className={styles.panelHeader}><h2>검토와 변경</h2></div><div className={styles.tools} role="group" aria-label="검토 작업">{[['selection','선택 항목'],['changes','원문 변경·영향'],['business','업무 검토 도구'],['extraction','개체·사실 검토'],['ontology','온톨로지 검토'],['snapshots','사용 버전 관리']].map(([id,label]) => <button key={id} aria-pressed={tool===id} onClick={() => setTool(id)}>{label}</button>)}</div>
        {tool === 'selection' && <div className={styles.reviewDetail}><p className={styles.muted}>저장, 재검수, 승인, 사용 버전 반영은 각각 별도의 단계입니다.</p>{view?.detail && <KnowledgeItemReview key={`${scopeKey}:${view.detail.item.id}`} detail={view.detail} onOpenSaved={(runId, id) => { setScopeKey(`run:${runId}`); setSelectedId(id || ""); setGraphRoot(""); setView(null); setQuery(""); setSubmitted(""); setLoading(true); setReload(r => r + 1); navigate('explore'); }} />}<KnowledgeSelection detail={view?.detail || null} onSelect={id => { select(id); navigate('explore'); }} /></div>}
        {tool === 'changes' && scope && <KnowledgeChanges key={scopeKey} scope={scope} onOpenScope={key => { changeScope(key); navigate('overview'); }} />}
        {tool !== 'selection' && tool !== 'changes' && <div className={styles.legacy}><p className={styles.warning}>기존 검토 도구의 별도 범위입니다. 아래에서 실행 또는 버전을 확인하세요.</p>{tool==='business' && <KnowledgeBusiness key={scopeKey} request={request} sources={sources} visible initialRunId={scope?.kind === "run" ? scope.id : view?.detail?.run_id} />}{tool==='extraction' && <KnowledgeExtraction request={request} sources={sources} />}{tool==='ontology' && <KnowledgeOntology request={request} sources={sources} />}{tool==='snapshots' && <KnowledgeSnapshots request={request} visible />}</div>}
      </section>}
      {area === "search" && <section className={styles.panel}><div className={styles.tools}><button aria-pressed={answerTool === 'stored'} onClick={() => setAnswerTool('stored')}>선택 범위의 저장 답변</button><button aria-pressed={answerTool === 'new'} onClick={() => setAnswerTool('new')}>사용 버전에서 새 검색</button></div>{answerTool === 'stored' ? scope ? <KnowledgeStoredAnswers key={scopeKey} scope={scope} onExplore={id => { select(id); navigate('explore'); }} /> : <p className={styles.empty}>저장 범위를 선택하세요.</p> : <div className={styles.legacy}><p className={styles.warning}>아래에서 별도로 선택한 사용 버전으로 새 검색을 실행합니다. 상단의 자동 추출 실행과 다른 범위입니다.</p><KnowledgeSearch key={scopeKey} request={request} visible /></div>}</section>}
    </main>
  </div>;
}
