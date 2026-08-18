import {useEffect, useRef, type ReactNode} from "react";
import {animate} from "motion/mini";
import type {DecisionPacket, FabCase, ProjectionStatus} from "./types";
import type {EvidenceGraphNode} from "./features/evidence/evidenceGraphModel";

export function ProvenanceBadge({kind}: {kind: "synthetic" | "inferred" | "real-public" | "evaluation"}) {
  const label = kind === "real-public" ? "REAL PUBLIC" : kind.toUpperCase();
  return <span className={`provenance provenance-${kind}`}>{label}</span>;
}

export function WorkbenchState({kind, title, detail, action}: {
  kind: "loading" | "empty" | "error" | "stale" | "degraded" | "unauthorized" | "ok";
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  const role = kind === "error" || kind === "unauthorized" ? "alert" : "status";
  return <section className={`workbench-state state-${kind}`} role={role} aria-live="polite">
    <strong>{title}</strong>
    <p>{detail}</p>
    {action ? <div>{action}</div> : null}
  </section>;
}

export function MetricStrip({items}: {items: Array<{label: string; value: string | number; detail?: string}>}) {
  return <div className="metric-strip">
    {items.map((item) => <div className="metric-cell" key={item.label}>
      <span>{item.label}</span>
      <strong>{item.value}</strong>
      {item.detail ? <small>{item.detail}</small> : null}
    </div>)}
  </div>;
}

export function ProjectionBadge({projection}: {projection: ProjectionStatus}) {
  return <span className={`projection-badge ${projection.stale ? "is-stale" : "is-fresh"}`}>
    {projection.stale ? `STALE · ${projection.lag_events} events` : "PROJECTION FRESH"}
  </span>;
}

export function ClassificationBadge({value}: {value: string}) {
  return <span className={`classification classification-${value}`}>{value.replaceAll("_", " ")}</span>;
}

function packetEvidenceBalance(packet: DecisionPacket | null) {
  const candidate = packet?.evidence.top_candidate;
  if (!candidate) return {support: 0, contradict: 0, sufficiency: "UNRANKED"};
  const support = candidate.supporting_evidence.length;
  const contradict = candidate.contradicting_evidence.length;
  const sufficiency = contradict > 0 ? "CONTESTED" : support >= 3 ? "SUPPORTED" : support > 0 ? "PARTIAL" : "THIN";
  return {support, contradict, sufficiency};
}

function selectedEvidenceClassification(node: EvidenceGraphNode | null) {
  if (!node) return {kind: "Missing evidence", detail: "No graph evidence object is selected. Select a source, projection, or inference object to inspect its classification."};
  if (node.type === "Case") return {kind: "Deterministic detection", detail: "Case state produced by deterministic detection logic; it is not a raw measurement."};
  if (node.provenance === "source") return {kind: "Observed fact", detail: "Source-linked operational evidence from the authoritative event contract."};
  if (node.provenance === "projection") return {kind: "Graph projection", detail: "Current rebuildable RCA/read projection; PostgreSQL/event truth remains authoritative."};
  return {kind: "System inference", detail: "Deterministic RCA/system inference. Score is a ranking value, not a confidence probability."};
}

export function EvidenceInspector({selectedCase, selectedPacket, projection, sourceTimestamp, selectedStep, selectedEvidenceNode = null}: {
  selectedCase: FabCase | null;
  selectedPacket: DecisionPacket | null;
  projection: ProjectionStatus | null;
  sourceTimestamp: string | null;
  selectedStep: string | null;
  selectedEvidenceNode?: EvidenceGraphNode | null;
}) {
  const classificationRef = useRef<HTMLElement>(null);
  const evidenceBalance = packetEvidenceBalance(selectedPacket);
  const recommended = selectedPacket?.options.find((option) => option.option_id === selectedPacket.recommended_option_id);
  const evidenceClassification = selectedEvidenceClassification(selectedEvidenceNode);
  const selectedTimestamp = selectedEvidenceNode && typeof selectedEvidenceNode.properties.event_time === "string" ? selectedEvidenceNode.properties.event_time : null;
  const selectedSourceIdentity = selectedEvidenceNode ? selectedEvidenceNode.properties.event_id ?? selectedEvidenceNode.properties.inspection_id ?? selectedEvidenceNode.properties.process_run_id ?? selectedEvidenceNode.id : null;
  useEffect(() => {
    const element = classificationRef.current;
    const reducedMotion = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!element || reducedMotion || typeof element.animate !== "function") return;
    const controls = animate(element, {opacity: [0.72, 1], transform: ["translateY(4px)", "translateY(0px)"]}, {duration: .16});
    return () => controls.cancel();
  }, [selectedEvidenceNode?.id]);
  return <aside className="evidence-inspector" aria-label="Evidence inspector">
    <header>
      <span className="eyebrow">Decision context</span>
      <strong>{selectedCase?.lot_id ?? "No case selected"}</strong>
      <small>{selectedCase?.case_id ?? "Select a decision packet"}</small>
    </header>
    {selectedPacket ? <section className="inspector-decision-card">
      <span className={`decision-priority ${selectedPacket.priority_band === "HIGH" ? "is-high" : selectedPacket.priority_band === "VERIFY_DATA" ? "is-verify" : "is-medium"}`}>{selectedPacket.priority_band}</span>
      <h3>Decision now</h3>
      <p>{selectedPacket.decision_question}</p>
      <div className="inspector-recommendation">
        <span>Recommended</span>
        <strong>{recommended?.label ?? selectedPacket.recommended_option_id}</strong>
      </div>
    </section> : null}
    {selectedPacket ? <section>
      <h3>Evidence sufficiency</h3>
      <div className={`evidence-balance evidence-balance--${evidenceBalance.sufficiency.toLowerCase()}`}>
        <strong>{evidenceBalance.sufficiency}</strong>
        <span>{evidenceBalance.support} supporting · {evidenceBalance.contradict} contradicting</span>
      </div>
      <dl className="property-list">
        <div><dt>Top hypothesis</dt><dd>{selectedPacket.evidence.top_candidate?.candidate_id ?? "unranked"}</dd></div>
        <div><dt>RCA score</dt><dd>{selectedPacket.evidence.top_candidate?.score.toFixed(2) ?? "—"}</dd></div>
        <div><dt>Yield gap</dt><dd>{selectedPacket.impact.synthetic_yield_gap_percentage_points == null ? "—" : `${selectedPacket.impact.synthetic_yield_gap_percentage_points.toFixed(2)} pp`}</dd></div>
        <div><dt>Affected scope</dt><dd>{selectedPacket.impact.affected_chamber_count} chambers</dd></div>
      </dl>
    </section> : null}
    <section ref={classificationRef} className="inspector-classification-instrument">
      <div className="inspector-instrument-heading"><div><span className="eyebrow">Engineering artifact</span><h3>Evidence classification</h3></div><b>{evidenceClassification.kind}</b></div>
      <div className="inspector-evidence-kind"><span>{evidenceClassification.kind}</span><strong>{selectedEvidenceNode?.label ?? "No evidence object selected"}</strong><p>{evidenceClassification.detail}</p></div>
      <div className="inspector-artifact-status" aria-label="Selected evidence artifact coordinates">
        <div><span>LAYER</span><strong>{selectedEvidenceNode?.provenance ?? "unselected"}</strong></div>
        <div><span>IDENTITY</span><strong>{selectedSourceIdentity == null ? "missing" : String(selectedSourceIdentity)}</strong></div>
        <div><span>TIME BASIS</span><strong>{selectedTimestamp ? "source timestamp" : "not available"}</strong></div>
      </div>
      <dl className="property-list">
        <div><dt>Source identity</dt><dd>{selectedSourceIdentity == null ? "Unavailable for current selection" : String(selectedSourceIdentity)}</dd></div>
        <div><dt>Timestamp</dt><dd>{selectedTimestamp ?? "No source timestamp on current selection"}</dd></div>
        <div><dt>Freshness</dt><dd>{selectedEvidenceNode?.provenance === "projection" || selectedEvidenceNode?.provenance === "inferred" ? projection?.stale ? `STALE · ${projection.lag_events} events` : "Current rebuildable projection" : "Source-record time applies"}</dd></div>
      </dl>
      <div className="evidence-classification-key" aria-label="Evidence classification key">
        <span><b>Observed fact</b> source-linked measurement / inspection</span>
        <span><b>Deterministic detection</b> case classification / anomaly output</span>
        <span><b>Graph projection</b> rebuildable read model</span>
        <span><b>System inference</b> deterministic RCA / advisory</span>
        <span><b>Human note</b> only when present in audit/workflow data</span>
        <span><b>AI wording</b> only inside bounded PresentationSpec output</span>
        <span><b>Missing evidence</b> shown as an explicit gap, never timestamped</span>
      </div>
    </section>
    <section>
      <h3>Provenance</h3>
      <div className="badge-row"><ProvenanceBadge kind="synthetic" /><ProvenanceBadge kind="inferred" /></div>
      <dl className="property-list">
        <div><dt>Source timestamp</dt><dd>{sourceTimestamp ?? "—"}</dd></div>
        <div><dt>Projection</dt><dd>{projection?.projection_version ?? "—"}</dd></div>
        <div><dt>Projection lag</dt><dd>{projection?.lag_events ?? "—"}</dd></div>
        <div><dt>Selected step</dt><dd>{selectedStep ?? "All steps"}</dd></div>
      </dl>
    </section>
    {selectedCase ? <section>
      <h3>Selected object</h3>
      <dl className="property-list">
        <div><dt>Lot</dt><dd>{selectedCase.lot_id}</dd></div>
        <div><dt>Class</dt><dd>{selectedCase.classification}</dd></div>
        <div><dt>Case state</dt><dd>{selectedCase.state}</dd></div>
        <div><dt>Detector</dt><dd>{selectedCase.detector_version}</dd></div>
        <div><dt>Evidence refs</dt><dd>{selectedCase.evidence_event_ids.length}</dd></div>
      </dl>
    </section> : null}
    <footer>
      <strong>Decision support only</strong>
      <span>No equipment control. LLM wording cannot change classification, RCA ranking, accepted recommendation, authorization or case state.</span>
    </footer>
  </aside>;
}

