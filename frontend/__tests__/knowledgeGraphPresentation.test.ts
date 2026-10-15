import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { graphElements } from "../components/KnowledgeGraph";
import { KnowledgeSelection } from "../components/KnowledgeWorkbench";
import type { KnowledgeDetail, KnowledgeGraphView } from "../lib/knowledgeWorkbench";

vi.mock("@/lib/knowledgeWorkbench", () => import("../lib/knowledgeWorkbench"));
vi.mock("@/lib/api", () => ({ API_BASE_URL: 'http://localhost' }));
vi.mock("@/lib/knowledgeReview", () => import("../lib/knowledgeReview"));

it("keeps distinct homonyms, parallel edge IDs and directions while abbreviating only visual labels", () => {
  const graph: KnowledgeGraphView = { depth: 1, nodes: 2, relations: 3, eligible_nodes: 2, eligible_relations: 3,
    omitted_nodes: 0, omitted_relations: 0, filter_excluded_relations: 0, selected_excluded: false, reason: 'contract fixture',
    items: [{ id: 'n1', kind: 'entity', label: '동명이름', claim_ids: ['c1'] },
      { id: 'n2', kind: 'event', label: '동명이름', claim_ids: ['c2'] },
      ...['e1', 'e2', 'e3'].map(id => ({ id, kind: 'relation', label: '저장된 긴 관계 문장 '.repeat(10), head: 'n2', tail: 'n1', claim_ids: ['c3'] }))] };
  const before = JSON.stringify(graph);
  const elements = graphElements(graph);
  expect(elements.map(e => e.data.id)).toEqual(['n1', 'n2', 'e1', 'e2', 'e3']);
  for (const edge of elements.slice(2)) {
    expect(edge.data).toMatchObject({ source: 'n2', target: 'n1', fullLabel: graph.items[2].label });
    expect(edge.data.label).toMatch(/…$/);
  }
  expect(JSON.stringify(graph)).toBe(before);
});

it("defers multi-claim evidence DOM but shows complete conditions and evidence for a single selected claim", () => {
  const claim = { id: 'c1', role: 'relation', statement: '계약 테스트 문장', review_status: 'unreviewed', editable: false,
    conditions: ['첫 번째 조건'], exceptions: ['저장 예외'], period: '저장 기간', meanings: [],
    evidence: [{ block_id: 'b1', quote: '생략하면 안 되는 전체 원문', source_title: '자료 이름', locator: { block_order: 24 } }] };
  const detail: KnowledgeDetail = { item: { id: 'node', kind: 'entity', label: '같은 이름', claim_ids: ['c1', 'c2'] },
    claims: [claim, { ...claim, id: 'c2' }], relations: [], history: [] };
  const render = (value: KnowledgeDetail) => renderToStaticMarkup(createElement(KnowledgeSelection, { detail: value, onSelect: () => {} }));
  const summary = render(detail);
  expect(summary).toContain('연결된 주장 · 2');
  expect(summary).toContain(claim.statement);
  expect(summary).not.toContain(claim.evidence[0].quote);
  const full = render({ ...detail, claims: [claim] });
  for (const text of ['첫 번째 조건', '저장 예외', '저장 기간', '생략하면 안 되는 전체 원문', '미검수', 'block_order']) expect(full).toContain(text);
});

it("keeps an unknown condition distinct from explicitly absent qualifiers and preserves accepted status", () => {
  const absent = { state: 'absent' };
  const detail: KnowledgeDetail = { item: { id: 'edge', kind: 'relation', label: '관계', claim_ids: ['claim'] }, relations: [], history: [],
    claims: [{ id: 'claim', role: 'relation', statement: '검토된 저장 문장', review_status: 'accepted', editable: false,
      meanings: [{ conditions: { state: 'unknown' }, exceptions: absent, time: absent, references: absent }], evidence: [] }] };
  const html = renderToStaticMarkup(createElement(KnowledgeSelection, { detail, onSelect: () => {} }));
  expect(html).toContain('수락');
  expect(html).toContain('<dt>조건</dt><dd>미확인</dd>');
  expect(html).toContain('예외·기간 / 시점·참조 없음으로 자동 기록');
  expect(html).not.toContain('조건·예외·기간 / 시점·참조 없음');
  expect(html).not.toContain('의미 미승인');
});
