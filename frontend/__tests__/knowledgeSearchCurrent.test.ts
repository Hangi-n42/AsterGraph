import { createElement, type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, expect, it, vi } from 'vitest';
import KnowledgeSearch, { businessSearchRequest } from '../components/KnowledgeSearch';
import type { KnowledgeScope } from '../lib/knowledgeWorkbench';

const hooks = vi.hoisted(() => ({ seeds: [] as unknown[], effects: [] as (() => unknown)[], setters: [] as ReturnType<typeof vi.fn>[] }));
vi.mock('react', async original => ({ ...await original<typeof import('react')>(),
  useState: (initial: unknown) => { const setter = vi.fn(); hooks.setters.push(setter); return [hooks.seeds.length ? hooks.seeds.shift() : initial, setter]; },
  useRef: (value: unknown) => ({ current: value }), useEffect: (effect: () => unknown) => hooks.effects.push(effect),
}));
vi.mock('@/lib/knowledgeWorkbench', () => import('../lib/knowledgeWorkbench'));
vi.mock('@/lib/api', () => ({ API_BASE_URL: 'http://localhost' }));
vi.mock('../components/KnowledgeStoredAnswers', () => ({ default: () => null }));
const scope = { id: 'reviewed-v1', kind: 'source_graph' } as KnowledgeScope;
const snapshot = { id: scope.id, run_id: 'run', reason: '검토한 상품 자료', created_at: '2026-10-19T00:00:00Z', counts: { claims: 3 } };
function seed(result: unknown = null) { hooks.seeds = [[snapshot], false, '상품의 보관 조건은?', 'hipporag2', result, false, '']; }
function nodes(node: unknown): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!node || typeof node !== 'object' || !('props' in node)) return [];
  const element = node as ReactElement<Record<string, unknown>>;
  return [element, ...nodes(element.props.children)];
}
beforeEach(() => { hooks.seeds=[]; hooks.effects=[]; hooks.setters=[]; });

it('uses only an explicit current snapshot and supported retrieval contract', () => {
  expect(businessSearchRequest('reviewed-v1', ' 보관 조건 ', 'hipporag2')).toEqual({ snapshot_id: 'reviewed-v1', question: '보관 조건', retrieval: 'hipporag2', graph_variant: 'full', answer_mode: 'synthesis' });
  for (const mode of ['hybrid','hybrid_graph','unsupported']) expect(() => businessSearchRequest('v','질문',mode)).toThrow();
  expect(() => businessSearchRequest('','질문','bm25')).toThrow();
  expect(() => businessSearchRequest('v',' ','bm25')).toThrow();
});

it('sends preservation options only through the explicit search configuration', async () => {
  const expanded = businessSearchRequest('v', '새 질문', 'hipporag2', 'preserved');
  expect(expanded).toMatchObject({ candidate_contract: 'r2_g1_w1', evidence_union: 'ranked_preserved_claims_v2' });
  expect(expanded).not.toHaveProperty('source_citation_contract');
  for (const retrieval of ['bm25', 'dense']) expect(() => businessSearchRequest('v', '질문', retrieval, 'preserved')).toThrow();
  seed(); hooks.seeds.push('preserved');
  const request = vi.fn().mockResolvedValue({ status: 'answered' });
  const tree = KnowledgeSearch({request,scope,onOpenScope:vi.fn(),onExplore:vi.fn()});
  const submit = nodes(tree).find(n=>n.type==='form')!.props.onSubmit as (e:{preventDefault:()=>void})=>void;
  submit({preventDefault:vi.fn()}); await Promise.resolve();
  expect(JSON.parse(request.mock.calls[0][1].body)).toMatchObject({ ...expanded, snapshot_id: scope.id, question: '상품의 보관 조건은?' });
});

it('mount reads current snapshots without starting a model call', async () => {
  const request=vi.fn().mockResolvedValue({items:[snapshot]});
  KnowledgeSearch({request,scope,onOpenScope:vi.fn(),onExplore:vi.fn()});
  hooks.effects[0](); await Promise.resolve();
  expect(request).toHaveBeenCalledTimes(1);
  expect(request.mock.calls[0][0]).toBe('/business/snapshots');
  expect(request.mock.calls[0][1].method).toBeUndefined();
});

it('does not silently substitute an old active snapshot or an extraction run', () => {
  seed();
  const html=renderToStaticMarkup(createElement(KnowledgeSearch,{request:vi.fn(),scope:{...scope,kind:'run'},onOpenScope:vi.fn(),onExplore:vi.fn()}));
  expect(html).toContain('다른 버전으로 자동 대체하지 않습니다');
  expect(html).toContain('disabled=""');
  expect(html).not.toContain('현재 활성 버전');
});

it('submits exactly one request and keeps the selected snapshot', async () => {
  seed(); let resolve: (value: unknown) => void = () => {};
  const request=vi.fn().mockImplementation(() => new Promise(r => {resolve=r;}));
  const tree=KnowledgeSearch({request,scope,onOpenScope:vi.fn(),onExplore:vi.fn()});
  const submit=nodes(tree).find(n=>n.type==='form')!.props.onSubmit as (e:{preventDefault:()=>void})=>void;
  submit({preventDefault:vi.fn()}); submit({preventDefault:vi.fn()});
  expect(request).toHaveBeenCalledTimes(1);
  expect(request.mock.calls[0][0]).toBe('/business/search');
  expect(JSON.parse(request.mock.calls[0][1].body)).toMatchObject({snapshot_id:scope.id,question:'상품의 보관 조건은?',retrieval:'hipporag2'});
  expect(JSON.parse(request.mock.calls[0][1].body)).not.toHaveProperty('source_run_id');
  resolve({run_id:'answer-1',status:'answered'}); await Promise.resolve(); await Promise.resolve();
  expect(hooks.setters[4]).toHaveBeenCalledWith({run_id:'answer-1',status:'answered'});
});

it('changes the parent scope and reuses saved-answer evidence for the exact new run', () => {
  seed({run_id:'answer-1',status:'answered'});
  const onOpenScope=vi.fn();const all=nodes(KnowledgeSearch({request:vi.fn(),scope,onOpenScope,onExplore:vi.fn()}));
  const change=all.find(n=>n.type==='select')!.props.onChange as (e:{target:{value:string}})=>void;
  change({target:{value:'reviewed-v2'}});expect(onOpenScope).toHaveBeenCalledWith('source_graph:reviewed-v2');
  expect(all.find(n=>n.props.initialAnswerId==='answer-1')?.props.scope).toEqual(scope);
});
