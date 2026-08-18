import type {CaseDetailResponse} from "../../types";

export type EvidenceGraphNodeType = "Case" | "Lot" | "ProcessRun" | "Step" | "Equipment" | "Chamber" | "Measurement" | "Inspection" | "Wafer" | "RCACandidate" | "EvidenceRecord";

export interface EvidenceGraphNode {
  id: string;
  type: EvidenceGraphNodeType;
  label: string;
  subtitle: string;
  properties: Record<string, string | number | boolean | null>;
  provenance: "source" | "projection" | "inferred";
  emphasis?: "top-rca" | "support" | "contradict";
}

export interface EvidenceGraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  emphasis?: "support" | "contradict";
  provenance: "authoritative-source-link" | "rebuildable-projection-link" | "system-inference-link";
  sourceIdentity?: string;
}

export interface EvidenceGraphModel {
  nodes: EvidenceGraphNode[];
  edges: EvidenceGraphEdge[];
}

function stableValue(value: unknown): string | number | boolean | null {
  if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") return value;
  return JSON.stringify(value);
}

function evidenceLabel(item: Record<string, unknown>) {
  const type = String(item.type ?? "evidence");
  const detail = item.detail ?? item.alarm_code ?? item.incident_type ?? item.sensor ?? item.defect_patterns ?? "linked record";
  return {label: type.replaceAll("_", " "), subtitle: String(detail)};
}

export function buildEvidenceGraph(detail: CaseDetailResponse): EvidenceGraphModel {
  const nodes = new Map<string, EvidenceGraphNode>();
  const edges = new Map<string, EvidenceGraphEdge>();

  const addNode = (node: EvidenceGraphNode) => nodes.set(node.id, node);
  const addEdge = (edge: EvidenceGraphEdge) => edges.set(edge.id, edge);

  const caseNodeId = `case:${detail.case.case_id}`;
  const lotNodeId = `lot:${detail.case.lot_id}`;
  addNode({
    id: caseNodeId,
    type: "Case",
    label: detail.case.case_id,
    subtitle: detail.case.classification.replaceAll("_", " "),
    properties: {state: detail.case.state, anomaly_score: detail.case.anomaly_score, detector_version: detail.case.detector_version},
    provenance: "inferred",
  });
  addNode({
    id: lotNodeId,
    type: "Lot",
    label: detail.case.lot_id,
    subtitle: "synthetic lot",
    properties: {mean_yield: detail.case.mean_yield, evidence_events: detail.case.evidence_event_ids.length},
    provenance: "source",
  });
  addEdge({id: `${caseNodeId}->${lotNodeId}`, source: caseNodeId, target: lotNodeId, type: "CASE_FOR_LOT", provenance: "system-inference-link", sourceIdentity: detail.case.case_id});

  for (const path of detail.trace.process_path) {
    const runId = `run:${path.process_run_id}`;
    const stepId = `step:${path.process_run_id}:${path.step_id}`;
    addNode({id: runId, type: "ProcessRun", label: path.process_run_id, subtitle: path.recipe_id, properties: {step_id: path.step_id, recipe_id: path.recipe_id}, provenance: "projection"});
    addNode({id: stepId, type: "Step", label: path.step_id, subtitle: path.recipe_id, properties: {step_id: path.step_id, process_run_id: path.process_run_id}, provenance: "projection"});
    addEdge({id: `${lotNodeId}->${runId}`, source: lotNodeId, target: runId, type: "PROCESSED_BY", provenance: "rebuildable-projection-link", sourceIdentity: path.process_run_id});
    addEdge({id: `${runId}->${stepId}`, source: runId, target: stepId, type: "HAS_STEP", provenance: "rebuildable-projection-link", sourceIdentity: path.process_run_id});

    if (path.equipment_id) {
      const equipmentId = `equipment:${path.equipment_id}`;
      addNode({id: equipmentId, type: "Equipment", label: path.equipment_id, subtitle: "equipment", properties: {equipment_id: path.equipment_id}, provenance: "projection"});
      addEdge({id: `${runId}->${equipmentId}`, source: runId, target: equipmentId, type: "USED_EQUIPMENT", provenance: "rebuildable-projection-link", sourceIdentity: path.process_run_id});
    }
    if (path.chamber_id) {
      const chamberId = `chamber:${path.chamber_id}`;
      addNode({id: chamberId, type: "Chamber", label: path.chamber_id, subtitle: "chamber", properties: {chamber_id: path.chamber_id}, provenance: "projection"});
      addEdge({id: `${runId}->${chamberId}`, source: runId, target: chamberId, type: "USED_CHAMBER", provenance: "rebuildable-projection-link", sourceIdentity: path.process_run_id});
    }
  }

  for (const measurement of detail.evidence_series.measurements) {
    const measurementId = `measurement:${measurement.event_id}`;
    const runId = `run:${measurement.process_run_id}`;
    addNode({
      id: measurementId,
      type: "Measurement",
      label: measurement.sensor_name,
      subtitle: `${measurement.value.toFixed(3)} ${measurement.unit}`,
      properties: {
        event_id: measurement.event_id,
        step_id: measurement.step_id,
        chamber_id: measurement.chamber_id,
        equipment_id: measurement.equipment_id,
        event_time: measurement.event_time,
        value: measurement.value,
        unit: measurement.unit,
      },
      provenance: "source",
    });
    if (nodes.has(runId)) addEdge({id: `${runId}->${measurementId}`, source: runId, target: measurementId, type: "HAS_MEASUREMENT", provenance: "authoritative-source-link", sourceIdentity: measurement.event_id});
  }

  for (const inspection of detail.evidence_series.inspections) {
    const waferId = `wafer:${inspection.wafer_id}`;
    const inspectionId = `inspection:${inspection.inspection_id}`;
    addNode({id: waferId, type: "Wafer", label: inspection.wafer_id, subtitle: detail.case.lot_id, properties: {wafer_id: inspection.wafer_id}, provenance: "source"});
    addNode({
      id: inspectionId,
      type: "Inspection",
      label: inspection.defect_pattern,
      subtitle: `yield ${(inspection.yield * 100).toFixed(1)}%`,
      properties: {inspection_id: inspection.inspection_id, yield: inspection.yield, failed_die_ratio: inspection.failed_die_ratio, event_time: inspection.event_time, pattern_provenance: inspection.pattern_provenance},
      provenance: "source",
    });
    addEdge({id: `${lotNodeId}->${waferId}`, source: lotNodeId, target: waferId, type: "CONTAINS_WAFER", provenance: "authoritative-source-link", sourceIdentity: inspection.inspection_id});
    addEdge({id: `${waferId}->${inspectionId}`, source: waferId, target: inspectionId, type: "HAS_INSPECTION", provenance: "authoritative-source-link", sourceIdentity: inspection.inspection_id});
  }

  detail.rca.candidates.forEach((candidate, candidateIndex) => {
    const candidateId = `rca:${candidate.candidate_id}`;
    addNode({
      id: candidateId,
      type: "RCACandidate",
      label: candidate.candidate_id,
      subtitle: `score ${candidate.score.toFixed(2)} · ${candidate.candidate_type}`,
      properties: {score: candidate.score, candidate_type: candidate.candidate_type, recommended_action: candidate.recommended_action},
      provenance: "inferred",
      emphasis: candidateIndex === 0 ? "top-rca" : undefined,
    });
    addEdge({id: `${caseNodeId}->${candidateId}`, source: caseNodeId, target: candidateId, type: "HAS_RCA_CANDIDATE", provenance: "system-inference-link", sourceIdentity: candidate.candidate_id});

    const records: Array<{kind: "support" | "contradict"; item: Record<string, unknown>}> = [
      ...candidate.supporting_evidence.map((item) => ({kind: "support" as const, item})),
      ...candidate.contradicting_evidence.map((item) => ({kind: "contradict" as const, item})),
    ];
    records.forEach(({kind, item}, index) => {
      const recordId = `evidence:${candidateIndex}:${kind}:${index}`;
      const description = evidenceLabel(item);
      addNode({
        id: recordId,
        type: "EvidenceRecord",
        label: description.label,
        subtitle: description.subtitle,
        properties: Object.fromEntries(Object.entries(item).map(([key, value]) => [key, stableValue(value)])),
        provenance: "projection",
        emphasis: kind,
      });
      addEdge({id: `${recordId}->${candidateId}`, source: recordId, target: candidateId, type: kind === "support" ? "SUPPORTS" : "CONTRADICTS", emphasis: kind, provenance: "system-inference-link", sourceIdentity: candidate.candidate_id});
      const eventId = typeof item.event_id === "string" ? `measurement:${item.event_id}` : null;
      if (eventId && nodes.has(eventId)) addEdge({id: `${recordId}->${eventId}`, source: recordId, target: eventId, type: "DERIVED_FROM", provenance: "authoritative-source-link", sourceIdentity: String(item.event_id)});
    });
  });

  return {nodes: Array.from(nodes.values()), edges: Array.from(edges.values())};
}

export function graphNeighbors(model: EvidenceGraphModel, nodeId: string) {
  const linked = new Set<string>([nodeId]);
  for (const edge of model.edges) {
    if (edge.source === nodeId) linked.add(edge.target);
    if (edge.target === nodeId) linked.add(edge.source);
  }
  return linked;
}

