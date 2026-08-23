import {useMemo, useState} from "react";
import type {CaseReplayTraceResponse, DecisionPacket} from "../../types";
import {buildDecisionProvenanceGraph, type ProvenanceNodeKind} from "./decisionProvenanceModel";

const laneOrder: Array<{kind: ProvenanceNodeKind; title: string}> = [
  {kind: "decision", title: "Decision"},
  {kind: "option", title: "Options"},
  {kind: "rca", title: "RCA projection"},
  {kind: "evidence", title: "Evidence"},
  {kind: "source_event", title: "Source events"},
  {kind: "process_run", title: "Process runs"},
];

export function DecisionProvenanceGraph({packet, trace}: {packet: DecisionPacket; trace: CaseReplayTraceResponse | null}) {
  const graph = useMemo(() => buildDecisionProvenanceGraph(packet, trace), [packet, trace]);
  const [selectedNodeId, setSelectedNodeId] = useState(`decision:${packet.case_id}`);
  const selected = graph.nodes.find((node) => node.id === selectedNodeId) ?? graph.nodes[0] ?? null;
  const selectedEdges = selected ? graph.edges.filter((edge) => edge.source === selected.id || edge.target === selected.id) : [];

  return <section className="panel decision-provenance-panel">
    <header>
      <div><span className="eyebrow">Decision provenance graph</span><h2>Trace the recommendation back to source identity</h2></div>
      <div className="provenance-authority"><span>Operational truth</span><strong>{graph.sourceOfTruth}</strong><small>{graph.projectionRole}</small></div>
    </header>
    <div className="decision-provenance-warning">Neo4j/RCA is a rebuildable read projection. This graph visualizes provenance; it does not grant RCA, LLM, or the UI authority over workflow or equipment.</div>
    <div className="decision-provenance-layout">
      <div className="decision-provenance-lanes" aria-label="Decision provenance graph lanes">
        {laneOrder.map((lane) => {
          const laneNodes = graph.nodes.filter((node) => node.kind === lane.kind);
          if (!laneNodes.length) return null;
          return <div className={`provenance-lane provenance-lane--${lane.kind}`} key={lane.kind}>
            <span className="provenance-lane__title">{lane.title}</span>
            <div className="provenance-lane__nodes">{laneNodes.map((node) => <button type="button" key={node.id} className={node.id === selected?.id ? "provenance-node is-selected" : "provenance-node"} onClick={() => setSelectedNodeId(node.id)}>
              <span>{node.kind.replaceAll("_", " ")}{node.evidenceKind ? ` · ${node.evidenceKind}` : ""}</span>
              <strong>{node.label}</strong>
              <small>{node.detail}</small>
              <code>{node.sourceIdentity}</code>
              {node.recommended ? <b>current recommendation</b> : null}
            </button>)}</div>
          </div>;
        })}
      </div>
      <aside className="decision-provenance-inspector">
        <span className="eyebrow">Selected provenance node</span>
        {selected ? <>
          <h3>{selected.kind.replaceAll("_", " ")}</h3>
          <strong className="decision-provenance-inspector__label">{selected.label}</strong>
          <p>{selected.detail}</p>
          <dl><div><dt>Kind</dt><dd>{selected.kind}</dd></div><div><dt>Source identity</dt><dd>{selected.sourceIdentity}</dd></div></dl>
          <h4>Exact / declared relationships</h4>
          {selectedEdges.length ? <ul>{selectedEdges.map((edge, index) => <li key={`${edge.source}-${edge.target}-${index}`}><strong>{edge.relationship}</strong><span>{edge.semantics}</span><code>{edge.source} → {edge.target}</code></li>)}</ul> : <p>No attached relationship in this bounded slice.</p>}
        </> : <p>No provenance node is available.</p>}
        {graph.gaps.length ? <div className="provenance-gap-list"><h4>Unresolved provenance gaps</h4><ul>{graph.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul></div> : null}
      </aside>
    </div>
  </section>;
}
