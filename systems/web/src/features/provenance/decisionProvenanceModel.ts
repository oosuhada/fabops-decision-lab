import type {CaseReplayTraceResponse, DecisionPacket} from "../../types";

export type ProvenanceNodeKind = "decision" | "option" | "rca" | "evidence" | "source_event" | "process_run";

export interface ProvenanceNode {
  id: string;
  kind: ProvenanceNodeKind;
  label: string;
  detail: string;
  sourceIdentity: string;
  recommended?: boolean;
  evidenceKind?: "support" | "contradict";
}

export interface ProvenanceEdge {
  source: string;
  target: string;
  relationship: string;
  semantics: string;
}

export interface DecisionProvenanceGraphModel {
  nodes: ProvenanceNode[];
  edges: ProvenanceEdge[];
  gaps: string[];
  sourceOfTruth: string;
  projectionRole: string;
}

function shortIdentity(value: string) {
  return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
}

function evidenceIdentity(record: Record<string, unknown>): {identity: string; label: string} | null {
  const candidates = ["event_id", "maintenance_id", "inspection_id", "process_run_id"];
  for (const key of candidates) {
    const value = record[key];
    if (typeof value === "string" && value) {
      return {identity: `${key}:${value}`, label: `${String(record.type ?? "evidence")} · ${shortIdentity(value)}`};
    }
  }
  return null;
}

function evidenceDetail(record: Record<string, unknown>) {
  return Object.entries(record)
    .filter(([key, value]) => !key.endsWith("_id") && value != null)
    .slice(0, 3)
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${Array.isArray(value) ? value.join(", ") : String(value)}`)
    .join(" · ");
}

export function buildDecisionProvenanceGraph(packet: DecisionPacket, trace: CaseReplayTraceResponse | null): DecisionProvenanceGraphModel {
  const nodes: ProvenanceNode[] = [];
  const edges: ProvenanceEdge[] = [];
  const gaps: string[] = [];
  const seenNodes = new Set<string>();
  const addNode = (node: ProvenanceNode) => {
    if (seenNodes.has(node.id)) return;
    seenNodes.add(node.id);
    nodes.push(node);
  };

  const decisionId = `decision:${packet.case_id}`;
  addNode({
    id: decisionId,
    kind: "decision",
    label: packet.decision_question,
    detail: `case ${packet.case_id} · state ${packet.state}`,
    sourceIdentity: packet.case_id,
  });

  packet.options.forEach((option) => {
    const optionId = `option:${option.option_id}`;
    addNode({
      id: optionId,
      kind: "option",
      label: option.label,
      detail: option.tradeoff,
      sourceIdentity: option.option_id,
      recommended: option.option_id === packet.recommended_option_id,
    });
    edges.push({
      source: decisionId,
      target: optionId,
      relationship: option.option_id === packet.recommended_option_id ? "CURRENT_RECOMMENDATION" : "AVAILABLE_OPTION",
      semantics: "deterministic decision packet",
    });
  });

  const top = packet.evidence.top_candidate;
  if (!top) {
    gaps.push("No ranked RCA candidate is present in the deterministic decision packet.");
    return {
      nodes,
      edges,
      gaps,
      sourceOfTruth: trace?.source_of_truth ?? "operational event model",
      projectionRole: trace?.projection_role ?? "RCA projection unavailable",
    };
  }

  const rcaId = `rca:${top.candidate_id}`;
  addNode({
    id: rcaId,
    kind: "rca",
    label: top.candidate_id,
    detail: `${top.candidate_type} · deterministic score ${top.score.toFixed(2)} (not probability)`,
    sourceIdentity: top.candidate_id,
  });
  const recommendedOptionNode = `option:${packet.recommended_option_id}`;
  edges.push({
    source: recommendedOptionNode,
    target: rcaId,
    relationship: "CURRENT_RCA_CONTEXT",
    semantics: "co-present in the deterministic decision packet; not a causal or Neo4j authority edge",
  });

  const sourceEvents = new Map(
    (trace?.timeline ?? [])
      .filter((item) => item.kind === "source_event" && item.event_id)
      .map((item) => [String(item.event_id), item]),
  );

  const attachEvidence = (records: Array<Record<string, unknown>>, kind: "support" | "contradict") => {
    records.forEach((record, index) => {
      const identity = evidenceIdentity(record);
      if (!identity) {
        gaps.push(`${kind} evidence record ${index + 1} has no source identity field; omitted rather than assigned a fabricated graph ID.`);
        return;
      }
      const evidenceId = `evidence:${identity.identity}`;
      addNode({
        id: evidenceId,
        kind: "evidence",
        label: identity.label,
        detail: evidenceDetail(record) || "source-linked RCA evidence",
        sourceIdentity: identity.identity,
        evidenceKind: kind,
      });
      edges.push({
        source: rcaId,
        target: evidenceId,
        relationship: kind === "support" ? "SUPPORTED_BY" : "CONTRADICTED_BY",
        semantics: "deterministic RCA evidence record",
      });

      const rawEventId = typeof record.event_id === "string" ? record.event_id : null;
      if (!rawEventId) {
        gaps.push(`${identity.identity} is source-linked evidence but has no event_id bridge into the replay event log.`);
        return;
      }
      const event = sourceEvents.get(rawEventId);
      if (!event) {
        gaps.push(`event_id:${rawEventId} is referenced by RCA evidence but is absent from the current case replay slice.`);
        return;
      }
      const sourceEventId = `source-event:${rawEventId}`;
      addNode({
        id: sourceEventId,
        kind: "source_event",
        label: event.event_type,
        detail: `${event.time_semantics} · sequence ${event.sequence}`,
        sourceIdentity: rawEventId,
      });
      edges.push({
        source: evidenceId,
        target: sourceEventId,
        relationship: "SOURCED_FROM",
        semantics: "exact event_id match",
      });

      const processRunId = event.payload.process_run_id;
      if (typeof processRunId !== "string" || !processRunId) return;
      const processNodeId = `process-run:${processRunId}`;
      addNode({
        id: processNodeId,
        kind: "process_run",
        label: `Process run ${shortIdentity(processRunId)}`,
        detail: `step ${String(event.payload.step_id ?? "unknown")} · recipe ${String(event.payload.recipe_id ?? "unknown")}`,
        sourceIdentity: processRunId,
      });
      edges.push({
        source: sourceEventId,
        target: processNodeId,
        relationship: "IN_PROCESS_RUN",
        semantics: "exact process_run_id from source event payload",
      });
    });
  };

  attachEvidence(top.supporting_evidence, "support");
  attachEvidence(top.contradicting_evidence, "contradict");

  return {
    nodes,
    edges,
    gaps: Array.from(new Set(gaps)),
    sourceOfTruth: trace?.source_of_truth ?? "operational event model",
    projectionRole: trace?.projection_role ?? "RCA projection unavailable",
  };
}
