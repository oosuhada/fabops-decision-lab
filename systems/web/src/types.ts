export type ScreenId = "overview" | "case" | "graph" | "decision" | "evaluation" | "replay";

export interface ProjectionStatus {
  projection_version: string;
  source_checkpoint: number;
  projection_checkpoint: number;
  lag_events: number;
  stale: boolean;
}

export interface FabCase {
  case_id: string;
  lot_id: string;
  classification: "physical_excursion" | "sensor_bias_suspected" | "data_quality_incident" | string;
  detector_version: string;
  anomaly_score: number;
  mean_yield: number | null;
  affected_scope: {equipment: string[]; chambers: string[]};
  evidence_event_ids: string[];
  data_quality_incidents: string[];
  state: string;
  proposed_action?: Record<string, unknown>;
  approval?: Record<string, unknown>;
  rejection?: Record<string, unknown>;
}

export interface OverviewResponse {
  source: string;
  source_timestamp: string;
  projection: ProjectionStatus;
  metrics: {
    active_cases: number;
    physical_excursions: number;
    sensor_bias_cases: number;
    data_quality_cases: number;
    event_count: number;
    quarantine_count: number;
  };
  cases: FabCase[];
}

export interface RcaCandidate {
  candidate_id: string;
  candidate_type: string;
  score: number;
  score_components: Record<string, number>;
  supporting_evidence: Array<Record<string, unknown>>;
  contradicting_evidence: Array<Record<string, unknown>>;
  recommended_action: string;
}

export interface ProcessPathItem {
  lot_id: string;
  process_run_id: string;
  step_id: string;
  equipment_id: string | null;
  chamber_id: string | null;
  recipe_id: string;
}

export interface MeasurementPoint {
  event_id: string;
  lot_id: string;
  process_run_id: string;
  step_id: string;
  sensor_name: string;
  value: number;
  unit: string;
  equipment_id: string;
  chamber_id: string;
  event_time: string;
}

export interface InspectionPoint {
  inspection_id: string;
  lot_id: string;
  wafer_id: string;
  yield: number;
  failed_die_ratio: number;
  defect_pattern: string;
  pattern_provenance: string;
  event_time: string;
}

export interface CaseDetailResponse {
  source: string;
  case: FabCase;
  rca: {projection: ProjectionStatus; candidates: RcaCandidate[]};
  trace: {projection: ProjectionStatus; affected_lots: string[]; process_path: ProcessPathItem[]};
  evidence_series: {measurements: MeasurementPoint[]; inspections: InspectionPoint[]};
  audit: Array<Record<string, unknown>>;
}

export interface AdvisoryResponse {
  source: string;
  llm_enabled: boolean;
  result: {
    provider: string;
    status: "ready" | "abstain" | "degraded";
    classification?: string;
    claims: Array<{claim: string; supported_by: Array<Record<string, unknown>>; contradicted_by: Array<Record<string, unknown>>}>;
    counter_evidence?: Array<Record<string, unknown>>;
    recommended_next_step: string;
    tool_calls: Array<{tool: string; status: string}>;
    errors: Array<Record<string, string>>;
  };
}

export interface EvaluationResponse {
  source: string;
  evidence_hash?: string;
  versions: Record<string, string>;
  metrics: {
    detector: Record<string, number>;
    rca: Record<string, number>;
    agent?: Record<string, number>;
  };
  negative_results?: Array<{id: string; description: string}>;
  release_gate?: Array<{threshold: string; actual: number; operator: string; required: number; passed: boolean}>;
  release_passed?: boolean;
  limitations: string[];
}

export interface ReplayResponse {
  source: string;
  event_count: number;
  detection_checkpoint: number;
  projection: ProjectionStatus;
  outbox_count: number;
  quarantine_count: number;
  delivery_status_counts: Record<string, number>;
  external_services: Record<string, string | boolean>;
  integration: {
    status: "verified" | "degraded" | "unverified" | string;
    compose_config_verified: boolean;
    postgres_runtime_verified: boolean;
    redpanda_runtime_verified: boolean;
    neo4j_runtime_verified: boolean;
    container_integration_verified: boolean;
    reason?: string | null;
  };
  release: {
    release_version: string;
    release_hash: string;
    source_git_commit: string | null;
    manifest_available: boolean;
  };
}

