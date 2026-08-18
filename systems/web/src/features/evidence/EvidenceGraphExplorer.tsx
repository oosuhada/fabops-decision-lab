import {useMemo, useRef, useState, type PointerEvent, type WheelEvent} from "react";
import {scalePoint} from "d3";
import type {CaseDetailResponse} from "../../types";
import {buildEvidenceGraph, graphNeighbors, type EvidenceGraphNode, type EvidenceGraphNodeType} from "./evidenceGraphModel";

const TYPE_ORDER: EvidenceGraphNodeType[] = ["Case", "Lot", "ProcessRun", "Step", "Equipment", "Chamber", "Measurement", "Wafer", "Inspection", "RCACandidate", "EvidenceRecord"];

function layoutNodes(nodes: EvidenceGraphNode[]) {
  const typeIndex = new Map(TYPE_ORDER.map((type, index) => [type, index]));
  const grouped = new Map<EvidenceGraphNodeType, EvidenceGraphNode[]>();
  for (const node of nodes) grouped.set(node.type, [...(grouped.get(node.type) ?? []), node]);
  const positions = new Map<string, {x: number; y: number}>();
  const columnScale = scalePoint<number>().domain([0, 1, 2, 3, 4, 5, 6, 7, 8]).range([110, 1630]);
  for (const [type, items] of grouped) {
    const lane = typeIndex.get(type) ?? 0;
    items.forEach((node, index) => {
      const column = lane < 6 ? lane : lane === 9 || lane === 10 ? 2 + (lane - 9) : 6 + (lane - 6);
      const baseY = lane === 9 || lane === 10 ? 440 : 110;
      positions.set(node.id, {x: columnScale(column) ?? 110, y: baseY + index * 92});
    });
  }
  return positions;
}

function nodeClass(node: EvidenceGraphNode, selected: boolean) {
  return ["typed-graph-node", `typed-graph-node--${node.type.toLowerCase()}`, `is-provenance-${node.provenance}`, node.emphasis ? `is-${node.emphasis}` : "", selected ? "is-selected" : ""].filter(Boolean).join(" ");
}

export function EvidenceGraphExplorer({detail, onSelectStep, onSelectNode}: {detail: CaseDetailResponse; onSelectStep: (step: string) => void; onSelectNode?: (node: EvidenceGraphNode) => void}) {
  const model = useMemo(() => buildEvidenceGraph(detail), [detail]);
  const positions = useMemo(() => layoutNodes(model.nodes), [model.nodes]);
  const [selectedNodeId, setSelectedNodeId] = useState(`case:${detail.case.case_id}`);
  const [focusMode, setFocusMode] = useState(false);
  const [hiddenTypes, setHiddenTypes] = useState<Set<EvidenceGraphNodeType>>(() => new Set(["EvidenceRecord"]));
  const [relationshipFilter, setRelationshipFilter] = useState<"all" | "lineage" | "evidence" | "rca">("all");
  const [view, setView] = useState({x: 26, y: 18, scale: .72});
  const drag = useRef<{x: number; y: number; viewX: number; viewY: number} | null>(null);

  const selectedNode = model.nodes.find((node) => node.id === selectedNodeId) ?? model.nodes[0];
  const focusNodes = focusMode && selectedNode ? graphNeighbors(model, selectedNode.id) : null;
  const nodes = model.nodes.filter((node) => !hiddenTypes.has(node.type) && (!focusNodes || focusNodes.has(node.id)));
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = model.edges.filter((edge) => {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) return false;
    if (relationshipFilter === "all") return true;
    if (relationshipFilter === "rca") return ["HAS_RCA_CANDIDATE", "SUPPORTS", "CONTRADICTS", "DERIVED_FROM"].includes(edge.type);
    if (relationshipFilter === "evidence") return ["HAS_MEASUREMENT", "HAS_INSPECTION", "SUPPORTS", "CONTRADICTS", "DERIVED_FROM"].includes(edge.type);
    return ["CASE_FOR_LOT", "PROCESSED_BY", "HAS_STEP", "USED_EQUIPMENT", "USED_CHAMBER", "CONTAINS_WAFER"].includes(edge.type);
  });

  function selectNode(node: EvidenceGraphNode) {
    setSelectedNodeId(node.id);
    onSelectNode?.(node);
    const step = node.properties.step_id;
    if (typeof step === "string") onSelectStep(step);
  }

  function toggleType(type: EvidenceGraphNodeType) {
    setHiddenTypes((current) => {
      const next = new Set(current);
      if (next.has(type)) next.delete(type); else next.add(type);
      return next;
    });
  }

  function wheel(event: WheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const nextScale = Math.max(.35, Math.min(1.8, view.scale * (event.deltaY > 0 ? .9 : 1.1)));
    setView((current) => ({...current, scale: nextScale}));
  }

  function beginPan(event: PointerEvent<SVGSVGElement>) {
    if ((event.target as Element).closest(".typed-graph-node")) return;
    drag.current = {x: event.clientX, y: event.clientY, viewX: view.x, viewY: view.y};
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function movePan(event: PointerEvent<SVGSVGElement>) {
    if (!drag.current) return;
    setView((current) => ({...current, x: drag.current!.viewX + event.clientX - drag.current!.x, y: drag.current!.viewY + event.clientY - drag.current!.y}));
  }

  function endPan(event: PointerEvent<SVGSVGElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    drag.current = null;
  }

  return <section className="typed-graph-workbench" aria-label="Typed evidence graph explorer">
    <header className="typed-graph-toolbar">
      <div><span className="eyebrow">Evidence Graph 2.0</span><strong>Typed projection explorer</strong><small>Neo4j is a rebuildable RCA/read projection; source event authority remains PostgreSQL.</small></div>
      <div className="typed-graph-toolbar__actions">
        <select aria-label="Relationship filter" value={relationshipFilter} onChange={(event) => setRelationshipFilter(event.target.value as typeof relationshipFilter)}>
          <option value="all">All relationships</option><option value="lineage">Lineage</option><option value="evidence">Evidence</option><option value="rca">RCA</option>
        </select>
        <button type="button" aria-pressed={focusMode} disabled={!selectedNode} onClick={() => setFocusMode((current) => !current)}>{focusMode ? "Show full graph" : "Expand 1-hop"}</button>
        <button type="button" onClick={() => setView({x: 26, y: 18, scale: .72})}>Fit view</button>
      </div>
    </header>
    <div className="typed-graph-type-filter" aria-label="Node type filter">{TYPE_ORDER.map((type) => <button key={type} type="button" aria-pressed={!hiddenTypes.has(type)} onClick={() => toggleType(type)}>{type}</button>)}</div>
    <div className="typed-graph-layer-legend" aria-label="Evidence graph authority layers">
      <span><i className="is-source" />Authoritative source record</span>
      <span><i className="is-projection" />Rebuildable projection</span>
      <span><i className="is-inference" />Deterministic system inference</span>
      <span><i className="is-contradict" />Contradicting evidence</span>
    </div>
    <div className="typed-graph-readout" aria-label="Evidence graph inspection state">
      <div><span>SELECTED</span><strong>{selectedNode?.label ?? "None"}</strong></div>
      <div><span>SCOPE</span><strong>{focusMode ? "1-HOP FOCUS" : "FULL GRAPH"}</strong></div>
      <div><span>VISIBLE</span><strong>{nodes.length} nodes · {edges.length} edges</strong></div>
      <div><span>PROJECTION</span><strong>{detail.rca.projection.stale ? `STALE · ${detail.rca.projection.lag_events}` : "FRESH"}</strong></div>
      <p>Relationship labels follow the arrow direction →. Edge layer and source identity remain inspectable in the object panel and table fallback.</p>
    </div>
    <div className="typed-graph-body">
      <svg className="typed-graph-canvas" viewBox="0 0 1760 650" role="img" aria-label={`${nodes.length} typed nodes and ${edges.length} visible relationships`} onWheel={wheel} onPointerDown={beginPan} onPointerMove={movePan} onPointerUp={endPan} onPointerCancel={endPan}>
        <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
          {edges.map((edge) => {
            const source = positions.get(edge.source);
            const target = positions.get(edge.target);
            if (!source || !target) return null;
            return <g key={edge.id} className={`typed-graph-edge typed-graph-edge--${edge.provenance} ${edge.emphasis ? `is-${edge.emphasis}` : ""}`}>
              <line x1={source.x + 60} y1={source.y} x2={target.x - 60} y2={target.y} />
              <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 5}>{edge.type} →</text>
            </g>;
          })}
          {nodes.map((node) => {
            const position = positions.get(node.id) ?? {x: 0, y: 0};
            return <g key={node.id} className={nodeClass(node, node.id === selectedNode?.id)} transform={`translate(${position.x} ${position.y})`} role="treeitem" tabIndex={0} aria-selected={node.id === selectedNode?.id} aria-label={`${node.type} ${node.label}`} onClick={(event) => {event.stopPropagation(); selectNode(node);}} onKeyDown={(event) => {if (event.key === "Enter" || event.key === " ") {event.preventDefault(); selectNode(node);}}}>
              <rect x="-66" y="-27" width="132" height="54" rx="8" />
              <text className="typed-graph-node__type" x="-54" y="-9">{node.type}</text>
              <text className="typed-graph-node__label" x="-54" y="8">{node.label.length > 20 ? `${node.label.slice(0, 18)}…` : node.label}</text>
              <text className="typed-graph-node__subtitle" x="-54" y="21">{node.subtitle.length > 24 ? `${node.subtitle.slice(0, 22)}…` : node.subtitle}</text>
            </g>;
          })}
        </g>
      </svg>
      <aside className="typed-graph-inspector" aria-label="Selected graph object inspector">
        {selectedNode ? <>
          <span className="eyebrow">Selected object</span>
          <h3>{selectedNode.label}</h3>
          <div className="typed-graph-inspector__meta"><span>{selectedNode.type}</span><span>{selectedNode.provenance === "source" ? "authoritative source record" : selectedNode.provenance === "projection" ? "rebuildable projection" : "deterministic inference"}</span>{selectedNode.emphasis ? <span>{selectedNode.emphasis}</span> : null}</div>
          <dl>{Object.entries(selectedNode.properties).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value ?? "—")}</dd></div>)}</dl>
          <div className="typed-graph-linked-edges">{model.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id).map((edge) => <div key={edge.id}><strong>{edge.source === selectedNode.id ? "OUT" : "IN"} · {edge.type}</strong><span>{edge.provenance.replaceAll("-", " ")}</span><code>{edge.sourceIdentity ?? "projection relationship"}</code></div>)}</div>
          <p>{model.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id).length} linked relationships in the current rebuildable graph payload.</p>
        </> : <p>No graph object selected.</p>}
      </aside>
    </div>
    <details className="typed-graph-fallback">
      <summary>Accessible relationship fallback</summary>
      <p>The same visible graph relationships are available below without pan, zoom, pointer input, or SVG interpretation.</p>
      <div className="table-scroll"><table><thead><tr><th>From</th><th>Relationship</th><th>To</th><th>Layer</th><th>Source identity</th></tr></thead><tbody>{edges.map((edge) => <tr key={`fallback-${edge.id}`}><td>{model.nodes.find((node) => node.id === edge.source)?.label ?? edge.source}</td><td>{edge.type}</td><td>{model.nodes.find((node) => node.id === edge.target)?.label ?? edge.target}</td><td>{edge.provenance.replaceAll("-", " ")}</td><td>{edge.sourceIdentity ?? "—"}</td></tr>)}</tbody></table></div>
    </details>
  </section>;
}

