import {useEffect, useMemo, useState} from "react";
import {ClassificationBadge, MetricStrip, ProjectionBadge, ProvenanceBadge, WorkbenchState} from "./components";
import {EvidenceDiff} from "./features/evidence/EvidenceDiff";
import {EvidenceGraphExplorer} from "./features/evidence/EvidenceGraphExplorer";
import type {EvidenceGraphNode} from "./features/evidence/evidenceGraphModel";
import {DecisionBoundaryPanel, RcaExplainability} from "./features/explainability/RcaExplainability";
import {AuthorityChain} from "./features/governance/AuthorityChain";
import {WaferInspectionContext} from "./features/inspection/WaferInspectionContext";
import {PresentationRenderer} from "./features/narration/PresentationRenderer";
import {DecisionProvenanceGraph} from "./features/provenance/DecisionProvenanceGraph";
import type {AdvisoryResponse, CaseDetailResponse, CaseReplayTraceResponse, ContinuousIntelligenceStatus, DecisionBriefResponse, DecisionCockpitResponse, DecisionPacket, EvaluationResponse, FabCase, LiveStatusResponse, MeasurementPoint, NarrationIntent, NarrationStatusResponse, OverviewResponse, ProjectionStatus, ReplayResponse} from "./types";

function priorityClass(band: string) {
  if (band === "HIGH") return "decision-priority is-high";
  if (band === "VERIFY_DATA") return "decision-priority is-verify";
  return "decision-priority is-medium";
}

function AdaptiveIntelligenceVisualization({intelligence, liveStatus, caseId, detail}: {intelligence: ContinuousIntelligenceStatus | null; liveStatus: LiveStatusResponse | null; caseId?: string; detail?: CaseDetailResponse | null}) {
  const plan = caseId ? intelligence?.visualization_plans.find((item) => item.case_id === caseId) : intelligence?.visualization_plans[0];
  if (!plan) return <div className="adaptive-intelligence-viz is-empty"><strong>Visualization planner warming up</strong><p>A renderer is selected after the first material intelligence change.</p></div>;
  if (caseId && plan.case_id !== caseId) return <div className="adaptive-intelligence-viz is-empty"><strong>Case-bound visualization unavailable</strong><p>The planner result does not match the selected case, so the UI refused to render it.</p></div>;
  const type = plan.primary.type;
  const learned = (intelligence?.latest_predictions ?? []).filter((item) => !plan.lot_id || item.lot_id === plan.lot_id).slice(0, 8);
  const caseMeasurements = detail?.case.case_id === plan.case_id ? detail.evidence_series.measurements : [];
  const latestMeasurement = caseMeasurements.at(-1);
  const caseSeries = latestMeasurement ? caseMeasurements.filter((item) => item.sensor_name === latestMeasurement.sensor_name && item.chamber_id === latestMeasurement.chamber_id).slice(-8) : [];
  const sensor = !caseId ? liveStatus?.prediction.top_sensor_forecasts[0] : null;
  if (type === "timeseries" && (caseSeries.length || sensor)) {
    const values = caseSeries.length ? caseSeries.map((item) => item.value) : [sensor!.last_value, ...sensor!.forecast_next];
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const span = Math.max(.001, maximum - minimum);
    const step = values.length > 1 ? 280 / (values.length - 1) : 0;
    const points = values.map((value, index) => `${20 + index * step},${104 - ((value - minimum) / span) * 74}`).join(" ");
    const seriesLabel = caseSeries.length ? `${latestMeasurement!.chamber_id} · ${latestMeasurement!.sensor_name}` : `${sensor!.chamber_id} · ${sensor!.sensor_name}`;
    return <div className="adaptive-intelligence-viz"><header><span>{plan.primary.title}</span><strong>{seriesLabel}</strong></header>{plan.decision_question ? <p className="adaptive-viz-question">{plan.decision_question}</p> : null}<svg viewBox="0 0 320 125" role="img" aria-label="Case-bound adaptive evidence trajectory"><polyline points={points} className="adaptive-viz-line" />{values.map((value, index) => <circle key={index} cx={20 + index * step} cy={104 - ((value - minimum) / span) * 74} r="4"><title>{value.toFixed(3)}</title></circle>)}</svg><footer><span>{caseSeries.length ? "case evidence" : "observed"}</span><span>{plan.case_id}</span><span>{plan.lot_id ?? ""}</span></footer></div>;
  }
  if (type === "heatmap") {
    const chamberRows = caseMeasurements.length ? caseMeasurements.slice(-12).map((item) => ({chamber_id: item.chamber_id, sensor_name: item.sensor_name, risk_score: Math.min(1, Math.abs(item.value) / 30)})) : liveStatus?.prediction.top_sensor_forecasts.slice(0, 8) ?? [];
    return <div className="adaptive-intelligence-viz"><header><span>{plan.primary.title}</span><strong>{caseId ? "case-bound chamber evidence" : "dynamic chamber intensity"}</strong></header>{plan.decision_question ? <p className="adaptive-viz-question">{plan.decision_question}</p> : null}<div className="adaptive-viz-heatmap">{chamberRows.map((item, index) => <div key={`${item.chamber_id}:${item.sensor_name}:${index}`} style={{"--adaptive-risk": Math.max(.08, item.risk_score)} as React.CSSProperties}><span>{item.chamber_id}</span><strong>{item.sensor_name}</strong><small>{caseId ? "selected case" : `${(item.risk_score * 100).toFixed(0)} risk`}</small></div>)}</div></div>;
  }
  if (type === "timeline") {
    return <div className="adaptive-intelligence-viz"><header><span>{plan.primary.title}</span><strong>material intelligence sequence</strong></header>{plan.decision_question ? <p className="adaptive-viz-question">{plan.decision_question}</p> : null}<ol className="adaptive-viz-timeline">{learned.slice(0, 6).map((item) => <li key={`${item.model_name}:${item.generated_at}`}><time>{item.source_event_time}</time><strong>{item.target.replaceAll("_", " ")}</strong><span>{(item.score * 100).toFixed(1)} · {item.lot_id}</span></li>)}</ol></div>;
  }
  return <div className="adaptive-intelligence-viz"><header><span>{plan.primary.title}</span><strong>{type} comparison</strong></header><div className="adaptive-viz-bars">{learned.slice(0, 6).map((item) => <div key={`${item.model_name}:${item.target}`}><span>{item.target.replaceAll("_", " ")}</span><i><b style={{width: `${Math.max(4, Math.min(100, item.score * 100))}%`}} /></i><strong>{(item.score * 100).toFixed(0)}</strong></div>)}</div></div>;
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

function classificationInterpretation(classification: string) {
  if (classification === "physical_excursion") return {label: "PHYSICAL PROCESS EXCURSION", detail: "Process evidence supports a physical excursion path; containment still requires human authority."};
  if (classification === "data_quality_incident") return {label: "DATA QUALITY INCIDENT", detail: "Treat as a data-path problem. Do not infer physical fab impact from this classification."};
  if (classification === "sensor_bias_suspected") return {label: "SENSOR BIAS SUSPECTED", detail: "Validate sensing / calibration evidence before interpreting the signal as a physical excursion."};
  return {label: classification.replaceAll("_", " ").toUpperCase(), detail: "Classification is shown exactly as returned by the deterministic case engine."};
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
  return <div className="yield-health-meter" aria-label={yieldValue == null ? "Yield unavailable" : `Yield ${percent.toFixed(1)} percent`}>
    <div className="yield-health-ring">
      <svg viewBox="0 0 108 108" role="img" aria-hidden="true">
        <circle cx="54" cy="54" r="42" className="yield-health-ring__track" />
        <circle cx="54" cy="54" r="42" className="yield-health-ring__value" strokeDasharray={circumference} strokeDashoffset={offset} />
      </svg>
      <strong>{yieldValue == null ? "—" : `${percent.toFixed(1)}%`}</strong>
    </div>
    <span className="yield-health-ring__caption">synthetic yield</span>
  </div>;
}

function buildSensorSeries(points: MeasurementPoint[], sensor: string, steps: string[]) {
  const orderedPoints = [...points].sort((a, b) => a.event_time.localeCompare(b.event_time) || a.sensor_name.localeCompare(b.sensor_name));
  const sensorNames = Array.from(new Set(orderedPoints.map((point) => point.sensor_name))).filter((name) => sensor === "all" || name === sensor);
  return sensorNames.map((name) => {
    const sensorPoints = orderedPoints.filter((point) => point.sensor_name === name);
    const values = sensorPoints.map((point) => point.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min;
    const mean = values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length);
    const normalize = (value: number) => span < 0.000001 ? 50 : boundedPercent(((value - min) / span) * 100);
    const seriesPoints = steps.flatMap((step, stepIndex) => {
      const stepPoints = sensorPoints.filter((point) => point.step_id === step);
      if (!stepPoints.length) return [];
      const value = stepPoints.reduce((sum, point) => sum + point.value, 0) / stepPoints.length;
      return [{step, stepIndex, value, normalized: normalize(value), unit: stepPoints[0].unit, count: stepPoints.length}];
    });
    return {name, min, max, mean, meanNormalized: normalize(mean), points: seriesPoints};
  });
}

function SignalTrendChart({points, sensor, step, steps}: {points: MeasurementPoint[]; sensor: string; step: string; steps: string[]}) {
  const sensorGroups = buildSensorSeries(points, sensor, steps);
  const xStart = 24;
  const xEnd = 616;
  const yTop = 24;
  const yBottom = 188;
  const xForStep = (stepIndex: number) => steps.length <= 1 ? (xStart + xEnd) / 2 : xStart + stepIndex * ((xEnd - xStart) / (steps.length - 1));
  const selectedStepIndex = Math.max(0, steps.indexOf(step));
  const stepSpacing = steps.length <= 1 ? 120 : (xEnd - xStart) / (steps.length - 1);
  const selectedBandWidth = Math.min(92, stepSpacing * .62);
  const selectedBandX = Math.max(4, Math.min(636 - selectedBandWidth, xForStep(selectedStepIndex) - selectedBandWidth / 2));

  return <div className="signal-chart signal-chart--trend">
    <div className="signal-chart__title">
      <div><span>Case-normalized process trend</span><strong>{sensor === "all" ? "Sensor trajectory across process steps" : sensor.replaceAll("_", " ")}</strong></div>
      <div className="signal-legend">{sensorGroups.map((group, index) => <span key={group.name}><i className={`signal-swatch signal-swatch--${index}`} />{group.name.replaceAll("_", " ")}</span>)}</div>
    </div>
    <div className="signal-trend-canvas">
      <div className="signal-y-scale" aria-hidden="true"><span>100</span><span>50</span><span>0</span></div>
      <svg viewBox="0 0 640 212" role="img" aria-label={`${step} selected within case-normalized sensor trajectories`} preserveAspectRatio="none">
        <rect x={selectedBandX} y="10" width={selectedBandWidth} height="190" rx="8" className="signal-selected-band" />
        {[yTop, (yTop + yBottom) / 2, yBottom].map((y) => <line key={y} x1={xStart} y1={y} x2={xEnd} y2={y} className="signal-grid-line" />)}
        <line x1={xForStep(selectedStepIndex)} y1="10" x2={xForStep(selectedStepIndex)} y2="200" className="signal-selected-guide" />
        {sensorGroups.map((group, groupIndex) => {
          const svgPoints = group.points.map((point) => ({
            ...point,
            x: xForStep(point.stepIndex),
            y: yBottom - (point.normalized / 100) * (yBottom - yTop),
          }));
          const path = smoothSvgPath(svgPoints);
          return <g key={group.name} className={`signal-series signal-series--${groupIndex}`}>
            <path d={path} className="signal-path" />
            {svgPoints.map((point) => <circle key={`${group.name}-${point.step}`} cx={point.x} cy={point.y} r={point.step === step ? 5.5 : 4} className={point.step === step ? "signal-point is-selected" : "signal-point"}><title>{`${point.step} · ${group.name}: ${point.value.toFixed(3)} ${point.unit} · ${point.normalized.toFixed(0)}% of this sensor's observed case range`}</title></circle>)}
          </g>;
        })}
      </svg>
    </div>
    <div className="signal-step-axis" style={{"--step-count": `${Math.max(1, steps.length)}`} as React.CSSProperties}>{steps.map((item) => <span key={item} className={item === step ? "is-selected" : ""}>{item}</span>)}</div>
    <div className="signal-chart__footer"><span>0 = sensor low</span><span>Per-sensor min–max within this case · not a spec limit</span><span>100 = sensor high</span></div>
  </div>;
}

function SignalRangeProfile({points, sensor, step, steps}: {points: MeasurementPoint[]; sensor: string; step: string; steps: string[]}) {
  const sensorGroups = buildSensorSeries(points, sensor, steps);
  if (!sensorGroups.length) return <WorkbenchState kind="empty" title="No range context" detail="No measurements match this sensor filter." />;
  return <div className="signal-chart signal-chart--range-profile">
    <div className="signal-chart__title"><div><span>Selected-step context</span><strong>Within-case range position</strong></div><b>{step}</b></div>
    <div className="range-profile" aria-label={`${step} sensor positions within observed case ranges`}>{sensorGroups.map((group, index) => {
      const current = group.points.find((point) => point.step === step);
      return <div className={`range-profile__row range-profile__row--${index}`} key={group.name}>
        <div className="range-profile__head"><span>{group.name.replaceAll("_", " ")}</span>{current ? <strong>{current.value.toFixed(2)} <small>{current.unit}</small></strong> : <strong>no measurement</strong>}</div>
        <div className="range-profile__track" aria-label={current ? `${group.name} at ${current.normalized.toFixed(0)} percent of its observed case range` : `${group.name} has no measurement at ${step}`}>
          <i className="range-profile__mean" style={{left: `${group.meanNormalized}%`}} title={`Case mean ${group.mean.toFixed(2)}`} />
          {current ? <b className={`range-profile__marker signal-marker--${index}`} style={{left: `${current.normalized}%`}} title={`${current.normalized.toFixed(0)}% of observed range`} /> : null}
        </div>
        <div className="range-profile__scale"><span>{group.min.toFixed(2)}</span><span>{current ? `${current.normalized.toFixed(0)}% of span` : "no selected-step point"}</span><span>{group.max.toFixed(2)}</span></div>
      </div>;
    })}</div>
    <p className="range-profile__note">Dot = selected step · tick = case mean. Each sensor is compared only with its own observed values.</p>
  </div>;
}

function ChamberHeatmap({points, selectedChamber}: {points: MeasurementPoint[]; selectedChamber: string | null}) {
  if (!points.length) return <WorkbenchState kind="empty" title="No chamber context" detail="No measurements match this sensor filter." />;
  const sensorNames = Array.from(new Set(points.map((point) => point.sensor_name)));
  const sensorRanges = new Map(sensorNames.map((name) => {
    const values = points.filter((point) => point.sensor_name === name).map((point) => point.value);
    return [name, {min: Math.min(...values), max: Math.max(...values)}];
  }));
  const normalizedPoints = points.map((point) => {
    const range = sensorRanges.get(point.sensor_name)!;
    const span = range.max - range.min;
    return {...point, normalized: span < 0.000001 ? .5 : boundedPercent(((point.value - range.min) / span) * 100) / 100};
  });
  const chamberNames = Array.from(new Set([...normalizedPoints].sort((a, b) => a.event_time.localeCompare(b.event_time)).map((point) => point.chamber_id)));
  const chambers = chamberNames.map((chamber) => {
    const chamberPoints = normalizedPoints.filter((point) => point.chamber_id === chamber);
    const average = chamberPoints.reduce((sum, point) => sum + point.normalized, 0) / Math.max(1, chamberPoints.length);
    return {chamber, count: chamberPoints.length, average};
  });
  return <div className="signal-chart signal-chart--heatmap">
    <div className="signal-chart__title"><div><span>Process map</span><strong>Relative sensor level by chamber</strong></div><b>{chambers.length} observed</b></div>
    <div className="chamber-heatmap" aria-label="Case-normalized chamber signal levels">{chambers.map((item) => <div key={item.chamber} className={item.chamber === selectedChamber ? "chamber-heatmap__cell is-selected" : "chamber-heatmap__cell"} style={{"--heat": `${Math.max(.12, item.average)}`} as React.CSSProperties}>
      <span>{item.chamber}</span><strong>{Math.round(item.average * 100)}</strong><small>{item.count} signals{item.chamber === selectedChamber ? " · selected step" : ""}</small>
    </div>)}</div>
    <p>0–100 averages each sensor’s position inside its own observed case range; it is not an equipment-health score.</p>
  </div>;
}

function SignalKpis({casePoints, stepPoints, sensor, step}: {casePoints: MeasurementPoint[]; stepPoints: MeasurementPoint[]; sensor: string; step: string}) {
  if (sensor === "all") {
    const sensorCount = new Set(stepPoints.map((point) => point.sensor_name)).size;
    return <div className="signal-kpis">
      <div><span>Selected step</span><strong>{step}</strong></div>
      <div><span>Sensors here</span><strong>{sensorCount}</strong></div>
      <div><span>Step events</span><strong>{stepPoints.length}</strong></div>
      <div><span>Case samples</span><strong>{casePoints.length}</strong></div>
    </div>;
  }
  const sensorPoints = casePoints.filter((point) => point.sensor_name === sensor);
  if (!sensorPoints.length) return null;
  const values = sensorPoints.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  return <div className="signal-kpis">
    <div><span>Case mean</span><strong>{mean.toFixed(2)}</strong></div>
    <div><span>Case range</span><strong>{(max - min).toFixed(2)}</strong></div>
    <div><span>Case σ</span><strong>{Math.sqrt(variance).toFixed(2)}</strong></div>
    <div><span>Observations</span><strong>{sensorPoints.length}</strong></div>
  </div>;
}

export function DecisionCockpit({cockpit, detail, projection, sourceTimestamp, liveStatus, intelligence, manualBrief, analyzing, analysisFeedback, selectedCaseId, onAnalyzeNow, onOpenCase, onOpenDecision}: {
  cockpit: DecisionCockpitResponse;
  detail: CaseDetailResponse | null;
  projection: ProjectionStatus;
  sourceTimestamp: string;
  liveStatus: LiveStatusResponse | null;
  intelligence: ContinuousIntelligenceStatus | null;
  manualBrief: DecisionBriefResponse | null;
  analyzing: boolean;
  analysisFeedback: string | null;
  selectedCaseId: string | null;
  onAnalyzeNow: () => void;
  onOpenCase: (caseId: string) => void;
  onOpenDecision: (caseId: string) => void;
}) {
  const top = cockpit.queue.find((packet) => packet.case_id === selectedCaseId) ?? cockpit.queue[0];
  const topEvidence = top ? evidenceBalance(top) : null;
  const matchingDetail = top && detail?.case.case_id === top.case_id ? detail : null;
  const classification = top ? classificationInterpretation(top.classification) : null;
  const unresolved = top ? [
    ...(projection.stale ? [`Projection stale by ${projection.lag_events} events`] : []),
    ...top.evidence.data_quality_incidents.map((item) => `Data quality · ${item}`),
    ...(top.decision_boundary?.conditions.filter((condition) => condition.status !== "met").map((condition) => `${condition.status.toUpperCase()} · ${condition.label}`) ?? []),
    ...top.uncertainties,
  ].filter((value, index, values) => values.indexOf(value) === index) : [];
  const topInspection = matchingDetail?.evidence_series.inspections[0] ?? null;
  const topProcess = matchingDetail?.trace.process_path[0] ?? null;
  const topForecast = liveStatus?.prediction.top_sensor_forecasts[0] ?? null;
  const topCaseRisk = liveStatus?.prediction.case_risks[0] ?? null;
  const liveDecision = top?.live_intelligence ?? null;
  const learnedByTarget = new Map<string, ContinuousIntelligenceStatus["latest_predictions"][number]>();
  for (const prediction of intelligence?.latest_predictions ?? []) if (!learnedByTarget.has(prediction.target)) learnedByTarget.set(prediction.target, prediction);
  const learnedYield = learnedByTarget.get("final_yield");
  const learnedExcursionAlarm = learnedByTarget.get("next_lot_excursion_alarm_probability");
  const learnedMaintenanceAttention = learnedByTarget.get("next_lot_maintenance_attention_probability");
  const learnedExcursion = learnedByTarget.get("final_excursion_probability");
  const autoReport = intelligence?.reports.find((report) => report.case_id === top?.case_id) ?? null;
  const situationAssessment = autoReport?.situation_assessment ?? null;
  const visibleBrief = manualBrief?.brief.case_id === top?.case_id ? manualBrief.brief : autoReport?.brief ?? null;
  const visibleProvider = manualBrief?.brief.case_id === top?.case_id ? manualBrief.brief.provider : autoReport?.provider ?? liveDecision?.llm.provider ?? null;
  const predictedYield = liveDecision?.predictions.final_yield ?? learnedYield?.score ?? null;
  const predictedExcursion = liveDecision?.predictions.final_excursion_probability ?? learnedExcursion?.score ?? null;
  const predictedExcursionAlarm = liveDecision?.predictions.next_lot_excursion_alarm_probability ?? learnedExcursionAlarm?.score ?? null;
  const predictedMaintenanceAttention = liveDecision?.predictions.next_lot_maintenance_attention_probability ?? learnedMaintenanceAttention?.score ?? null;
  return <div className="screen-stack decision-cockpit">
    <section className="cockpit-hero">
      <div className="cockpit-hero__intro">
        <span className="eyebrow">Semiconductor forensics · current decision packet</span>
        <h1>What needs a decision now?</h1>
        <p>Resolve whether the excursion is physical, data-quality related, or still under-evidenced before a human chooses the next governed diagnostic stance.</p>
      </div>
      <div className="cockpit-hero__status">
        <div><span>Projection</span><strong>{projection.stale ? "STALE" : "FRESH"}</strong><small>{projection.lag_events} lag events</small></div>
        <div><span>Evidence provenance</span><strong>SYNTHETIC</strong><small>source-linked portfolio data</small></div>
        <div><span>Decision authority</span><strong>HUMAN</strong><small>AI wording cannot decide</small></div>
        <div className="cockpit-trust"><span>Execution boundary</span><strong>NONE</strong><small>NO EQUIPMENT CONTROL</small></div>
      </div>
    </section>
    <section className={`live-intelligence-strip ${liveStatus?.live_enabled ? "is-live" : "is-snapshot"}`} aria-label="Live operational intelligence">
      <div><span>Runtime</span><strong>{liveStatus?.live_enabled ? "LIVE" : "SNAPSHOT"}</strong><small>{liveStatus?.transport ?? "SSE pending"}</small></div>
      <div><span>Event ledger</span><strong>{liveStatus?.event_count ?? "—"}</strong><small>{liveStatus?.latest_lot_id ?? "no live lot"} · {liveStatus?.latest_event_type?.replaceAll(".v1", "") ?? "no event"}</small></div>
      <div><span>Highest drift watch</span><strong>{topForecast ? `${topForecast.chamber_id} / ${topForecast.sensor_name}` : "—"}</strong><small>{topForecast ? `${topForecast.risk_band} · ${(topForecast.risk_score * 100).toFixed(0)} risk score` : "forecast unavailable"}</small></div>
      <div><span>Predictive case risk</span><strong>{topCaseRisk?.lot_id ?? "—"}</strong><small>{topCaseRisk ? `${topCaseRisk.risk_band} · ${(topCaseRisk.risk_score * 100).toFixed(0)} risk score` : "no active forecast"}</small></div>
    </section>
    <section className="learned-intelligence-strip" aria-label="Learned predictive intelligence">
      <div><span>Final yield · POST_CMP</span><strong>{predictedYield != null ? `${(predictedYield * 100).toFixed(1)}%` : "—"}</strong><small>{learnedYield?.model_version ?? "cutoff-aware champion"}</small></div>
      <div><span>Final excursion · POST_CMP</span><strong>{predictedExcursion != null ? `${(predictedExcursion * 100).toFixed(0)}%` : "—"}</strong><small>{learnedExcursion?.calibrated ? "calibrated champion" : "live case score"}</small></div>
      <div><span>Next-lot excursion / alarm</span><strong>{predictedExcursionAlarm != null ? `${(predictedExcursionAlarm * 100).toFixed(0)}%` : "—"}</strong><small>{predictedExcursionAlarm != null && predictedExcursionAlarm >= .7 ? "HIGH · NOT FAILURE PROBABILITY" : predictedExcursionAlarm != null && predictedExcursionAlarm >= .4 ? "WATCH · NOT FAILURE PROBABILITY" : "NORMAL · NOT FAILURE PROBABILITY"}</small></div>
      <div><span>Maintenance attention</span><strong>{predictedMaintenanceAttention != null ? `${(predictedMaintenanceAttention * 100).toFixed(0)}%` : "—"}</strong><small>{predictedMaintenanceAttention != null && predictedMaintenanceAttention >= .7 ? "HIGH · NOT RUL" : predictedMaintenanceAttention != null && predictedMaintenanceAttention >= .4 ? "WATCH · NOT RUL" : "NORMAL · NOT RUL"}</small></div>
      <div><span>Auto analyst</span><strong>{visibleProvider?.toUpperCase() ?? "WAITING"}</strong><small>{visibleBrief?.headline ?? "5-minute risk review + material-change trigger"}</small></div>
    </section>
    {top && liveDecision ? <section className={`live-decision-command live-decision-command--${liveDecision.urgency.toLowerCase()}`} aria-label="Live decision intelligence">
      <header>
        <div>
          <span className="eyebrow">Live decision intelligence · {liveDecision.watch_horizon}</span>
          <h2>{liveDecision.headline}</h2>
          <p>고정 문구가 아니라 현재 champion prediction, case evidence, RCA와 최신 LLM 분석을 합쳐 만든 실시간 의사결정 맥락입니다.</p>
        </div>
        <div className="live-decision-command__status">
          <span>{liveDecision.signal.replaceAll("_", " ")}</span>
          <strong>{liveDecision.urgency}</strong>
          <small>priority {(liveDecision.priority_score * 100).toFixed(0)}</small>
        </div>
      </header>
      <div className="live-decision-command__grid">
        <article>
          <span>왜 지금 봐야 하나</span>
          <ul>{liveDecision.why_now.map((item) => <li key={item}>{item}</li>)}</ul>
        </article>
        <article>
          <span>다음 확인 순서</span>
          <ol>{liveDecision.next_actions.map((item, index) => <li key={`${item.action}-${index}`}><b>{item.action}</b><small>{item.target} · {item.purpose}</small></li>)}</ol>
        </article>
        <article>
          <span>Escalation trigger</span>
          <ul>{liveDecision.trigger_conditions.map((item) => <li className={item.met ? "is-met" : ""} key={item.condition}><b>{item.met ? "TRIGGERED" : "WATCH"}</b><span>{item.meaning}</span><small>{item.current == null ? "current —" : `current ${(item.current * 100).toFixed(0)}%`}</small></li>)}</ul>
        </article>
      </div>
      <AdaptiveIntelligenceVisualization intelligence={intelligence} liveStatus={liveStatus} caseId={top.case_id} detail={matchingDetail} />
      <div className="live-analyst-brief">
        <div>
          <span>AI 상황 분석</span>
          <strong>{visibleBrief?.headline ?? "자동 Analyst가 다음 주기에서 업데이트합니다."}</strong>
          <p>{visibleBrief?.summary ?? liveDecision.llm.summary ?? "현재는 학습 모델과 deterministic evidence를 기준으로 판단 맥락을 제공하고 있습니다."}</p>
          {situationAssessment ? <div className="situation-delta-strip">
            <b>{situationAssessment.risk_trajectory ?? "DELTA REVIEW"}</b>
            {(situationAssessment.what_changed ?? []).slice(0, 3).map((item, index) => <span key={`${item.metric ?? item.status ?? "delta"}-${index}`}>
              {item.metric ? `${item.metric.replaceAll("_", " ")} ${item.delta == null ? "—" : `${item.delta >= 0 ? "+" : ""}${(item.delta * 100).toFixed(1)}pp`}` : item.status?.replaceAll("_", " ")}
            </span>)}
          </div> : null}
          <small>{visibleProvider ? `${visibleProvider} · ${manualBrief?.brief.case_id === top.case_id ? "manual refresh" : autoReport?.trigger_type ?? "periodic review"}` : "LLM report warming"}{visibleBrief?.generated_at ? ` · ${visibleBrief.generated_at}` : ""}</small>
        </div>
        <button type="button" className="primary live-analyze-button" disabled={analyzing} onClick={onAnalyzeNow}>{analyzing ? "분석 중…" : "지금 다시 분석"}</button>
      </div>
      {analysisFeedback ? <p className="live-analysis-feedback" aria-live="polite">{analysisFeedback}</p> : null}
    </section> : null}
    <section className="evidence-authority-matrix" aria-label="Evidence authority separation">
      <article><span>OBSERVED</span><strong>Source records</strong><small>Event, measurement, inspection</small></article>
      <article><span>COMPUTED</span><strong>Deterministic logic</strong><small>Anomaly, classification, RCA score</small></article>
      <article><span>PROJECTED</span><strong>Rebuildable view</strong><small>Neo4j read projection · not source truth</small></article>
      <article><span>INFERRED</span><strong>Advisory stance</strong><small>Evidence-grounded proposal only</small></article>
      <article><span>AI WORDING</span><strong>Presentation only</strong><small>Cannot change recommendation identity</small></article>
      <article className="is-human"><span>HUMAN DECISION</span><strong>Final authority</strong><small>Approve · reject · request evidence</small></article>
    </section>
    {top ? <section className="decision-spotlight panel">
      <div className="decision-spotlight__main">
        <div className="decision-spotlight__meta">
          <span className={priorityClass(top.priority_band)}>{top.priority_band}</span>
          <span>{top.lot_id}</span>
          <ClassificationBadge value={top.classification} />
        </div>
        <span className="eyebrow">Highest-ranked live decision signal</span>
        <h2>{liveDecision?.headline ?? top.decision_question}</h2>
        {liveDecision ? <p className="guardrail-question">Guardrail question · {top.decision_question}</p> : null}
        {classification ? <div className={`forensic-classification forensic-classification--${top.classification}`}><span>{classification.label}</span><p>{classification.detail}</p></div> : null}
        <div className="decision-context-grid" aria-label="Affected semiconductor scope">
          <div><span>Lot</span><strong>{top.lot_id}</strong><small>current decision object</small></div>
          <div><span>Wafer</span><strong>{topInspection?.wafer_id ?? "Not exposed"}</strong><small>{topInspection ? "inspection source record" : "current packet has no wafer identifier"}</small></div>
          <div><span>Step</span><strong>{topProcess?.step_id ?? "Not exposed"}</strong><small>{topProcess?.recipe_id ?? "open case investigation for process path"}</small></div>
          <div><span>Equipment / chamber</span><strong>{top.evidence.affected_scope.equipment[0] ?? "—"}</strong><small>{top.evidence.affected_scope.chambers.join(", ") || "no affected chamber returned"}</small></div>
        </div>
        {topEvidence ? <div className="mobile-evidence-summary" aria-label="Evidence sufficiency summary"><span>Evidence sufficiency</span><strong>{topEvidence.label}</strong><small>{topEvidence.support} supporting · {topEvidence.contradict} contradicting</small></div> : null}
        <div className="recommended-callout">
          <span>Deterministic guardrail stance</span>
          <strong>{top.options.find((option) => option.option_id === top.recommended_option_id)?.label}</strong>
          <p>{top.options.find((option) => option.option_id === top.recommended_option_id)?.tradeoff} · 이 항목은 안전 경계이며 위 live intelligence보다 우선하는 상황 설명이 아닙니다.</p>
        </div>
        <div className="decision-impact-grid">
          <div><span>Affected scope</span><strong>{top.impact.affected_chamber_count}</strong><small>chambers</small></div>
          <div><span>Affected lots</span><strong>{top.impact.affected_lot_count}</strong><small>synthetic lots</small></div>
          <div><span>Yield gap</span><strong>{top.impact.synthetic_yield_gap_percentage_points == null ? "—" : top.impact.synthetic_yield_gap_percentage_points.toFixed(1)}</strong><small>percentage points</small></div>
        </div>
        <div className="decision-unresolved-strip">
          <span>Resolve before acting</span>
          {unresolved.length ? <ul>{unresolved.slice(0, 4).map((item) => <li key={item}>{item}</li>)}</ul> : <strong>No unresolved deterministic boundary conditions are reported.</strong>}
        </div>
        <div className="decision-spotlight__actions" aria-label="Human investigation actions">
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
        {liveDecision?.priority_components ? <div className="evidence-meter-card">
          <div><span>Priority composition</span><strong>{(liveDecision.priority_score * 100).toFixed(1)}</strong></div>
          <small>{Object.entries(liveDecision.priority_components).map(([key, value]) => `${key.replaceAll("_", " ")} ${(value * 100).toFixed(0)}`).join(" · ")}</small>
          {liveDecision.why_ranked_above_next_case ? <p>{liveDecision.why_ranked_above_next_case}</p> : null}
        </div> : null}
        {topEvidence ? <div className="evidence-meter-card">
          <div><span>Evidence balance</span><strong>{topEvidence.label}</strong></div>
          <div className="evidence-meter" aria-label={`${topEvidence.support} supporting and ${topEvidence.contradict} contradicting evidence`}><span style={{width: `${Math.max(6, topEvidence.supportRatio)}%`}} /></div>
          <small>{topEvidence.support} supporting · {topEvidence.contradict} contradicting</small>
        </div> : null}
        <div className="forensic-source-stamp"><span>Source / freshness</span><strong>{sourceTimestamp}</strong><small>{projection.stale ? "Projection requires freshness review" : "Projection current at returned checkpoint"}</small></div>
      </aside>
    </section> : null}
    <AuthorityChain projection={projection} />
    {top ? <section className="panel option-comparison-panel">
      <header><div><span className="eyebrow">Decision design</span><h2>Compare the available stances before acting</h2></div><small>Trade-offs are deterministic; LLM narration cannot add or replace options.</small></header>
      <DecisionOptionCards packet={top} compact />
    </section> : null}
    <section className="panel decision-queue-panel">
      <header><div><span className="eyebrow">Ranked decision backlog</span><h2>Next decisions</h2></div><small>Learned risk priority · deterministic guardrails preserved</small></header>
      <div className="decision-queue">{cockpit.queue.map((packet) => {
        const recommended = packet.options.find((option) => option.option_id === packet.recommended_option_id);
        const balance = evidenceBalance(packet);
        return <article key={packet.case_id} className="decision-queue-item">
          <div className="decision-queue-item__identity">
            <span className={priorityClass(packet.priority_band)}>{packet.priority_band}</span>
            <strong>{packet.lot_id}</strong>
            <small>{packet.incident_episode ? `${packet.incident_episode.status} · ${packet.incident_episode.case_count} correlated cases` : `#${packet.priority_rank}`} · {packet.classification.replaceAll("_", " ")}</small>
          </div>
          <div className="decision-queue-item__question"><strong>{packet.live_intelligence?.headline ?? packet.decision_question}</strong><span>{packet.live_intelligence ? `${packet.live_intelligence.urgency} · priority ${(packet.live_intelligence.priority_score * 100).toFixed(0)} · guardrail: ${recommended?.label}` : `Guardrail: ${recommended?.label}`}</span></div>
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

export function OperationsOverview({overview, liveStatus, intelligence, onSelectCase}: {overview: OverviewResponse; liveStatus: LiveStatusResponse | null; intelligence: ContinuousIntelligenceStatus | null; onSelectCase: (caseId: string) => void}) {
  const classificationTotal = Math.max(1, overview.metrics.physical_excursions + overview.metrics.sensor_bias_cases + overview.metrics.data_quality_cases);
  const averageYield = overview.cases.filter((item) => item.mean_yield != null).reduce((sum, item) => sum + (item.mean_yield ?? 0), 0) / Math.max(1, overview.cases.filter((item) => item.mean_yield != null).length);
  const maxAnomaly = Math.max(...overview.cases.map((item) => item.anomaly_score), 1);
  const databaseBacked = overview.source === "postgresql-read-only";
  const topForecasts = liveStatus?.prediction.top_sensor_forecasts.slice(0, 4) ?? [];
  const champions = Object.values(intelligence?.champions ?? {});
  const predictionByTarget = new Map<string, NonNullable<ContinuousIntelligenceStatus["latest_predictions"]>[number]>();
  for (const prediction of intelligence?.latest_predictions ?? []) if (!predictionByTarget.has(prediction.target)) predictionByTarget.set(prediction.target, prediction);
  const latestReport = intelligence?.reports[0] ?? null;
  const latestPlan = intelligence?.visualization_plans[0] ?? null;
  const feedbackSamples = Object.values(intelligence?.feedback ?? {}).reduce((sum, item) => sum + item.samples, 0);
  return <div className="screen-stack">
    <section className="surface-header">
      <div><span className="eyebrow">Operations overview</span><h1>Yield excursion triage queue</h1></div>
      <div className="badge-row">{databaseBacked ? <span className="source-mode-chip">POSTGRESQL READ-ONLY</span> : <span className="source-mode-chip">PREVIEW DATA</span>}<ProvenanceBadge kind="synthetic" /><ProjectionBadge projection={overview.projection} /></div>
    </section>
    <MetricStrip items={[
      {label: "Active cases", value: overview.metrics.active_cases, detail: "deterministic case engine"},
      {label: "Physical", value: overview.metrics.physical_excursions, detail: "yield-confirmed baseline"},
      {label: "Sensor bias", value: overview.metrics.sensor_bias_cases, detail: "non-physical"},
      {label: "Data quality", value: overview.metrics.data_quality_cases, detail: "no fab action"},
      {label: "Events", value: overview.metrics.event_count, detail: "source event log"},
    ]} />
    <section className="panel live-operations-panel">
      <header><div><span className="eyebrow">Live + predictive intelligence</span><h2>{liveStatus?.live_enabled ? "Continuous fab runtime" : "Runtime-ready snapshot"}</h2></div><small>{liveStatus?.prediction.model.version ?? "prediction service loading"}</small></header>
      <div className="live-operations-grid">
        <article><span>Stream state</span><strong>{liveStatus?.live_enabled ? "CONTINUOUS" : "PAUSED"}</strong><small>{liveStatus?.event_count ?? overview.metrics.event_count} events · {liveStatus?.case_count ?? overview.cases.length} cases</small></article>
        <article><span>Latest source event</span><strong>{liveStatus?.latest_lot_id ?? "—"}</strong><small>{liveStatus?.latest_event_time ?? overview.source_timestamp}</small></article>
        <article><span>Forecast contract</span><strong>{liveStatus?.prediction.model.trained_model ? "TRAINED" : "TRANSPARENT BASELINE"}</strong><small>{liveStatus?.prediction.model.calibrated ? "calibrated" : "not calibrated · not probability"}</small></article>
      </div>
      <div className="forecast-watchlist">
        {topForecasts.length ? topForecasts.map((forecast) => <article key={`${forecast.chamber_id}:${forecast.sensor_name}`}>
          <div><span>{forecast.step_id} · {forecast.chamber_id}</span><strong>{forecast.sensor_name}</strong></div>
          <div><span>EWMA {forecast.ewma.toFixed(2)}</span><span>trend {forecast.trend_per_measurement >= 0 ? "+" : ""}{forecast.trend_per_measurement.toFixed(3)}</span></div>
          <div><b>{forecast.risk_band}</b><strong>{(forecast.risk_score * 100).toFixed(0)}</strong><small>risk score</small></div>
          <div className="forecast-horizon"><span>next</span>{forecast.forecast_next.map((value, index) => <b key={index}>{value.toFixed(2)}</b>)}</div>
        </article>) : <p className="muted">Sensor forecasts appear as soon as measurement history is available.</p>}
      </div>
    </section>
    <section className="panel learning-engine-panel">
      <header><div><span className="eyebrow">Continuous learning engine</span><h2>{intelligence?.learning_enabled ? "Models learn from completed lots" : "Learning registry unavailable"}</h2></div><small>{intelligence?.feedback_loop ?? "waiting for intelligence worker"}</small></header>
      <div className="learning-kpis">
        <article><span>Outcome memory</span><strong>{intelligence?.outcome_count ?? 0}</strong><small>completed lots available for feedback</small></article>
        <article><span>Champion models</span><strong>{champions.length}</strong><small>cutoff yield · excursion · next-lot alarm · maintenance attention</small></article>
        <article><span>Prediction feedback</span><strong>{feedbackSamples}</strong><small>predictions compared with realized outcomes</small></article>
        <article><span>Feature drift</span><strong>{intelligence?.drift.status?.toUpperCase() ?? "WAITING"}</strong><small>{intelligence ? `drift score ${intelligence.drift.score.toFixed(3)}` : "learning window warming"}</small></article>
      </div>
      <div className="champion-model-grid">
        {champions.length ? champions.map((model) => <article key={model.model_name}>
          <div><span>{model.model_name.replaceAll("_", " ")}</span><strong>{model.model_version}</strong></div>
          <div className="model-metric-row"><span>{model.training_rows} rows</span><span>{model.metrics.brier != null ? `Brier ${model.metrics.brier.toFixed(3)}` : `MAE ${(model.metrics.mae ?? 0).toFixed(3)}`}</span><span>{model.metrics.auprc != null ? `AUPRC ${model.metrics.auprc.toFixed(3)}` : model.metrics.rmse != null ? `RMSE ${model.metrics.rmse.toFixed(3)}` : "shadow test"}</span></div>
          <small>{model.prediction_cutoff ?? "cutoff unknown"} · test {model.test_window?.start_lot ?? "—"}→{model.test_window?.end_lot ?? "—"}</small>
        </article>) : <p className="muted">The first champion set appears after enough completed lot outcomes are persisted.</p>}
      </div>
      <div className="learned-prediction-grid">
        {["final_yield", "final_excursion_probability", "next_lot_excursion_alarm_probability", "next_lot_maintenance_attention_probability"].map((target) => {
          const prediction = predictionByTarget.get(target);
          return <article key={target}><span>{target.replaceAll("_", " ")}</span><strong>{prediction ? `${(prediction.score * 100).toFixed(target === "final_yield" ? 1 : 0)}%` : "—"}</strong><small>{prediction ? `${prediction.lot_id} · ${prediction.prediction_cutoff ?? "cutoff"}` : "awaiting champion prediction"}</small></article>;
        })}
      </div>
      {(latestReport || latestPlan) ? <div className="intelligence-narrative-grid">
        <article>
          <span className="eyebrow">Auto analyst report</span>
          <strong>{latestReport?.brief?.headline ?? `Case ${latestReport?.case_id ?? "—"}`}</strong>
          <p>{latestReport?.brief?.summary ?? "A material change was detected and persisted; deterministic wording remains available when no LLM provider succeeds."}</p>
          <small>{latestReport ? `${latestReport.trigger_type} · ${latestReport.provider} · ${latestReport.material_signature}` : "no report yet"}</small>
        </article>
        <article>
          <span className="eyebrow">Adaptive visualization planner</span>
          <strong>{latestPlan ? `${latestPlan.primary.type} → ${latestPlan.secondary.type}` : "Waiting"}</strong>
          <p>{latestPlan?.rationale ?? "The planner changes chart strategy when the dominant operational question changes."}</p>
          <small>{latestPlan ? `${latestPlan.primary.title} · ${latestPlan.secondary.title}` : "no plan yet"}</small>
        </article>
      </div> : null}
      <AdaptiveIntelligenceVisualization intelligence={intelligence} liveStatus={liveStatus} />
    </section>
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
  const [counterEvidenceFirst, setCounterEvidenceFirst] = useState(true);
  const evidenceColumns = top ? [
    {
      kind: "support" as const,
      title: "Supporting evidence",
      count: supportCount,
      items: top.supporting_evidence,
      empty: "No explicit supporting evidence.",
      bullet: "+",
    },
    {
      kind: "contradict" as const,
      title: "Contradicting evidence",
      count: contradictCount,
      items: top.contradicting_evidence,
      empty: "No explicit contradiction recorded. Treat absence of contradiction as uncertainty, not proof.",
      bullet: "−",
    },
  ].sort((left, right) => counterEvidenceFirst ? (left.kind === "contradict" ? -1 : 1) - (right.kind === "contradict" ? -1 : 1) : 0) : [];
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
        <header><div><span className="eyebrow">Evidence ledger</span><h2>What supports — and weakens — the hypothesis?</h2></div><button className="counter-evidence-toggle" type="button" aria-pressed={counterEvidenceFirst} onClick={() => setCounterEvidenceFirst((current) => !current)}>{counterEvidenceFirst ? "Counter-evidence first" : "Balanced order"}</button></header>
        {top ? <>
          <div className="evidence-ledger-grid">
            {evidenceColumns.map((column) => <div key={column.kind} className={`evidence-ledger-column evidence-ledger-column--${column.kind}`} data-evidence-order={column.kind}>
              <h3>{column.title} <span>{column.count}</span></h3>
              {column.items.length ? <ul>{column.items.map((item, index) => <li key={`${column.kind}-${index}`}><span className="evidence-bullet">{column.bullet}</span><p>{readableEvidence(item)}</p></li>)}</ul> : <p>{column.empty}</p>}
            </div>)}
          </div>
          <p className="counter-evidence-note">Counter-evidence-first changes inspection order only. It never changes the deterministic candidate ranking or recommendation.</p>
        </> : <WorkbenchState kind="empty" title="No ranked candidate" detail="The deterministic RCA service did not produce a supported candidate." />}
      </section>
    </div>
    <EvidenceDiff candidates={detail.rca.candidates} />
    <RcaExplainability candidates={detail.rca.candidates} />
    <section className="panel advisory-strip advisory-strip--decision">
      <div><span className="eyebrow">Evidence-grounded next step</span><h2>{advisory?.result.status === "ready" ? "Ready for human review" : advisory?.result.status ?? "loading"}</h2></div>
      <p>{advisory?.result.recommended_next_step ?? "Resolving evidence-grounded recommendation…"}</p>
      <span className="advisory-authority">Deterministic advisory · no state mutation</span>
    </section>
  </div>;
}

export function EvidenceGraph({detail, selectedStep, onSelectStep, onSelectEvidenceNode}: {detail: CaseDetailResponse; selectedStep: string | null; onSelectStep: (step: string) => void; onSelectEvidenceNode: (node: EvidenceGraphNode) => void}) {
  const step = selectedStep ?? detail.trace.process_path[0]?.step_id ?? "LITHO";
  const allMeasurements = detail.evidence_series.measurements;
  const stepOrder = Array.from(new Set(detail.trace.process_path.map((item) => item.step_id)));
  const filtered = allMeasurements.filter((item) => item.step_id === step);
  const sensorOptions = Array.from(new Set([...allMeasurements].sort((a, b) => a.event_time.localeCompare(b.event_time) || a.sensor_name.localeCompare(b.sensor_name)).map((item) => item.sensor_name)));
  const [sensorFilter, setSensorFilter] = useState("all");
  const activeSensor = sensorFilter === "all" || sensorOptions.includes(sensorFilter) ? sensorFilter : "all";
  const selectedSignals = filtered.filter((item) => activeSensor === "all" || item.sensor_name === activeSensor);
  const caseSignals = allMeasurements.filter((item) => activeSensor === "all" || item.sensor_name === activeSensor);
  const selectedProcess = detail.trace.process_path.find((item) => item.step_id === step) ?? null;
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
      <div className="console-toolbar__readout">{activeSensor === "all" ? <><span>Signals</span><strong>{selectedSignals.length}</strong><small>at {step}</small></> : <><span>Latest</span><strong>{latestMeasurement ? latestMeasurement.value.toFixed(3) : "—"}</strong><small>{latestMeasurement?.unit ?? `no ${step} sample`}</small></>}</div>
    </section>
    <section className="panel graph-workspace graph-workspace--console">
      <header><div><span className="eyebrow">Process lineage</span><h2>Lot → run → chamber → evidence</h2></div><div className="graph-header-meta"><ProjectionBadge projection={detail.trace.projection} /><small>Select a step to coordinate every lens.</small></div></header>
      <EvidenceGraphExplorer detail={detail} onSelectStep={onSelectStep} onSelectNode={onSelectEvidenceNode} />
      <div className="lineage-row" aria-label="Process lineage">{detail.trace.process_path.map((item, index) => <div className="lineage-fragment" key={item.process_run_id}>
        <button className={item.step_id === step ? "lineage-node is-selected" : "lineage-node"} aria-pressed={item.step_id === step} onClick={() => onSelectStep(item.step_id)}>
          <span>{item.step_id}</span><strong>{item.chamber_id ?? "no chamber"}</strong><small>{item.equipment_id ?? "—"}</small>
        </button>{index < detail.trace.process_path.length - 1 ? <span className="lineage-arrow" aria-hidden="true">→</span> : null}
      </div>)}</div>
      <div className="signal-console-grid">
        <div className="signal-console-grid__trend"><SignalTrendChart points={allMeasurements} sensor={activeSensor} step={step} steps={stepOrder} /></div>
        <SignalRangeProfile points={allMeasurements} sensor={activeSensor} step={step} steps={stepOrder} />
        <ChamberHeatmap points={caseSignals} selectedChamber={selectedProcess?.chamber_id ?? null} />
      </div>
      <SignalKpis casePoints={allMeasurements} stepPoints={selectedSignals} sensor={activeSensor} step={step} />
      <WaferInspectionContext inspections={detail.evidence_series.inspections} />
      <div className="console-ledger-head"><div><span className="eyebrow">Raw evidence ledger</span><strong>Selected signal events</strong></div><small>Values below are source-linked synthetic evidence.</small></div>
      <div className="table-scroll console-table"><table>
        <thead><tr><th>Sensor</th><th>Value</th><th>Chamber</th><th>Event time</th><th>Event</th></tr></thead>
        <tbody>{selectedSignals.map((item) => <tr key={item.event_id}><td><span className="sensor-ledger-name"><i />{item.sensor_name}</span></td><td>{item.value.toFixed(3)}</td><td>{item.chamber_id}</td><td>{item.event_time}</td><td><code>{item.event_id.slice(0, 12)}…</code></td></tr>)}</tbody>
      </table></div>
    </section>
  </div>;
}

export function DecisionApproval({detail, packet, replayTrace, advisory, busy, feedback, brief, briefAudience, narrationBusy, narrationFeedback, narrationStatus, onBriefAudience, onGenerateBrief, onRequestEvidence, onPropose, onApprove, onReject}: {
  detail: CaseDetailResponse;
  packet: DecisionPacket | null;
  replayTrace: CaseReplayTraceResponse | null;
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
    <AuthorityChain projection={detail.rca.projection} />
    {packet ? <section className="panel option-comparison-panel option-comparison-panel--decision">
      <header><div><span className="eyebrow">Option comparison</span><h2>Choose a stance, not an opaque AI answer</h2></div><small>Recommendation is deterministic · approval remains human-controlled</small></header>
      <DecisionOptionCards packet={packet} />
    </section> : null}
    {packet ? <DecisionBoundaryPanel packet={packet} /> : null}
    {packet ? <DecisionProvenanceGraph packet={packet} trace={replayTrace} /> : null}
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
        <article className="replay-event-inspector" aria-label="Selected replay event">
          {replayItem ? <>
            <section className="replay-event-metadata" aria-label="Selected source event metadata">
              <div className="replay-event-inspector__title"><span>{replayItem.kind.replaceAll("_", " ")}</span><h3>{replayItem.event_type}</h3><small>{replayItem.event_time ?? "No persisted wall-clock timestamp"}</small></div>
              <dl>
                <div><dt>Phase</dt><dd>{replayItem.phase}</dd></div>
                <div><dt>Source</dt><dd>{replayItem.source}</dd></div>
                <div><dt>Time semantics</dt><dd>{replayItem.time_semantics.replaceAll("_", " ")}</dd></div>
                <div><dt>Delivery</dt><dd>{replayItem.delivery_status ?? "not applicable"}</dd></div>
                <div><dt>Event ID</dt><dd>{replayItem.event_id ?? "not an authoritative source event"}</dd></div>
              </dl>
            </section>
            <section className="replay-payload" aria-label="Recorded payload"><span>Recorded payload</span><pre>{JSON.stringify(replayItem.payload, null, 2)}</pre></section>
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

