from __future__ import annotations

import asyncio
import hmac
import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Iterator, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse

from services.decision import DecisionSupportService
from services.intelligence import ContinuousIntelligenceService
from services.narration import NarrationService
from services.narration.demo import DemoPolicyError, DemoSessionPolicy, demo_policy_from_env
from services.prediction import PredictiveIntelligenceService
from services.rca.cqrs import RankRootCausesQuery, TraceAffectedLotsQuery
from services.release import RELEASE_VERSION, load_deployment_identity, load_release_identity
from services.workflow.state_machine import AuthorizationError, InvalidTransitionError
from systems.api.runtime import DatabaseReadOnlyRuntime, IntegrationRuntime, LocalRuntime, build_runtime

app = FastAPI(
    title="FabOps Decision Lab API",
    version=RELEASE_VERSION,
    description="Deterministic/read-only portfolio API. It does not control real fab equipment.",
)

Runtime = LocalRuntime | IntegrationRuntime | DatabaseReadOnlyRuntime


def _cors_origins_from_env() -> list[str]:
    origins = ["http://127.0.0.1:5173", "http://localhost:5173"]
    configured = os.getenv("FABOPS_CORS_ORIGINS", "").strip()
    for origin in configured.split(",") if configured else []:
        normalized = origin.strip().rstrip("/")
        if normalized and normalized not in origins:
            origins.append(normalized)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_from_env(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "X-FabOps-Role",
        "X-FabOps-Actor",
        "X-FabOps-Demo-Session",
        "X-Correlation-ID",
        "X-FabOps-Trace-ID",
        "traceparent",
    ],
    expose_headers=["X-Correlation-ID", "X-FabOps-Trace-ID"],
)
app.state.runtime = build_runtime()
app.state.narration_service = None
app.state.demo_policy = None
app.state.demo_policy_loaded = False


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


def get_runtime() -> Runtime:
    return app.state.runtime


def _refresh_projection(runtime: Runtime) -> None:
    """Catch a long-lived API process up with newly persisted source events."""
    try:
        runtime.projection.catch_up()
    except Exception:  # noqa: BLE001 - endpoint payloads still expose stale/degraded state
        return


def _live_status(runtime: Runtime) -> dict[str, Any]:
    _refresh_projection(runtime)
    stored = runtime.event_repository.all_events()
    cases = runtime.case_repository.list_cases()
    latest = stored[-1].event if stored else None
    prediction = PredictiveIntelligenceService(runtime.event_repository, runtime.case_repository).snapshot()
    live_enabled = os.getenv("FABOPS_LIVE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "schema_version": "fabops-live-status-v1",
        "mode": "continuous" if live_enabled else "snapshot",
        "live_enabled": live_enabled,
        "runtime_mode": runtime.runtime_mode,
        "transport": "server-sent-events",
        "read_only": runtime.runtime_mode == "database-readonly",
        "event_count": len(stored),
        "case_count": len(cases),
        "latest_event_time": latest.get("event_time") if latest else None,
        "latest_event_type": latest.get("event_type") if latest else None,
        "latest_lot_id": latest.get("lot_id") if latest else None,
        "projection": asdict(runtime.projection.status()),
        "prediction": prediction,
    }


def _continuous_intelligence_status(runtime: Runtime) -> dict[str, Any]:
    try:
        return ContinuousIntelligenceService(runtime.event_repository).status()
    except Exception as exc:  # noqa: BLE001 - old/local schemas degrade without hiding live runtime
        return {
            "schema_version": "fabops-continuous-intelligence-v1",
            "learning_enabled": False,
            "feedback_loop": "unavailable",
            "outcome_count": 0,
            "champions": {},
            "latest_predictions": [],
            "feedback": {},
            "drift": {"status": "unavailable", "score": 0.0, "recent_rows": 0, "baseline_rows": 0},
            "reports": [],
            "visualization_plans": [],
            "degraded_reason": type(exc).__name__,
        }


def get_narration_service() -> NarrationService:
    service = getattr(app.state, "narration_service", None)
    if service is None:
        service = NarrationService()
        app.state.narration_service = service
    return service


def get_demo_policy() -> DemoSessionPolicy | None:
    if not getattr(app.state, "demo_policy_loaded", False):
        app.state.demo_policy = demo_policy_from_env()
        app.state.demo_policy_loaded = True
    return app.state.demo_policy


def actor_headers(
    role: Annotated[str, Header(alias="X-FabOps-Role")] = "process_engineer",
    actor: Annotated[str, Header(alias="X-FabOps-Actor")] = "local-portfolio-user",
) -> tuple[str, str]:
    return role, actor


@contextmanager
def case_telemetry(runtime: Runtime, case_id: str) -> Iterator[None]:
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


class DemoNarrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=3, max_length=120)
    audience: Literal["manager", "engineer"] = "manager"
    intent: Literal["manager_summary", "engineer_checklist", "tradeoff_compare", "counter_evidence"] = "manager_summary"


class NarrationPrecomputeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_ids: list[str] | None = None
    audiences: list[Literal["manager", "engineer"]] = Field(default_factory=lambda: ["manager", "engineer"], min_length=1, max_length=2)


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
def health(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
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
def readiness(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    return {**runtime.health_status(), "release": load_release_identity()}


@app.get("/api/release")
def release_identity() -> dict[str, Any]:
    return {"source": "generated-release-manifest", **load_release_identity()}


@app.get("/api/deployment-identity")
def deployment_identity() -> dict[str, Any]:
    return load_deployment_identity()


@app.get("/api/live/status")
def live_status(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    return _live_status(runtime)


@app.get("/api/predictions")
def predictions(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    _refresh_projection(runtime)
    return {"source": "transparent-online-baseline", **PredictiveIntelligenceService(runtime.event_repository, runtime.case_repository).snapshot()}


@app.get("/api/intelligence/status")
def continuous_intelligence_status(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    return {"source": "continuous-learning-registry", **_continuous_intelligence_status(runtime)}


@app.get("/api/live/stream")
async def live_stream(runtime: Annotated[Runtime, Depends(get_runtime)]) -> StreamingResponse:
    async def events() -> Iterator[str]:
        previous_signature: tuple[Any, ...] | None = None
        heartbeat = 0
        while True:
            snapshot = await asyncio.to_thread(_live_status, runtime)
            top_sensor = snapshot["prediction"]["top_sensor_forecasts"][:1]
            top_risk = top_sensor[0]["risk_score"] if top_sensor else None
            signature = (
                snapshot["event_count"],
                snapshot["case_count"],
                snapshot["projection"]["projection_checkpoint"],
                snapshot["latest_event_time"],
                top_risk,
            )
            if signature != previous_signature:
                previous_signature = signature
                yield f"event: fabops-update\ndata: {json.dumps(snapshot, separators=(',', ':'))}\n\n"
            elif heartbeat % 10 == 0:
                yield f"event: heartbeat\ndata: {json.dumps({'event_count': snapshot['event_count']})}\n\n"
            heartbeat += 1
            await asyncio.sleep(1.0)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.get("/api/overview")
def overview(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    _refresh_projection(runtime)
    cases = runtime.case_repository.list_cases()
    projection = asdict(runtime.projection.status())
    return {
        "source": "postgresql-read-only" if runtime.runtime_mode == "database-readonly" else "synthetic",
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
def list_cases(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    return {"source": "inferred", "items": runtime.case_repository.list_cases()}


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    _refresh_projection(runtime)
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


@app.get("/api/cases/{case_id}/replay-trace")
def get_case_replay_trace(case_id: str, runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    case = runtime.case_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")

    lot_id = str(case["lot_id"])
    source_events = [item for item in runtime.event_repository.all_events() if item.event.get("lot_id") == lot_id]
    source_by_id = {str(item.event.get("event_id")): item for item in source_events}

    def _phase(event_type: str) -> str:
        if event_type == "lot.released.v1":
            return "baseline"
        if event_type in {"process.started.v1", "process.completed.v1"}:
            return "process"
        if event_type == "process.measurement.recorded.v1":
            return "signal"
        if event_type == "equipment.alarm.raised.v1":
            return "anomaly"
        if event_type == "inspection.completed.v1":
            return "inspection"
        if event_type == "data.quality.incident.v1":
            return "data_quality"
        return "event"

    timeline: list[dict[str, Any]] = []
    for stored in source_events:
        event = stored.event
        timeline.append(
            {
                "timeline_id": f"source:{event['event_id']}",
                "kind": "source_event",
                "phase": _phase(str(event["event_type"])),
                "sequence": stored.sequence,
                "event_time": event.get("event_time"),
                "time_semantics": "source_event_time",
                "event_type": event["event_type"],
                "event_id": event["event_id"],
                "delivery_status": stored.delivery_status,
                "source": "postgresql-event-model" if runtime.runtime_mode != "local" else "local-event-adapter",
                "payload": dict(event.get("payload", {})),
            }
        )

    trigger_times = [
        source_by_id[event_id].event.get("event_time")
        for event_id in case.get("evidence_event_ids", [])
        if event_id in source_by_id
    ]
    detection_time = max((value for value in trigger_times if value), default=None)
    audit_records = [record for record in runtime.case_repository.audit_log() if record.get("case_id") == case_id]
    for record in audit_records:
        event_name = str(record.get("event", "workflow.audit"))
        inferred_time = detection_time if event_name == "case.detected" else None
        timeline.append(
            {
                "timeline_id": f"audit:{record.get('audit_sequence')}",
                "kind": "audit_event",
                "phase": "detection" if event_name == "case.detected" else "human_governance",
                "sequence": int(record.get("audit_sequence", 0)),
                "event_time": inferred_time,
                "time_semantics": "trigger_event_time" if inferred_time else "audit_sequence_only",
                "event_type": event_name,
                "event_id": None,
                "delivery_status": None,
                "source": "decision-audit",
                "payload": {key: value for key, value in record.items() if key not in {"case_id", "audit_sequence", "event"}},
            }
        )

    ranking = runtime.queries.execute(RankRootCausesQuery(case_id))
    projection_status = ranking["projection"]
    timeline.append(
        {
            "timeline_id": "projection:rca-current",
            "kind": "projection_snapshot",
            "phase": "rca",
            "sequence": projection_status["projection_checkpoint"],
            "event_time": None,
            "time_semantics": "current_rebuildable_snapshot",
            "event_type": "rca.projection.snapshot",
            "event_id": None,
            "delivery_status": None,
            "source": "neo4j-rebuildable-projection",
            "payload": {
                "projection_version": projection_status["projection_version"],
                "projection_checkpoint": projection_status["projection_checkpoint"],
                "source_checkpoint": projection_status["source_checkpoint"],
                "stale": projection_status["stale"],
                "candidate_count": len(ranking["candidates"]),
                "top_candidate_id": ranking["candidates"][0]["candidate_id"] if ranking["candidates"] else None,
            },
        }
    )

    source_timeline = sorted(
        (item for item in timeline if item["kind"] == "source_event"),
        key=lambda item: (str(item["event_time"]), int(item["sequence"])),
    )
    audit_timeline = sorted(
        (item for item in timeline if item["kind"] == "audit_event"),
        key=lambda item: (item["event_time"] is None, str(item["event_time"] or ""), int(item["sequence"])),
    )
    projection_timeline = [item for item in timeline if item["kind"] == "projection_snapshot"]
    ordered = source_timeline + audit_timeline + projection_timeline

    return {
        "source": "source-event-and-audit-replay",
        "case_id": case_id,
        "lot_id": lot_id,
        "source_of_truth": "postgresql" if runtime.runtime_mode != "local" else "local adapter shaped as the PostgreSQL event contract",
        "projection_role": "rebuildable RCA/read projection",
        "timeline": ordered,
        "summary": {
            "source_event_count": len(source_timeline),
            "audit_event_count": len(audit_timeline),
            "projection_snapshot_count": len(projection_timeline),
            "out_of_order_count": sum(item["delivery_status"] == "out_of_order" for item in source_timeline),
            "late_count": sum(item["delivery_status"] == "late" for item in source_timeline),
        },
        "limitations": [
            "Workflow audit rows without persisted timestamps are ordered by audit_sequence and are not assigned fabricated wall-clock times.",
            "The RCA entry is the current rebuildable projection snapshot, not a fabricated historical Neo4j event.",
            "All simulator-originated process evidence is synthetic and is not a real-fab performance claim.",
        ],
    }


@app.get("/api/cases/{case_id}/advisory")
def advisory(case_id: str, runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    _refresh_projection(runtime)
    with case_telemetry(runtime, case_id):
        try:
            result = runtime.advisory.advise(case_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="case not found") from exc
    return {"source": "inferred-advisory", "llm_enabled": False, "result": result}


@app.get("/api/decision-cockpit")
def decision_cockpit(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    _refresh_projection(runtime)
    with runtime.telemetry.operation("decision.cockpit"):
        return DecisionSupportService(runtime).cockpit()


@app.get("/api/narration/status")
def narration_status() -> dict[str, Any]:
    demo_policy = get_demo_policy()
    return {
        "source": "runtime-configuration",
        **get_narration_service().status(),
        "public_get_mode": "cache_only",
        "public_demo": demo_policy.status() if demo_policy is not None else {"enabled": False},
    }


@app.get("/api/cases/{case_id}/decision-brief")
def decision_brief(
    case_id: str,
    runtime: Annotated[Runtime, Depends(get_runtime)],
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
            brief = get_narration_service().cached_or_deterministic(packet, audience)
    return {"source": "inferred-decision-support", "packet": packet, "brief": brief}


def _public_client_id(request: Request) -> str:
    cloudflare_ip = request.headers.get("CF-Connecting-IP", "").strip()
    if cloudflare_ip:
        return cloudflare_ip[:80]
    forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded[:80]
    return (request.client.host if request.client else "unknown")[:80]


@app.get("/api/demo/session")
def create_demo_session() -> dict[str, Any]:
    policy = get_demo_policy()
    if policy is None:
        raise HTTPException(status_code=404, detail="public AI demo is disabled")
    return {"source": "server-owned-demo-policy", **policy.issue()}


@app.post("/api/demo/narration")
def demo_narration(
    body: DemoNarrationRequest,
    request: Request,
    runtime: Annotated[Runtime, Depends(get_runtime)],
    demo_session: Annotated[str | None, Header(alias="X-FabOps-Demo-Session")] = None,
) -> dict[str, Any]:
    policy = get_demo_policy()
    if policy is None:
        raise HTTPException(status_code=404, detail="public AI demo is disabled")
    if not demo_session:
        raise HTTPException(status_code=401, detail="demo session required")
    try:
        session_id = policy.consume(demo_session, _public_client_id(request), body.intent)
    except DemoPolicyError as exc:
        status = 429 if exc.reason in {"session_generation_limit", "client_hourly_limit"} else 401
        raise HTTPException(status_code=status, detail=exc.reason) from exc
    with case_telemetry(runtime, body.case_id):
        try:
            packet = DecisionSupportService(runtime).packet(body.case_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="case not found") from exc
        with runtime.telemetry.operation(
            "decision.demo_narrate",
            case_id=body.case_id,
            audience=body.audience,
            intent=body.intent,
        ):
            brief = get_narration_service().generate(packet, body.audience, intent=body.intent)
    return {
        "source": "bounded-public-demo-narration",
        "session_id": session_id,
        "packet": packet,
        "brief": brief,
    }


@app.post("/api/internal/narration/precompute")
def precompute_narration(
    body: NarrationPrecomputeRequest,
    runtime: Annotated[Runtime, Depends(get_runtime)],
    internal_token: Annotated[str | None, Header(alias="X-FabOps-Internal-Token")] = None,
) -> dict[str, Any]:
    expected = os.getenv("FABOPS_INTERNAL_NARRATION_TOKEN", "")
    if len(expected) < 24:
        raise HTTPException(status_code=404, detail="internal narration precompute is disabled")
    if not internal_token or not hmac.compare_digest(internal_token, expected):
        raise HTTPException(status_code=401, detail="invalid internal narration credential")
    case_ids = body.case_ids or [case["case_id"] for case in runtime.case_repository.list_cases()]
    generated: list[dict[str, Any]] = []
    for case_id in case_ids:
        try:
            packet = DecisionSupportService(runtime).packet(case_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"case not found: {case_id}") from exc
        for audience in body.audiences:
            brief = get_narration_service().generate(packet, audience)
            generated.append(
                {
                    "case_id": case_id,
                    "audience": audience,
                    "mode": brief["mode"],
                    "provider": brief["provider"],
                    "cache_hit": brief.get("cache_hit", False),
                }
            )
    return {"source": "internal-precompute", "generated": generated, "count": len(generated)}


@app.post("/api/cases/{case_id}/request-evidence")
def request_evidence(
    case_id: str,
    body: EvidenceRequest,
    identity: Annotated[tuple[str, str], Depends(actor_headers)],
    runtime: Annotated[Runtime, Depends(get_runtime)],
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
    runtime: Annotated[Runtime, Depends(get_runtime)],
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
    runtime: Annotated[Runtime, Depends(get_runtime)],
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
    runtime: Annotated[Runtime, Depends(get_runtime)],
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
    runtime: Annotated[Runtime, Depends(get_runtime)],
) -> dict[str, Any]:
    role, actor = identity
    with case_telemetry(runtime, case_id):
        case = _workflow_call(lambda: runtime.workflow.close(case_id, actor, role, body.outcome))
    return {"source": "inferred-workflow", "case": case}


@app.get("/api/evaluation")
def evaluation(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    release_path = Path("evidence/release/evaluation-summary.json")
    if release_path.exists():
        release = json.loads(release_path.read_text(encoding="utf-8"))
        held_out = list(release.get("seed_results", {}).get("held_out", []))
        family_names = sorted({family for result in held_out for family in result.get("stratified", {})})
        fault_family_slices = []
        for family in family_names:
            rows = [result["stratified"][family] for result in held_out if family in result.get("stratified", {})]
            if not rows:
                continue
            fault_family_slices.append(
                {
                    "family": family,
                    "seed_count": len(rows),
                    "mean_case_count": round(sum(float(row.get("case_count", 0)) for row in rows) / len(rows), 5),
                    "rca_top1": round(sum(float(row.get("rca_top1", 0)) for row in rows) / len(rows), 5),
                    "agent_ready_rate": round(sum(float(row.get("agent_ready_rate", 0)) for row in rows) / len(rows), 5),
                }
            )
        held_out_seed_metrics = [
            {
                "seed": result.get("seed"),
                "fault_recall": result.get("detector", {}).get("fault_recall"),
                "false_alarms_per_simulated_day": result.get("detector", {}).get("false_alarms_per_simulated_day"),
                "rca_top1": result.get("rca", {}).get("top1_accuracy"),
                "rca_top3": result.get("rca", {}).get("top3_accuracy"),
                "contradicting_evidence_coverage": result.get("rca", {}).get("contradicting_evidence_coverage"),
            }
            for result in held_out
        ]

        def _seed_range(metric_group: str, metric_name: str) -> dict[str, float] | None:
            values = [
                float(result.get(metric_group, {}).get(metric_name))
                for result in held_out
                if result.get(metric_group, {}).get(metric_name) is not None
            ]
            if not values:
                return None
            return {
                "mean": round(sum(values) / len(values), 5),
                "minimum": round(min(values), 5),
                "maximum": round(max(values), 5),
            }

        return {
            "source": "generated-evaluation-evidence",
            "evidence_hash": release["canonical_hash"],
            "versions": release["version_registry"],
            "metrics": release["held_out_metrics"],
            "negative_results": release["negative_results"],
            "release_gate": release["release_gate"],
            "release_passed": release["release_passed"],
            "validation_console": {
                "evidence_schema_version": release.get("evidence_schema_version"),
                "held_out_seed_metrics": held_out_seed_metrics,
                "seed_ranges": {
                    "fault_recall": _seed_range("detector", "fault_recall"),
                    "rca_top1": _seed_range("rca", "top1_accuracy"),
                    "rca_top3": _seed_range("rca", "top3_accuracy"),
                    "contradicting_evidence_coverage": _seed_range("rca", "contradicting_evidence_coverage"),
                },
                "fault_family_slices": fault_family_slices,
                "unseen_family_results": release.get("unseen_family_results", []),
                "common_random_number_comparison": release.get("common_random_number_comparison", {}),
                "claims_boundary": release.get("claims_boundary", {}),
                "evidence_gaps": [
                    "Case-level false-positive/false-negative rows are not persisted in evaluation-summary.json; only aggregate detector metrics are available.",
                    "A statistical confidence interval is not persisted in this release evidence; seed min/max is shown instead and must not be described as a confidence interval.",
                    "Public narration provider grounded-response acceptance rate is not part of the historical 0.6 evaluation evidence and is not backfilled here.",
                    "Deterministic-versus-LLM wording consistency is not part of the historical 0.6 release evidence and requires a separate v0.7 evaluation artifact.",
                ],
            },
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
def replay_status(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict[str, Any]:
    _refresh_projection(runtime)
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

