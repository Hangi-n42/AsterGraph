"use client";

import { useEffect, useRef, useState } from "react";
import cytoscape, { type Core } from "cytoscape";
import { itemLabel, type KnowledgeGraphView } from "@/lib/knowledgeWorkbench";
import styles from "./KnowledgeWorkbench.module.css";

export default function KnowledgeGraph({ graph, selectedId, onSelect, onExpand, onReset, onFocus, busy }: {
  graph: KnowledgeGraphView; selectedId: string; onSelect: (id: string) => void;
  onFocus: () => void; onExpand: () => void; onReset: () => void; busy: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<Core | null>(null);
  const [renderMs, setRenderMs] = useState<number | null>(null);
  const selectHandler = useRef(onSelect);
  const graphSignature = useRef("");
  useEffect(() => { selectHandler.current = onSelect; }, [onSelect]);
  useEffect(() => {
    if (!container.current) return;
    const cy = cytoscape({ container: container.current, minZoom: .25, maxZoom: 3, wheelSensitivity: .2,
      elements: [],
      style: [
        { selector: 'node', style: { label: 'data(label)', 'background-color': '#e3eaf0', 'border-color': '#71869a', 'border-width': 1.5, color: '#24303e', 'font-family': 'Arial, sans-serif', 'font-size': 16, 'text-wrap': 'wrap', 'text-max-width': '150px', 'text-valign': 'center', width: 160, height: 76, shape: 'round-rectangle' } },
        { selector: 'node[kind="event"]', style: { 'background-color': '#edf0e8', 'border-color': '#879277' } },
        { selector: 'edge', style: { label: 'data(label)', 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'line-color': '#9aa9b5', 'target-arrow-color': '#758897', width: 1.5, color: '#465462', 'font-size': 14, 'text-background-color': '#fff', 'text-background-opacity': .9, 'text-background-padding': '3px', 'text-rotation': 'autorotate', 'min-zoomed-font-size': 10 } },
        { selector: ':selected', style: { 'border-color': '#254e76', 'border-width': 4, 'line-color': '#254e76', 'target-arrow-color': '#254e76', width: 3 } },
        { selector: 'node:selected', style: { width: 160 } },
      ],
    });
    instance.current = cy;
    cy.on('tap', 'node, edge', event => selectHandler.current(event.target.id()));
    const observer = new ResizeObserver(() => cy.resize());
    observer.observe(container.current);
    return () => { observer.disconnect(); cy.destroy(); instance.current = null; graphSignature.current = ""; };
  }, []);
  useEffect(() => {
    const cy = instance.current;
    const signature = JSON.stringify(graph.items);
    if (!cy || graphSignature.current === signature) return;
    graphSignature.current = signature;
    const started = performance.now();
    const positions = new Map(cy.nodes().map(n => [n.id(), n.position()]));
    cy.batch(() => {
      cy.elements().remove();
      cy.add(graph.items.map(item => ({ data: { id: item.id, label: itemLabel(item).length > 26 ? itemLabel(item).slice(0, 26) + '…' : itemLabel(item), kind: item.kind,
        ...(item.kind === 'relation' ? { source: item.head, target: item.tail } : {}) }, position: positions.get(item.id) })));
    });
    cy.layout(graph.nodes <= 4 ? { name: 'circle', animate: false, padding: 24, spacingFactor: 1.1 }
      : graph.nodes <= 12 ? { name: 'grid', animate: false, padding: 24, rows: 4 }
      : { name: 'cose', animate: false, randomize: false, nodeRepulsion: () => 12000, idealEdgeLength: () => 100, padding: 24 }).run();
    const frame = requestAnimationFrame(() => setRenderMs(Math.round(performance.now() - started)));
    return () => cancelAnimationFrame(frame);
  }, [graph.items, graph.nodes]);
  useEffect(() => {
    instance.current?.elements().unselect();
    instance.current?.getElementById(selectedId).select();
  }, [selectedId, graph.items]);
  return <div className={styles.graphPanel}>
    <div className={styles.graphToolbar} role="group" aria-label="그래프 조작">
      <button onClick={() => instance.current?.zoom(instance.current.zoom() * 1.25)} aria-label="그래프 확대">＋</button>
      <button onClick={() => instance.current?.zoom(instance.current.zoom() / 1.25)} aria-label="그래프 축소">－</button>
      <button onClick={() => instance.current?.fit(undefined, 36)}>화면 맞춤</button>
      <button onClick={onFocus} disabled={!selectedId || busy}>선택 주변 보기</button>
      <button onClick={onReset}>처음 범위</button>
      <button onClick={onExpand} disabled={busy || graph.depth >= 3 || !selectedId}>이웃 한 단계 더</button>
    </div>
    <p className={styles.graphCounts}>표시 대상 {graph.nodes} · 관계 {graph.relations} / 필터 통과 대상 {graph.eligible_nodes} · 관계 {graph.eligible_relations}</p>
    {graph.selected_excluded && <p className={styles.warning}>선택 항목이 현재 필터에서 제외되어 그래프에 표시되지 않습니다. 상세 선택은 유지됩니다.</p>}
    {!graph.items.length && <p className={styles.empty}>표시할 연결이 없습니다. 필터를 풀거나 다른 대상을 선택하세요.</p>}
    <div ref={container} className={styles.graphCanvas} aria-hidden="true" />
    <p className={styles.graphCounts}>미표시 대상 {graph.omitted_nodes} · 관계 {graph.omitted_relations} (필터 제외 관계 {graph.filter_excluded_relations}) · {graph.depth}단계</p>
    <p className={styles.graphHelp}>{graph.reason} 짧은 이름은 상세에서 전체 내용을 확인하세요. 연결선은 저장된 자동 추출 결과이며 인과 검증을 뜻하지 않습니다.</p>
    <details className={styles.graphList}><summary>표시 그래프를 키보드 목록으로 탐색 ({graph.items.length}개)</summary><ul>{graph.items.map(item => <li key={item.id}><button aria-pressed={selectedId === item.id} onClick={() => onSelect(item.id)}>{item.kind === 'relation' ? `${item.head_label} → ${itemLabel(item)} → ${item.tail_label}` : itemLabel(item)}<small>{item.id}</small></button></li>)}</ul></details>
    <details className={styles.graphList}><summary>진단 · 표시 시간</summary><p>이번 배치·첫 화면 대기 {renderMs == null ? '측정 중' : `${renderMs}ms`} · 브라우저 실측, 통신 시간 제외</p></details>
  </div>;
}
