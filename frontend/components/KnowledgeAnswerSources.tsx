export type AnswerSourceCitations = {
  status: "not_recorded" | "recorded" | "unresolved" | "needs_review";
  answer_binding: "global";
  semantic_support: "not_assessed";
  duplicates_removed: number;
  citations: {
    quote: string; address_status: "matched" | "unresolved";
    source_title?: string; source_version_id?: string; parse_run_id?: string;
    block_id?: string; start_char?: number; end_char?: number;
  }[];
};

export default function KnowledgeAnswerSources({ record }: { record?: AnswerSourceCitations }) {
  return <section className="my-4 rounded border p-3 text-sm">
    <h3 className="font-semibold">별도로 반환한 원문 구절</h3>
    {record?.status === "needs_review" ? <p>사용 상태 또는 요구 변경으로 원문 구절을 표시하지 않습니다.</p> : !record || record.status === "not_recorded" ?
      <p>당시 응답에는 별도로 반환한 원문 구절이 기록되지 않았습니다. 기존 인용 ID의 근거와 구분합니다.</p> : <>
        {!record.citations.length && <p>응답이 원문 인용 목록을 비워 반환했습니다.</p>}
        {record.status === "unresolved" && <p>위치를 확인하지 못한 원문 인용이 있습니다.</p>}
        {record.citations.map((citation, i) => <article key={i} className="my-2 border-t pt-2">
          <p>{citation.source_title || "원문 인용"} · {citation.address_status === "matched" ? "원문 위치 일치" : "원문 위치 미확정"}</p>
          <blockquote className="whitespace-pre-wrap">{citation.quote}</blockquote>
          {citation.address_status === "matched" && <details><summary>저장된 원문 위치</summary>
            <p>원문 버전 {citation.source_version_id} · 원문 처리 기록 {citation.parse_run_id}</p>
            <p>구간 {citation.block_id} · 문자 [{citation.start_char}, {citation.end_char})</p>
          </details>}
        </article>)}
        {!!record.duplicates_removed && <p>같은 위치의 반복 인용 {record.duplicates_removed}건을 합쳤습니다.</p>}
      </>}
    <p className="mt-2 text-slate-600">원문 위치 일치는 문장별 의미 지지 판정이 아닙니다. 답변 구절과의 연결은 기록되지 않았습니다.</p>
  </section>;
}
