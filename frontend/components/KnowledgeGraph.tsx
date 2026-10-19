"use client";

import { useEffect, useRef, useState } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import fcose, { type FcoseLayoutOptions } from "cytoscape-fcose";
import { itemLabel, type KnowledgeGraphView } from "@/lib/knowledgeWorkbench";
import styles from "./KnowledgeWorkbench.module.css";

cytoscape.use(fcose);

export function graphElements(graph: KnowledgeGraphView): ElementDefinition[] {
  return graph.items.map(item => {
    const name = itemLabel(item);
    const maximum = item.kind === 'event' ? 48 : 26;
    return { data: { id: item.id, label: name.length > maximum ? name.slice(0, maximum) + '…' : name,
      fullLabel: [name, item.disambiguation].filter(Boolean).join(' · '), kind: item.kind,
      ...(item.kind === 'relation' ? { source: item.head, target: item.tail } : {}) } };
  });
}

export default function KnowledgeGraph({ graph, selectedId, rootId, dataLabel, onSelect, onExpand, onReset, onFocus, busy }: {
  graph: KnowledgeGraphView; selectedId: string; rootId: string; dataLabel: string; onSelect: (id: string, keyboard?: boolean) => void;
  onFocus: () => void; onExpand: () => void; onReset: () => void; busy: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<Core | null>(null);
  const [renderMs, setRenderMs] = useState<number | null>(null);
  const [renderZoom, setRenderZoom] = useState(1);
  const [hovered, setHovered] = useState("");
  const selectHandler = useRef(onSelect);
  const graphSignature = useRef("");
  const previousDepth = useRef(1);
  const selected = graph.items.find(item => item.id === selectedId);
  useEffect(() => { selectHandler.current = onSelect; }, [onSelect]);
  useEffect(() => {
    if (!container.current) return;
    const cy = cytoscape({ container: container.current, minZoom: .2, maxZoom: 2.5, wheelSensitivity: .15,
      elements: [], boxSelectionEnabled: false,
      style: [
        { selector: 'node', style: { label: 'data(label)', 'background-color': '#ffffff', 'border-color': '#9aabb9', 'border-width': 1.5,
          color: '#263d4c', 'font-family': '"Apple SD Gothic Neo", "Noto Sans KR", sans-serif', 'font-size': 18, 'font-weight': 500,
          'text-wrap': 'wrap', 'text-max-width': '162px', 'text-valign': 'center', 'line-height': 1.35,
          width: 190, height: 84, shape: 'round-rectangle', 'overlay-opacity': 0 } },
        { selector: 'node[kind="event"]', style: { 'background-color': '#edf6f2', 'border-color': '#6c9c8b', 'text-max-width': '224px', width: 250, height: 118 } },
        { selector: 'node[kind="search_concept"]', style: { 'background-color': '#f2eef8', 'border-color': '#9986b2', shape: 'ellipse' } },
        { selector: 'edge', style: { label: '', 'curve-style': 'bezier', 'control-point-step-size': 64,
          'target-arrow-shape': 'triangle', 'arrow-scale': 1.15, 'line-color': '#a9b8c3', 'target-arrow-color': '#8a9eac', width: 1.8,
          color: '#344f62', 'font-size': 14, 'font-family': '"Apple SD Gothic Neo", sans-serif',
          'text-background-color': '#fff', 'text-background-opacity': 1, 'text-background-padding': '5px',
          'text-border-color': '#e1e7eb', 'text-border-width': 1, 'text-border-opacity': 1,
          'text-rotation': 'none', 'text-wrap': 'wrap', 'text-max-width': '130px',
          'source-distance-from-node': 4, 'target-distance-from-node': 4, 'overlay-opacity': 0 } },
        { selector: '.muted', style: { opacity: .48 } },
        { selector: 'edge.connected', style: { 'line-color': '#65879d', 'target-arrow-color': '#65879d', width: 2.2 } },
        { selector: 'edge.caption', style: { label: 'data(label)' } },
        { selector: 'node.anchor', style: { 'border-color': '#4d7f9e', 'border-width': 2.5, 'background-color': '#eaf1f6' } },
        { selector: 'node:selected', style: { 'background-color': '#244a61', 'border-color': '#244a61', color: '#fff', 'font-weight': 650, 'border-width': 3 } },
        { selector: 'edge:selected, edge.hovered', style: { label: 'data(label)', 'line-color': '#286f97', 'target-arrow-color': '#286f97', width: 3, opacity: 1, 'z-index': 10, 'font-weight': 600 } },
        { selector: 'node.hovered', style: { 'border-width': 3, 'border-color': '#286f97' } },
      ],
    });
    instance.current = cy;
    cy.on('zoom', () => setRenderZoom(cy.zoom()));
    cy.on('tap', 'node, edge', event => selectHandler.current(event.target.id(), false));
    cy.on('mouseover', 'node, edge', event => { event.target.addClass('hovered'); setHovered(event.target.data('fullLabel')); });
    cy.on('mouseout', 'node, edge', event => { event.target.removeClass('hovered'); setHovered(''); });
    let size = { width: cy.width(), height: cy.height() };
    const observer = new ResizeObserver(() => {
      const pan = cy.pan(); cy.resize();
      cy.pan({ x: pan.x + (cy.width() - size.width) / 2, y: pan.y + (cy.height() - size.height) / 2 });
      size = { width: cy.width(), height: cy.height() };
    });
    observer.observe(container.current);
    return () => { observer.disconnect(); cy.destroy(); instance.current = null; graphSignature.current = ""; };
  }, []);
  useEffect(() => {
    const cy = instance.current;
    const signature = JSON.stringify(graph.items);
    if (!cy || graphSignature.current === signature) return;
    graphSignature.current = signature;
    const started = performance.now();
    const positions = new Map(cy.nodes().map(n => [n.id(), { ...n.position() }]));
    const expanding = graph.depth > previousDepth.current && graph.items.some(item => positions.has(item.id));
    previousDepth.current = graph.depth;
    const pan = { ...cy.pan() }, zoom = cy.zoom();
    cy.batch(() => {
      cy.elements().remove();
      cy.add(graphElements(graph));
      cy.nodes().forEach((node, i) => {
        const saved = positions.get(node.id());
        const neighbour = node.neighborhood('node').map(n => positions.get(n.id())).find(Boolean);
        const center = saved || neighbour || { x: 0, y: 0 };
        node.position(saved || { x: center.x + Math.cos(i * 2.4) * 220, y: center.y + Math.sin(i * 2.4) * 180 });
      });
    });
    if (graph.nodes) {
      const anchor = positions.get(rootId);
      cy.layout({ name: 'fcose', quality: 'proof', randomize: !expanding, animate: false, fit: false,
        packComponents: false, nodeSeparation: 65, nodeRepulsion: () => 6000, idealEdgeLength: () => 85,
        edgeElasticity: () => .3, gravity: .18, numIter: 2500,
        ...(expanding && anchor ? { fixedNodeConstraint: [{ nodeId: rootId, position: anchor }] } : {}),
      } as FcoseLayoutOptions).run();
      if (expanding) { cy.zoom(zoom); cy.pan(pan); }
      else { cy.fit(undefined, 42); if (cy.zoom() > 1.15) { cy.zoom(1.15); cy.center(); } }
    }
    const frame = requestAnimationFrame(() => setRenderMs(Math.round(performance.now() - started)));
    return () => cancelAnimationFrame(frame);
  }, [graph, rootId]);
  useEffect(() => {
    const cy = instance.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements().unselect().removeClass('muted connected caption anchor');
      const anchor = cy.getElementById(rootId); anchor.filter('node').addClass('anchor');
      const selected = cy.getElementById(selectedId);
      if (selected.length) {
        selected.select();
        const connected = selected.group() === 'nodes' ? selected.closedNeighborhood() : selected.union(selected.connectedNodes());
        cy.elements().difference(connected).addClass('muted');
        connected.edges().addClass('connected');
        if (connected.edges().length <= 5) connected.edges().addClass('caption');
      } else if (cy.edges().length <= 4) cy.edges().addClass('caption');
    });
  }, [selectedId, rootId, graph.items]);
  return <div className={styles.graphPanel}>
    <div className={styles.graphStage}>
      <div className={styles.graphLegend}><span><i />대상</span><span><i data-kind="event" />업무 내용</span><span><i data-kind="search_concept" />검색용 개념</span><span className={styles.graphUnreviewed}>{dataLabel}</span></div>
      <div ref={container} className={styles.graphCanvas} aria-hidden="true" />
      {!graph.items.length && <div className={styles.graphEmpty}><strong>표시할 연결이 없습니다</strong><p>필터를 풀거나 다른 대상을 선택하세요.</p></div>}
      <div className={styles.graphZoom} role="group" aria-label="그래프 화면 조작"><button onClick={() => { const cy = instance.current; if (cy) cy.zoom({ level: cy.zoom() * 1.2, renderedPosition: { x: cy.width()/2, y: cy.height()/2 } }); }} aria-label="그래프 확대">＋</button><button onClick={() => { const cy = instance.current; if (cy) cy.zoom({ level: cy.zoom() / 1.2, renderedPosition: { x: cy.width()/2, y: cy.height()/2 } }); }} aria-label="그래프 축소">−</button><button onClick={() => instance.current?.fit(undefined, 42)}>화면 맞춤</button></div>
      <div className={styles.graphHover}>{hovered || (selected ? `${selected.kind === 'relation' ? '선택 관계' : '선택 대상'} · ${[itemLabel(selected), selected.disambiguation].filter(Boolean).join(' · ')}` : '대상이나 연결선을 선택해 원문과 조건을 확인하세요')}</div>
    </div>
    <div className={styles.graphToolbar} role="group" aria-label="그래프 조작"><div><strong>대상·개념 {graph.nodes}</strong><span>관계 {graph.relations} · {graph.depth}단계</span></div><button onClick={onFocus} disabled={!selectedId || busy}>선택 주변 보기</button><button onClick={onExpand} disabled={busy || graph.depth >= 3 || !selectedId}>이웃 한 단계 더</button><button onClick={onReset}>처음 범위</button></div>
    {graph.selected_excluded && <p className={styles.warning}>선택 항목이 현재 필터에서 제외되었습니다. 상세 선택은 유지됩니다.</p>}
    <div className={styles.graphExtras}><details className={styles.graphList}><summary>동일 그래프 목록 · {graph.items.length}개 항목 <span>키보드로 탐색</span></summary><ul>{graph.items.map(item => <li key={item.id}><button aria-pressed={selectedId === item.id} onClick={() => onSelect(item.id, true)}><span>{item.kind === 'event' ? '업무 내용' : item.kind === 'relation' ? '관계' : item.kind === 'search_concept' ? '검색용 개념' : '대상'}</span>{item.kind === 'relation' ? `${item.head_label} → ${itemLabel(item)} → ${item.tail_label}` : itemLabel(item)}<small>{item.disambiguation || item.id}</small></button></li>)}</ul></details>
    <details className={styles.graphList}><summary>표시 범위와 진단</summary><p>필터 통과 대상 {graph.eligible_nodes} · 관계 {graph.eligible_relations} / 미표시 대상 {graph.omitted_nodes} · 관계 {graph.omitted_relations} (필터 제외 {graph.filter_excluded_relations})</p><p>{graph.reason}</p><p>이번 배치·첫 화면 대기 {renderMs == null ? '측정 중' : `${renderMs}ms`} · 브라우저 실측, 통신 제외</p><p>노드 글자 화면 환산 {(18 * renderZoom).toFixed(1)}px · 확대 {Math.round(renderZoom * 100)}%</p><p>확장 시 기존 화면 위치를 유지합니다. 새 이웃이 화면 밖에 있으면 화면 맞춤을 누르세요. 축약한 이름은 상세에서 전체 내용을 확인하세요. 저장된 연결은 인과 검증을 뜻하지 않습니다.</p></details></div>
  </div>;
}
