import {describe, expect, it} from "vitest";
import type {DecisionPacket} from "../../types";
import {compareDecisionPackets} from "./caseComparisonModel";

function packet(overrides: Partial<DecisionPacket> = {}): DecisionPacket {
  return {
    schema_version: "decision-packet-v1",
    case_id: "CASE-A",
    lot_id: "LOT-A",
    classification: "physical_excursion",
    state: "OPEN",
    decision_question: "What should the operator review?",
    priority_band: "HIGH",
    priority_rank: 10,
    recommended_option_id: "confirm_evidence",
    options: [],
    impact: {
      synthetic_yield_gap_percentage_points: 2.1,
      affected_equipment_count: 1,
      affected_chamber_count: 2,
      affected_lot_count: 1,
      basis: "synthetic evidence",
    },
    evidence: {
      anomaly_score: 0.82,
      mean_yield: 0.91,
      affected_scope: {equipment: ["ETCH-01"], chambers: ["ETCH-01-A"]},
      top_candidate: {
        candidate_id: "chamber:ETCH-01-A",
        candidate_type: "chamber",
        score: 0.72,
        score_components: {},
        supporting_evidence: [{type: "measurement"}],
        contradicting_evidence: [{type: "inspection"}],
      },
      advisory_status: "ready",
      advisory_next_step: "review evidence",
      data_quality_incidents: [],
    },
    uncertainties: ["sample size"],
    evidence_refs: ["case.affected_scope", "rca.top_candidate", "decision.recommended_option_id"],
    provenance: {equipment_control: false},
    ...overrides,
  };
}

describe("caseComparisonModel", () => {
  it("compares only recorded packet fields and preserves evidence-ref identity", () => {
    const left = packet();
    const right = packet({
      case_id: "CASE-B",
      lot_id: "LOT-B",
      classification: "sensor_bias_suspected",
      evidence_refs: ["rca.top_candidate", "decision.recommended_option_id", "case.mean_yield"],
    });

    const result = compareDecisionPackets(left, right);

    expect(result.sharedEvidenceRefs).toEqual(["decision.recommended_option_id", "rca.top_candidate"]);
    expect(result.leftOnlyEvidenceRefs).toEqual(["case.affected_scope"]);
    expect(result.rightOnlyEvidenceRefs).toEqual(["case.mean_yield"]);
    expect(result.sameClassification).toBe(false);
  });

  it("does not convert RCA score into probability semantics", () => {
    const result = compareDecisionPackets(packet(), packet({case_id: "CASE-B"}));
    const rcaScore = result.rows.find((row) => row.metric === "RCA score");

    expect(rcaScore?.semantics).toContain("not a probability");
    expect(rcaScore?.left).toBe("0.72");
  });

  it("keeps recommendation comparison descriptive rather than changing authority", () => {
    const result = compareDecisionPackets(packet(), packet({case_id: "CASE-B", recommended_option_id: "containment_review"}));
    const recommendation = result.rows.find((row) => row.metric === "Current recommendation");

    expect(result.sameRecommendation).toBe(false);
    expect(recommendation?.direction).toBe("different");
    expect(recommendation?.semantics).toContain("human authority remains unchanged");
  });
});

