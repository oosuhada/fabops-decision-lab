import {describe, expect, it} from "vitest";
import type {CaseDetailResponse} from "../../types";
import {buildEvidenceGraph, graphNeighbors} from "./evidenceGraphModel";

const projection = {projection_version: "neo4j-v1", source_checkpoint: 5, projection_checkpoint: 5, lag_events: 0, stale: false};
const detail: CaseDetailResponse = {
  source: "synthetic",
  case: {case_id: "CASE-1", lot_id: "LOT-1", classification: "physical_excursion", detector_version: "det-v1", anomaly_score: .8, mean_yield: .91, affected_scope: {equipment: ["EQ-1"], chambers: ["CH-1"]}, evidence_event_ids: ["evt-1"], data_quality_incidents: [], state: "detected"},
  trace: {projection, affected_lots: ["LOT-1"], process_path: [{lot_id: "LOT-1", process_run_id: "run-1", step_id: "ETCH", equipment_id: "EQ-1", chamber_id: "CH-1", recipe_id: "R1"}]},
  rca: {projection, candidates: [{candidate_id: "chamber:CH-1", candidate_type: "chamber", score: .8, score_components: {temporal_proximity: .2}, supporting_evidence: [{type: "alarm", event_id: "evt-1"}], contradicting_evidence: [{type: "yield", detail: "normal downstream check"}], recommended_action: "inspect"}]},
  evidence_series: {measurements: [{event_id: "evt-1", lot_id: "LOT-1", process_run_id: "run-1", step_id: "ETCH", sensor_name: "pressure", value: 12, unit: "psi", equipment_id: "EQ-1", chamber_id: "CH-1", event_time: "2026-01-01T00:00:00Z"}], inspections: [{inspection_id: "insp-1", lot_id: "LOT-1", wafer_id: "W1", yield: .91, failed_die_ratio: .09, defect_pattern: "Edge-Loc", pattern_provenance: "synthetic", event_time: "2026-01-01T00:01:00Z"}]},
  audit: [],
};

describe("evidence graph projection", () => {
  it("creates only typed nodes backed by current case, trace, evidence and RCA payloads", () => {
    const model = buildEvidenceGraph(detail);
    expect(model.nodes.some((node) => node.id === "case:CASE-1" && node.type === "Case")).toBe(true);
    expect(model.nodes.some((node) => node.id === "measurement:evt-1" && node.type === "Measurement")).toBe(true);
    expect(model.nodes.some((node) => node.id === "rca:chamber:CH-1" && node.emphasis === "top-rca")).toBe(true);
    expect(model.edges.some((edge) => edge.type === "SUPPORTS")).toBe(true);
    expect(model.edges.some((edge) => edge.type === "CONTRADICTS")).toBe(true);
  });

  it("expands exactly one relationship hop without inventing graph members", () => {
    const model = buildEvidenceGraph(detail);
    const neighbors = graphNeighbors(model, "run:run-1");
    expect(neighbors.has("lot:LOT-1")).toBe(true);
    expect(neighbors.has("measurement:evt-1")).toBe(true);
    expect(neighbors.has("missing-node")).toBe(false);
  });
});

