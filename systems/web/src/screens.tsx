import {useMemo, useState} from "react";
import {ClassificationBadge, MetricStrip, ProjectionBadge, ProvenanceBadge, WorkbenchState} from "./components";
import type {AdvisoryResponse, CaseDetailResponse, DecisionBriefResponse, DecisionCockpitResponse, DecisionPacket, EvaluationResponse, FabCase, NarrationIntent, NarrationStatusResponse, OverviewResponse, ReplayResponse} from "./types";

function priorityClass(band: string) {
  if (band === "HIGH") return "decision-priority is-high";
  if (band === "VERIFY_DATA") return "decision-priority is-verify";
  return "decision-priority is-medium";
}

function optionStanceLabel(stance: string) {
  if (stance === "recommended") return "RECOMMENDED";
  if (stance === "conditional") return "CONDITIONAL";
  if (stance === "guardrail") return "GUARDRAIL";
  return "ALTERNATIVE";
}

function evidenceBalance(packet: DecisionPacket) {
  const candidate = packet.evidence.top_candidate;
  const support = candidate?.supporting_evidence.length ?? 0;
  const contradict = candidate?.contradicting_evidence.length ?? 0;
  const total = support + contradict;
  const supportRatio = total ? Math.round((support / total) * 100) : 0;
  const label = contradict > 0 ? "CONTESTED" : support >= 3 ? "SUPPORTED" : support > 0 ? "PARTIAL" : "THIN";
  return {support, contradict, supportRatio, label};
}

function DecisionOptionCards({packet, compact = false}: {packet: DecisionPacket; compact?: boolean}) {
  return <div className={compact ? "decision-options decision-options--compact" : "decision-options"}>
    {packet.options.map((option, index) => {
      const recommended = option.option_id === packet.recommended_option_id;
      return <article className={recommended ? "decision-option is-recommended" : "decision-option"} key={option.option_id}>
        <div className="decision-option__head">
          <span className="decision-option__number">0{index + 1}</span>
          <span className={recommended ? "option-stance option-stance--recommended" : `option-stance option-stance--${option.stance}`}>{optionStanceLabel(option.stance)}</span>
        </div>
        <strong>{option.label}</strong>
        <p>{option.tradeoff}</p>
        <footer>
          <span>{option.requires_human_approval ? "Human approval required" : "Evidence / diagnostic step"}</span>
          {recommended ? <b>Current recommendation</b> : null}
        </footer>
      </article>;
    })}
  </div>;
}

function readableEvidence(item: Record<string, unknown>) {
  const entries = Object.entries(item).filter(([, value]) => value != null).slice(0, 4);
  return entries.length ? entries.map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`).join(" · ") : "Evidence record";
}

export function DecisionCockpit({cockpit, onOpenCase, onOpenDecision}: {
  cockpit: DecisionCockpitResponse;
  onOpenCase: (caseId: string) => void;
  onOpenDecision: (caseId: string) => void;
}) {
  const top = cockpit.queue[0];
  const topEvidence = top ? evidenceBalance(top) : null;
  return <div className="screen-stack decision-cockpit">
    <section className="cockpit-hero">
      <div className="cockpit-hero__intro">
        <span className="eyebrow">Decision cockpit · shift view</span>
        <h1>What needs a decision now?</h1>
        <p>FabOps turns excursion signals into a ranked human decision queue: what happened, why it matters, what the evidence says, and which next step is safest.</p>
      </div>
      <div className="cockpit-hero__status">
        <div><span>Decision packets</span><strong>{cockpit.summary.decision_count}</strong><small>open inferred cases</small></div>
        <div><span>High priority</span><strong>{cockpit.summary.high_priority}</strong><small>review first</small></div>
        <div><span>Verify data</span><strong>{cockpit.summary.data_verification}</strong><small>no fab action</small></div>
        <div className="cockpit-trust"><span>Decision authority</span><strong>HUMAN</strong><small>LLM wording only</small></div>
      </div>
    </section>
    {top ? <section className="decision-spotlight panel">
      <div className="decision-spotlight__main">
        <div className="decision-spotlight__meta">
          <span className={priorityClass(top.priority_band)}>{top.priority_band}</span>
          <span>{top.lot_id}</span>
          <ClassificationBadge value={top.classification} />
        </div>
        <span className="eyebrow">Highest-ranked unresolved decision</span>
        <h2>{top.decision_question}</h2>
        <div className="recommended-callout">
          <span>Recommended next stance</span>
          <strong>{top.options.find((option) => option.option_id === top.recommended_option_id)?.label}</strong>
          <p>{top.options.find((option) => option.option_id === top.recommended_option_id)?.tradeoff}</p>
        </div>
        <div className="decision-impact-grid">
          <div><span>Affected scope</span><strong>{top.impact.affected_chamber_count}</strong><small>chambers</small></div>
          <div><span>Affected lots</span><strong>{top.impact.affected_lot_count}</strong><small>synthetic lots</small></div>
          <div><span>Yield gap</span><strong>{top.impact.synthetic_yield_gap_percentage_points == null ? "—" : top.impact.synthetic_yield_gap_percentage_points.toFixed(1)}</strong><small>percentage points</small></div>
        </div>
        <div className="decision-spotlight__actions">
          <button onClick={() => onOpenCase(top.case_id)}>Investigate evidence</button>
          <button className="primary" onClick={() => onOpenDecision(top.case_id)}>Compare options →</button>
        </div>
      </div>
      <aside className="decision-spotlight__evidence">
        <span className="eyebrow">Why this is ranked first</span>
        <div className="hypothesis-card">
          <span>Top RCA hypothesis</span>
          <strong>{top.evidence.top_candidate?.candidate_id ?? "Not ranked"}</strong>
          <small>deterministic score {top.evidence.top_candidate?.score.toFixed(2) ?? "—"}</small>
        </div>
        {topEvidence ? <div className="evidence-meter-card">
          <div><span>Evidence balance</span><strong>{topEvidence.label}</strong></div>
          <div className="evidence-meter" aria-label={`${topEvidence.support} supporting and ${topEvidence.contradict} contradicting evidence`}><span style={{width: `${Math.max(6, topEvidence.supportRatio)}%`}} /></div>
          <small>{topEvidence.support} supporting · {topEvidence.contradict} contradicting</small>
        </div> : null}
        <div className="uncertainty-list">
          <span>Decision uncertainty</span>
          <ul>{top.uncertainties.slice(0, 2).map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      </aside>
    </section> : null}
    {top ? <section className="panel option-comparison-panel">
      <header><div><span className="eyebrow">Decision design</span><h2>Compare the available stances before acting</h2></div><small>Trade-offs are deterministic; LLM narration cannot add or replace options.</small></header>
      <DecisionOptionCards packet={top} compact />
    </section> : null}
    <section className="panel decision-queue-panel">
      <header><div><span className="eyebrow">Ranked decision backlog</span><h2>Next decisions</h2></div><small>Classification-aware priority · deterministic ordering</small></header>
      <div className="decision-queue">{cockpit.queue.map((packet) => {
        const recommended = packet.options.find((option) => option.option_id === packet.recommended_option_id);
        const balance = evidenceBalance(packet);
        return <article key={packet.case_id} className="decision-queue-item">
          <div className="decision-queue-item__identity">
            <span className={priorityClass(packet.priority_band)}>{packet.priority_band}</span>
            <strong>{packet.lot_id}</strong>
            <small>#{packet.priority_rank} · {packet.classification.replaceAll("_", " ")}</small>
          </div>
          <div className="decision-queue-item__question"><strong>{packet.decision_question}</strong><span>Recommended: {recommended?.label}</span></div>
          <div className="decision-queue-item__evidence">
            <strong>{balance.label}</strong>
            <span>{balance.support} support / {balance.contradict} contradict · RCA {packet.evidence.top_candidate?.score.toFixed(2) ?? "—"}</span>
          </div>
          <div className="decision-queue-item__impact"><strong>{packet.impact.synthetic_yield_gap_percentage_points == null ? "—" : `${packet.impact.synthetic_yield_gap_percentage_points.toFixed(1)} pp`}</strong><span>yield gap</span></div>
          <button onClick={() => onOpenDecision(packet.case_id)}>Open →</button>
        </article>;
      })}</div>
    </section>
  </div>;
}

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
  const supportCount = top?.supporting_evidence.length ?? 0;
  const contradictCount = top?.contradicting_evidence.length ?? 0;
  return <div className="screen-stack">
    <section className="case-hero">
      <div>
        <span className="eyebrow">Case investigation · {detail.case.lot_id}</span>
        <h1>{top ? `Is ${top.candidate_id} the best explanation?` : detail.case.case_id}</h1>
        <p>Separate observed evidence from the current RCA hypothesis before any governed decision.</p>
        <div className="badge-row"><ClassificationBadge value={detail.case.classification} /><ProvenanceBadge kind="inferred" /><ProjectionBadge projection={detail.rca.projection} /></div>
      </div>
      <div className="case-hero__hypothesis">
        <span>Top hypothesis</span>
        <strong>{top?.candidate_id ?? "Unranked"}</strong>
        <small>score {top?.score.toFixed(2) ?? "—"} · {supportCount} support · {contradictCount} contradict</small>
      </div>
    </section>
    <MetricStrip items={[
      {label: "Anomaly score", value: detail.case.anomaly_score.toFixed(3), detail: detail.case.detector_version},
      {label: "Mean yield", value: detail.case.mean_yield == null ? "N/A" : `${(detail.case.mean_yield * 100).toFixed(1)}%`, detail: "synthetic inspection"},
      {label: "Affected chambers", value: detail.case.affected_scope.chambers.length},
      {label: "Evidence events", value: detail.case.evidence_event_ids.length},
      {label: "Projection lag", value: detail.rca.projection.lag_events, detail: detail.rca.projection.projection_version},
    ]} />
    <div className="case-investigation-grid">
      <section className="panel candidate-panel">
        <header><div><span className="eyebrow">Deterministic RCA</span><h2>Competing hypotheses</h2></div><small>Ranking is not generated by the LLM.</small></header>
        <ol className="candidate-list">{detail.rca.candidates.map((candidate, index) => <li key={candidate.candidate_id}>
          <div className="candidate-rank">#{index + 1}</div>
          <div><strong>{candidate.candidate_id}</strong><span>{candidate.candidate_type}</span></div>
          <div className="candidate-score"><b>{candidate.score.toFixed(2)}</b><small>{candidate.supporting_evidence.length} / {candidate.contradicting_evidence.length}</small></div>
        </li>)}</ol>
      </section>
      <section className="panel evidence-panel">
        <header><div><span className="eyebrow">Evidence ledger</span><h2>What supports — and weakens — the hypothesis?</h2></div></header>
        {top ? <>
          <div className="evidence-ledger-grid">
            <div className="evidence-ledger-column evidence-ledger-column--support">
              <h3>Supporting evidence <span>{supportCount}</span></h3>
              {top.supporting_evidence.length ? <ul>{top.supporting_evidence.map((item, index) => <li key={`s-${index}`}><span className="evidence-bullet">+</span><p>{readableEvidence(item)}</p></li>)}</ul> : <p>No explicit supporting evidence.</p>}
            </div>
            <div className="evidence-ledger-column evidence-ledger-column--contradict">
              <h3>Contradicting evidence <span>{contradictCount}</span></h3>
              {top.contradicting_evidence.length ? <ul>{top.contradicting_evidence.map((item, index) => <li key={`c-${index}`}><span className="evidence-bullet">−</span><p>{readableEvidence(item)}</p></li>)}</ul> : <p>No explicit contradiction recorded. Treat absence of contradiction as uncertainty, not proof.</p>}
            </div>
          </div>
        </> : <WorkbenchState kind="empty" title="No ranked candidate" detail="The deterministic RCA service did not produce a supported candidate." />}
      </section>
    </div>
    <section className="panel advisory-strip advisory-strip--decision">
      <div><span className="eyebrow">Evidence-grounded next step</span><h2>{advisory?.result.status === "ready" ? "Ready for human review" : advisory?.result.status ?? "loading"}</h2></div>
      <p>{advisory?.result.recommended_next_step ?? "Resolving evidence-grounded recommendation…"}</p>
      <span className="advisory-authority">Deterministic advisory · no state mutation</span>
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

export function DecisionApproval({detail, packet, advisory, busy, feedback, brief, briefAudience, narrationBusy, narrationFeedback, narrationStatus, onBriefAudience, onGenerateBrief, onRequestEvidence, onPropose, onApprove, onReject}: {
  detail: CaseDetailResponse;
  packet: DecisionPacket | null;
  advisory: AdvisoryResponse | null;
  busy: boolean;
  feedback: {kind: "ok" | "error" | "unauthorized"; message: string} | null;
  brief: DecisionBriefResponse | null;
  briefAudience: "manager" | "engineer";
  narrationBusy: boolean;
  narrationFeedback: string | null;
  narrationStatus: NarrationStatusResponse | null;
  onBriefAudience: (audience: "manager" | "engineer") => void;
  onGenerateBrief: (intent: NarrationIntent) => Promise<void>;
  onRequestEvidence: (reason: string) => Promise<void>;
  onPropose: (target: string, rationale: string) => Promise<void>;
  onApprove: (reason: string) => Promise<void>;
  onReject: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("Collect confirming metrology before any containment decision.");
  const recommended = packet?.options.find((option) => option.option_id === packet.recommended_option_id);
  const narrationSource = !brief ? "DETERMINISTIC FALLBACK" : brief.brief.cache_hit ? "CACHED" : brief.brief.provider === "vertex-ai-gemini" ? "VERTEX AI" : brief.brief.provider === "local-qwen" || brief.brief.provider === "local-openai-compatible" ? "LOCAL QWEN" : brief.brief.mode === "deterministic_fallback" ? "DETERMINISTIC FALLBACK" : brief.brief.provider.toUpperCase();
  return <div className="screen-stack">
    <section className="decision-header">
      <div>
        <div className="decision-header__meta">
          {packet ? <span className={priorityClass(packet.priority_band)}>{packet.priority_band}</span> : null}
          <span>{detail.case.lot_id}</span>
          <ClassificationBadge value={detail.case.classification} />
        </div>
        <span className="eyebrow">Decision workspace · case state {detail.case.state}</span>
        <h1>{packet?.decision_question ?? "Governed action proposal"}</h1>
        <p>{recommended ? <>Current recommendation: <strong>{recommended.label}</strong> · {recommended.tradeoff}</> : "The deterministic recommendation is resolved before narrative generation."}</p>
      </div>
      <div className="decision-header__guardrail"><span>Authority boundary</span><strong>HUMAN DECISION</strong><small>No equipment command path</small></div>
    </section>
    {feedback ? <WorkbenchState kind={feedback.kind === "unauthorized" ? "unauthorized" : feedback.kind === "error" ? "error" : "degraded"} title={feedback.kind === "ok" ? "Workflow updated" : "Workflow action not applied"} detail={feedback.message} /> : null}
    {packet ? <section className="panel option-comparison-panel option-comparison-panel--decision">
      <header><div><span className="eyebrow">Option comparison</span><h2>Choose a stance, not an opaque AI answer</h2></div><small>Recommendation is deterministic · approval remains human-controlled</small></header>
      <DecisionOptionCards packet={packet} />
    </section> : null}
    <section className="panel grounded-brief">
      <header>
        <div><span className="eyebrow">Grounded decision brief</span><h2>{brief?.brief.headline ?? "Generating evidence-grounded wording…"}</h2></div>
        <div className="brief-audience-toggle" aria-label="Decision brief audience">
          <button className={briefAudience === "manager" ? "is-active" : ""} onClick={() => onBriefAudience("manager")}>Manager</button>
          <button className={briefAudience === "engineer" ? "is-active" : ""} onClick={() => onBriefAudience("engineer")}>Engineer</button>
        </div>
      </header>
      {brief ? <>
        <div className="brief-summary-grid">
          <div className="brief-summary-main"><span>Executive summary</span><p>{brief.brief.summary}</p></div>
          <div className="brief-provider-card">
            <span>Narration source</span>
            <strong>{narrationSource}</strong>
            <small>{brief.brief.cache_hit ? "cache hit" : brief.brief.mode}{brief.brief.latency_ms !== undefined ? ` · ${Math.round(brief.brief.latency_ms)} ms` : ""}</small>
            <b>Decision ID preserved</b>
          </div>
        </div>
        <div className="brief-sections">{brief.brief.sections.map((section) => <article key={section.section_id}>
          <strong>{section.title}</strong><p>{section.body}</p><small>Evidence: {section.evidence_refs.join(" · ")}</small>
        </article>)}</div>
        <div className="brief-meta"><span>recommended option: {brief.brief.recommended_option_id}</span><span>{brief.brief.citations.length} evidence refs</span>{brief.brief.fallback_reason ? <span>fallback: {brief.brief.fallback_reason}</span> : null}</div>
        <div className="brief-meta"><span>AI wording does not change the deterministic recommendation.</span>{narrationStatus ? <><span>local: {narrationStatus.provider_health.local_llm}</span><span>vertex: {narrationStatus.provider_health.vertex}</span></> : null}</div>
      </> : <WorkbenchState kind="loading" title="Building decision wording" detail="The deterministic packet is fixed first; an available LLM may only rewrite grounded wording." />}
      <div className="brief-live-controls">
        <div>
          <span className="eyebrow">Bounded AI demo</span>
          <strong>Generate only on explicit intent</strong>
          <small>No free-form prompt · server session + rate/budget gates · local Qwen → Vertex → deterministic</small>
        </div>
        <div className="brief-intent-actions">
          <button disabled={narrationBusy} onClick={() => void onGenerateBrief("manager_summary")}>Manager summary</button>
          <button disabled={narrationBusy} onClick={() => void onGenerateBrief("engineer_checklist")}>Engineer checklist</button>
          <button disabled={narrationBusy} onClick={() => void onGenerateBrief("tradeoff_compare")}>Compare trade-offs</button>
          <button disabled={narrationBusy} onClick={() => void onGenerateBrief("counter_evidence")}>Counter-evidence</button>
        </div>
        {narrationFeedback ? <p className="brief-live-feedback">{narrationFeedback}</p> : null}
      </div>
    </section>
    <div className="decision-bottom-grid">
      <section className="panel decision-rationale-panel">
        <header><div><span className="eyebrow">Why this recommendation</span><h2>Evidence before action</h2></div><ProvenanceBadge kind="inferred" /></header>
        <div className="recommendation-evidence">
          <div><span>Deterministic advisory</span><strong>{advisory?.result.recommended_next_step ?? "Loading advisory evidence…"}</strong></div>
          <div><span>Top hypothesis</span><strong>{packet?.evidence.top_candidate?.candidate_id ?? detail.rca.candidates[0]?.candidate_id ?? "—"}</strong><small>RCA score {packet?.evidence.top_candidate?.score.toFixed(2) ?? detail.rca.candidates[0]?.score.toFixed(2) ?? "—"}</small></div>
          <div><span>Counter-evidence</span><strong>{packet?.evidence.top_candidate?.contradicting_evidence.length ?? detail.rca.candidates[0]?.contradicting_evidence.length ?? 0}</strong><small>explicit contradictory records</small></div>
        </div>
        {packet?.uncertainties.length ? <div className="uncertainty-list uncertainty-list--panel"><span>What remains uncertain</span><ul>{packet.uncertainties.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
        {advisory?.result.status === "abstain" ? <WorkbenchState kind="degraded" title="Advisory abstained" detail="Required evidence is missing or a tool failed. Request more evidence rather than guessing." /> : null}
      </section>
      <section className="panel decision-form">
        <header><div><span className="eyebrow">Governed workflow</span><h2>Record the human decision</h2></div><span className="safety-chip">NO TOOL CONTROL</span></header>
        <label><span>Decision rationale</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={5} /></label>
        <div className="action-grid">
          <button disabled={busy} onClick={() => void onRequestEvidence(reason)}>Request evidence</button>
          <button disabled={busy || !["detected", "evidence_requested", "rejected"].includes(detail.case.state)} onClick={() => void onPropose(detail.case.lot_id, reason)}>Propose diagnostic</button>
          <button className="primary" disabled={busy || detail.case.state !== "proposed"} onClick={() => void onApprove(reason)}>Approve as yield lead</button>
          <button className="danger-outline" disabled={busy || detail.case.state !== "proposed"} onClick={() => void onReject(reason)}>Reject</button>
        </div>
        <p className="muted">Approval records a governed decision token only. This portfolio never executes holds, recipe changes or equipment commands.</p>
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
    <section className="panel">
      <header><div><span className="eyebrow">Release identity</span><h2>Portfolio release {replay.release.release_version}</h2></div></header>
      <dl className="property-list">
        <div><dt>Canonical hash</dt><dd><code>{replay.release.release_hash}</code></dd></div>
        <div><dt>Source commit</dt><dd>{replay.release.source_git_commit?.slice(0, 12) ?? "pending manifest"}</dd></div>
        <div><dt>Manifest</dt><dd>{replay.release.manifest_available ? "generated" : "pending"}</dd></div>
      </dl>
    </section>
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

