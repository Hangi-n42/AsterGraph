import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import KnowledgeChanges from "../components/KnowledgeChanges";
import { unchangedSourceFields } from "../lib/knowledgeWorkbench";

const hooks = vi.hoisted(() => ({ seeds: [] as unknown[] }));
vi.mock("react", async original => ({ ...await original<typeof import("react")>(), useEffect: () => {}, useState: (initial: unknown) => [hooks.seeds.length ? hooks.seeds.shift() : initial, vi.fn()] }));
vi.mock("@/lib/knowledgeWorkbench", () => import("../lib/knowledgeWorkbench"));
vi.mock("@/lib/api", () => ({ API_BASE_URL: 'http://localhost' }));

// Actual saved row /12 in the two 1127 snapshots, not a new policy condition.
const before = { ROUTE_ID: 100100143, 노선명: '1127', 순번: 13, NODE_ID: 109000035, ARS_ID: '10118', 정류소명: '도봉보건소', X좌표: 127.04, Y좌표: 37.657913 };
const after = { ...before, NODE_ID: 109000011, ARS_ID: '10011', X좌표: 127.0407623758, Y좌표: 37.6589364195 };
const scope = { kind: 'source_graph' as const, id: 'new', title: '새 버전', status: 'selection_recorded', data_label: '선택 기록' };
const fixture = (key: string) => ({ scope_key: key, versions: [], requirements: [], snapshot_review_requirement_ids: [], records: [{ id: 'change', status: 'succeeded', before_version_id: 'before', after_version_id: 'after', before_version: {filename:'1127_before.json'}, after_version: {filename:'1127_after.json'}, diff: { comparison:'exact_row_values', changes:[{key:['13'],before,after,fields:[{field:'NODE_ID',before:before.NODE_ID,after:after.NODE_ID}]}] }, impacts:[], after_scopes:[] }] });

it('reports only the four exact typed values unchanged in the modified row', () => {
  expect(unchangedSourceFields(before,after)).toEqual([
    {field:'ROUTE_ID',value:100100143},{field:'노선명',value:'1127'},{field:'순번',value:13},{field:'정류소명',value:'도봉보건소'},
  ]);
  expect(unchangedSourceFields({id:13,nested:{value:1},missing:'x'},{id:'13',nested:{value:1}})).toEqual([]);
  expect(unchangedSourceFields(['same'],['same'])).toEqual([]);
});

it('shows unchanged field values without asserting independence or approval', () => {
  hooks.seeds=[fixture('source_graph:new'),null];
  const html=renderToStaticMarkup(createElement(KnowledgeChanges,{scope}));
  expect(html).toContain('전후 같은 값');
  expect(html).toContain('값의 동일 여부와 업무 영향 판단은 별도입니다');
  expect(html).toContain('109000035');expect(html).toContain('109000011');
  expect(html).not.toContain('독립성 확인');expect(html).not.toContain('승인 완료');
});

it('does not render the old change record or error for a new scope', () => {
  hooks.seeds=[fixture('source_graph:old'),{scope_key:'source_graph:old',message:'old error'}];
  const html=renderToStaticMarkup(createElement(KnowledgeChanges,{scope}));
  expect(html).toContain('변경·재검토 기록을 확인');
  expect(html).not.toContain('old error');expect(html).not.toContain('변경된 원문 행');
});

it('shows rebuild execution failures, exact source text and separate use versions', () => {
  const record = { id: 'rebuild', status: 'planned', before_version: { filename: 'source.md' }, after_version: { filename: 'SYNTHETIC_source-v2.md' },
    action_counts: { preserve: 1, rebuild_source: 1 }, requirement_discovery: { candidate_ids: ['r'] },
    source_comparison: { before: { status: 'available', blocks: [{ text: '용도: 카레' }] }, after: { status: 'unavailable', blocks: [], reason: '파싱 기록 미확인' } },
    execution_scopes: [{ ...scope, kind: 'run', id: 'failed-run', status: 'failed' }], review_scopes: [], snapshots: [scope], unavailable_run_ids: ['missing'] };
  hooks.seeds = [{ ...fixture('source_graph:new'), records: [], rebuild_plans: [record] }, null];
  const html = renderToStaticMarkup(createElement(KnowledgeChanges, { scope, onOpenScope: vi.fn() }));
  expect(html).toContain('부분 재구축 계획');
  expect(html).toContain('계획에 기록된 처리 대상 수');
  expect(html).toContain('용도: 카레');
  expect(html).toContain('계획 당시 원문 확인 불가');
  expect(html).toContain('실패');
  expect(html).toContain('별도 확정한 사용 버전');
  expect(html).toContain('연결을 확인할 수 없는 기록 1건');
  expect(html).not.toContain('이 선택 범위에 연결된 원문 버전 비교·영향 결과나 부분 재구축 계획이 없습니다');
  expect(html).not.toContain('재구축 완료');
});
