import {useMemo, useState} from "react";
import {ClassificationBadge, MetricStrip, ProjectionBadge, ProvenanceBadge, WorkbenchState} from "./components";
import type {AdvisoryResponse, CaseDetailResponse, EvaluationResponse, FabCase, OverviewResponse, ReplayResponse} from "./types";

export function OperationsOverview({overview, onSelectCase}: {overview: OverviewResponse; onSelectCase: (caseId: string) => void}) {
  return <div className="screen-stack">
    <section className="surface-header">
      <div><span className="eyebrow">Operations overview</span><h1>Yield excursion triage queue</h1></div>
      <div className="badge-row"><ProvenanceBadge kind="synthetic" /><ProjectionBadge projection={overview.projection} /></div>
    </section>
    <MetricStrip items={[
      {label: "Active cases", value: overview.metrics.active_cases, detail: "deterministic case engine"},
      {label: "Physical", value: overview.metrics.physical_excursions, detail: "yield-confirmed baseline"},
      {label: "Sensor bias", value: overview.metrics.sensor_bias_cases, detail: "non-physical"},
      {label: "Data quality", value: overview.metrics.data_quality_cases, detail: "no fab action"},
      {label: "Events", value: overview.metrics.event_count, detail: "source event log"},
    ]} />
    {overview.projection.stale ? <WorkbenchState kind="stale" title="Projection is stale" detail={`${overview.projection.lag_events} source events have not reached the RCA read model.`} /> : null}
    <section className="panel dense-table-panel">
      <header><div><span className="eyebrow">Object set</span><h2>Excursion cases</h2></div><small>Source: synthetic events · result: inferred</small></header>
      <div className="table-scroll"><table>
        <thead><tr><th>Case</th><th>Lot</th><th>Classification</th><th>Score</th><th>Yield</th><th>State</th><th>Scope</th></tr></thead>
        <tbody>{overview.cases.map((item) => <tr key={item.case_id}>
          <td><button className="table-link" onClick={() => onSelectCase(item.case_id)}>{item.case_id}</button></td>
          <td>{item.lot_id}</td>
          <td><ClassificationBadge value={item.classification} /></td>
          <td>{item.anomaly_score.toFixed(3)}</td>
          <td>{item.mean_yield == null ? "—" : `${(item.mean_yield * 100).toFixed(1)}%`}</td>
          <td>{item.state}</td>
          <td>{item.affected_scope.chambers.slice(0, 2).join(", ") || "data path"}</td>
        </tr>)}</tbody>
      </table></div>
    </section>
  </div>;
}

export function ExcursionCase({detail, advisory}: {detail: CaseDetailResponse; advisory: AdvisoryResponse | null}) {
  const top = detail.rca.candidates[0];
  return <div className="screen-stack">
    <section className="surface-header">
      <div><span className="eyebrow">Excursion case · {detail.case.lot_id}</span><h1>{detail.case.case_id}</h1></div>
      <div className="badge-row"><ClassificationBadge value={detail.case.classification} /><ProvenanceBadge kind="inferred" /></div>
    </section>
    <MetricStrip items={[
      {label: "Anomaly score", value: detail.case.anomaly_score.toFixed(3), detail: detail.case.detector_version},
      {label: "Mean yield", value: detail.case.mean_yield == null ? "N/A" : `${(detail.case.mean_yield * 100).toFixed(1)}%`, detail: "synthetic inspection"},
      {label: "Affected chambers", value: detail.case.affected_scope.chambers.length},
      {label: "Evidence events", value: detail.case.evidence_event_ids.length},
      {label: "Projection lag", value: detail.rca.projection.lag_events, detail: detail.rca.projection.projection_version},
    ]} />
    <div className="two-column">
      <section className="panel">
        <header><div><span className="eyebrow">Deterministic RCA</span><h2>Candidate ranking</h2></div></header>
        <ol className="candidate-list">{detail.rca.candidates.map((candidate, index) => <li key={candidate.candidate_id}>
          <div className="candidate-rank">#{index + 1}</div>
          <div><strong>{candidate.candidate_id}</strong><span>{candidate.candidate_type}</span></div>
          <b>{candidate.score.toFixed(2)}</b>
        </li>)}</ol>
      </section>
      <section className="panel evidence-panel">
        <header><div><span className="eyebrow">Evidence ledger</span><h2>Support vs contradiction</h2></div></header>
        {top ? <>
          <h3>Supporting evidence</h3>
          <ul>{top.supporting_evidence.map((item, index) => <li key={`s-${index}`}><code>{JSON.stringify(item)}</code></li>)}</ul>
          <h3>Contradicting evidence</h3>
          {top.contradicting_evidence.length ? <ul>{top.contradicting_evidence.map((item, index) => <li key={`c-${index}`}><code>{JSON.stringify(item)}</code></li>)}</ul> : <p>No explicit contradiction recorded for this top candidate.</p>}
        </> : <WorkbenchState kind="empty" title="No ranked candidate" detail="The deterministic RCA service did not produce a supported candidate." />}
      </section>
    </div>
    <section className="panel advisory-strip">
      <div><span className="eyebrow">Advisory · LLM off</span><h2>{advisory?.result.status ?? "loading"}</h2></div>
      <p>{advisory?.result.recommended_next_step ?? "Resolving evidence-grounded recommendation…"}</p>
    </section>
  </div>;
}

function EvidenceLine({detail, selectedStep}: {detail: CaseDetailResponse; selectedStep: string}) {
  const points = detail.evidence_series.measurements.filter((point) => point.step_id === selectedStep);
  if (!points.length) return <WorkbenchState kind="empty" title="No measurements" detail={`No measurement evidence exists for ${selectedStep}.`} />;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(0.001, max - min);
  const svgPoints = points.map((point, index) => {
    const x = points.length === 1 ? 50 : 4 + index * (92 / (points.length - 1));
    const y = 88 - ((point.value - min) / span) * 72;
    return `${x},${y}`;
  }).join(" ");
  return <div className="series-wrap">
    <svg viewBox="0 0 100 100" role="img" aria-label={`${selectedStep} normalized measurement series`} preserveAspectRatio="none">
      <line x1="4" y1="88" x2="96" y2="88" className="axis-line" />
      <polyline points={svgPoints} className="series-line" />
    </svg>
    <div className="series-caption"><span>min {min.toFixed(2)}</span><span>{points.length} points · {selectedStep}</span><span>max {max.toFixed(2)}</span></div>
  </div>;
}

export function EvidenceGraph({detail, selectedStep, onSelectStep}: {detail: CaseDetailResponse; selectedStep: string | null; onSelectStep: (step: string) => void}) {
  const step = selectedStep ?? detail.trace.process_path[0]?.step_id ?? "LITHO";
  const filtered = detail.evidence_series.measurements.filter((item) => item.step_id === step);
  return <div className="screen-stack">
    <section className="surface-header"><div><span className="eyebrow">Evidence graph</span><h1>{detail.case.lot_id} lineage</h1></div><ProjectionBadge projection={detail.trace.projection} /></section>
    <section className="panel graph-workspace">
      <header><div><span className="eyebrow">Coordinated selection</span><h2>Lot → run → chamber → evidence</h2></div><small>Select a step to update graph, series and table together.</small></header>
      <div className="lineage-row" aria-label="Process lineage">{detail.trace.process_path.map((item, index) => <div className="lineage-fragment" key={item.process_run_id}>
        <button className={item.step_id === step ? "lineage-node is-selected" : "lineage-node"} aria-pressed={item.step_id === step} onClick={() => onSelectStep(item.step_id)}>
          <span>{item.step_id}</span><strong>{item.chamber_id ?? "no chamber"}</strong><small>{item.equipment_id ?? "—"}</small>
        </button>{index < detail.trace.process_path.length - 1 ? <span className="lineage-arrow" aria-hidden="true">→</span> : null}
      </div>)}</div>
      <EvidenceLine detail={detail} selectedStep={step} />
      <div className="table-scroll"><table>
        <thead><tr><th>Sensor</th><th>Value</th><th>Chamber</th><th>Event time</th><th>Event</th></tr></thead>
        <tbody>{filtered.map((item) => <tr key={item.event_id}><td>{item.sensor_name}</td><td>{item.value.toFixed(3)}</td><td>{item.chamber_id}</td><td>{item.event_time}</td><td><code>{item.event_id.slice(0, 12)}…</code></td></tr>)}</tbody>
      </table></div>
    </section>
  </div>;
}

export function DecisionApproval({detail, advisory, busy, feedback, onRequestEvidence, onPropose, onApprove, onReject}: {
  detail: CaseDetailResponse;
  advisory: AdvisoryResponse | null;
  busy: boolean;
  feedback: {kind: "ok" | "error" | "unauthorized"; message: string} | null;
  onRequestEvidence: (reason: string) => Promise<void>;
  onPropose: (target: string, rationale: string) => Promise<void>;
  onApprove: (reason: string) => Promise<void>;
  onReject: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("Collect confirming metrology before any containment decision.");
  return <div className="screen-stack">
    <section className="surface-header"><div><span className="eyebrow">Decision & approval</span><h1>Governed action proposal</h1></div><span className="safety-chip">PROPOSAL ONLY · NO TOOL CONTROL</span></section>
    {feedback ? <WorkbenchState kind={feedback.kind === "unauthorized" ? "unauthorized" : feedback.kind === "error" ? "error" : "degraded"} title={feedback.kind === "ok" ? "Workflow updated" : "Workflow action not applied"} detail={feedback.message} /> : null}
    <div className="two-column">
      <section className="panel">
        <header><div><span className="eyebrow">Advisory provider</span><h2>Evidence-grounded recommendation</h2></div><ProvenanceBadge kind="inferred" /></header>
        <p className="lead-copy">{advisory?.result.recommended_next_step ?? "Loading advisory evidence…"}</p>
        <dl className="property-list">
          <div><dt>Provider</dt><dd>{advisory?.result.provider ?? "—"}</dd></div>
          <div><dt>LLM enabled</dt><dd>{advisory?.llm_enabled ? "Yes" : "No"}</dd></div>
          <div><dt>Status</dt><dd>{advisory?.result.status ?? "—"}</dd></div>
          <div><dt>Tool calls</dt><dd>{advisory?.result.tool_calls.length ?? 0} / 5</dd></div>
        </dl>
        {advisory?.result.status === "abstain" ? <WorkbenchState kind="degraded" title="Advisory abstained" detail="Required evidence is missing or a tool failed. Request more evidence rather than guessing." /> : null}
      </section>
      <section className="panel decision-form">
        <header><div><span className="eyebrow">Human-controlled transition</span><h2>Case state: {detail.case.state}</h2></div></header>
        <label><span>Decision rationale</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={5} /></label>
        <div className="action-grid">
          <button disabled={busy} onClick={() => void onRequestEvidence(reason)}>Request evidence</button>
          <button disabled={busy || !["detected", "evidence_requested", "rejected"].includes(detail.case.state)} onClick={() => void onPropose(detail.case.lot_id, reason)}>Propose diagnostic</button>
          <button className="primary" disabled={busy || detail.case.state !== "proposed"} onClick={() => void onApprove(reason)}>Approve as yield lead</button>
          <button className="danger-outline" disabled={busy || detail.case.state !== "proposed"} onClick={() => void onReject(reason)}>Reject</button>
        </div>
        <p className="muted">Approval records a governed decision token only. This portfolio does not execute holds, recipe changes, or equipment commands.</p>
      </section>
    </div>
  </div>;
}

export function EvaluationLab({evaluation}: {evaluation: EvaluationResponse}) {
  const detector = evaluation.metrics.detector;
  const rca = evaluation.metrics.rca;
  const agent = evaluation.metrics.agent ?? {};
  return <div className="screen-stack">
    <section className="surface-header"><div><span className="eyebrow">Evaluation lab</span><h1>Checked-in release evidence</h1></div><ProvenanceBadge kind="evaluation" /></section>
    <MetricStrip items={[
      {label: "Fault recall", value: `${((detector.fault_recall ?? 0) * 100).toFixed(0)}%`, detail: "synthetic test profile"},
      {label: "False alarms/day", value: detector.false_alarms_per_simulated_day ?? "—"},
      {label: "RCA Top-1", value: `${((rca.top1_accuracy ?? 0) * 100).toFixed(0)}%`, detail: evaluation.versions.projection},
      {label: "Tool selection", value: `${((agent.tool_selection_accuracy ?? 0) * 100).toFixed(0)}%`, detail: evaluation.versions.agent},
      {label: "Unsupported claims", value: `${((agent.unsupported_claim_rate ?? 0) * 100).toFixed(0)}%`},
    ]} />
    <section className="panel">
      <header><div><span className="eyebrow">Version registry</span><h2>Evidence contract</h2></div></header>
      <div className="version-grid">{Object.entries(evaluation.versions).map(([key, value]) => <div key={key}><span>{key}</span><strong>{value}</strong></div>)}</div>
      <h3>Limitations</h3>
      <ul>{evaluation.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      {evaluation.negative_results?.length ? <><h3>Negative results</h3><ul>{evaluation.negative_results.map((item) => <li key={item.id}><strong>{item.id}</strong> · {item.description}</li>)}</ul></> : null}
      {evaluation.evidence_hash ? <p className="muted">Evidence hash: <code>{evaluation.evidence_hash}</code></p> : null}
    </section>
  </div>;
}

export function ReplayOperations({replay}: {replay: ReplayResponse}) {
  const integration = replay.integration;
  const integrationState = integration.container_integration_verified
    ? {kind: "ok" as const, title: "Container integration verified", detail: "M6 evidence verifies PostgreSQL, Redpanda and Neo4j runtime integration. This is verification state, not a claim that Docker is currently running."}
    : integration.status === "degraded"
      ? {kind: "degraded" as const, title: "Container integration degraded", detail: integration.reason ?? "One or more configured integration dependencies are unavailable."}
      : {kind: "degraded" as const, title: "Container integration unverified", detail: integration.reason ?? "No successful container-backed verification evidence is available yet."};
  return <div className="screen-stack">
    <section className="surface-header"><div><span className="eyebrow">Replay & operations</span><h1>Deterministic pipeline state</h1></div><ProjectionBadge projection={replay.projection} /></section>
    <MetricStrip items={[
      {label: "Event log", value: replay.event_count},
      {label: "Detection checkpoint", value: replay.detection_checkpoint},
      {label: "Projection checkpoint", value: replay.projection.projection_checkpoint},
      {label: "Outbox", value: replay.outbox_count},
      {label: "Quarantine", value: replay.quarantine_count},
    ]} />
    <div className="two-column">
      <section className="panel"><header><div><span className="eyebrow">Delivery behavior</span><h2>Accepted event status</h2></div></header>
        <dl className="property-list">{Object.entries(replay.delivery_status_counts).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
      </section>
      <section className="panel"><header><div><span className="eyebrow">External adapters</span><h2>Verification status</h2></div></header>
        <dl className="property-list">{Object.entries(replay.external_services).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
        <WorkbenchState {...integrationState} />
      </section>
    </div>
  </div>;
}

export function caseById(cases: FabCase[], caseId: string | null): FabCase | null {
  return cases.find((item) => item.case_id === caseId) ?? cases[0] ?? null;
}

