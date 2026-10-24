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
  semantic_support: "not_assessed"; relation: "model_declared" | "reviewer_corrected";
  links: { status: "resolved" | "unresolved"; declaration: unknown;
    location?: { target: "answer" | "limitations"; limitation_index?: number; start_char: number; end_char: number } }[];
  claims_without_resolved_links: string[]; duplicates_removed: number;
  quote_lookup?: Record<string, { status: string; citation_index?: number }>;
};

export type AnswerLinkClaims = {
  status: "recorded" | "unresolved" | "needs_review"; unit_id?: string;
  claims: Record<string, { status: "recorded" | "unresolved"; statement?: string;
    body_origin?: "statement" | "raw_duplicate"; source_version_ids?: string[] }>;
};
type ClaimEvidence = { id: string; evidence: { quote?: string; precision?: string; source_version_id?: string;
  parse_run_id?: string; block_id?: string; start_char?: number; end_char?: number }[] };

function linkedQuote(id: string, links: AnswerLinks, record?: AnswerSourceCitations) {
  const lookup = links.quote_lookup?.[id];
  if (lookup?.status !== "resolved" || !Number.isInteger(lookup.citation_index) || lookup.citation_index! < 0) return;
  const citation = record?.citations[lookup.citation_index!];
  if (!citation || citation.address_status !== "matched" || !Array.isArray(citation.quote_ids) || !citation.quote_ids.includes(id) ||
    record!.citations.filter(c => Array.isArray(c.quote_ids) && c.quote_ids.includes(id)).length !== 1 ||
    [citation.source_version_id, citation.parse_run_id, citation.block_id, citation.quote].some(v => typeof v !== "string" || !v.trim()) ||
    !Number.isInteger(citation.start_char) || !Number.isInteger(citation.end_char) ||
    citation.start_char! < 0 || citation.end_char! <= citation.start_char!) return;
  return citation;
}

type Declaration = { target: "answer" | "limitations"; anchor: string; claim_refs: string[]; quote_refs: string[] };
function isDeclaration(value: unknown): value is Declaration {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (v.target === "answer" || v.target === "limitations") && typeof v.anchor === "string" &&
    Array.isArray(v.claim_refs) && v.claim_refs.every(x => typeof x === "string") &&
    Array.isArray(v.quote_refs) && v.quote_refs.every(x => typeof x === "string");
}

export default function KnowledgeAnswerSources({ record, links, claimBodies, claimEvidence = [] }: {
  record?: AnswerSourceCitations; links?: AnswerLinks; claimBodies?: AnswerLinkClaims; claimEvidence?: ClaimEvidence[];
}) {
  const withheld = record?.status === "needs_review" || links?.status === "needs_review" || claimBodies?.status === "needs_review";
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
      <h4 className="font-semibold">{links.relation === "reviewer_corrected" ? "명시 정정된 인용 연결" : "답변 구절의 모델 선언 연결"}</h4>
      {links.status === "recorded" && !links.links.length && <p>연결 목록을 비워 반환했습니다. 답변 전체의 근거 충족을 뜻하지 않습니다.</p>}
      {links.status === "unresolved" && <p>구절 또는 참조를 해석하지 못한 연결이 있습니다.</p>}
      {links.links.map((link, i) => {
        const declaration = isDeclaration(link.declaration) ? link.declaration : null;
        return <article key={i} className="my-2 border-t pt-2">
        <p>연결 {i + 1} · {link.status === "resolved" ? "구절·참조 해석됨" : "연결 미확정"}</p>
        {isDeclaration(link.declaration) && <>
          <p>대상: {link.declaration.target === "answer" ? "답변 본문" : "한계 설명"}</p>
          <blockquote className="whitespace-pre-wrap">{link.declaration.anchor}</blockquote>
          <p>{links.relation === "reviewer_corrected" ? "정정 후 주장 참조" : "선언한 주장 참조"}: {link.declaration.claim_refs.join(", ") || "없음"}</p>
          <p>선언한 원문 참조: {link.declaration.quote_refs.join(", ") || "없음"}</p>
        </>}
        {link.location && <p>{link.location.target === "answer" ? "답변" : `한계 항목 ${(link.location.limitation_index ?? 0) + 1}`} · 문자 [{link.location.start_char}, {link.location.end_char})</p>}
        {claimBodies && declaration && <>
          <details><summary>{links.relation === "reviewer_corrected" ? "정정 후 주장 참조 · 원래 생성 입력" : "모델이 연결한 주장 본문 · 생성 입력"}</summary>
            {!declaration.claim_refs.length && <p>이 연결에는 주장 참조 없이 원문 참조만 선언했습니다.</p>}
            {declaration.claim_refs.map((id, j) => {
              const body = claimBodies.claims[id];
              const scope = claimEvidence.filter(c => c.id === id);
              return <div key={j} className="my-2"><p className="break-all">{id}</p>
                {body?.status === "recorded" && typeof body.statement === "string" ? <>
                  <blockquote className="whitespace-pre-wrap">{body.statement}</blockquote>
                  <p>{body.body_origin === "raw_duplicate" ? "입력 원형에서 복원한 본문" : "입력에 기록된 본문"}</p>
                  <details><summary>생성 입력 위치·버전</summary><p>QA 기록 {claimBodies.unit_id}</p><p>원문 버전 {body.source_version_ids?.join(", ")}</p></details>
                </> : <p>생성 입력의 주장 본문을 확인할 수 없습니다.</p>}
                <details><summary>선택한 지식 버전의 저장 근거 · 생성 입력 본문과 별도</summary>
                  {scope.length === 1 && scope[0].evidence.length ? scope[0].evidence.map((e, k) => <div key={k}>
                    <p>{e.precision === "chunk" ? "넓은 문맥 근거 (chunk)" : `저장 범위 (${e.precision || "정밀도 미기록"})`}</p>
                    <p>원문 버전 {e.source_version_id || "미기록"} · 처리 기록 {e.parse_run_id || "미기록"} · 구간 {e.block_id || "미기록"}</p>
                    <p>문자 [{e.start_char ?? "미기록"}, {e.end_char ?? "미기록"})</p><blockquote>{e.quote || "원문 구절 미기록"}</blockquote>
                  </div>) : <p>선택한 지식 버전의 근거 연결을 확인할 수 없습니다.</p>}
                </details>
              </div>;
            })}
          </details>
          <details><summary>연결된 원문 구절 · 해당 답변의 기록된 위치</summary>
            {declaration.quote_refs.map((id, j) => {
              const citation = linkedQuote(id, links, record);
              return <div key={j} className="my-2"><p>{id}</p>{citation ? <>
                <blockquote className="whitespace-pre-wrap">{citation.quote}</blockquote>
                <p>원문 버전 {citation.source_version_id} · 처리 기록 {citation.parse_run_id}</p>
                <p>구간 {citation.block_id} · 문자 [{citation.start_char}, {citation.end_char})</p>
              </> : <p>저장된 원문 참조 연결을 확인할 수 없습니다.</p>}</div>;
            })}
          </details>
        </>}
        <details><summary>{links.relation === "reviewer_corrected" ? "정정 후 연결 진단" : "원래 연결 선언 진단"}</summary><pre className="whitespace-pre-wrap">{JSON.stringify(link.declaration, null, 2)}</pre></details>
      </article>; })}
      {!!links.duplicates_removed && <p>동일한 연결 선언 {links.duplicates_removed}건을 합쳤습니다.</p>}
      {!!links.claims_without_resolved_links.length && <details><summary>해석가능한 연결 미기록 주장 {links.claims_without_resolved_links.length}개</summary><p>{links.claims_without_resolved_links.join(", ")}</p><p>미사용 또는 허위 주장 판정이 아닙니다.</p></details>}
      <p>{links.relation === "reviewer_corrected" ? "명시적으로 정정한 참조입니다. 모델 자동 교정이나 일반 의미 검증 결과가 아닙니다." : "모델이 선언한 연결입니다. 실제 내부 사용이나 개별 주장과 원문 사이의 의미 지지는 검증하지 않았습니다."}</p>
    </div>}
    <p className="mt-2 text-slate-600">원문 위치 일치는 문장별 의미 지지 판정이 아닙니다.{!withheld && (!links || links.status === "not_recorded") && " 답변 구절과의 연결은 기록되지 않았습니다."}</p>
  </section>;
}
