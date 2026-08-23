import type {CaseDetailResponse, MeasurementPoint} from "../../types";
import type {VisualizationSpec} from "../../platform/visualization/registry";
import {validateVisualizationSpec} from "../../platform/visualization/registry";

export type AnalysisStepType = "input_case" | "filter_step" | "filter_chamber" | "filter_sensor" | "time_range" | "compare_chambers" | "aggregate" | "chart" | "verify_evidence";

export interface AnalysisStep {
  step_id: string;
  type: AnalysisStepType;
  label: string;
  config: Record<string, string>;
  provenance: "user-bounded" | "system-required";
}

export interface AnalysisSession {
  schema_version: "analysis-session-v1";
  session_id: string;
  case_id: string;
  branch_parent_id: string | null;
  steps: AnalysisStep[];
}

export interface AnalysisResult {
  measurements: MeasurementPoint[];
  evidence_refs: string[];
  applied_steps: string[];
  visualization: VisualizationSpec | null;
  comparison: Array<{key: string; count: number; mean: number}>;
  verified: boolean;
}

const STEP_TYPES = new Set<AnalysisStepType>(["input_case", "filter_step", "filter_chamber", "filter_sensor", "time_range", "compare_chambers", "aggregate", "chart", "verify_evidence"]);

export function createAnalysisSession(caseId: string, sessionId = `analysis:${caseId}`): AnalysisSession {
  return {
    schema_version: "analysis-session-v1",
    session_id: sessionId,
    case_id: caseId,
    branch_parent_id: null,
    steps: [{step_id: "input", type: "input_case", label: `Input ${caseId}`, config: {}, provenance: "system-required"}],
  };
}

export function serializeAnalysisSession(session: AnalysisSession) {
  return JSON.stringify(session);
}

export function parseAnalysisSession(value: string | null, caseId: string): AnalysisSession {
  if (!value) return createAnalysisSession(caseId);
  try {
    const parsed = JSON.parse(value) as Partial<AnalysisSession>;
    if (parsed.schema_version !== "analysis-session-v1" || parsed.case_id !== caseId || !Array.isArray(parsed.steps)) return createAnalysisSession(caseId);
    const validSteps = parsed.steps.filter((step): step is AnalysisStep => Boolean(step && typeof step === "object" && typeof step.step_id === "string" && STEP_TYPES.has(step.type)));
    if (!validSteps.length || validSteps[0].type !== "input_case") return createAnalysisSession(caseId);
    return {
      schema_version: "analysis-session-v1",
      session_id: typeof parsed.session_id === "string" ? parsed.session_id : `analysis:${caseId}`,
      case_id: caseId,
      branch_parent_id: typeof parsed.branch_parent_id === "string" ? parsed.branch_parent_id : null,
      steps: validSteps,
    };
  } catch {
    return createAnalysisSession(caseId);
  }
}

function nextId(session: AnalysisSession, type: AnalysisStepType) {
  const matching = session.steps.filter((step) => step.type === type).length + 1;
  return `${type}:${matching}`;
}

export function appendAnalysisStep(session: AnalysisSession, type: AnalysisStepType, config: Record<string, string>, label: string): AnalysisSession {
  if (type === "input_case") return session;
  return {...session, steps: [...session.steps, {step_id: nextId(session, type), type, config, label, provenance: "user-bounded"}]};
}

export function branchAnalysisSession(session: AnalysisSession, branchId: string): AnalysisSession {
  return {...session, session_id: branchId, branch_parent_id: session.session_id, steps: session.steps.map((step) => ({...step, config: {...step.config}}))};
}

function groupedComparison(points: MeasurementPoint[], key: "chamber_id" | "sensor_name" | "step_id") {
  const groups = new Map<string, number[]>();
  for (const point of points) groups.set(point[key], [...(groups.get(point[key]) ?? []), point.value]);
  return Array.from(groups, ([groupKey, values]) => ({key: groupKey, count: values.length, mean: values.reduce((sum, value) => sum + value, 0) / values.length})).sort((a, b) => a.key.localeCompare(b.key));
}

export function evaluateAnalysis(detail: CaseDetailResponse, session: AnalysisSession): AnalysisResult {
  let measurements = [...detail.evidence_series.measurements];
  let visualization: VisualizationSpec | null = null;
  let comparison: AnalysisResult["comparison"] = [];
  let verified = false;
  const appliedSteps: string[] = [];

  for (const step of session.steps.slice(1)) {
    if (step.type === "filter_step" && step.config.step_id) measurements = measurements.filter((item) => item.step_id === step.config.step_id);
    else if (step.type === "filter_chamber" && step.config.chamber_id) measurements = measurements.filter((item) => item.chamber_id === step.config.chamber_id);
    else if (step.type === "filter_sensor" && step.config.sensor_name) measurements = measurements.filter((item) => item.sensor_name === step.config.sensor_name);
    else if (step.type === "time_range") {
      const start = step.config.start ?? "";
      const end = step.config.end ?? "~";
      measurements = measurements.filter((item) => item.event_time >= start && item.event_time <= end);
    } else if (step.type === "compare_chambers") comparison = groupedComparison(measurements, "chamber_id");
    else if (step.type === "aggregate") comparison = groupedComparison(measurements, (step.config.group_by === "sensor_name" || step.config.group_by === "step_id") ? step.config.group_by : "chamber_id");
    else if (step.type === "chart") {
      const candidate: VisualizationSpec = {
        type: (step.config.type || "timeseries") as VisualizationSpec["type"],
        x: (step.config.x || "event_time") as VisualizationSpec["x"],
        y: (step.config.y || "value") as VisualizationSpec["y"],
        group_by: step.config.group_by ? step.config.group_by as VisualizationSpec["group_by"] : undefined,
        title: step.label,
      };
      visualization = validateVisualizationSpec(candidate).valid ? candidate : null;
    } else if (step.type === "verify_evidence") verified = true;
    appliedSteps.push(step.step_id);
  }

  return {
    measurements,
    evidence_refs: measurements.map((item) => item.event_id).sort(),
    applied_steps: appliedSteps,
    visualization,
    comparison,
    verified,
  };
}

