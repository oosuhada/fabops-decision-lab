import {useEffect, useMemo, useState} from "react";
import {ClassificationBadge, MetricStrip, ProjectionBadge, ProvenanceBadge, WorkbenchState} from "./components";
import {EvidenceGraphExplorer} from "./features/evidence/EvidenceGraphExplorer";
import {DecisionBoundaryPanel, RcaExplainability} from "./features/explainability/RcaExplainability";
import {PresentationRenderer} from "./features/narration/PresentationRenderer";
import type {AdvisoryResponse, CaseDetailResponse, CaseReplayTraceResponse, DecisionBriefResponse, DecisionCockpitResponse, DecisionPacket, EvaluationResponse, FabCase, MeasurementPoint, NarrationIntent, NarrationStatusResponse, OverviewResponse, ReplayResponse} from "./types";

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

function boundedPercent(value: number) {
  return Math.max(0, Math.min(100, value));
}

function smoothSvgPath(points: Array<{x: number; y: number}>) {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  return points.slice(1).reduce((path, point, index) => {
    const previous = points[index];
    const midpoint = (previous.x + point.x) / 2;
    return `${path} C ${midpoint} ${previous.y}, ${midpoint} ${point.y}, ${point.x} ${point.y}`;
  }, `M ${points[0].x} ${points[0].y}`);
}

function YieldHealthRing({yieldValue}: {yieldValue: number | null}) {
  const percent = boundedPercent((yieldValue ?? 0) * 100);
  const circumference = 2 * Math.PI * 42;
  const offset = circumference * (1 - percent / 100);
  return <div className="yield-health-ring" aria-label={yieldValue == null ? "Yield unavailable" : `Yield ${percent.toFixed(1)} percent`}>
    <svg viewBox="0 0 108 108" role="img">
      <circle cx="54" cy="54" r="42" className="yield-health-ring__track" />
      <circle cx="54" cy="54" r="42" className="yield-health-ring__value" strokeDasharray={circumference} strokeDashoffset={offset} />
    </svg>
    <div><strong>{yieldValue == null ? "—" : `${percent.toFixed(1)}%`}</strong><span>synthetic yield</span></div>
  </div>;
}

function SignalTrendChart({points, sensor, step}: {points: MeasurementPoint[]; sensor: string; step: string}) {
  const sensorGroups = Array.from(new Set(points.map((point) => point.sensor_name)))
    .filter((name) => sensor === "all" || name === sensor)
    .slice(0, 3)
    .map((name) => ({name, points: points.filter((point) => point.sensor_name === name)}));

  return <div className="signal-chart signal-chart--trend">
    <div className="signal-chart__title">
      <div><span>Normalized signal trend</span><strong>{sensor === "all" ? "Multi-sensor overlay" : sensor.replaceAll("_", " ")}</strong></div>
      <div className="signal-legend">{sensorGroups.map((group, index) => <span key={group.name}><i className={`signal-swatch signal-swatch--${index}`} />{group.name}</span>)}</div>
    </div>
    <svg viewBox="0 0 640 250" role="img" aria-label={`${step} normalized measurement series`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="signalAreaGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.28" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[54, 98, 142, 186].map((y) => <line key={y} x1="42" y1={y} x2="620" y2={y} className="signal-grid-line" />)}
      {sensorGroups.map((group, groupIndex) => {
        const values = group.points.map((point) => point.value);
        const min = Math.min(...values);
        const max = Math.max(...values);
        const span = Math.max(0.0001, max - min);
        const svgPoints = group.points.map((point, index) => ({
          x: group.points.length === 1 ? 330 : 42 + index * (578 / (group.points.length - 1)),
          y: 204 - ((point.value - min) / span) * 158,
        }));
        const path = smoothSvgPath(svgPoints);
        const areaPath = groupIndex === 0 && svgPoints.length > 1 ? `${path} L ${svgPoints.at(-1)?.x ?? 620} 218 L ${svgPoints[0].x} 218 Z` : "";
        return <g key={group.name} className={`signal-series signal-series--${groupIndex}`}>
          {areaPath ? <path d={areaPath} className="signal-area" /> : null}
          <path d={path} className="signal-path" />
          {svgPoints.map((point, index) => <circle key={`${point.x}-${point.y}-${index}`} cx={point.x} cy={point.y} r="4" className="signal-point"><title>{`${group.points[index].sensor_name}: ${group.points[index].value.toFixed(3)} ${group.points[index].unit}`}</title></circle>)}
        </g>;
      })}
    </svg>
    <div className="signal-chart__footer"><span>earliest evidence</span><span>{points.length} measurements</span><span>latest evidence</span></div>
  </div>;
}

function SignalHistogram({points, sensor}: {points: MeasurementPoint[]; sensor: string}) {
  const selected = points.filter((point) => sensor === "all" || point.sensor_name === sensor);
  if (!selected.length) return <WorkbenchState kind="empty" title="No distribution" detail="No measurements match this sensor filter." />;
  const values = selected.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(0.0001, max - min);
  const bucketCount = Math.min(8, Math.max(4, Math.ceil(Math.sqrt(values.length))));
  const buckets = Array.from({length: bucketCount}, () => 0);
  for (const value of values) {
    const index = Math.min(bucketCount - 1, Math.floor(((value - min) / span) * bucketCount));
    buckets[index] += 1;
  }
  const maxCount = Math.max(...buckets, 1);
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  return <div className="signal-chart signal-chart--histogram">
    <div className="signal-chart__title"><div><span>Distribution</span><strong>Signal density</strong></div><b>μ {mean.toFixed(2)}</b></div>
    <div className="histogram-bars" aria-label="Signal distribution histogram">{buckets.map((count, index) => <div key={index} className="histogram-column"><span style={{height: `${Math.max(8, (count / maxCount) * 100)}%`}}><i>{count}</i></span></div>)}</div>
    <div className="signal-chart__footer"><span>{min.toFixed(2)}</span><span>{values.length} values</span><span>{max.toFixed(2)}</span></div>
  </div>;
}

function ChamberHeatmap({points}: {points: MeasurementPoint[]}) {
  const chambers = Array.from(new Set(points.map((point) => point.chamber_id))).map((chamber) => {
    const chamberPoints = points.filter((point) => point.chamber_id === chamber);
    const average = chamberPoints.reduce((sum, point) => sum + Math.abs(point.value), 0) / Math.max(1, chamberPoints.length);
    return {chamber, count: chamberPoints.length, average};
  });
  const maxAverage = Math.max(...chambers.map((item) => item.average), 1);
  return <div className="signal-chart signal-chart--heatmap">
    <div className="signal-chart__title"><div><span>Chamber map</span><strong>Relative signal intensity</strong></div><b>{chambers.length} nodes</b></div>
    <div className="chamber-heatmap" aria-label="Chamber relative signal intensity">{chambers.map((item) => <div key={item.chamber} className="chamber-heatmap__cell" style={{"--heat": `${Math.max(.14, item.average / maxAverage)}`} as React.CSSProperties}>
      <span>{item.chamber}</span><strong>{item.average.toFixed(2)}</strong><small>{item.count} events</small>
    </div>)}</div>
    <p>Intensity is normalized within this case view; it is not an equipment-health score.</p>
  </div>;
}

function SignalKpis({points}: {points: MeasurementPoint[]}) {
  if (!points.length) return null;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  return <div className="signal-kpis">
    <div><span>Mean</span><strong>{mean.toFixed(2)}</strong></div>
    <div><span>Range</span><strong>{(max - min).toFixed(2)}</strong></div>
    <div><span>σ</span><strong>{Math.sqrt(variance).toFixed(2)}</strong></div>
    <div><span>Events</span><strong>{points.length}</strong></div>
  </div>;
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
  const classificationTotal = Math.max(1, overview.metrics.physical_excursions + overview.metrics.sensor_bias_cases + overview.metrics.data_quality_cases);
  const averageYield = overview.cases.filter((item) => item.mean_yield != null).reduce((sum, item) => sum + (item.mean_yield ?? 0), 0) / Math.max(1, overview.cases.filter((item) => item.mean_yield != null).length);
  const maxAnomaly = Math.max(...overview.cases.map((item) => item.anomaly_score), 1);
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
    <section className="overview-visual-grid">
      <article className="glass-visual-card glass-visual-card--yield">
        <div className="visual-card-head"><div><span className="eyebrow">Portfolio pulse</span><strong>Yield health</strong></div><small>synthetic case mean</small></div>
        <YieldHealthRing yieldValue={averageYield || null} />
        <div className="visual-card-foot"><span>{overview.cases.length} cases in view</span><b>{overview.projection.stale ? "projection delayed" : "projection fresh"}</b></div>
      </article>
      <article className="glass-visual-card glass-visual-card--mix">
        <div className="visual-card-head"><div><span className="eyebrow">Case mix</span><strong>Classification distribution</strong></div><small>read-only</small></div>
        <div className="classification-stack" aria-label="Case classification distribution">
          <span className="classification-stack__physical" style={{width: `${(overview.metrics.physical_excursions / classificationTotal) * 100}%`}} />
          <span className="classification-stack__bias" style={{width: `${(overview.metrics.sensor_bias_cases / classificationTotal) * 100}%`}} />
          <span className="classification-stack__quality" style={{width: `${(overview.metrics.data_quality_cases / classificationTotal) * 100}%`}} />
        </div>
        <div className="classification-legend">
          <div><i className="classification-dot classification-dot--physical" /><span>Physical</span><strong>{overview.metrics.physical_excursions}</strong></div>
          <div><i className="classification-dot classification-dot--bias" /><span>Sensor bias</span><strong>{overview.metrics.sensor_bias_cases}</strong></div>
          <div><i className="classification-dot classification-dot--quality" /><span>Data quality</span><strong>{overview.metrics.data_quality_cases}</strong></div>
        </div>
      </article>
      <article className="glass-visual-card glass-visual-card--anomaly">
        <div className="visual-card-head"><div><span className="eyebrow">Signal pressure</span><strong>Anomaly ranking</strong></div><small>top cases</small></div>
        <div className="anomaly-bars">{[...overview.cases].sort((a, b) => b.anomaly_score - a.anomaly_score).slice(0, 5).map((item) => <button key={item.case_id} onClick={() => onSelectCase(item.case_id)}>
          <span>{item.lot_id}</span><i><b style={{width: `${Math.max(6, (item.anomaly_score / maxAnomaly) * 100)}%`}} /></i><strong>{item.anomaly_score.toFixed(2)}</strong>
        </button>)}</div>
      </article>
    </section>
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
    <RcaExplainability candidates={detail.rca.candidates} />
    <section className="panel advisory-strip advisory-strip--decision">
      <div><span className="eyebrow">Evidence-grounded next step</span><h2>{advisory?.result.status === "ready" ? "Ready for human review" : advisory?.result.status ?? "loading"}</h2></div>
      <p>{advisory?.result.recommended_next_step ?? "Resolving evidence-grounded recommendation…"}</p>
      <span className="advisory-authority">Deterministic advisory · no state mutation</span>
    </section>
  </div>;
}

export function EvidenceGraph({detail, selectedStep, onSelectStep}: {detail: CaseDetailResponse; selectedStep: string | null; onSelectStep: (step: string) => void}) {
  const step = selectedStep ?? detail.trace.process_path[0]?.step_id ?? "LITHO";
  const filtered = detail.evidence_series.measurements.filter((item) => item.step_id === step);
  const sensorOptions = Array.from(new Set(filtered.map((item) => item.sensor_name)));
  const [sensorFilter, setSensorFilter] = useState("all");
  const activeSensor = sensorFilter === "all" || sensorOptions.includes(sensorFilter) ? sensorFilter : "all";
  const selectedSignals = filtered.filter((item) => activeSensor === "all" || item.sensor_name === activeSensor);
  const latestMeasurement = [...selectedSignals].sort((a, b) => b.event_time.localeCompare(a.event_time))[0];
  return <div className="screen-stack">
    <section className="signal-console-hero">
      <div><span className="eyebrow">Evidence console · read-only explorer</span><h1>{detail.case.lot_id} lineage · signal workspace</h1><p>Correlate process lineage, sensor shape, chamber intensity, and event-level evidence without changing case state or equipment.</p></div>
      <div className="console-live-status"><span className="console-live-dot" /><div><strong>{detail.trace.projection.stale ? "DEGRADED" : "LIVE SNAPSHOT"}</strong><small>{detail.trace.projection.lag_events} projection lag · {filtered.length} measurements</small></div></div>
    </section>
    <section className="console-toolbar" aria-label="Signal console controls">
      <div className="console-toolbar__scope"><span>STEP</span><strong>{step}</strong><i>/</i><span>SENSOR</span></div>
      <div className="console-filter-group">
        <button className={activeSensor === "all" ? "is-active" : ""} onClick={() => setSensorFilter("all")}>All signals</button>
        {sensorOptions.map((sensor) => <button className={activeSensor === sensor ? "is-active" : ""} key={sensor} onClick={() => setSensorFilter(sensor)}>{sensor.replaceAll("_", " ")}</button>)}
      </div>
      <div className="console-toolbar__readout"><span>Latest</span><strong>{latestMeasurement ? latestMeasurement.value.toFixed(3) : "—"}</strong><small>{latestMeasurement?.unit ?? "no signal"}</small></div>
    </section>
    <section className="panel graph-workspace graph-workspace--console">
      <header><div><span className="eyebrow">Process lineage</span><h2>Lot → run → chamber → evidence</h2></div><div className="graph-header-meta"><ProjectionBadge projection={detail.trace.projection} /><small>Select a step to coordinate every lens.</small></div></header>
      <EvidenceGraphExplorer detail={detail} onSelectStep={onSelectStep} />
      <div className="lineage-row" aria-label="Process lineage">{detail.trace.process_path.map((item, index) => <div className="lineage-fragment" key={item.process_run_id}>
        <button className={item.step_id === step ? "lineage-node is-selected" : "lineage-node"} aria-pressed={item.step_id === step} onClick={() => onSelectStep(item.step_id)}>
          <span>{item.step_id}</span><strong>{item.chamber_id ?? "no chamber"}</strong><small>{item.equipment_id ?? "—"}</small>
        </button>{index < detail.trace.process_path.length - 1 ? <span className="lineage-arrow" aria-hidden="true">→</span> : null}
      </div>)}</div>
      <div className="signal-console-grid">
        <div className="signal-console-grid__trend"><SignalTrendChart points={filtered} sensor={activeSensor} step={step} /></div>
        <SignalHistogram points={filtered} sensor={activeSensor} />
        <ChamberHeatmap points={selectedSignals} />
      </div>
      <SignalKpis points={selectedSignals} />
      <div className="console-ledger-head"><div><span className="eyebrow">Raw evidence ledger</span><strong>Selected signal events</strong></div><small>Values below are source-linked synthetic evidence.</small></div>
      <div className="table-scroll console-table"><table>
        <thead><tr><th>Sensor</th><th>Value</th><th>Chamber</th><th>Event time</th><th>Event</th></tr></thead>
        <tbody>{selectedSignals.map((item) => <tr key={item.event_id}><td><span className="sensor-ledger-name"><i />{item.sensor_name}</span></td><td>{item.value.toFixed(3)}</td><td>{item.chamber_id}</td><td>{item.event_time}</td><td><code>{item.event_id.slice(0, 12)}…</code></td></tr>)}</tbody>
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
    {packet ? <DecisionBoundaryPanel packet={packet} /> : null}
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
        {brief.brief.presentation ? <PresentationRenderer spec={brief.brief.presentation} /> : null}
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
  const console = evaluation.validation_console;
  const comparison = console?.common_random_number_comparison;
  return <div className="screen-stack">
    <section className="surface-header"><div><span className="eyebrow">Evaluation Lab 2.0</span><h1>Checked-in release evidence</h1><p>Inspect held-out slices, seed stability, release gates and known failures without rewriting historical evidence.</p></div><ProvenanceBadge kind="evaluation" /></section>
    <MetricStrip items={[
      {label: "Fault recall", value: `${((detector.fault_recall ?? 0) * 100).toFixed(0)}%`, detail: "synthetic test profile"},
      {label: "False alarms/day", value: detector.false_alarms_per_simulated_day ?? "—"},
      {label: "RCA Top-1", value: `${((rca.top1_accuracy ?? 0) * 100).toFixed(0)}%`, detail: evaluation.versions.projection},
      {label: "Tool selection", value: `${((agent.tool_selection_accuracy ?? 0) * 100).toFixed(0)}%`, detail: evaluation.versions.agent},
      {label: "Contradict coverage", value: `${((rca.contradicting_evidence_coverage ?? 0) * 100).toFixed(1)}%`, detail: "known negative preserved"},
    ]} />
    {console ? <>
      <section className="evaluation-grid">
        <article className="panel evaluation-slices">
          <header><div><span className="eyebrow">Fault-family slices</span><h2>Held-out F1–F6 performance</h2></div><small>{console.held_out_seed_metrics.length} held-out seeds</small></header>
          <div className="evaluation-family-grid">{console.fault_family_slices.map((slice) => <div key={slice.family}>
            <span>{slice.family}</span><strong>{(slice.rca_top1 * 100).toFixed(0)}%</strong><small>RCA Top-1</small><b>{slice.mean_case_count.toFixed(1)} cases/seed</b><i>agent ready {(slice.agent_ready_rate * 100).toFixed(0)}%</i>
          </div>)}</div>
        </article>
        <article className="panel evaluation-baseline">
          <header><div><span className="eyebrow">Common-random-number baseline</span><h2>Current vs retained weaker detector</h2></div></header>
          <div className="baseline-comparison">
            <div><span>Current</span><strong>{comparison?.current_detector ? `${(comparison.current_detector.fault_recall * 100).toFixed(1)}%` : "—"}</strong><small>{comparison?.current_detector?.version ?? "not recorded"}</small></div>
            <div className="is-legacy"><span>Legacy baseline</span><strong>{comparison?.legacy_detector ? `${(comparison.legacy_detector.fault_recall * 100).toFixed(1)}%` : "—"}</strong><small>{comparison?.legacy_detector?.version ?? "not recorded"}</small></div>
          </div>
          <p>Same held-out random streams: {(comparison?.seeds ?? []).join(" · ") || "not recorded"}. The weaker baseline remains visible by design.</p>
        </article>
      </section>
      <section className="panel evaluation-seeds">
        <header><div><span className="eyebrow">Seed stability</span><h2>Held-out metric rows</h2></div><small>min/max shown below are seed ranges, not confidence intervals</small></header>
        <div className="table-scroll"><table><thead><tr><th>Seed</th><th>Fault recall</th><th>False alarms/day</th><th>RCA Top-1</th><th>RCA Top-3</th><th>Contradict coverage</th></tr></thead><tbody>{console.held_out_seed_metrics.map((row) => <tr key={row.seed}><td>{row.seed}</td><td>{(row.fault_recall * 100).toFixed(1)}%</td><td>{row.false_alarms_per_simulated_day.toFixed(2)}</td><td>{(row.rca_top1 * 100).toFixed(1)}%</td><td>{(row.rca_top3 * 100).toFixed(1)}%</td><td className="evaluation-negative-cell">{(row.contradicting_evidence_coverage * 100).toFixed(2)}%</td></tr>)}</tbody></table></div>
        <div className="seed-range-strip">{Object.entries(console.seed_ranges).map(([key, range]) => range ? <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{range.mean.toFixed(5)}</strong><small>{range.minimum.toFixed(5)} → {range.maximum.toFixed(5)}</small></div> : null)}</div>
      </section>
      <section className="evaluation-grid evaluation-grid--lower">
        <article className="panel evaluation-gates">
          <header><div><span className="eyebrow">Release gates</span><h2>{evaluation.release_passed ? "Historical gate passed" : "Historical gate not passed"}</h2></div></header>
          <div className="evaluation-gate-list">{(evaluation.release_gate ?? []).map((gate) => <div key={gate.threshold} className={gate.passed ? "is-pass" : "is-fail"}><span>{gate.passed ? "PASS" : "FAIL"}</span><strong>{gate.threshold.replaceAll("_", " ")}</strong><small>{gate.actual} {gate.operator} {gate.required}</small></div>)}</div>
        </article>
        <article className="panel evaluation-unseen">
          <header><div><span className="eyebrow">Unseen evidence gap</span><h2>Safe abstention U1</h2></div></header>
          <div className="evaluation-unseen-list">{console.unseen_family_results.map((item, index) => <div key={`${item.family}-${index}`}><span>{item.family}</span><strong>{item.actual_status.toUpperCase()}</strong><small>{item.appropriate ? "appropriate" : "review"} · {item.claim_count} claims · physical action {item.physical_action_proposed ? "proposed" : "none"}</small></div>)}</div>
        </article>
      </section>
      <section className="panel evaluation-gaps">
        <header><div><span className="eyebrow">Evidence schema gaps</span><h2>What this release evidence cannot prove</h2></div></header>
        <ul>{console.evidence_gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
      </section>
    </> : null}
    <section className="panel">
      <header><div><span className="eyebrow">Version registry</span><h2>Evidence contract</h2></div></header>
      <div className="version-grid">{Object.entries(evaluation.versions).map(([key, value]) => <div key={key}><span>{key}</span><strong>{value}</strong></div>)}</div>
      <h3>Limitations</h3>
      <ul>{evaluation.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      {evaluation.negative_results?.length ? <><h3>Negative results — preserved</h3><ul className="negative-result-list">{evaluation.negative_results.map((item) => <li key={item.id}><strong>{item.id}</strong><span>{item.description}</span></li>)}</ul></> : null}
      {evaluation.evidence_hash ? <p className="muted">Evidence hash: <code>{evaluation.evidence_hash}</code></p> : null}
    </section>
  </div>;
}

export function ReplayOperations({replay, trace = null}: {replay: ReplayResponse; trace?: CaseReplayTraceResponse | null}) {
  const integration = replay.integration;
  const [replayIndex, setReplayIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const replayItem = trace?.timeline[Math.min(replayIndex, Math.max(0, trace.timeline.length - 1))] ?? null;
  useEffect(() => {
    setReplayIndex(0);
    setPlaying(false);
  }, [trace?.case_id]);
  useEffect(() => {
    if (!playing || !trace?.timeline.length) return;
    const timer = window.setInterval(() => {
      setReplayIndex((current) => {
        if (current >= trace.timeline.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 700);
    return () => window.clearInterval(timer);
  }, [playing, trace?.timeline.length]);
  const integrationState = integration.container_integration_verified
    ? {kind: "ok" as const, title: "Container integration verified", detail: "M6 evidence verifies PostgreSQL, Redpanda and Neo4j runtime integration. This is verification state, not a claim that Docker is currently running."}
    : integration.status === "degraded"
      ? {kind: "degraded" as const, title: "Container integration degraded", detail: integration.reason ?? "One or more configured integration dependencies are unavailable."}
      : {kind: "degraded" as const, title: "Container integration unverified", detail: integration.reason ?? "No successful container-backed verification evidence is available yet."};
  return <div className="screen-stack">
    <section className="surface-header"><div><span className="eyebrow">Replay & decision trace</span><h1>Deterministic pipeline state</h1><p>Replay source events, workflow audit order and the current rebuildable RCA snapshot without inventing missing timestamps.</p></div><ProjectionBadge projection={replay.projection} /></section>
    <MetricStrip items={[
      {label: "Event log", value: replay.event_count},
      {label: "Detection checkpoint", value: replay.detection_checkpoint},
      {label: "Projection checkpoint", value: replay.projection.projection_checkpoint},
      {label: "Outbox", value: replay.outbox_count},
      {label: "Quarantine", value: replay.quarantine_count},
    ]} />
    {trace ? <section className="panel replay-trace-panel">
      <header><div><span className="eyebrow">Case replay · {trace.lot_id}</span><h2>Event-backed decision trace</h2></div><div className="replay-trace-authority"><span>{trace.source_of_truth}</span><strong>{trace.projection_role}</strong></div></header>
      <div className="replay-controls">
        <button type="button" disabled={replayIndex === 0} onClick={() => setReplayIndex((current) => Math.max(0, current - 1))}>Previous</button>
        <button type="button" aria-pressed={playing} disabled={!trace.timeline.length} onClick={() => setPlaying((current) => !current)}>{playing ? "Pause" : "Play"}</button>
        <input aria-label="Replay scrubber" type="range" min="0" max={Math.max(0, trace.timeline.length - 1)} value={Math.min(replayIndex, Math.max(0, trace.timeline.length - 1))} onChange={(event) => {setPlaying(false); setReplayIndex(Number(event.target.value));}} />
        <span>{trace.timeline.length ? replayIndex + 1 : 0} / {trace.timeline.length}</span>
        <button type="button" disabled={replayIndex >= trace.timeline.length - 1} onClick={() => setReplayIndex((current) => Math.min(trace.timeline.length - 1, current + 1))}>Next</button>
      </div>
      <div className="replay-trace-layout">
        <ol className="replay-event-strip" aria-label="Case replay event timeline">{trace.timeline.map((item, index) => <li key={item.timeline_id} className={`${index === replayIndex ? "is-current" : ""} replay-event-strip__${item.kind}`}>
          <button type="button" onClick={() => {setPlaying(false); setReplayIndex(index);}} aria-current={index === replayIndex ? "step" : undefined}>
            <span>{item.phase.replaceAll("_", " ")}</span><strong>{item.event_type.replaceAll(".v1", "")}</strong><small>{item.event_time ? item.event_time.slice(11, 19) : `#${item.sequence} order`}</small>
          </button>
        </li>)}</ol>
        <article className="replay-event-inspector">
          {replayItem ? <>
            <div className="replay-event-inspector__title"><span>{replayItem.kind.replaceAll("_", " ")}</span><h3>{replayItem.event_type}</h3><small>{replayItem.event_time ?? "No persisted wall-clock timestamp"}</small></div>
            <dl>
              <div><dt>Phase</dt><dd>{replayItem.phase}</dd></div>
              <div><dt>Source</dt><dd>{replayItem.source}</dd></div>
              <div><dt>Time semantics</dt><dd>{replayItem.time_semantics.replaceAll("_", " ")}</dd></div>
              <div><dt>Delivery</dt><dd>{replayItem.delivery_status ?? "not applicable"}</dd></div>
              <div><dt>Event ID</dt><dd>{replayItem.event_id ?? "not an authoritative source event"}</dd></div>
            </dl>
            <div className="replay-payload"><span>Recorded payload</span><pre>{JSON.stringify(replayItem.payload, null, 2)}</pre></div>
          </> : <p>No replay item is available for the selected case.</p>}
        </article>
      </div>
      <div className="replay-summary-strip"><div><span>Source events</span><strong>{trace.summary.source_event_count}</strong></div><div><span>Audit events</span><strong>{trace.summary.audit_event_count}</strong></div><div><span>Out-of-order</span><strong>{trace.summary.out_of_order_count}</strong></div><div><span>Late</span><strong>{trace.summary.late_count}</strong></div></div>
      <footer className="replay-limitations"><strong>Replay semantics</strong><ul>{trace.limitations.map((item) => <li key={item}>{item}</li>)}</ul></footer>
    </section> : null}
    <section className="panel release-identity-panel">
      <header><div><span className="eyebrow">Release identity</span><h2>Portfolio release {replay.release.release_version}</h2></div></header>
      <dl className="property-list release-identity-list">
        <div><dt>Canonical hash</dt><dd><code>{replay.release.release_hash}</code></dd></div>
        <div><dt>Source commit</dt><dd>{replay.release.source_git_commit?.slice(0, 12) ?? "pending manifest"}</dd></div>
        <div><dt>Manifest</dt><dd>{replay.release.manifest_available ? "generated" : "pending"}</dd></div>
      </dl>
    </section>
    <div className="two-column system-health-grid">
      <section className="panel health-card"><header><div><span className="eyebrow">Delivery behavior</span><h2>Accepted event status</h2></div></header>
        <div className="health-stat-list">{Object.entries(replay.delivery_status_counts).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{value}</strong><i aria-hidden="true" /></div>)}</div>
      </section>
      <section className="panel health-card"><header><div><span className="eyebrow">External adapters</span><h2>Verification status</h2></div></header>
        <div className="adapter-status-list">{Object.entries(replay.external_services).map(([key, value]) => <div key={key}><div><span className="adapter-dot" aria-hidden="true" /><strong>{key.replaceAll("_", " ")}</strong></div><span className="adapter-state">{String(value)}</span></div>)}</div>
        <WorkbenchState {...integrationState} />
      </section>
    </div>
  </div>;
}

export function caseById(cases: FabCase[], caseId: string | null): FabCase | null {
  return cases.find((item) => item.case_id === caseId) ?? cases[0] ?? null;
}

