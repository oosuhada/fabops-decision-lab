import type {ReactNode} from "react";
import type {DecisionPacket, FabCase, ProjectionStatus} from "./types";

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
  if (!candidate) return {support: 0, contradict: 0, confidence: "UNRANKED"};
  const support = candidate.supporting_evidence.length;
  const contradict = candidate.contradicting_evidence.length;
  const confidence = contradict > 0 ? "CONTESTED" : support >= 3 ? "SUPPORTED" : support > 0 ? "PARTIAL" : "THIN";
  return {support, contradict, confidence};
}

export function EvidenceInspector({selectedCase, selectedPacket, projection, sourceTimestamp, selectedStep}: {
  selectedCase: FabCase | null;
  selectedPacket: DecisionPacket | null;
  projection: ProjectionStatus | null;
  sourceTimestamp: string | null;
  selectedStep: string | null;
}) {
  const evidenceBalance = packetEvidenceBalance(selectedPacket);
  const recommended = selectedPacket?.options.find((option) => option.option_id === selectedPacket.recommended_option_id);
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
      <h3>Evidence balance</h3>
      <div className={`evidence-balance evidence-balance--${evidenceBalance.confidence.toLowerCase()}`}>
        <strong>{evidenceBalance.confidence}</strong>
        <span>{evidenceBalance.support} supporting · {evidenceBalance.contradict} contradicting</span>
      </div>
      <dl className="property-list">
        <div><dt>Top hypothesis</dt><dd>{selectedPacket.evidence.top_candidate?.candidate_id ?? "unranked"}</dd></div>
        <div><dt>RCA score</dt><dd>{selectedPacket.evidence.top_candidate?.score.toFixed(2) ?? "—"}</dd></div>
        <div><dt>Yield gap</dt><dd>{selectedPacket.impact.synthetic_yield_gap_percentage_points == null ? "—" : `${selectedPacket.impact.synthetic_yield_gap_percentage_points.toFixed(2)} pp`}</dd></div>
        <div><dt>Affected scope</dt><dd>{selectedPacket.impact.affected_chamber_count} chambers</dd></div>
      </dl>
    </section> : null}
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

