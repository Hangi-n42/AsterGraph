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
