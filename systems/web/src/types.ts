export type ScreenId = "cockpit" | "overview" | "case" | "graph" | "decision" | "evaluation" | "replay";

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

export interface DecisionOption {
  option_id: string;
  label: string;
  stance: "recommended" | "alternative" | "conditional" | "guardrail" | string;
  tradeoff: string;
  requires_human_approval: boolean;
}

export interface DecisionPacket {
  schema_version: string;
  case_id: string;
  lot_id: string;
  classification: string;
  state: string;
  decision_question: string;
  priority_band: "HIGH" | "MEDIUM" | "VERIFY_DATA" | string;
  priority_rank: number;
  recommended_option_id: string;
  options: DecisionOption[];
  impact: {
    synthetic_yield_gap_percentage_points: number | null;
    affected_equipment_count: number;
    affected_chamber_count: number;
    affected_lot_count: number;
    basis: string;
  };
  evidence: {
    anomaly_score: number;
    mean_yield: number | null;
    affected_scope: {equipment: string[]; chambers: string[]};
    top_candidate: null | {
      candidate_id: string;
      candidate_type: string;
      score: number;
      supporting_evidence: Array<Record<string, unknown>>;
      contradicting_evidence: Array<Record<string, unknown>>;
    };
    advisory_status: string;
    advisory_next_step: string;
    data_quality_incidents: string[];
  };
  uncertainties: string[];
  evidence_refs: string[];
  provenance: Record<string, string | boolean>;
}

export interface DecisionCockpitResponse {
  schema_version: string;
  source: string;
  summary: {
    decision_count: number;
    high_priority: number;
    medium_priority: number;
    data_verification: number;
  };
  queue: DecisionPacket[];
}

export interface DecisionBriefResponse {
  source: string;
  session_id?: string;
  packet: DecisionPacket;
  brief: {
    schema_version: string;
    case_id: string;
    audience: "manager" | "engineer";
    mode: "llm" | "deterministic_fallback" | string;
    provider: string;
    fallback_reason?: string | null;
    cache_hit?: boolean;
    headline: string;
    summary: string;
    recommended_option_id: string;
    sections: Array<{section_id: string; title: string; body: string; evidence_refs: string[]}>;
    citations: string[];
    uncertainties: string[];
    limitations: string[];
    generated_at: string;
    intent?: string;
  };
}

export type NarrationIntent = "manager_summary" | "engineer_checklist" | "tradeoff_compare" | "counter_evidence";

export interface DemoSessionResponse {
  source: string;
  token: string;
  expires_at: string;
  generation_limit: number;
  allowed_intents: NarrationIntent[];
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

