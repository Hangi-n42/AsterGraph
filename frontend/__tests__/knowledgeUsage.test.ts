import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import KnowledgeUsageState, { KnowledgeUsageDetails } from "../components/KnowledgeUsage";
import type { KnowledgeUsage } from "../lib/knowledgeWorkbench";

const hooks = vi.hoisted(() => ({ effects: [] as (() => (() => void))[], seeds: [] as unknown[], setters: [] as ReturnType<typeof vi.fn>[] }));
vi.mock("react", async original => ({ ...await original<typeof import("react")>(), useEffect: (effect: () => (() => void)) => hooks.effects.push(effect), useState: (initial: unknown) => { const set = vi.fn(); hooks.setters.push(set); return [hooks.seeds.length ? hooks.seeds.shift() : initial, set]; } }));
vi.mock("@/lib/knowledgeWorkbench", () => import("../lib/knowledgeWorkbench"));
vi.mock("@/lib/api", () => ({ API_BASE_URL: 'http://localhost' }));

const fixture = (): KnowledgeUsage => ({ scope: { kind: 'source_graph', id: 'old' }, run_id: 'run', version_ids: ['v1'], version_files: [{id:'v1',filename:'계약 원문.json'}], missing_version_ids: [], snapshot_id: 'old', activation: 'explicit_query_only', active_snapshot_id: null, status_revision: 0, status_checked_at: '2026-10-12T00:00:00Z', source_restrictions: [], excluded_claim_ids: ['c13'], excluded_block_ids: ['b13'], invalidations: [{ event: 'business_source_change', requirement_ids: ['r13'], claim_ids: ['c13'] }], linked_snapshots: [], review: { changeset_id: 'change', eligible_ids: ['c12'], blocks: { c13: ['confirmed_expression_error'] }, explicit_review_ids: [] }, requirements: [{ id: 'r12', question: '순번 12', recorded_revision: 1, current_revision: 1, recorded_status: 'satisfied', current_status: 'unknown', revision_matches: true, source_change_requires_review: false }, { id: 'r13', question: '순번 13', recorded_revision: 1, current_revision: 2, recorded_status: 'satisfied', current_status: 'partial', revision_matches: false, source_change_requires_review: true }] });

it('shows explicit use, uncertainty and each restriction without declaring approval or availability', () => {
  const html = renderToStaticMarkup(createElement(KnowledgeUsageDetails, { view: fixture(), selectedClaimIds: ['c13'] }));
  for (const text of ['일반 활성 지식 버전: 없음', '질문에서 직접 지정하는 버전', '미확인', '일부 미완료', '원문 변경 후 재검토', '요구 버전 일치가 확인되지', '표현 오류 확인', '선택 항목에 변경 후 제외된 주장 1개']) expect(html).toContain(text);
  expect(html).not.toContain('현재 사용가능');
  expect(html).not.toContain('승인 완료');
});

it('does not call every saved run automatic extraction', () => {
  const view=fixture();view.scope={kind:'run',id:'edited'};
  const html=renderToStaticMarkup(createElement(KnowledgeUsageDetails,{view}));
  expect(html).toContain('저장 결과 · 미승인');
  expect(html).not.toContain('자동 추출');
});

it('shows linked public criteria as an unassessed unusable draft beside historical registry status', () => {
  const view=fixture();view.scope={kind:'run',id:'prepared'};view.linked_snapshots=[];
  view.requirements=[{...view.requirements[0],question:'원래 상품 비교 질문',criterion:'원래 비교 기준',recorded_status:'unassessed',current_status:'partial'}];
  view.requirement_link={reference_run_id:'historical',assessment_status:'unassessed',usage:'review_draft_only',
    public_answer_items:[{id:'public-item',request_quote:'확정할 수 없는 점'}]};
  const before=JSON.stringify(view);
  const html=renderToStaticMarkup(createElement(KnowledgeUsageDetails,{view,onOpenScope:()=>{}}));
  for (const text of ['검토 초안 · 사용 불가','미실행이며 사용 승인은 없습니다','현재 요구 상태는 원장의 과거 기록',
    '원래 상품 비교 질문','원래 비교 기준','확정할 수 없는 점','이 버전의 검토: 미평가','과거 요구 실행 기록 열기']) expect(html).toContain(text);
  expect(html).not.toContain('선택 항목 승인');
  expect(html).not.toContain('검색하고 답변 생성');
  expect(JSON.stringify(view)).toBe(before);
});

it('does not show an old scope while a different scope is loading', () => {
  hooks.seeds = [fixture(), '']; hooks.effects = []; hooks.setters = [];
  const html = renderToStaticMarkup(createElement(KnowledgeUsageState, { scope: { kind: 'source_graph', id: 'new', title: '새 범위', status: 'selection_recorded', data_label: '선택 기록' }, reload: 0, selectedClaimIds: [], onOpenScope: () => {} }));
  expect(html).toContain('현재 사용·검토 상태를 확인');
  expect(html).not.toContain('순번 13');
});

it('reports a required response record missing instead of rendering an empty normal state', () => {
  const incomplete = fixture(); delete (incomplete as Partial<KnowledgeUsage>).version_files;
  const html = renderToStaticMarkup(createElement(KnowledgeUsageDetails, { view: incomplete }));
  expect(html).toContain('필수 버전·검토 기록을 읽지 못했습니다');
  expect(html).not.toContain('저장된 제한 없음');
});

it('ignores a late response after scope cleanup even if fetch resolves', async () => {
  hooks.seeds = [null, '']; hooks.effects = []; hooks.setters = [];
  let finish: (response: Response) => void = () => {};
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish = resolve; })));
  renderToStaticMarkup(createElement(KnowledgeUsageState, { scope: { kind: 'source_graph', id: 'old', title: '기존 범위', status: 'selection_recorded', data_label: '선택 기록' }, reload: 0, selectedClaimIds: [], onOpenScope: () => {} }));
  const cleanup = hooks.effects[0](); cleanup();
  finish(new Response(JSON.stringify({ success: true, data: fixture() }), { status: 200 }));
  await new Promise(resolve => setImmediate(resolve));
  expect(hooks.setters.every(set => set.mock.calls.length === 0)).toBe(true);
  vi.unstubAllGlobals();
});
