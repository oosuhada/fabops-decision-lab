import {fireEvent, render, screen} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";
import App from "./App";
import {WorkbenchState} from "./components";
import {ReplayOperations} from "./screens";

const projection = {projection_version: "rca-graph-v1.0.0", source_checkpoint: 3, projection_checkpoint: 3, lag_events: 0, stale: false};
const fabCase = {
  case_id: "CASE-1", lot_id: "LOT-00002", classification: "physical_excursion", detector_version: "spc-ewma-v1.0.0",
  anomaly_score: 1.2, mean_yield: 0.8, affected_scope: {equipment: ["ETCH-01"], chambers: ["ETCH-01-A"]},
  evidence_event_ids: ["evt-1"], data_quality_incidents: [], state: "detected",
};
const overview = {source: "synthetic", source_timestamp: "2026-01-01T00:00:00Z", projection, metrics: {active_cases: 1, physical_excursions: 1, sensor_bias_cases: 0, data_quality_cases: 0, event_count: 3, quarantine_count: 0}, cases: [fabCase]};
const detail = {source: "inferred", case: fabCase, rca: {projection, candidates: [{candidate_id: "chamber:ETCH-01-A", candidate_type: "chamber", score: .9, score_components: {}, supporting_evidence: [{type: "alarm"}], contradicting_evidence: [], recommended_action: "inspect"}]}, trace: {projection, affected_lots: [fabCase.lot_id], process_path: [{lot_id: fabCase.lot_id, process_run_id: "run-1", step_id: "ETCH", equipment_id: "ETCH-01", chamber_id: "ETCH-01-A", recipe_id: "R-v2"}]}, evidence_series: {measurements: [{event_id: "evt-1", lot_id: fabCase.lot_id, process_run_id: "run-1", step_id: "ETCH", sensor_name: "temperature", value: 12, unit: "normalized-unit", equipment_id: "ETCH-01", chamber_id: "ETCH-01-A", event_time: "2026-01-01T00:01:00Z"}], inspections: []}, audit: []};
const advisory = {source: "inferred-advisory", llm_enabled: false, result: {provider: "deterministic-advisory-v1.1.0", status: "ready", classification: "physical_excursion", claims: [{claim: "supported", supported_by: [{type: "alarm"}], contradicted_by: []}], counter_evidence: [], recommended_next_step: "inspect chamber", tool_calls: [{tool: "get_excursion_summary", status: "ok"}], errors: []}};
const decisionPacket = {
  schema_version: "decision-packet-v1", case_id: fabCase.case_id, lot_id: fabCase.lot_id, classification: fabCase.classification, state: fabCase.state,
  decision_question: "Should the team collect confirming evidence first or prepare a governed containment review for this excursion?",
  priority_band: "HIGH", priority_rank: 3, recommended_option_id: "confirm_evidence",
  options: [
    {option_id: "confirm_evidence", label: "Collect confirming metrology", stance: "recommended", tradeoff: "Reduce false containment risk.", requires_human_approval: false},
    {option_id: "containment_review", label: "Prepare containment review", stance: "conditional", tradeoff: "Human decision required.", requires_human_approval: true},
  ],
  impact: {synthetic_yield_gap_percentage_points: 20, affected_equipment_count: 1, affected_chamber_count: 1, affected_lot_count: 1, basis: "synthetic inspection yield and inferred affected scope"},
  evidence: {anomaly_score: 1.2, mean_yield: .8, affected_scope: fabCase.affected_scope, top_candidate: {candidate_id: "chamber:ETCH-01-A", candidate_type: "chamber", score: .9, supporting_evidence: [{type: "alarm"}], contradicting_evidence: []}, advisory_status: "ready", advisory_next_step: "inspect", data_quality_incidents: []},
  uncertainties: ["No explicit contradicting evidence is recorded."], evidence_refs: ["rca.top_candidate"], provenance: {input: "synthetic", equipment_control: false},
};
const cockpit = {schema_version: "decision-cockpit-v1", source: "synthetic-events-and-inferred-cases", summary: {decision_count: 1, high_priority: 1, medium_priority: 0, data_verification: 0}, queue: [decisionPacket]};
const decisionBrief = {source: "inferred-decision-support", packet: decisionPacket, brief: {schema_version: "decision-brief-v1", case_id: fabCase.case_id, audience: "manager", mode: "deterministic_fallback", provider: "deterministic", fallback_reason: "llm_not_configured", headline: "HIGH decision · LOT-00002", summary: "Grounded summary", recommended_option_id: "confirm_evidence", sections: [{section_id: "impact", title: "Operational impact", body: "Synthetic scope only.", evidence_refs: ["case.affected_scope"]}], citations: ["rca.top_candidate"], uncertainties: [], limitations: [], generated_at: "2026-01-01T00:00:00Z"}};
const evaluation = {source: "generated-evaluation-evidence", versions: {detector: "spc-ewma-v1.0.0", projection: "rca-graph-v1.0.0", advisory: "deterministic-advisory-v1.1.0"}, metrics: {detector: {fault_recall: 1, false_alarms_per_simulated_day: 0}, rca: {top1_accuracy: 1, mrr: 1, false_causal_attribution_rate: 0}}, limitations: ["synthetic only"]};
const replay = {source: "synthetic-replay", event_count: 3, detection_checkpoint: 3, projection, outbox_count: 3, quarantine_count: 0, delivery_status_counts: {on_time: 3, late: 0, out_of_order: 0}, external_services: {postgres: true, redpanda: true, neo4j: true, external_llm: "disabled-not-required"}, integration: {status: "verified", compose_config_verified: true, postgres_runtime_verified: true, redpanda_runtime_verified: true, neo4j_runtime_verified: true, container_integration_verified: true, reason: null}, release: {release_version: "0.6.0", release_hash: "a".repeat(64), source_git_commit: "b".repeat(40), manifest_available: true}};

describe("FabOps workbench", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const value = url.endsWith("/api/decision-cockpit") ? cockpit : url.includes("/decision-brief?") ? decisionBrief : url.endsWith("/api/overview") ? overview : url.endsWith("/api/evaluation") ? evaluation : url.endsWith("/api/replay") ? replay : url.endsWith("/advisory") ? advisory : detail;
      return new Response(JSON.stringify(value), {status: 200, headers: {"Content-Type": "application/json"}});
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("opens on an API-backed decision cockpit instead of a generic metric dashboard", async () => {
    render(<App />);
    expect(await screen.findByRole("heading", {name: "What needs a decision now?"})).toBeInTheDocument();
    expect(screen.getAllByText("LOT-00002").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Collect confirming metrology", {exact: false}).length).toBeGreaterThan(1);
    expect(screen.getByText("Prepare containment review", {exact: false})).toBeInTheDocument();
    expect(screen.getByText("READ-ONLY PREVIEW")).toBeInTheDocument();
    expect(screen.getByText("0.6.0", {exact: true})).toBeInTheDocument();
  });

  it("coordinates evidence graph selection and exposes no equipment execution control", async () => {
    render(<App />);
    await screen.findByRole("heading", {name: "What needs a decision now?"});
    fireEvent.click(screen.getByRole("button", {name: /Evidence Graph/i}));
    expect(await screen.findByRole("heading", {name: /LOT-00002 lineage/})).toBeInTheDocument();
    expect(screen.getByRole("button", {name: /ETCH/i})).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", {name: /Decision & Approval/i}));
    expect(await screen.findByRole("heading", {name: /Should the team collect confirming evidence first/i})).toBeInTheDocument();
    expect(screen.getByText("Choose a stance, not an opaque AI answer")).toBeInTheDocument();
    expect(screen.getAllByText("NO TOOL CONTROL").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", {name: /execute equipment/i})).not.toBeInTheDocument();
  });

  it("renders unauthorized state as an alert", () => {
    render(<WorkbenchState kind="unauthorized" title="Not authorized" detail="Approval role required" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Approval role required");
  });

  it("renders verified, degraded and unverified integration state from API data", () => {
    const {rerender} = render(<ReplayOperations replay={replay} />);
    expect(screen.getByRole("status")).toHaveTextContent("Container integration verified");

    rerender(<ReplayOperations replay={{...replay, integration: {...replay.integration, status: "degraded", container_integration_verified: false, reason: "Neo4j unavailable"}}} />);
    expect(screen.getByRole("status")).toHaveTextContent("Container integration degraded");
    expect(screen.getByRole("status")).toHaveTextContent("Neo4j unavailable");

    rerender(<ReplayOperations replay={{...replay, integration: {...replay.integration, status: "unverified", container_integration_verified: false, reason: "No integration evidence"}}} />);
    expect(screen.getByRole("status")).toHaveTextContent("Container integration unverified");
  });
});

