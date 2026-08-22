from __future__ import annotations

import json

from fastapi.testclient import TestClient

from services.observability.context import canonical_trace_id
from systems.api.app import app
from systems.api.runtime import build_local_runtime


def test_api_propagates_causal_trace_and_operational_correlation_without_sensitive_fields() -> None:
    runtime = build_local_runtime()
    app.state.runtime = runtime
    client = TestClient(app)
    case = runtime.case_repository.list_cases()[0]
    case_id = case["case_id"]
    causal_trace_id = case["causal_trace_id"]
    correlation_id = "m6-test-correlation"
    headers = {"X-Correlation-ID": correlation_id, "X-FabOps-Trace-ID": canonical_trace_id(causal_trace_id)}
    request_record_start = len(runtime.telemetry.records())

    detail = client.get(f"/api/cases/{case_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.headers["X-Correlation-ID"] == correlation_id
    assert detail.headers["X-FabOps-Trace-ID"] == canonical_trace_id(causal_trace_id)

    advisory = client.get(f"/api/cases/{case_id}/advisory", headers=headers)
    assert advisory.status_code == 200
    proposed = client.post(
        f"/api/cases/{case_id}/actions/propose",
        headers={**headers, "X-FabOps-Role": "process_engineer", "X-FabOps-Actor": "m6-tester"},
        json={"action_type": "diagnostic_review", "target": case["lot_id"], "rationale": "M6 trace propagation"},
    )
    assert proposed.status_code == 200
    approved = client.post(
        f"/api/cases/{case_id}/actions/approve",
        headers={**headers, "X-FabOps-Role": "yield_lead", "X-FabOps-Actor": "m6-lead"},
        json={"reason": "M6 trace propagation approval"},
    )
    assert approved.status_code == 200
    closed = client.post(
        f"/api/cases/{case_id}/close",
        headers={**headers, "X-FabOps-Role": "yield_lead", "X-FabOps-Actor": "m6-lead"},
        json={"outcome": "M6 trace propagation closed"},
    )
    assert closed.status_code == 200

    records = [record for record in runtime.telemetry.records()[request_record_start:] if record.get("case_id") == case_id]
    operations = {record["operation"] for record in records}
    assert {"rca.query", "advisory.tool_call", "advisory.advise", "workflow.action_proposed", "workflow.action_approved", "workflow.case_closed"} <= operations
    assert all(record["trace_id"] == canonical_trace_id(causal_trace_id) for record in records)
    assert all(record["correlation_id"] == correlation_id for record in records)
    serialized = json.dumps(runtime.telemetry.records(), sort_keys=True)
    assert "ground_truth" not in serialized
    approval_records = [record for record in records if record["operation"] == "workflow.action_approved"]
    assert approval_records[0]["approval_token"] == "[REDACTED]"


def test_health_readiness_is_dynamic_and_distinguishes_integration_state() -> None:
    runtime = build_local_runtime()
    healthy = runtime.health_status()
    assert healthy["ready"] is True
    assert healthy["source_of_truth"]["production_authority"] == "postgresql"
    assert healthy["advisory"]["external_llm_state"] == "disabled-optional"
    assert healthy["equipment_control_enabled"] is False
    assert "container_integration_verified" in healthy["integration"]

    runtime.projection.projection_checkpoint -= 1
    degraded = runtime.health_status()
    assert degraded["ready"] is False
    assert degraded["projection"]["stale"] is True
