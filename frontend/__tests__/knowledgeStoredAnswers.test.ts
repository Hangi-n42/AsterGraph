import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import KnowledgeStoredAnswers from "../components/KnowledgeStoredAnswers";

const hooks = vi.hoisted(() => ({ seeds: [] as unknown[] }));
vi.mock("react", async original => ({ ...await original<typeof import("react")>(), useEffect: () => {}, useState: (initial: unknown) => [hooks.seeds.length ? hooks.seeds.shift() : initial, vi.fn()] }));
vi.mock("@/lib/knowledgeWorkbench", () => import("../lib/knowledgeWorkbench"));
vi.mock("@/lib/api", () => ({ API_BASE_URL: "http://localhost" }));
vi.mock("../components/KnowledgeUsage", () => ({ KnowledgeUsageDetails: () => null }));

const scope = { kind: "source_graph" as const, id: "snapshot", title: "저장 결과", status: "selection_recorded", data_label: "저장 결과" };
const render = (evidence: Record<string, unknown>[]) => {
  const detail = { note: "저장 기록", answer: { answer: "저장 본문", limitations: ["저장 한계"] }, used_versions: [], used_version_ids: [], requirement_ids: [],
    current_usage: { requirements: [] }, evidence: evidence.map((e, i) => ({ id: `claim${i}`, cited: true, claim_ids: [`claim${i}`], evidence: [e] })),
    graph_links: [], recorded_links: [] };
  const original = structuredClone(detail);
  hooks.seeds = [[], "answer", detail, "", "", false];
  const html = renderToStaticMarkup(createElement(KnowledgeStoredAnswers, { scope, onExplore: () => {} }));
  expect(detail).toEqual(original);
  return html;
};

it("distinguishes a recorded claim range from a whole chunk and surrounding text", () => {
  const html = render([
    { block_id: "block", source_version_id: "version", parse_run_id: "parse", start_char: 367, end_char: 461, precision: "exact_unverified_meaning", quote: "생산량 구절", block_text: "주변 원문 전체" },
    { block_id: "block", source_version_id: "version", parse_run_id: "parse", start_char: 0, end_char: 1272, precision: "chunk", quote: "넓은 원문" },
  ]);
  for (const text of ["블록 내 문자 [367, 461)", "블록 내 문자 [0, 1272)", "의미 지지 미검증", "넓은 문맥 근거 (chunk)", "주변 원문 · 주장 근거 범위와 별도", "주소 범위는 문장별 의미 지지 판정이 아닙니다", "원문 버전 version", "원문 처리 기록 parse", "생산량 구절", "저장 본문", "저장 한계"]) expect(html).toContain(text);
});

it.each([
  {},
  { start_char: 0 },
  { start_char: -1, end_char: 10 },
  { start_char: 10, end_char: 0 },
  { start_char: 0, end_char: 0 },
  { start_char: 0.5, end_char: 10 },
  { start_char: NaN, end_char: Infinity },
])("does not invent zero or an exact range for incomplete/invalid address %j", fields => {
  const html = render([{ block_id: "", precision: "future_unknown", quote: "기존 구절", ...fields }]);
  for (const text of ["문자 범위 미기록·미확정", "원문 버전 미기록", "원문 처리 기록 미기록", "구간 미기록", "근거 정밀도 미기록·미확정", "기존 구절"]) expect(html).toContain(text);
  expect(html).not.toContain("블록 내 문자 [");
});
