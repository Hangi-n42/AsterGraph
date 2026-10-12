import { API_BASE_URL } from "./api";

export async function knowledgeRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/v1/knowledge${path}`, init);
  const result = await response.json();
  if (!response.ok || result.success === false) {
    throw Object.assign(new Error(result.error?.message || result.detail || `요청 실패 (${response.status})`), {
      status: response.status, code: result.error?.code,
    });
  }
  return result.data as T;
}

export type KnowledgeScope = { kind: "run" | "source_graph"; id: string; title: string; status: string; data_label: string; created_at?: string; partial?: boolean; graph_available?: boolean; changeset_id?: string; version_ids?: string[] };
export type KnowledgeItem = { id: string; kind: string; label: string; claim_ids: string[]; disambiguation?: string; state?: string; issue?: string; concepts?: string[]; head?: string; tail?: string; head_label?: string; tail_label?: string };
export type KnowledgeClaim = {
  id: string; role: string; statement: string; review_status?: string; conditions?: string[]; exceptions?: string[]; period?: string;
  extraction_error?: string; editable: boolean; meanings: Record<string, unknown>[];
  evidence: { block_id: string; quote?: string; source_title?: string; precision?: string; context_only?: boolean; locator?: Record<string, unknown>; block_text?: string }[];
};
export type KnowledgeDetail = { item: KnowledgeItem; claims: KnowledgeClaim[]; relations: { id: string; relation: string; head_label: string; tail_label: string }[]; changeset_id?: string; run_id?: string; history: { id: string; actor?: string; reason?: string; status?: string; changes: { before?: string; after?: string }[] }[] };
export type KnowledgeView = {
  scope: KnowledgeScope; counts: { nodes: number | null; relations: number | null; claims: number; blocks: number; sources: number; versions: number; concepts: number; failed_concepts: number; excluded_claims: number; claim_review: Record<string, number> };
  items: KnowledgeItem[]; filtered_count: number; offset: number; limit: number; detail: KnowledgeDetail | null; count_policy: string;
  graph: KnowledgeGraphView;
  filters: { relation_types: string[]; sources: { id: string; title: string }[]; review_states: string[] };
};
export type KnowledgeGraphView = { items: KnowledgeItem[]; depth: number; nodes: number; relations: number; eligible_nodes: number; eligible_relations: number; omitted_nodes: number; omitted_relations: number; filter_excluded_relations: number; selected_excluded: boolean; reason: string };
export function relationLabel(value: string) { return ({ participation: '참여 연결', is: '이다 연결 (자동 추출)', 'located at': '위치 연결 (자동 추출)', because: '원인 연결 (자동 추출)', result: '결과 연결 (자동 추출)', 'as a result': '결과 연결 (자동 추출)', 'at the same time': '동시 연결 (자동 추출)', condition: '조건 연결', before: '선행 연결', after: '후행 연결' } as Record<string, string>)[value] || value; }
export function itemLabel(item: KnowledgeItem) { return item.kind === 'relation' ? relationLabel(item.label) : item.label; }
export type KnowledgeCatalog = { scopes: KnowledgeScope[]; registered_sources: number; registered_versions: number; legacy_snapshots: number; ontology_versions: number; count_policy: string };
export const knowledgeLabels: Record<string, string> = { needs_review: "재검토 필요", satisfied: "충족 기록", unaffected: "영향 없음 기록", affected: "영향 있음 기록", claim: "검토 대상 주장", concept: "자동 개념화 기록", entity: "대상", event: "업무 내용", relation: "관계", unreviewed: "미검수", unrecorded: "기록 없음", reviewed: "검토됨", accepted: "수락", partial: "일부 완료", succeeded: "처리 완료", review_ready: "검토 대기", cancelled: "중단", failed: "실패", unknown: "미확인", queued: "대기", running: "처리 중" };
export function knowledgeDate(value?: string) { return value ? new Date(value).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "medium", timeStyle: "short" }) : "시각 미기록"; }
export function qualifier(value: unknown): string {
  if (typeof value === "string") return value || "별도 기록 없음";
  if (value && typeof value === "object" && "state" in value) {
    const item = value as { state: string; text?: string };
    return item.text || (item.state === "absent" ? "이 자동 해석에는 없음으로 기록" : "미확인");
  }
  return "별도 기록 없음 · 원문에서 확인";
}
