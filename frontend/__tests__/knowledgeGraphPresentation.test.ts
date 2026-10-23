import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { graphElements } from "../components/KnowledgeGraph";
import { KnowledgeSelection } from "../components/KnowledgeWorkbench";
import type { KnowledgeDetail, KnowledgeGraphView } from "../lib/knowledgeWorkbench";

vi.mock("@/lib/knowledgeWorkbench", () => import("../lib/knowledgeWorkbench"));
vi.mock("@/lib/api", () => ({ API_BASE_URL: 'http://localhost' }));

it("shows stored interpretation record errors separately while preserving the accepted statement", () => {
  const detail: KnowledgeDetail = { item: { id: 'edge', kind: 'relation', label: '관계', claim_ids: ['claim'] }, relations: [], history: [],
    claims: [{ id: 'claim', role: 'relation', statement: '저장된 정상 문장', review_status: 'accepted', editable: false,
      meanings: [], evidence: [], interpretation_errors: ['invalid premise state'] }] };
  const before = JSON.stringify(detail);
  const render = (value: KnowledgeDetail) => renderToStaticMarkup(createElement(KnowledgeSelection, { detail: value, onSelect: () => {} }));
  const html = render(detail);
  for (const text of ['대상·조건 기록에 확인할 오류가 있음', '자동 해석에 저장된 오류 사유 · 의미 판정과 별도', 'invalid premise state', '수락', '저장된 정상 문장']) expect(html).toContain(text);
  expect(JSON.stringify(detail)).toBe(before);
  expect(render({ ...detail, claims: [{ ...detail.claims[0], interpretation_errors: [] }] })).not.toContain('대상·조건 기록에 확인할 오류가 있음');
});

it("keeps an unresolved concept link visible without treating it as an approval or a false claim", () => {
  const detail: KnowledgeDetail = { item: { id: 'unlinked', kind: 'concept', label: '보존된 대상', claim_ids: [],
    issue: '현재 주장·그래프의 대상 연결 확인 필요', state: 'failed' }, relations: [], history: [], claims: [] };
  const html = renderToStaticMarkup(createElement(KnowledgeSelection, { detail, onSelect: () => {} }));
  for (const text of ['현재 주장·그래프의 대상 연결 확인 필요', '실패·미연결 기록도 현재 목록에 보존', '승인된 온톨로지가 아닙니다']) expect(html).toContain(text);
});

it("distinguishes explicit field corrections from automatic output and human use approval", () => {
  const absent = { state: 'absent', text: null };
  const detail: KnowledgeDetail = { item: { id: 'claim', kind: 'claim', label: '보존된 문장', claim_ids: ['claim'] }, relations: [],
    history: [{ id: 'edit', actor: 'Codex 검토', reason: '원문에 한정한 필드 정정', status: 'applied_awaiting_recheck',
      changes: [{ before: 'present: null', after: 'absent' }] }],
    claims: [{ id: 'claim', role: 'event_entity', statement: '보존된 문장', review_status: 'unreviewed', editable: true,
      qualifier_status: 'explicit_reviewer_correction_unverified',
      meanings: [{ conditions: absent, exceptions: absent, time: absent, references: absent, relation_kind: 'other' }], evidence: [] }] };
  const before = JSON.stringify(detail);
  const html = renderToStaticMarkup(createElement(KnowledgeSelection, { detail, onSelect: () => {} }));
  for (const text of ['일부 해석 필드를 정정', '의미 미검증·사용 미승인', '현재 관계 해석: other',
    '조건·예외·기간 / 시점·참조 없음으로 정정 기록', 'Codex 검토', 'present: null', 'absent', '미검수']) expect(html).toContain(text);
  expect(html).not.toContain('이 항목의 저장된 수정 이력이 없습니다');
  expect(html).not.toContain('없음으로 자동 기록');
  expect(html).not.toContain('이 자동 해석에는');
  expect(JSON.stringify(detail)).toBe(before);
  const inherited = renderToStaticMarkup(createElement(KnowledgeSelection, {
    detail: { ...detail, parent_run_id: 'previous-edit', history: [] }, onSelect: () => {},
  }));
  for (const text of ['일부 해석 필드를 정정', '현재 실행에서 추가한 기록만', 'previous-edit',
    '이전 실행의 이력이 없다는 뜻은 아닙니다']) expect(inherited).toContain(text);
  expect(inherited).not.toContain('이 항목의 저장된 수정 이력이 없습니다');
});

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

it("keeps search concept nodes distinct and links their actual concept records", () => {
  const graph: KnowledgeGraphView = { depth: 1, nodes: 2, relations: 1, eligible_nodes: 2, eligible_relations: 1,
    omitted_nodes: 0, omitted_relations: 0, filter_excluded_relations: 0, selected_excluded: false, reason: 'contract fixture',
    items: [{ id: 'source-node', kind: 'entity', label: '같은 이름', claim_ids: ['c1'], disambiguation: '검사 자료 A' },
      { id: 'search-node', kind: 'search_concept', label: '같은 이름', claim_ids: ['c1', 'c2'], concept_record_ids: ['record1', 'record2'] },
      { id: 'actual-link', kind: 'relation', label: 'has_concept', head: 'source-node', tail: 'search-node', claim_ids: ['c1'], approved_is_a: false }] };
  const before = JSON.stringify(graph);
  const elements = graphElements(graph);
  expect(elements.map(e => e.data.id)).toEqual(['source-node', 'search-node', 'actual-link']);
  expect(elements[1].data.kind).toBe('search_concept');
  expect(elements[0].data.fullLabel).toBe('같은 이름 · 검사 자료 A');
  expect(elements[2].data).toMatchObject({ source: 'source-node', target: 'search-node', fullLabel: '검색용 개념 연결' });
  expect(JSON.stringify(graph)).toBe(before);
  const detail: KnowledgeDetail = { item: graph.items[1], claims: [], relations: [], history: [], concept_records:
    [1, 2].map(n => ({ id: `record${n}`, target: { id: `target${n}`, label: `출처 대상 ${n}`, kind: 'entity', claim_ids: [`c${n}`] },
      concepts: ['같은 이름'], status: 'unreviewed', request_id: `request${n}`, work_id: `work${n}` })) };
  const html = renderToStaticMarkup(createElement(KnowledgeSelection, { detail, onSelect: () => {} }));
  for (const text of ['검색용 개념', '대상 동일성·유형 승인과 별도', '연결된 개념화 기록', '출처 대상 1', '출처 대상 2']) expect(html).toContain(text);
});

it("shows stored public source links and unknown rights without inventing permission", () => {
  const detail: KnowledgeDetail = { item: { id: 'claim', kind: 'claim', label: '저장 내용', claim_ids: ['claim'] }, relations: [], history: [],
    claims: [{ id: 'claim', role: 'event_entity', statement: '저장 내용', editable: false, meanings: [],
      evidence: [{ block_id: 'b1', quote: '저장 발췌', source_url: 'https://example.invalid/source', rights: { status: 'unknown', note: 'unit fixture' } }] }] };
  const render = (value: KnowledgeDetail) => renderToStaticMarkup(createElement(KnowledgeSelection, { detail: value, onSelect: () => {} }));
  const html = render(detail);
  expect(html).toContain('href="https://example.invalid/source"');
  expect(html).toContain('출처 페이지 열기');
  expect(html).toContain('등록된 이용 상태 · 미확인');
  expect(html).not.toContain('이용 허용 기록');
  detail.claims[0].evidence[0].source_url = 'javascript:invalid()';
  expect(render(detail)).not.toContain('href="javascript:');
});

it("renders relation concepts as annotations without adding graph nodes", () => {
  const detail: KnowledgeDetail = { item: { id: 'relation', kind: 'relation', label: '이름', claim_ids: ['claim'],
    head_label: '대상', tail_label: '값', concepts: ['명칭 속성'] }, claims: [], relations: [], history: [] };
  const html = renderToStaticMarkup(createElement(KnowledgeSelection, { detail, onSelect: () => {} }));
  expect(html).toContain('관계의 검색용 개념 · 명칭 속성');
  expect(html).not.toContain('출처별 대상을 연결하는 검색용 개념');
});
