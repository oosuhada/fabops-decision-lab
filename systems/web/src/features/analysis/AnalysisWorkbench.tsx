import {useEffect, useMemo, useState} from "react";
import type {CaseDetailResponse} from "../../types";
import {AnalysisVisualization} from "../../platform/visualization/AnalysisVisualization";
import {VISUALIZATION_REGISTRY, type VisualizationType} from "../../platform/visualization/registry";
import {appendAnalysisStep, branchAnalysisSession, createAnalysisSession, evaluateAnalysis, parseAnalysisSession, serializeAnalysisSession, type AnalysisSession, type AnalysisStepType} from "./analysisModel";

const BLOCK_LABELS: Record<Exclude<AnalysisStepType, "input_case">, string> = {
  filter_step: "Filter Step",
  filter_chamber: "Filter Chamber",
  filter_sensor: "Filter Sensor",
  time_range: "Time Range",
  compare_chambers: "Compare Chambers",
  aggregate: "Aggregate",
  chart: "Chart",
  verify_evidence: "Verify Evidence",
};

function storageKey(caseId: string) {
  return `fabops:v07:analysis:${caseId}`;
}

export function AnalysisWorkbench({detail}: {detail: CaseDetailResponse}) {
  const [session, setSession] = useState<AnalysisSession>(() => parseAnalysisSession(window.localStorage.getItem(storageKey(detail.case.case_id)), detail.case.case_id));
  const [selectedStep, setSelectedStep] = useState(detail.trace.process_path[0]?.step_id ?? "");
  const [selectedChamber, setSelectedChamber] = useState(detail.case.affected_scope.chambers[0] ?? detail.evidence_series.measurements[0]?.chamber_id ?? "");
  const [selectedSensor, setSelectedSensor] = useState(detail.evidence_series.measurements[0]?.sensor_name ?? "");
  const [chartType, setChartType] = useState<VisualizationType>("timeseries");
  const [branchCounter, setBranchCounter] = useState(1);

  useEffect(() => {
    setSession(parseAnalysisSession(window.localStorage.getItem(storageKey(detail.case.case_id)), detail.case.case_id));
    setSelectedStep(detail.trace.process_path[0]?.step_id ?? "");
    setSelectedChamber(detail.case.affected_scope.chambers[0] ?? detail.evidence_series.measurements[0]?.chamber_id ?? "");
    setSelectedSensor(detail.evidence_series.measurements[0]?.sensor_name ?? "");
  }, [detail.case.case_id]);

  useEffect(() => {
    window.localStorage.setItem(storageKey(detail.case.case_id), serializeAnalysisSession(session));
  }, [detail.case.case_id, session]);

  const result = useMemo(() => evaluateAnalysis(detail, session), [detail, session]);
  const stepOptions = Array.from(new Set(detail.trace.process_path.map((item) => item.step_id)));
  const chamberOptions = Array.from(new Set(detail.evidence_series.measurements.map((item) => item.chamber_id)));
  const sensorOptions = Array.from(new Set(detail.evidence_series.measurements.map((item) => item.sensor_name)));

  function addBlock(type: Exclude<AnalysisStepType, "input_case">) {
    if (type === "filter_step") setSession((current) => appendAnalysisStep(current, type, {step_id: selectedStep}, `Step = ${selectedStep}`));
    else if (type === "filter_chamber") setSession((current) => appendAnalysisStep(current, type, {chamber_id: selectedChamber}, `Chamber = ${selectedChamber}`));
    else if (type === "filter_sensor") setSession((current) => appendAnalysisStep(current, type, {sensor_name: selectedSensor}, `Sensor = ${selectedSensor}`));
    else if (type === "time_range") {
      const sorted = [...detail.evidence_series.measurements].sort((a, b) => a.event_time.localeCompare(b.event_time));
      setSession((current) => appendAnalysisStep(current, type, {start: sorted[0]?.event_time ?? "", end: sorted.at(-1)?.event_time ?? ""}, "Current evidence time range"));
    } else if (type === "compare_chambers") setSession((current) => appendAnalysisStep(current, type, {}, "Compare current chambers"));
    else if (type === "aggregate") setSession((current) => appendAnalysisStep(current, type, {group_by: "chamber_id"}, "Mean by chamber"));
    else if (type === "chart") {
      const definition = VISUALIZATION_REGISTRY.find((item) => item.type === chartType);
      const config: Record<string, string> = {type: chartType};
      if (chartType === "metric") config.y = "value";
      else if (chartType === "histogram") {
        config.x = "value";
        config.group_by = "chamber_id";
      } else if (chartType === "heatmap" || chartType === "bar" || chartType === "comparison") {
        config.x = "chamber_id";
        config.y = "value";
        config.group_by = "chamber_id";
      } else if (chartType === "timeline") {
        config.x = "event_time";
        config.group_by = "step_id";
      } else if (chartType === "timeseries") {
        config.x = "event_time";
        config.y = "value";
        config.group_by = "chamber_id";
      }
      setSession((current) => appendAnalysisStep(current, type, config, `${definition?.label ?? chartType} · selected evidence`));
    } else setSession((current) => appendAnalysisStep(current, type, {}, "Verify source evidence references"));
  }

  function removeStep(stepId: string) {
    setSession((current) => ({...current, steps: current.steps.filter((step) => step.step_id === "input" || step.step_id !== stepId)}));
  }

  function branch() {
    setBranchCounter((current) => current + 1);
    setSession((current) => branchAnalysisSession(current, `${current.case_id}:branch-${branchCounter + 1}`));
  }

  function reset() {
    setSession(createAnalysisSession(detail.case.case_id));
  }

  return <div className="screen-stack analysis-screen">
    <section className="surface-header"><div><span className="eyebrow">Governed analysis workbench</span><h1>Build a reproducible evidence path</h1><p>Bounded blocks inspect source-linked evidence. They cannot run SQL/code, change RCA ranking, mutate workflow state, or control equipment.</p></div><div className="analysis-session-badge"><span>{session.session_id}</span><strong>{session.steps.length} blocks</strong></div></section>
    <section className="analysis-workbench">
      <aside className="analysis-builder">
        <header><span className="eyebrow">Block catalog</span><strong>Domain-safe operations</strong></header>
        <label><span>Step</span><select value={selectedStep} onChange={(event) => setSelectedStep(event.target.value)}>{stepOptions.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label><span>Chamber</span><select value={selectedChamber} onChange={(event) => setSelectedChamber(event.target.value)}>{chamberOptions.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label><span>Sensor</span><select value={selectedSensor} onChange={(event) => setSelectedSensor(event.target.value)}>{sensorOptions.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label><span>Visualization</span><select value={chartType} onChange={(event) => setChartType(event.target.value as VisualizationType)}>{VISUALIZATION_REGISTRY.map((item) => <option key={item.type} value={item.type}>{item.label}</option>)}</select></label>
        <div className="analysis-block-catalog">{Object.entries(BLOCK_LABELS).map(([type, label]) => <button key={type} type="button" onClick={() => addBlock(type as Exclude<AnalysisStepType, "input_case">)}><span>+</span><strong>{label}</strong></button>)}</div>
      </aside>
      <main className="analysis-canvas">
        <header><div><span className="eyebrow">Analysis path</span><strong>{detail.case.case_id} · {detail.case.lot_id}</strong></div><div><button type="button" onClick={branch}>Branch analysis</button><button type="button" onClick={reset}>Reset</button></div></header>
        <ol className="analysis-path">{session.steps.map((step, index) => <li key={step.step_id} className={`analysis-step analysis-step--${step.type}`}>
          <span className="analysis-step__index">{String(index + 1).padStart(2, "0")}</span><div><strong>{step.label}</strong><small>{step.type.replaceAll("_", " ")} · {step.provenance}</small></div>{step.type !== "input_case" ? <button type="button" aria-label={`Remove ${step.label}`} onClick={() => removeStep(step.step_id)}>×</button> : <span className="analysis-step__locked">LOCKED</span>}
        </li>)}</ol>
        <div className="analysis-result-strip"><div><span>Selected records</span><strong>{result.measurements.length}</strong></div><div><span>Evidence refs</span><strong>{result.evidence_refs.length}</strong></div><div><span>Verification block</span><strong>{result.verified ? "PRESENT" : "NOT ADDED"}</strong></div><div><span>Decision effect</span><strong>NONE</strong></div></div>
        <AnalysisVisualization spec={result.visualization} points={result.measurements} />
        {result.comparison.length ? <section className="analysis-comparison"><header><span>Deterministic descriptive comparison</span><strong>Grouped evidence</strong></header>{result.comparison.map((item) => <div key={item.key}><span>{item.key}</span><strong>μ {item.mean.toFixed(3)}</strong><small>{item.count} records</small></div>)}</section> : null}
      </main>
      <aside className="analysis-provenance">
        <header><span className="eyebrow">Provenance</span><strong>Reproducible state</strong></header>
        <dl><div><dt>Schema</dt><dd>{session.schema_version}</dd></div><div><dt>Case</dt><dd>{session.case_id}</dd></div><div><dt>Branch parent</dt><dd>{session.branch_parent_id ?? "root"}</dd></div><div><dt>Source records</dt><dd>{detail.evidence_series.measurements.length}</dd></div><div><dt>Selected records</dt><dd>{result.measurements.length}</dd></div></dl>
        <h3>Evidence references</h3><div className="analysis-evidence-refs">{result.evidence_refs.slice(0, 40).map((ref) => <code key={ref}>{ref}</code>)}</div>
        <footer><strong>Authority boundary</strong><span>Analysis is read-only inspection state. Deterministic recommendation and RCA remain unchanged.</span></footer>
      </aside>
    </section>
  </div>;
}

