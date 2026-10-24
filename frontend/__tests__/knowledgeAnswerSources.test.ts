import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import KnowledgeAnswerSources, { type AnswerSourceCitations } from "../components/KnowledgeAnswerSources";

const base: AnswerSourceCitations = {
  status: "recorded", citations: [], duplicates_removed: 0, answer_binding: "global", semantic_support: "not_assessed",
};
const render = (record?: AnswerSourceCitations) => renderToStaticMarkup(createElement(KnowledgeAnswerSources, { record }));

it("labels explicitly corrected references without calling them model declarations", () => {
  const html=renderToStaticMarkup(createElement(KnowledgeAnswerSources,{claimBodies:{status:"recorded",claims:{}},links:{status:"recorded",semantic_support:"not_assessed",relation:"reviewer_corrected",
    links:[{status:"resolved",declaration:{target:"answer",anchor:"직접 사실",claim_refs:[],quote_refs:["sq_kept"]}}],
    claims_without_resolved_links:[],duplicates_removed:0}}));
  for(const text of ["명시 정정된 인용 연결","정정 후 주장 참조: 없음","정정 후 주장 참조 · 원래 생성 입력","정정 후 연결 진단","모델 자동 교정이나 일반 의미 검증 결과가 아닙니다"]) expect(html).toContain(text);
  expect(html).not.toContain("답변 구절의 모델 선언 연결");
});

it("keeps a missing historical quotation distinct from an explicitly empty list", () => {
  expect(render()).toContain("별도로 반환한 원문 구절이 기록되지 않았습니다");
  expect(render({ ...base, status: "not_recorded" })).toContain("별도로 반환한 원문 구절이 기록되지 않았습니다");
  expect(render(base)).toContain("목록을 비워 반환했습니다");
  expect(render(base)).not.toContain("별도로 반환한 원문 구절이 기록되지 않았습니다");
  expect(render()).not.toContain("주장 인용");
  expect(render()).not.toContain("직접 원문 인용이 기록되지");
});

it("shows matched and unresolved source quotes without asserting sentence support", () => {
  const html = render({ ...base, status: "unresolved", citations: [
    { quote: "상품 무게: 0.5kg", address_status: "matched", source_version_id: "v", parse_run_id: "p", block_id: "b", start_char: 0, end_char: 12 },
    { quote: "미확정 인용", address_status: "unresolved" },
  ] });
  for (const text of ["원문 위치 일치", "원문 위치 미확정", "상품 무게: 0.5kg", "미확정 인용", "문장별 의미 지지 판정이 아닙니다", "연결은 기록되지 않았습니다"]) expect(html).toContain(text);
});

it("withholds source quotations when the existing answer gate requires review", () => {
  const html = render({ ...base, status: "needs_review", citations: [{ quote: "상품 무게: 0.5kg", address_status: "matched" }] });
  expect(html).toContain("원문 구절을 표시하지 않습니다");
  expect(html).not.toContain("목록을 비워 반환했습니다");
  expect(html).not.toContain("상품 무게: 0.5kg");
});

it("renders declared anchors and references without claiming semantic support or coverage", () => {
  const links = { status: "recorded" as const, semantic_support: "not_assessed" as const, relation: "model_declared" as const,
    links: [{ status: "resolved" as const, declaration: { target: "answer", anchor: "일반 특성 구절", claim_refs: [], quote_refs: ["sq_alpha"] },
      location: { target: "answer" as const, start_char: 0, end_char: 8 } }],
    claims_without_resolved_links: ["kept-global"], duplicates_removed: 0 };
  const html = renderToStaticMarkup(createElement(KnowledgeAnswerSources, { record: base, links }));
  for (const text of ["일반 특성 구절", "대상: 답변 본문", "선언한 주장 참조: 없음", "sq_alpha", "모델이 선언한 연결", "의미 지지는 검증하지", "해석가능한 연결 미기록", "미사용 또는 허위 주장 판정이 아닙니다"]) expect(html).toContain(text);
  expect(html).not.toContain("연결은 기록되지 않았습니다");
  const empty = renderToStaticMarkup(createElement(KnowledgeAnswerSources, { links: { ...links, links: [] } }));
  expect(empty).toContain("답변 전체의 근거 충족을 뜻하지 않습니다");
  const blocked = renderToStaticMarkup(createElement(KnowledgeAnswerSources, { record: { ...base, status: "needs_review" }, links }));
  for (const text of ["일반 특성 구절", "sq_alpha", "kept-global", "원래 연결 선언"]) expect(blocked).not.toContain(text);
});

it("keeps malformed link declarations readable as diagnostics", () => {
  const html = renderToStaticMarkup(createElement(KnowledgeAnswerSources, { links: { status: "unresolved", semantic_support: "not_assessed", relation: "model_declared",
    links: [{ status: "unresolved", declaration: { target: [], anchor: { bad: true } } }], claims_without_resolved_links: [], duplicates_removed: 0 } }));
  expect(html).toContain("연결 미확정");
  expect(html).toContain("원래 연결 선언 진단");
  expect(html).not.toContain("연결 목록을 비워 반환했습니다");
});

const inspection = {
  status:"recorded" as const, relation:"model_declared" as const, semantic_support:"not_assessed" as const,
  duplicates_removed:0,claims_without_resolved_links:[],quote_lookup:{sq_local:{status:"resolved",citation_index:1}},
  links:[{status:"resolved" as const,declaration:{target:"answer",anchor:"일반 부위 설명",claim_refs:["proposal"],quote_refs:["sq_local"]}}],
};
const inspectionBodies={status:"recorded" as const,unit_id:"qa",claims:{proposal:{status:"recorded" as const,statement:"별미 세 가지를 제안했다",body_origin:"raw_duplicate" as const,source_version_ids:["v"]}}};
const quoteRecord: AnswerSourceCitations={...base,citations:[
  {quote:"다른 원문",quote_ids:["sq_other"],address_status:"matched"},
  {quote:"등심은 담백해 어떤 요리에도 무난하게 어울린다.",quote_ids:["sq_local"],address_status:"matched",source_version_id:"v",parse_run_id:"p",block_id:"b",start_char:582,end_char:608},
]};

it("inspects recorded claim bodies and exact quotes through opaque ID lookup without changing declarations",()=>{
  const props={record:quoteRecord,links:inspection,claimBodies:inspectionBodies};const before=structuredClone(props);
  const html=renderToStaticMarkup(createElement(KnowledgeAnswerSources,props));
  for(const s of ["별미 세 가지를 제안했다","일반 부위 설명","연결된 원문 구절 · 해당 답변의 기록된 위치","문자 [582, 608)","의미 지지는 검증하지"]) expect(html).toContain(s);
  expect(props).toEqual(before);
  expect(html).not.toContain("직접지원");
});

it.each([undefined,{sq_local:{status:"unresolved"}},{sq_local:{status:"resolved",citation_index:0}},{sq_local:{status:"resolved",citation_index:99}}])("does not guess a source from an unavailable or conflicting lookup %j",lookup=>{
  const html=renderToStaticMarkup(createElement(KnowledgeAnswerSources,{record:quoteRecord,links:{...inspection,quote_lookup:lookup},claimBodies:{status:"unresolved",claims:{proposal:{status:"unresolved"}}}}));
  expect(html).toContain("저장된 원문 참조 연결을 확인할 수 없습니다");
  expect(html).toContain("생성 입력의 주장 본문을 확인할 수 없습니다");
});

it("withholds the added bodies and quotes on review and preserves source-only declarations",()=>{
  const blocked=renderToStaticMarkup(createElement(KnowledgeAnswerSources,{record:quoteRecord,links:inspection,claimBodies:{...inspectionBodies,status:"needs_review"}}));
  for(const s of ["별미 세 가지를 제안했다","일반 부위 설명","sq_local","582"]) expect(blocked).not.toContain(s);
  const sourceOnly=renderToStaticMarkup(createElement(KnowledgeAnswerSources,{record:quoteRecord,links:{...inspection,links:[{status:"resolved",declaration:{target:"answer",anchor:"일반 부위 설명",claim_refs:[],quote_refs:["sq_local"]}}]},claimBodies:{status:"recorded",claims:{}}}));
  expect(sourceOnly).toContain("주장 참조 없이 원문 참조만 선언했습니다");
  const immediate=renderToStaticMarkup(createElement(KnowledgeAnswerSources,{record:quoteRecord,links:inspection}));
  expect(immediate).not.toContain("모델이 연결한 주장 본문 · 생성 입력");
});

it.each(["missing_parse","duplicate_id","invalid_span"])("keeps an invalid source address local to the inspection %s",fault=>{
  const record=structuredClone(quoteRecord);
  if(fault==="missing_parse") delete record.citations[1].parse_run_id;
  else if(fault==="duplicate_id") record.citations[0].quote_ids=["sq_local"];
  else record.citations[1].end_char=500;
  const html=renderToStaticMarkup(createElement(KnowledgeAnswerSources,{record,links:inspection,claimBodies:inspectionBodies}));
  expect(html).toContain("저장된 원문 참조 연결을 확인할 수 없습니다");
  expect(html).toContain("별미 세 가지를 제안했다");
});
