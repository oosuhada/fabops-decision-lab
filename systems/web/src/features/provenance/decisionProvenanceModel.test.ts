import {describe, expect, it} from "vitest";
import type {CaseReplayTraceResponse, DecisionPacket} from "../../types";
import {buildDecisionProvenanceGraph} from "./decisionProvenanceModel";

const packet = {
  schema_version: "decision-packet-v1",
  case_id: "CASE-1",
  lot_id: "LOT-1",
  classification: "physical_excursion",
  state: "detected",
  decision_question: "What should be reviewed?",
  priority_band: "HIGH",
  priority_rank: 1,
  recommended_option_id: "confirm_evidence",
  options: [
    {option_id: "confirm_evidence", label: "Confirm evidence", stance: "recommended", tradeoff: "Collect more evidence", requires_human_approval: false},
    {option_id: "containment_review", label: "Review containment", stance: "conditional", tradeoff: "Requires human approval", requires_human_approval: true},
  ],
  impact: {synthetic_yield_gap_percentage_points: 4, affected_equipment_count: 1, affected_chamber_count: 1, affected_lot_count: 1, basis: "synthetic"},
  evidence: {
    anomaly_score: 0.8,
    mean_yield: 0.9,
    affected_scope: {equipment: ["EQ-1"], chambers: ["CH-1"]},
    top_candidate: {
      candidate_id: "chamber:CH-1",
      candidate_type: "chamber",
      score: 0.75,
      score_components: {scope: 0.3},
      supporting_evidence: [
        {type: "measurement", event_id: "EVENT-1", sensor: "temperature"},
        {type: "maintenance", maintenance_id: "MAINT-1"},
      ],
      contradicting_evidence: [{type: "yield", detail: "Nominal yield"}],
    },
    advisory_status: "ready",
    advisory_next_step: "review",
    data_quality_incidents: [],
  },
  uncertainties: [],
  evidence_refs: ["rca.top_candidate"],
  provenance: {equipment_control: false},
} satisfies DecisionPacket;

const trace = {
  source: "inferred",
  case_id: "CASE-1",
  lot_id: "LOT-1",
  source_of_truth: "postgresql-event-model",
  projection_role: "current rebuildable RCA projection snapshot",
  timeline: [
    {
      timeline_id: "source:EVENT-1",
      kind: "source_event",
      phase: "signal",
      sequence: 7,
      event_time: "2026-01-01T00:00:00Z",
      time_semantics: "source_event_time",
      event_type: "process.measurement.recorded.v1",
      event_id: "EVENT-1",
      delivery_status: "delivered",
      source: "postgresql-event-model",
      payload: {process_run_id: "RUN-1", step_id: "ETCH", recipe_id: "R-1"},
    },
  ],
  summary: {source_event_count: 1, audit_event_count: 0, projection_snapshot_count: 0, out_of_order_count: 0, late_count: 0},
  limitations: [],
} satisfies CaseReplayTraceResponse;

describe("decision provenance model", () => {
  it("builds an exact decision-to-option-to-RCA-to-event-to-process chain", () => {
    const graph = buildDecisionProvenanceGraph(packet, trace);
    expect(graph.nodes.some((node) => node.id === "decision:CASE-1")).toBe(true);
    expect(graph.nodes.some((node) => node.id === "option:confirm_evidence" && node.recommended)).toBe(true);
    expect(graph.nodes.some((node) => node.id === "rca:chamber:CH-1")).toBe(true);
    expect(graph.nodes.some((node) => node.id === "source-event:EVENT-1")).toBe(true);
    expect(graph.nodes.some((node) => node.id === "process-run:RUN-1")).toBe(true);
    expect(graph.edges.some((edge) => edge.relationship === "SOURCED_FROM" && edge.semantics === "exact event_id match")).toBe(true);
    expect(graph.edges.some((edge) => edge.relationship === "IN_PROCESS_RUN" && edge.semantics.includes("exact process_run_id"))).toBe(true);
  });

  it("omits anonymous evidence instead of fabricating graph identity", () => {
    const graph = buildDecisionProvenanceGraph(packet, trace);
    expect(graph.nodes.some((node) => node.label.includes("Nominal yield"))).toBe(false);
    expect(graph.gaps.some((gap) => gap.includes("omitted rather than assigned a fabricated graph ID"))).toBe(true);
    expect(graph.gaps.some((gap) => gap.includes("maintenance_id:MAINT-1") && gap.includes("no event_id bridge"))).toBe(true);
  });

  it("keeps Neo4j/read projection semantics subordinate to the operational source of truth", () => {
    const graph = buildDecisionProvenanceGraph(packet, trace);
    expect(graph.sourceOfTruth).toBe("postgresql-event-model");
    expect(graph.projectionRole).toContain("rebuildable");
    expect(graph.edges.find((edge) => edge.relationship === "CURRENT_RCA_CONTEXT")?.semantics).toContain("not a causal or Neo4j authority edge");
  });
});
