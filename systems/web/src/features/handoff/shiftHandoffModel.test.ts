import {describe, expect, it} from "vitest";
import type {DecisionCockpitResponse, DecisionPacket, OverviewResponse, ReplayResponse} from "../../types";
import {buildShiftHandoffSnapshot} from "./shiftHandoffModel";

function packet(caseId: string, rank: number, contradict: number): DecisionPacket {
  return {
    schema_version: "decision-packet-v1",
    case_id: caseId,
    lot_id: `LOT-${caseId}`,
    classification: "physical_excursion",
    state: "OPEN",
    decision_question: `Review ${caseId}`,
    priority_band: rank > 5 ? "HIGH" : "MEDIUM",
    priority_rank: rank,
    recommended_option_id: "confirm_evidence",
    options: [{option_id: "confirm_evidence", label: "Confirm evidence", stance: "recommended", tradeoff: "Review evidence", requires_human_approval: false}],
    impact: {synthetic_yield_gap_percentage_points: null, affected_equipment_count: 1, affected_chamber_count: 1, affected_lot_count: 1, basis: "synthetic"},
    evidence: {
      anomaly_score: .7,
      mean_yield: .9,
      affected_scope: {equipment: [], chambers: []},
      top_candidate: {
        candidate_id: `candidate-${caseId}`,
        candidate_type: "chamber",
        score: .61,
        score_components: {},
        supporting_evidence: [{type: "measurement"}],
        contradicting_evidence: Array.from({length: contradict}, () => ({type: "inspection"})),
      },
      advisory_status: "ready",
      advisory_next_step: "review",
      data_quality_incidents: [],
    },
    uncertainties: ["bounded uncertainty"],
    evidence_refs: ["rca.top_candidate"],
    provenance: {equipment_control: false},
  };
}

const overview = {
  source: "runtime",
  source_timestamp: "2026-08-23T12:00:00+00:00",
  projection: {projection_version: "rca-v1", source_checkpoint: 10, projection_checkpoint: 10, lag_events: 0, stale: false},
  metrics: {active_cases: 2, physical_excursions: 2, sensor_bias_cases: 0, data_quality_cases: 0, event_count: 10, quarantine_count: 0},
  cases: [],
} satisfies OverviewResponse;

const replay = {
  source: "runtime",
  event_count: 10,
  detection_checkpoint: 10,
  projection: overview.projection,
  outbox_count: 0,
  quarantine_count: 0,
  delivery_status_counts: {},
  external_services: {},
  integration: {status: "verified", compose_config_verified: true, postgres_runtime_verified: true, redpanda_runtime_verified: true, neo4j_runtime_verified: true, container_integration_verified: true},
  release: {release_version: "0.6.0", release_hash: "hash", source_git_commit: null, manifest_available: true},
} satisfies ReplayResponse;

describe("shiftHandoffModel", () => {
  it("orders handoff items by the existing deterministic priority rank", () => {
    const cockpit = {schema_version: "decision-cockpit-v1", source: "runtime", summary: {decision_count: 2, high_priority: 1, medium_priority: 1, data_verification: 0}, queue: [packet("A", 3, 0), packet("B", 9, 1)]} satisfies DecisionCockpitResponse;
    const snapshot = buildShiftHandoffSnapshot(cockpit, overview, replay);

    expect(snapshot.items.map((item) => item.caseId)).toEqual(["B", "A"]);
    expect(snapshot.summary.contestedHypotheses).toBe(1);
  });

  it("uses the source timestamp instead of inventing a handoff event time", () => {
    const cockpit = {schema_version: "decision-cockpit-v1", source: "runtime", summary: {decision_count: 1, high_priority: 1, medium_priority: 0, data_verification: 0}, queue: [packet("A", 9, 0)]} satisfies DecisionCockpitResponse;
    const snapshot = buildShiftHandoffSnapshot(cockpit, overview, replay);

    expect(snapshot.sourceTimestamp).toBe(overview.source_timestamp);
    expect(snapshot.limitations.join(" ")).toContain("not a historical reconstruction");
  });

  it("preserves RCA projection and human-authority boundaries", () => {
    const cockpit = {schema_version: "decision-cockpit-v1", source: "runtime", summary: {decision_count: 1, high_priority: 1, medium_priority: 0, data_verification: 0}, queue: [packet("A", 9, 0)]} satisfies DecisionCockpitResponse;
    const snapshot = buildShiftHandoffSnapshot(cockpit, overview, replay);

    expect(snapshot.projection.version).toBe("rca-v1");
    expect(snapshot.limitations.join(" ")).toContain("Human approval remains authoritative");
    expect(snapshot.limitations.join(" ")).toContain("no equipment control");
  });
});

