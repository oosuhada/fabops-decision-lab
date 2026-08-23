import {describe, expect, it} from "vitest";
import type {RcaCandidate} from "../../types";
import {buildCandidateEvidenceDiff, diffEvidenceRecords, stableEvidenceKey} from "./evidenceDiffModel";

function candidate(overrides: Partial<RcaCandidate>): RcaCandidate {
  return {
    candidate_id: "candidate:A",
    candidate_type: "chamber",
    score: 0.8,
    score_components: {scope: 0.3, temporal: 0.2},
    supporting_evidence: [],
    contradicting_evidence: [],
    recommended_action: "review",
    ...overrides,
  };
}

describe("evidence diff model", () => {
  it("uses deterministic record identity independent of object key order", () => {
    expect(stableEvidenceKey({event_id: "E1", type: "alarm"})).toBe(stableEvidenceKey({type: "alarm", event_id: "E1"}));
  });

  it("preserves shared, candidate-only, supporting, and contradicting evidence without inventing a baseline", () => {
    const shared = {type: "inspection", inspection_id: "I1"};
    const left = candidate({
      candidate_id: "candidate:A",
      score: 0.75,
      score_components: {scope: 0.3, temporal: 0.2},
      supporting_evidence: [shared, {type: "alarm", event_id: "E1"}],
      contradicting_evidence: [{type: "maintenance", maintenance_id: "M1"}],
    });
    const right = candidate({
      candidate_id: "candidate:B",
      score: 0.1,
      score_components: {scope: 0.1, temporal: 0.05, contradiction: 0.05},
      supporting_evidence: [shared, {type: "alarm", event_id: "E2"}],
      contradicting_evidence: [{type: "maintenance", maintenance_id: "M2"}],
    });

    const diff = buildCandidateEvidenceDiff(left, right);

    expect(diff.scoreDelta).toBeCloseTo(0.65);
    expect(diff.support.shared).toHaveLength(1);
    expect(diff.support.leftOnly).toEqual([{type: "alarm", event_id: "E1"}]);
    expect(diff.support.rightOnly).toEqual([{type: "alarm", event_id: "E2"}]);
    expect(diff.contradict.leftOnly).toEqual([{type: "maintenance", maintenance_id: "M1"}]);
    expect(diff.contradict.rightOnly).toEqual([{type: "maintenance", maintenance_id: "M2"}]);
    expect(diff.components.find((item) => item.component === "contradiction")).toEqual({component: "contradiction", left: 0, right: 0.05, delta: -0.05});
  });

  it("keeps duplicate evidence as a multiset rather than collapsing counts", () => {
    const duplicate = {type: "alarm", event_id: "E1"};
    const diff = diffEvidenceRecords([duplicate, duplicate], [duplicate]);
    expect(diff.shared).toHaveLength(1);
    expect(diff.leftOnly).toHaveLength(1);
    expect(diff.rightOnly).toHaveLength(0);
  });
});
