import type {DecisionCockpitResponse, DecisionPacket, OverviewResponse, ReplayResponse} from "../../types";

export interface ShiftHandoffItem {
  caseId: string;
  lotId: string;
  priorityBand: string;
  priorityRank: number;
  classification: string;
  decisionQuestion: string;
  recommendationId: string;
  recommendationLabel: string;
  topCandidateId: string | null;
  rcaScore: number | null;
  supportCount: number;
  contradictCount: number;
  uncertaintyCount: number;
  dataQualityIncidentCount: number;
  humanApprovalRequired: boolean;
}

export interface ShiftHandoffSnapshot {
  sourceTimestamp: string;
  releaseVersion: string;
  projection: {
    version: string;
    stale: boolean;
    lagEvents: number;
  };
  summary: {
    openDecisions: number;
    highPriority: number;
    verifyData: number;
    contestedHypotheses: number;
    explicitUncertainties: number;
  };
  items: ShiftHandoffItem[];
  limitations: string[];
}

function toHandoffItem(packet: DecisionPacket): ShiftHandoffItem {
  const candidate = packet.evidence.top_candidate;
  const recommendation = packet.options.find((option) => option.option_id === packet.recommended_option_id);
  return {
    caseId: packet.case_id,
    lotId: packet.lot_id,
    priorityBand: packet.priority_band,
    priorityRank: packet.priority_rank,
    classification: packet.classification,
    decisionQuestion: packet.decision_question,
    recommendationId: packet.recommended_option_id,
    recommendationLabel: recommendation?.label ?? packet.recommended_option_id,
    topCandidateId: candidate?.candidate_id ?? null,
    rcaScore: candidate?.score ?? null,
    supportCount: candidate?.supporting_evidence.length ?? 0,
    contradictCount: candidate?.contradicting_evidence.length ?? 0,
    uncertaintyCount: packet.uncertainties.length,
    dataQualityIncidentCount: packet.evidence.data_quality_incidents.length,
    humanApprovalRequired: recommendation?.requires_human_approval ?? false,
  };
}

export function buildShiftHandoffSnapshot(
  cockpit: DecisionCockpitResponse,
  overview: OverviewResponse,
  replay: ReplayResponse,
): ShiftHandoffSnapshot {
  const items = cockpit.queue
    .map(toHandoffItem)
    .sort((left, right) => right.priorityRank - left.priorityRank || left.caseId.localeCompare(right.caseId));

  return {
    sourceTimestamp: overview.source_timestamp,
    releaseVersion: replay.release.release_version,
    projection: {
      version: overview.projection.projection_version,
      stale: overview.projection.stale,
      lagEvents: overview.projection.lag_events,
    },
    summary: {
      openDecisions: items.length,
      highPriority: items.filter((item) => item.priorityBand === "HIGH").length,
      verifyData: items.filter((item) => item.priorityBand === "VERIFY_DATA" || item.dataQualityIncidentCount > 0).length,
      contestedHypotheses: items.filter((item) => item.contradictCount > 0).length,
      explicitUncertainties: items.reduce((total, item) => total + item.uncertaintyCount, 0),
    },
    items,
    limitations: [
      "This handoff is a deterministic snapshot of currently loaded decision packets, not a historical reconstruction.",
      "RCA is a rebuildable read projection; the operational event model remains authoritative.",
      "Recommendations are decision support only. Human approval remains authoritative and no equipment control is available.",
    ],
  };
}

