export type ScreenId = "cockpit" | "overview" | "case" | "graph" | "analysis" | "decision" | "evaluation" | "replay";

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
      score_components: Record<string, number>;
      score_explanation?: {
        contract_version: string;
        formula: string;
        components: Array<{component_id: string; direction: "support" | "contradict" | "neutral"; raw_value: number; signed_value: number}>;
        reconstructed_score: number;
        reported_score: number;
        faithful: boolean;
        probability: false;
      } | null;
      supporting_evidence: Array<Record<string, unknown>>;
      contradicting_evidence: Array<Record<string, unknown>>;
    };
    advisory_status: string;
    advisory_next_step: string;
    data_quality_incidents: string[];
  };
  uncertainties: string[];
  decision_boundary?: {
    contract_version: string;
    confidence_semantics: string;
    target_option_id: string;
    all_conditions_met: boolean;
    conditions: Array<{
      condition_id: string;
      label: string;
      status: "met" | "unmet" | "unknown";
      current_value: string | number | null;
      required: string;
      evidence_refs: string[];
    }>;
    policy_statement: string;
  };
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
    latency_ms?: number;
    headline: string;
    summary: string;
    recommended_option_id: string;
    sections: Array<{section_id: string; title: string; body: string; evidence_refs: string[]}>;
    citations: string[];
    uncertainties: string[];
    limitations: string[];
    generated_at: string;
    intent?: string;
    presentation?: {
      schema_version: "presentation-spec-v1";
      renderer_contract: "known-components-only";
      case_id: string;
      intent: string;
      execution_capabilities: [];
      blocks: Array<{
        type: "SummaryCard" | "Checklist" | "ComparisonCard" | "EvidenceTable" | "Timeline" | "RiskMatrix" | "MiniGraph" | "ChartSpec";
        title: string;
        body?: string;
        evidence_refs: string[];
        recommended_option_id?: string;
        options?: Array<{option_id: string; label: string; stance: string; tradeoff: string; requires_human_approval: boolean}>;
        items?: Array<{label: string; detail: string; evidence_refs: string[]}>;
        candidate_id?: string | null;
        rows?: Array<{kind: "support" | "contradict"; record_index: number; summary: string}>;
      }>;
    };
  };
}

export interface NarrationStatusResponse {
  source: string;
  public_get_mode: "cache_only" | string;
  provider_health: {
    local_llm: "healthy" | "degraded" | "offline" | "circuit_open" | string;
    vertex: "healthy" | "degraded" | "disabled" | "budget_exhausted" | "unconfigured" | "circuit_open" | string;
  };
  narration: {last_source: "cached" | "local" | "vertex" | "deterministic_fallback" | string};
  public_demo: {
    enabled: boolean;
    session_ttl_seconds?: number;
    max_generations_per_session?: number;
    max_generations_per_ip_hour?: number;
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
  validation_console?: {
    evidence_schema_version?: string;
    held_out_seed_metrics: Array<{
      seed: number;
      fault_recall: number;
      false_alarms_per_simulated_day: number;
      rca_top1: number;
      rca_top3: number;
      contradicting_evidence_coverage: number;
    }>;
    seed_ranges: Record<string, {mean: number; minimum: number; maximum: number} | null>;
    fault_family_slices: Array<{family: string; seed_count: number; mean_case_count: number; rca_top1: number; agent_ready_rate: number}>;
    unseen_family_results: Array<{
      family: string;
      expected_behavior: string;
      actual_status: string;
      appropriate: boolean;
      claim_count: number;
      physical_action_proposed: boolean;
      tool_calls: string[];
    }>;
    common_random_number_comparison: {
      current_detector?: {fault_recall: number; version: string};
      legacy_detector?: {fault_recall: number; version: string};
      seeds?: number[];
    };
    claims_boundary: Record<string, unknown>;
    evidence_gaps: string[];
  };
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

export interface CaseReplayTraceResponse {
  source: string;
  case_id: string;
  lot_id: string;
  source_of_truth: string;
  projection_role: string;
  timeline: Array<{
    timeline_id: string;
    kind: "source_event" | "audit_event" | "projection_snapshot";
    phase: string;
    sequence: number;
    event_time: string | null;
    time_semantics: "source_event_time" | "trigger_event_time" | "audit_sequence_only" | "current_rebuildable_snapshot" | string;
    event_type: string;
    event_id: string | null;
    delivery_status: string | null;
    source: string;
    payload: Record<string, unknown>;
  }>;
  summary: {
    source_event_count: number;
    audit_event_count: number;
    projection_snapshot_count: number;
    out_of_order_count: number;
    late_count: number;
  };
  limitations: string[];
}

