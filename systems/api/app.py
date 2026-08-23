from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.decision import DecisionSupportService
from services.narration import NarrationService
from services.rca.cqrs import RankRootCausesQuery, TraceAffectedLotsQuery
from services.release import RELEASE_VERSION, load_release_identity
from services.workflow.state_machine import AuthorizationError, InvalidTransitionError
from systems.api.runtime import LocalRuntime, build_runtime

app = FastAPI(
    title="FabOps Decision Lab API",
    version=RELEASE_VERSION,
    description="Deterministic local portfolio API. It does not control real fab equipment.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-FabOps-Role", "X-FabOps-Actor", "X-Correlation-ID", "X-FabOps-Trace-ID", "traceparent"],
    expose_headers=["X-Correlation-ID", "X-FabOps-Trace-ID"],
)
app.state.runtime = build_runtime()
app.state.narration_service = None


@app.middleware("http")
async def correlation_middleware(request: Request, call_next: Any) -> Any:
    runtime = get_runtime()
    trace_header = request.headers.get("traceparent") or request.headers.get("X-FabOps-Trace-ID")
    correlation_header = request.headers.get("X-Correlation-ID")
    fallback = f"request:{request.method}:{request.url.path}:{uuid.uuid4()}"
    with runtime.telemetry.bind_request(trace_header, correlation_header, fallback) as context:
        with runtime.telemetry.operation("http.request", method=request.method, path=request.url.path):
            response = await call_next(request)
        response.headers["X-Correlation-ID"] = context.correlation_id
        response.headers["X-FabOps-Trace-ID"] = context.trace_id
        return response


def get_runtime() -> LocalRuntime:
    return app.state.runtime


def get_narration_service() -> NarrationService:
    service = getattr(app.state, "narration_service", None)
    if service is None:
        service = NarrationService()
        app.state.narration_service = service
    return service


def actor_headers(
    role: Annotated[str, Header(alias="X-FabOps-Role")] = "process_engineer",
    actor: Annotated[str, Header(alias="X-FabOps-Actor")] = "local-portfolio-user",
) -> tuple[str, str]:
    return role, actor


@contextmanager
def case_telemetry(runtime: LocalRuntime, case_id: str) -> Iterator[None]:
    case = runtime.case_repository.get_case(case_id)
    causal_trace_id = case_id
    if case is not None:
        lot_id = str(case.get("lot_id") or "")
        for stored in runtime.event_repository.all_events():
            event = stored.event
            if str(event.get("lot_id") or "") == lot_id and event.get("trace_id"):
                causal_trace_id = str(event["trace_id"])
                break
    with runtime.telemetry.bind_causal_trace(causal_trace_id):
        yield


class EvidenceRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ProposalRequest(BaseModel):
    action_type: str = Field(min_length=2, max_length=80)
    target: str = Field(min_length=2, max_length=120)
    rationale: str = Field(min_length=3, max_length=800)


class DecisionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=800)


class CloseRequest(BaseModel):
    outcome: str = Field(min_length=3, max_length=800)


def _workflow_call(callable_: Any) -> dict[str, Any]:
    try:
        return callable_()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/health")
def health(runtime: Annotated[LocalRuntime, Depends(get_runtime)]) -> dict[str, Any]:
    return {**runtime.health_status(), "release": load_release_identity()}


@app.get("/health/live")
def liveness() -> dict[str, Any]:
    return {
        "status": "alive",
        "service": "fabops-api",
        "equipment_control_enabled": False,
        "release": load_release_identity(),
    }


@app.get("/health/ready")
def readiness(runtime: Annotated[LocalRuntime, Depends(get_runtime)]) -> dict[str, Any]:
    return {**runtime.health_status(), "release": load_release_identity()}


@app.get("/api/release")
def release_identity() -> dict[str, Any]:
    return {"source": "generated-release-manifest", **load_release_identity()}


@app.get("/api/overview")
def overview(runtime: Annotated[LocalRuntime, Depends(get_runtime)]) -> dict[str, Any]:
    cases = runtime.case_repository.list_cases()
    projection = asdict(runtime.projection.status())
    return {
        "source": "synthetic",
        "source_timestamp": max(item.event["event_time"] for item in runtime.event_repository.all_events()),
        "projection": projection,
        "metrics": {
            "active_cases": sum(case["state"] != "closed" for case in cases),
            "physical_excursions": sum(case["classification"] == "physical_excursion" for case in cases),
            "sensor_bias_cases": sum(case["classification"] == "sensor_bias_suspected" for case in cases),
            "data_quality_cases": sum(case["classification"] == "data_quality_incident" for case in cases),
            "event_count": len(runtime.event_repository.all_events()),
            "quarantine_count": len(runtime.quarantine.all()),
        },
        "cases": cases,
    }


@app.get("/api/cases")
def list_cases(runtime: Annotated[LocalRuntime, Depends(get_runtime)]) -> dict[str, Any]:
    return {"source": "inferred", "items": runtime.case_repository.list_cases()}


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, runtime: Annotated[LocalRuntime, Depends(get_runtime)]) -> dict[str, Any]:
    case = runtime.case_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    with case_telemetry(runtime, case_id):
        ranking = runtime.queries.execute(RankRootCausesQuery(case_id))
        trace = runtime.queries.execute(TraceAffectedLotsQuery(case_id))
        lot_id = case["lot_id"]
        measurements = [node.properties for node in runtime.graph.nodes("Measurement") if node.properties.get("lot_id") == lot_id]
        inspections = [node.properties for node in runtime.graph.nodes("Inspection") if node.properties.get("lot_id") == lot_id]
        return {
            "source": "inferred",
            "case": case,
            "rca": ranking,
            "trace": trace,
            "evidence_series": {"measurements": measurements, "inspections": inspections},
            "audit": [record for record in runtime.case_repository.audit_log() if record["case_id"] == case_id],
        }


@app.get("/api/cases/{case_id}/advisory")
def advisory(case_id: str, runtime: Annotated[LocalRuntime, Depends(get_runtime)]) -> dict[str, Any]:
    with case_telemetry(runtime, case_id):
        try:
            result = runtime.advisory.advise(case_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="case not found") from exc
    return {"source": "inferred-advisory", "llm_enabled": False, "result": result}


@app.get("/api/decision-cockpit")
def decision_cockpit(runtime: Annotated[LocalRuntime, Depends(get_runtime)]) -> dict[str, Any]:
    with runtime.telemetry.operation("decision.cockpit"):
        return DecisionSupportService(runtime).cockpit()


@app.get("/api/narration/status")
def narration_status() -> dict[str, Any]:
    return {"source": "runtime-configuration", **get_narration_service().status()}


@app.get("/api/cases/{case_id}/decision-brief")
def decision_brief(
    case_id: str,
    runtime: Annotated[LocalRuntime, Depends(get_runtime)],
    audience: str = "manager",
) -> dict[str, Any]:
    if audience not in {"manager", "engineer"}:
        raise HTTPException(status_code=422, detail="audience must be manager or engineer")
    with case_telemetry(runtime, case_id):
        try:
            packet = DecisionSupportService(runtime).packet(case_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="case not found") from exc
        with runtime.telemetry.operation("decision.narrate", case_id=case_id, audience=audience):
            brief = get_narration_service().generate(packet, audience)
    return {"source": "inferred-decision-support", "packet": packet, "brief": brief}


@app.post("/api/cases/{case_id}/request-evidence")
def request_evidence(
    case_id: str,
    body: EvidenceRequest,
    identity: Annotated[tuple[str, str], Depends(actor_headers)],
    runtime: Annotated[LocalRuntime, Depends(get_runtime)],
) -> dict[str, Any]:
    role, actor = identity
    with case_telemetry(runtime, case_id):
        case = _workflow_call(lambda: runtime.workflow.request_evidence(case_id, actor, role, body.reason))
    return {"source": "inferred-workflow", "case": case}


@app.post("/api/cases/{case_id}/actions/propose")
def propose_action(
    case_id: str,
    body: ProposalRequest,
    identity: Annotated[tuple[str, str], Depends(actor_headers)],
    runtime: Annotated[LocalRuntime, Depends(get_runtime)],
) -> dict[str, Any]:
    role, actor = identity
    with case_telemetry(runtime, case_id):
        case = _workflow_call(lambda: runtime.workflow.propose_action(case_id, actor, role, body.action_type, body.target, body.rationale))
    return {"source": "inferred-workflow", "case": case}


@app.post("/api/cases/{case_id}/actions/approve")
def approve_action(
    case_id: str,
    body: DecisionRequest,
    identity: Annotated[tuple[str, str], Depends(actor_headers)],
    runtime: Annotated[LocalRuntime, Depends(get_runtime)],
) -> dict[str, Any]:
    role, actor = identity
    with case_telemetry(runtime, case_id):
        case = _workflow_call(lambda: runtime.workflow.approve(case_id, actor, role, body.reason))
    return {"source": "inferred-workflow", "case": case}


@app.post("/api/cases/{case_id}/actions/reject")
def reject_action(
    case_id: str,
    body: DecisionRequest,
    identity: Annotated[tuple[str, str], Depends(actor_headers)],
    runtime: Annotated[LocalRuntime, Depends(get_runtime)],
) -> dict[str, Any]:
    role, actor = identity
    with case_telemetry(runtime, case_id):
        case = _workflow_call(lambda: runtime.workflow.reject(case_id, actor, role, body.reason))
    return {"source": "inferred-workflow", "case": case}


@app.post("/api/cases/{case_id}/close")
def close_case(
    case_id: str,
    body: CloseRequest,
    identity: Annotated[tuple[str, str], Depends(actor_headers)],
    runtime: Annotated[LocalRuntime, Depends(get_runtime)],
) -> dict[str, Any]:
    role, actor = identity
    with case_telemetry(runtime, case_id):
        case = _workflow_call(lambda: runtime.workflow.close(case_id, actor, role, body.outcome))
    return {"source": "inferred-workflow", "case": case}


@app.get("/api/evaluation")
def evaluation(runtime: Annotated[LocalRuntime, Depends(get_runtime)]) -> dict[str, Any]:
    release_path = Path("evidence/release/evaluation-summary.json")
    if release_path.exists():
        release = json.loads(release_path.read_text(encoding="utf-8"))
        return {
            "source": "generated-evaluation-evidence",
            "evidence_hash": release["canonical_hash"],
            "versions": release["version_registry"],
            "metrics": release["held_out_metrics"],
            "negative_results": release["negative_results"],
            "release_gate": release["release_gate"],
            "release_passed": release["release_passed"],
            "limitations": [
                "synthetic held-out test profile only",
                "U1 evaluates safe abstention under an unseen evidence gap; it is not a real-fab fault benchmark",
                "not a synthetic-to-real performance claim",
            ],
        }
    m2 = json.loads(Path("evidence/m2-gate.json").read_text(encoding="utf-8"))
    m3 = json.loads(Path("evidence/m3-gate.json").read_text(encoding="utf-8"))
    return {
        "source": "generated-evaluation-evidence",
        "versions": {
            "detector": runtime.detector.config.version,
            "projection": runtime.projection.status().projection_version,
            "advisory": "deterministic-advisory-v1.1.0",
        },
        "metrics": {
            "detector": {
                "fault_recall": m2["fault_recall"],
                "false_alarms_per_simulated_day": m2["false_alarms_per_simulated_day"],
                "affected_scope_precision": m2["affected_scope_precision"],
                "affected_scope_recall": m2["affected_scope_recall"],
            },
            "rca": {
                "top1_accuracy": m3["top1_accuracy"],
                "top3_accuracy": m3["top3_accuracy"],
                "mrr": m3["mrr"],
                "false_causal_attribution_rate": m3["false_causal_attribution_rate"],
            },
        },
        "limitations": ["synthetic test profile only", "not a synthetic-to-real performance claim"],
    }


@app.get("/api/replay")
def replay_status(runtime: Annotated[LocalRuntime, Depends(get_runtime)]) -> dict[str, Any]:
    stored = runtime.event_repository.all_events()
    status = runtime.projection.status()
    return {
        "source": "synthetic-replay",
        "event_count": len(stored),
        "detection_checkpoint": runtime.event_repository.checkpoint("detection"),
        "projection": asdict(status),
        "outbox_count": len(runtime.event_repository.outbox()),
        "quarantine_count": len(runtime.quarantine.all()),
        "delivery_status_counts": {
            key: sum(item.delivery_status == key for item in stored)
            for key in ("on_time", "late", "out_of_order")
        },
        "external_services": {
            "postgres": runtime.integration_status()["postgres_runtime_verified"],
            "redpanda": runtime.integration_status()["redpanda_runtime_verified"],
            "neo4j": runtime.integration_status()["neo4j_runtime_verified"],
            "external_llm": "disabled-not-required",
        },
        "integration": runtime.integration_status(),
        "release": load_release_identity(),
    }

