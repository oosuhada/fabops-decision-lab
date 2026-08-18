from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.advisory.provider import DeterministicAdvisoryProvider
from services.workflow.state_machine import ApprovalTokenIssuer, AuthorizationError, CaseWorkflowService, InvalidTransitionError
from systems.api.app import _cors_origins_from_env, app
from systems.api.runtime import build_local_runtime


def test_cors_origins_keep_safe_defaults_and_allow_explicit_isolated_web_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FABOPS_CORS_ORIGINS", "http://127.0.0.1:35173")
    origins = _cors_origins_from_env()

    assert "http://127.0.0.1:5173" in origins
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:35173" in origins


def test_tool_registry_is_capped_at_exact_required_five_tools():
    runtime = build_local_runtime()
    assert runtime.tools.names == (
        "get_excursion_summary",
        "compare_chamber_baselines",
        "trace_affected_lots",
        "find_related_alarms_and_changes",
        "retrieve_sop_and_past_cases",
    )
    assert len(runtime.tools.names) == 5


def test_deterministic_advisory_uses_evidence_and_does_not_need_llm():
    runtime = build_local_runtime()
    case = next(case for case in runtime.case_repository.list_cases() if case["lot_id"] == "LOT-00002")
    result = runtime.advisory.advise(case["case_id"])
    assert result["status"] == "ready"
    assert len(result["tool_calls"]) == 4
    assert result["claims"][0]["supported_by"]
    assert "equipment_execution" in result["prohibited_capabilities"]


def test_advisory_abstains_when_required_summary_tool_errors():
    runtime = build_local_runtime()
    original = runtime.tools._tools["get_excursion_summary"]

    def fail(_: str):
        raise RuntimeError("fixture tool failure")

    runtime.tools._tools["get_excursion_summary"] = fail
    provider = DeterministicAdvisoryProvider(runtime.tools)
    case_id = runtime.case_repository.list_cases()[0]["case_id"]
    result = provider.advise(case_id)
    runtime.tools._tools["get_excursion_summary"] = original
    assert result["status"] == "abstain"
    assert result["recommended_next_step"] == "request_more_evidence"
    assert result["claims"] == []


def test_workflow_requires_proposal_then_authorized_human_approval():
    runtime = build_local_runtime()
    case = runtime.case_repository.list_cases()[0]
    proposed = runtime.workflow.propose_action(
        case["case_id"], "eng-1", "process_engineer", "diagnostic_inspection", case["lot_id"], "verify metrology before containment"
    )
    assert proposed["state"] == "proposed"
    try:
        runtime.workflow.approve(case["case_id"], "eng-1", "process_engineer", "self approve")
        raise AssertionError("engineer approval should be forbidden")
    except AuthorizationError:
        pass
    approved = runtime.workflow.approve(case["case_id"], "lead-1", "yield_lead", "evidence sufficient for diagnostic action")
    assert approved["state"] == "approved"
    assert approved["approval"]["actual_equipment_execution"] is False
    assert approved["approval"]["approval_token"].startswith("fabops-local-policy.")
    closed = runtime.workflow.close(case["case_id"], "lead-1", "yield_lead", "diagnostic action recorded; no physical execution performed")
    assert closed["state"] == "closed"


def test_forbidden_actual_equipment_action_cannot_be_proposed():
    runtime = build_local_runtime()
    case = runtime.case_repository.list_cases()[0]
    try:
        runtime.workflow.propose_action(case["case_id"], "eng-1", "process_engineer", "execute_equipment_control", "ETCH-01", "stop tool")
        raise AssertionError("physical equipment mutation must be blocked")
    except AuthorizationError:
        pass


def test_timeout_enters_manual_intervention_with_no_automatic_compensation():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = {"now": now}
    runtime = build_local_runtime()
    workflow = CaseWorkflowService(
        runtime.case_repository,
        ApprovalTokenIssuer(b"test"),
        clock=lambda: state["now"],
        proposal_timeout=timedelta(minutes=30),
    )
    case = runtime.case_repository.list_cases()[0]
    workflow.propose_action(case["case_id"], "eng-1", "process_engineer", "diagnostic_inspection", case["lot_id"], "fixture")
    state["now"] = now + timedelta(minutes=31)
    assert workflow.check_timeouts() == [case["case_id"]]
    escalated = runtime.case_repository.get_case(case["case_id"])
    assert escalated is not None
    assert escalated["state"] == "manual_intervention"
    assert escalated["compensation"]["automatic_equipment_action"] is False


def test_api_end_to_end_llm_off_and_ground_truth_not_exposed():
    app.state.runtime = build_local_runtime()
    client = TestClient(app)
    overview = client.get("/api/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["metrics"]["active_cases"] == 7
    assert "ground_truth" not in overview.text
    case_id = body["cases"][0]["case_id"]
    advisory = client.get(f"/api/cases/{case_id}/advisory")
    assert advisory.status_code == 200
    assert advisory.json()["llm_enabled"] is False
    assert "ground_truth" not in advisory.text
    propose = client.post(
        f"/api/cases/{case_id}/actions/propose",
        headers={"X-FabOps-Role": "process_engineer", "X-FabOps-Actor": "eng-1"},
        json={"action_type": "diagnostic_inspection", "target": "LOT-00002", "rationale": "collect confirming metrology"},
    )
    assert propose.status_code == 200
    denied = client.post(
        f"/api/cases/{case_id}/actions/approve",
        headers={"X-FabOps-Role": "process_engineer", "X-FabOps-Actor": "eng-1"},
        json={"reason": "self approval must fail"},
    )
    assert denied.status_code == 403
    approved = client.post(
        f"/api/cases/{case_id}/actions/approve",
        headers={"X-FabOps-Role": "yield_lead", "X-FabOps-Actor": "lead-1"},
        json={"reason": "evidence checked; approve diagnostic only"},
    )
    assert approved.status_code == 200
    assert approved.json()["case"]["approval"]["actual_equipment_execution"] is False


def test_api_visible_metrics_match_case_and_replay_state():
    app.state.runtime = build_local_runtime()
    client = TestClient(app)
    overview = client.get("/api/overview").json()
    replay = client.get("/api/replay").json()
    cases = client.get("/api/cases").json()["items"]
    assert overview["metrics"]["active_cases"] == len(cases)
    assert overview["metrics"]["event_count"] == replay["event_count"]
    assert replay["event_count"] == replay["detection_checkpoint"] == replay["projection"]["projection_checkpoint"]


def test_case_replay_trace_is_source_backed_and_never_fabricates_missing_audit_timestamps():
    runtime = build_local_runtime()
    app.state.runtime = runtime
    client = TestClient(app)
    case = runtime.case_repository.list_cases()[0]
    response = client.get(f"/api/cases/{case['case_id']}/replay-trace")
    assert response.status_code == 200
    body = response.json()
    source_rows = [item for item in body["timeline"] if item["kind"] == "source_event"]
    audit_rows = [item for item in body["timeline"] if item["kind"] == "audit_event"]
    projection_rows = [item for item in body["timeline"] if item["kind"] == "projection_snapshot"]
    expected_event_ids = {
        stored.event["event_id"]
        for stored in runtime.event_repository.all_events()
        if stored.event.get("lot_id") == case["lot_id"]
    }
    assert {item["event_id"] for item in source_rows} == expected_event_ids
    assert all("ground_truth" not in item["payload"] for item in source_rows)
    assert projection_rows[0]["source"] == "neo4j-rebuildable-projection"
    assert body["projection_role"] == "rebuildable RCA/read projection"
    assert audit_rows
    assert all(
        item["event_time"] is not None or item["time_semantics"] == "audit_sequence_only"
        for item in audit_rows
    )


def test_evaluation_api_reads_checked_in_release_evidence_when_present():
    app.state.runtime = build_local_runtime()
    client = TestClient(app)
    response = client.get("/api/evaluation")
    assert response.status_code == 200
    body = response.json()
    if body.get("evidence_hash"):
        release = json.loads(Path("evidence/release/evaluation-summary.json").read_text(encoding="utf-8"))
        assert body["evidence_hash"] == release["canonical_hash"]
        assert body["metrics"] == release["held_out_metrics"]
        assert body["negative_results"] == release["negative_results"]
        console = body["validation_console"]
        assert [row["family"] for row in console["fault_family_slices"]] == ["F1", "F2", "F3", "F4", "F5", "F6"]
        assert console["seed_ranges"]["contradicting_evidence_coverage"] == {
            "mean": 0.42857,
            "minimum": 0.42857,
            "maximum": 0.42857,
        }
        assert console["common_random_number_comparison"] == release["common_random_number_comparison"]
        assert all(item["appropriate"] for item in console["unseen_family_results"])
        assert any("not persisted" in gap for gap in console["evidence_gaps"])


def test_rejection_and_request_evidence_transitions_are_explicit():
    runtime = build_local_runtime()
    first, second = runtime.case_repository.list_cases()[:2]
    requested = runtime.workflow.request_evidence(first["case_id"], "eng-1", "process_engineer", "need independent metrology")
    assert requested["state"] == "evidence_requested"
    proposed = runtime.workflow.propose_action(second["case_id"], "eng-1", "process_engineer", "diagnostic_inspection", second["lot_id"], "verify")
    assert proposed["state"] == "proposed"
    rejected = runtime.workflow.reject(second["case_id"], "lead-1", "yield_lead", "insufficient supporting evidence")
    assert rejected["state"] == "rejected"
    try:
        runtime.workflow.close(first["case_id"], "lead-1", "yield_lead", "premature")
        raise AssertionError("evidence requested case cannot close directly")
    except InvalidTransitionError:
        pass

