import {describe, expect, it} from "vitest";
import type {CaseDetailResponse} from "../../types";
import {appendAnalysisStep, branchAnalysisSession, createAnalysisSession, evaluateAnalysis, parseAnalysisSession, serializeAnalysisSession} from "./analysisModel";

const projection = {projection_version: "v1", source_checkpoint: 1, projection_checkpoint: 1, lag_events: 0, stale: false};
const detail: CaseDetailResponse = {
  source: "synthetic",
  case: {case_id: "CASE-1", lot_id: "LOT-1", classification: "physical_excursion", detector_version: "d1", anomaly_score: .7, mean_yield: .9, affected_scope: {equipment: ["E1"], chambers: ["C1", "C2"]}, evidence_event_ids: ["a", "b"], data_quality_incidents: [], state: "detected"},
  rca: {projection, candidates: []}, trace: {projection, affected_lots: ["LOT-1"], process_path: []}, audit: [],
  evidence_series: {measurements: [
    {event_id: "a", lot_id: "LOT-1", process_run_id: "r1", step_id: "ETCH", sensor_name: "pressure", value: 10, unit: "u", equipment_id: "E1", chamber_id: "C1", event_time: "2026-01-01T00:00:00Z"},
    {event_id: "b", lot_id: "LOT-1", process_run_id: "r2", step_id: "LITHO", sensor_name: "temperature", value: 20, unit: "u", equipment_id: "E2", chamber_id: "C2", event_time: "2026-01-01T01:00:00Z"},
  ], inspections: []},
};

describe("governed analysis model", () => {
  it("serializes, reloads and branches without losing bounded steps", () => {
    const session = appendAnalysisStep(createAnalysisSession("CASE-1"), "filter_step", {step_id: "ETCH"}, "Filter ETCH");
    expect(parseAnalysisSession(serializeAnalysisSession(session), "CASE-1")).toEqual(session);
    const branch = branchAnalysisSession(session, "analysis:CASE-1:branch-2");
    expect(branch.branch_parent_id).toBe(session.session_id);
    expect(branch.steps).toEqual(session.steps);
  });

  it("filters deterministic evidence without mutating RCA or case state", () => {
    let session = createAnalysisSession("CASE-1");
    session = appendAnalysisStep(session, "filter_step", {step_id: "ETCH"}, "Filter ETCH");
    session = appendAnalysisStep(session, "verify_evidence", {}, "Verify evidence refs");
    const result = evaluateAnalysis(detail, session);
    expect(result.measurements.map((item) => item.event_id)).toEqual(["a"]);
    expect(result.evidence_refs).toEqual(["a"]);
    expect(result.verified).toBe(true);
    expect(detail.case.state).toBe("detected");
  });
});

