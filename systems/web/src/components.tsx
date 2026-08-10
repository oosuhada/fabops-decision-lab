import type {ReactNode} from "react";
import type {FabCase, ProjectionStatus} from "./types";

export function ProvenanceBadge({kind}: {kind: "synthetic" | "inferred" | "real-public" | "evaluation"}) {
  const label = kind === "real-public" ? "REAL PUBLIC" : kind.toUpperCase();
  return <span className={`provenance provenance-${kind}`}>{label}</span>;
}

export function WorkbenchState({kind, title, detail, action}: {
  kind: "loading" | "empty" | "error" | "stale" | "degraded" | "unauthorized";
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

export function EvidenceInspector({selectedCase, projection, sourceTimestamp, selectedStep}: {
  selectedCase: FabCase | null;
  projection: ProjectionStatus | null;
  sourceTimestamp: string | null;
  selectedStep: string | null;
}) {
  return <aside className="evidence-inspector" aria-label="Evidence inspector">
    <header>
      <span className="eyebrow">Evidence inspector</span>
      <strong>{selectedCase?.case_id ?? "No case selected"}</strong>
    </header>
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
      <strong>No equipment mutation</strong>
      <span>All actions in this workbench are governed proposals or diagnostic requests.</span>
    </footer>
  </aside>;
}

