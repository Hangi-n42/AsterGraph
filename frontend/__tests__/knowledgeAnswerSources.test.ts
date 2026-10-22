import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import KnowledgeAnswerSources, { type AnswerSourceCitations } from "../components/KnowledgeAnswerSources";

const base: AnswerSourceCitations = {
  status: "recorded", citations: [], duplicates_removed: 0, answer_binding: "global", semantic_support: "not_assessed",
};
const render = (record?: AnswerSourceCitations) => renderToStaticMarkup(createElement(KnowledgeAnswerSources, { record }));

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
