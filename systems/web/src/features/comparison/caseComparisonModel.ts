import type {DecisionPacket} from "../../types";

export type ComparisonDirection = "same" | "left-higher" | "right-higher" | "different" | "not-comparable";

export interface CaseComparisonRow {
  metric: string;
  left: string;
  right: string;
  direction: ComparisonDirection;
  semantics: string;
}

export interface CaseComparisonResult {
  leftCaseId: string;
  rightCaseId: string;
  rows: CaseComparisonRow[];
  sharedEvidenceRefs: string[];
  leftOnlyEvidenceRefs: string[];
  rightOnlyEvidenceRefs: string[];
  sameClassification: boolean;
  sameRecommendation: boolean;
}

function compareNumber(left: number | null, right: number | null): ComparisonDirection {
  if (left == null || right == null) return "not-comparable";
  if (left === right) return "same";
  return left > right ? "left-higher" : "right-higher";
}

function compareString(left: string, right: string): ComparisonDirection {
  return left === right ? "same" : "different";
}

function percent(value: number | null): string {
  return value == null ? "N/A" : `${(value * 100).toFixed(1)}%`;
}

function score(value: number | undefined): string {
  return value == null ? "N/A" : value.toFixed(2);
}

export function compareDecisionPackets(left: DecisionPacket, right: DecisionPacket): CaseComparisonResult {
  const leftCandidate = left.evidence.top_candidate;
  const rightCandidate = right.evidence.top_candidate;
  const leftRefs = new Set(left.evidence_refs);
  const rightRefs = new Set(right.evidence_refs);

  const rows: CaseComparisonRow[] = [
    {
      metric: "Classification",
      left: left.classification,
      right: right.classification,
      direction: compareString(left.classification, right.classification),
      semantics: "Deterministic case classification",
    },
    {
      metric: "Priority rank",
      left: String(left.priority_rank),
      right: String(right.priority_rank),
      direction: compareNumber(left.priority_rank, right.priority_rank),
      semantics: "Queue ranking only; higher number is not presented as probability",
    },
    {
      metric: "Anomaly score",
      left: left.evidence.anomaly_score.toFixed(3),
      right: right.evidence.anomaly_score.toFixed(3),
      direction: compareNumber(left.evidence.anomaly_score, right.evidence.anomaly_score),
      semantics: "Detector output from the current case snapshot",
    },
    {
      metric: "Mean yield",
      left: percent(left.evidence.mean_yield),
      right: percent(right.evidence.mean_yield),
      direction: compareNumber(left.evidence.mean_yield, right.evidence.mean_yield),
      semantics: "Synthetic inspection evidence; not a real-fab benchmark",
    },
    {
      metric: "Affected chambers",
      left: String(left.impact.affected_chamber_count),
      right: String(right.impact.affected_chamber_count),
      direction: compareNumber(left.impact.affected_chamber_count, right.impact.affected_chamber_count),
      semantics: "Source-linked affected scope count",
    },
    {
      metric: "Top RCA candidate",
      left: leftCandidate?.candidate_id ?? "Unranked",
      right: rightCandidate?.candidate_id ?? "Unranked",
      direction: compareString(leftCandidate?.candidate_id ?? "Unranked", rightCandidate?.candidate_id ?? "Unranked"),
      semantics: "Current deterministic RCA projection snapshot",
    },
    {
      metric: "RCA score",
      left: score(leftCandidate?.score),
      right: score(rightCandidate?.score),
      direction: compareNumber(leftCandidate?.score ?? null, rightCandidate?.score ?? null),
      semantics: "Ranker score, explicitly not a probability",
    },
    {
      metric: "Contradicting evidence",
      left: String(leftCandidate?.contradicting_evidence.length ?? 0),
      right: String(rightCandidate?.contradicting_evidence.length ?? 0),
      direction: compareNumber(leftCandidate?.contradicting_evidence.length ?? 0, rightCandidate?.contradicting_evidence.length ?? 0),
      semantics: "Explicit counter-evidence count",
    },
    {
      metric: "Supporting evidence",
      left: String(leftCandidate?.supporting_evidence.length ?? 0),
      right: String(rightCandidate?.supporting_evidence.length ?? 0),
      direction: compareNumber(leftCandidate?.supporting_evidence.length ?? 0, rightCandidate?.supporting_evidence.length ?? 0),
      semantics: "Explicit supporting evidence count",
    },
    {
      metric: "Current recommendation",
      left: left.recommended_option_id,
      right: right.recommended_option_id,
      direction: compareString(left.recommended_option_id, right.recommended_option_id),
      semantics: "Deterministic decision-support recommendation; human authority remains unchanged",
    },
    {
      metric: "Uncertainties",
      left: String(left.uncertainties.length),
      right: String(right.uncertainties.length),
      direction: compareNumber(left.uncertainties.length, right.uncertainties.length),
      semantics: "Recorded uncertainty items only",
    },
  ];

  return {
    leftCaseId: left.case_id,
    rightCaseId: right.case_id,
    rows,
    sharedEvidenceRefs: [...leftRefs].filter((reference) => rightRefs.has(reference)).sort(),
    leftOnlyEvidenceRefs: [...leftRefs].filter((reference) => !rightRefs.has(reference)).sort(),
    rightOnlyEvidenceRefs: [...rightRefs].filter((reference) => !leftRefs.has(reference)).sort(),
    sameClassification: left.classification === right.classification,
    sameRecommendation: left.recommended_option_id === right.recommended_option_id,
  };
}

