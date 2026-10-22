export type AnswerSourceCitations = {
  status: "not_recorded" | "recorded" | "unresolved" | "needs_review";
  answer_binding: "global";
  semantic_support: "not_assessed";
  duplicates_removed: number;
  citations: {
    quote: string; address_status: "matched" | "unresolved";
    source_title?: string; source_version_id?: string; parse_run_id?: string;
    block_id?: string; start_char?: number; end_char?: number; quote_ids?: string[];
  }[];
};

export type AnswerLinks = {
  status: "not_recorded" | "recorded" | "unresolved" | "needs_review";
  semantic_support: "not_assessed"; relation: "model_declared";
  links: { status: "resolved" | "unresolved"; declaration: unknown;
    location?: { target: "answer" | "limitations"; limitation_index?: number; start_char: number; end_char: number } }[];
  claims_without_resolved_links: string[]; duplicates_removed: number;
};

type Declaration = { target: "answer" | "limitations"; anchor: string; claim_refs: string[]; quote_refs: string[] };
function isDeclaration(value: unknown): value is Declaration {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (v.target === "answer" || v.target === "limitations") && typeof v.anchor === "string" &&
    Array.isArray(v.claim_refs) && v.claim_refs.every(x => typeof x === "string") &&
    Array.isArray(v.quote_refs) && v.quote_refs.every(x => typeof x === "string");
}

export default function KnowledgeAnswerSources({ record, links }: { record?: AnswerSourceCitations; links?: AnswerLinks }) {
  const withheld = record?.status === "needs_review" || links?.status === "needs_review";
  return <section className="my-4 rounded border p-3 text-sm">
    <h3 className="font-semibold">별도로 반환한 원문 구절</h3>
    {withheld ? <p>사용 상태 또는 요구 변경으로 원문 구절을 표시하지 않습니다.</p> : !record || record.status === "not_recorded" ?
      <p>당시 응답에는 별도로 반환한 원문 구절이 기록되지 않았습니다. 기존 인용 ID의 근거와 구분합니다.</p> : <>
        {!record.citations.length && <p>응답이 원문 인용 목록을 비워 반환했습니다.</p>}
        {record.status === "unresolved" && <p>위치를 확인하지 못한 원문 인용이 있습니다.</p>}
        {record.citations.map((citation, i) => <article key={i} className="my-2 border-t pt-2">
          <p>{citation.source_title || "원문 인용"} · {citation.address_status === "matched" ? "원문 위치 일치" : "원문 위치 미확정"}</p>
          <blockquote className="whitespace-pre-wrap">{citation.quote}</blockquote>
          {!!citation.quote_ids?.length && <p>이번 응답의 원문 참조: {citation.quote_ids.join(", ")}</p>}
          {citation.address_status === "matched" && <details><summary>저장된 원문 위치</summary>
            <p>원문 버전 {citation.source_version_id} · 원문 처리 기록 {citation.parse_run_id}</p>
            <p>구간 {citation.block_id} · 문자 [{citation.start_char}, {citation.end_char})</p>
          </details>}
        </article>)}
        {!!record.duplicates_removed && <p>같은 위치의 반복 인용 {record.duplicates_removed}건을 합쳤습니다.</p>}
      </>}
    {!withheld && links && links.status !== "not_recorded" && <div className="border-t pt-2">
      <h4 className="font-semibold">답변 구절의 모델 선언 연결</h4>
      {links.status === "recorded" && !links.links.length && <p>연결 목록을 비워 반환했습니다. 답변 전체의 근거 충족을 뜻하지 않습니다.</p>}
      {links.status === "unresolved" && <p>구절 또는 참조를 해석하지 못한 연결이 있습니다.</p>}
      {links.links.map((link, i) => <article key={i} className="my-2 border-t pt-2">
        <p>연결 {i + 1} · {link.status === "resolved" ? "구절·참조 해석됨" : "연결 미확정"}</p>
        {isDeclaration(link.declaration) && <>
          <p>대상: {link.declaration.target === "answer" ? "답변 본문" : "한계 설명"}</p>
          <blockquote className="whitespace-pre-wrap">{link.declaration.anchor}</blockquote>
          <p>선언한 주장 참조: {link.declaration.claim_refs.join(", ") || "없음"}</p>
          <p>선언한 원문 참조: {link.declaration.quote_refs.join(", ") || "없음"}</p>
        </>}
        {link.location && <p>{link.location.target === "answer" ? "답변" : `한계 항목 ${(link.location.limitation_index ?? 0) + 1}`} · 문자 [{link.location.start_char}, {link.location.end_char})</p>}
        <details><summary>원래 연결 선언 진단</summary><pre className="whitespace-pre-wrap">{JSON.stringify(link.declaration, null, 2)}</pre></details>
      </article>)}
      {!!links.duplicates_removed && <p>동일한 연결 선언 {links.duplicates_removed}건을 합쳤습니다.</p>}
      {!!links.claims_without_resolved_links.length && <details><summary>해석가능한 연결 미기록 주장 {links.claims_without_resolved_links.length}개</summary><p>{links.claims_without_resolved_links.join(", ")}</p><p>미사용 또는 허위 주장 판정이 아닙니다.</p></details>}
      <p>모델이 선언한 연결입니다. 실제 내부 사용이나 개별 주장과 원문 사이의 의미 지지는 검증하지 않았습니다.</p>
    </div>}
    <p className="mt-2 text-slate-600">원문 위치 일치는 문장별 의미 지지 판정이 아닙니다.{!withheld && (!links || links.status === "not_recorded") && " 답변 구절과의 연결은 기록되지 않았습니다."}</p>
  </section>;
}
