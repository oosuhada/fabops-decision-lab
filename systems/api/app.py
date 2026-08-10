from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.rca.cqrs import RankRootCausesQuery, TraceAffectedLotsQuery
from services.workflow.state_machine import AuthorizationError, InvalidTransitionError
from systems.api.runtime import LocalRuntime, build_local_runtime

app = FastAPI(
    title="FabOps Decision Lab API",
    version="0.4.0",
    description="Deterministic local portfolio API. It does not control real fab equipment.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-FabOps-Role", "X-FabOps-Actor"],
)
app.state.runtime = build_local_runtime()


def get_runtime() -> LocalRuntime:
    return app.state.runtime


def actor_headers(
    role: Annotated[str, Header(alias="X-FabOps-Role")] = "process_engineer",
    actor: Annotated[str, Header(alias="X-FabOps-Actor")] = "local-portfolio-user",
) -> tuple[str, str]:
    return role, actor


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
    status = runtime.projection.status()
    return {
        "status": "ok" if not status.stale else "degraded",
        "external_llm_required": False,
        "equipment_control_enabled": False,
        "projection": asdict(status),
    }


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
    ranking = runtime.queries.execute(RankRootCausesQuery(case_id))
    trace = runtime.queries.execute(TraceAffectedLotsQuery(case_id))
    lot_id = case["lot_id"]
    measurements = [
        node.properties
        for node in runtime.graph.nodes("Measurement")
        if node.properties.get("lot_id") == lot_id
    ]
    inspections = [
        node.properties
        for node in runtime.graph.nodes("Inspection")
        if node.properties.get("lot_id") == lot_id
    ]
    return {
        "source": "inferred",
        "case": case,
        "rca": ranking,
        "trace": trace,
        "evidence_series": {
            "measurements": measurements,
            "inspections": inspections,
        },
        "audit": [record for record in runtime.case_repository.audit_log() if record["case_id"] == case_id],
    }


@app.get("/api/cases/{case_id}/advisory")
def advisory(case_id: str, runtime: Annotated[LocalRuntime, Depends(get_runtime)]) -> dict[str, Any]:
    try:
        result = runtime.advisory.advise(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    return {"source": "inferred-advisory", "llm_enabled": False, "result": result}


@app.post("/api/cases/{case_id}/request-evidence")
def request_evidence(
    case_id: str,
    body: EvidenceRequest,
    identity: Annotated[tuple[str, str], Depends(actor_headers)],
    runtime: Annotated[LocalRuntime, Depends(get_runtime)],
) -> dict[str, Any]:
    role, actor = identity
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
            "advisory": "deterministic-advisory-v1.0.0",
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
            "postgres": "contract-only-local-gate",
            "redpanda": "contract-only-local-gate",
            "neo4j": "contract-only-local-gate",
            "external_llm": "disabled-not-required",
        },
    }

