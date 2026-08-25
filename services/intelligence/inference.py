from __future__ import annotations

from copy import deepcopy
from typing import Any

from .assessment import build_situation_assessment


def assessment_request_document(
    *,
    packet: dict[str, Any],
    decision_context: dict[str, Any],
    visualization_plan: dict[str, Any],
    previous_report: dict[str, Any] | None,
    case_predictions: list[dict[str, Any]],
    trigger_type: str,
    audience: str = "engineer",
    intent: str = "situation_update",
) -> dict[str, Any]:
    return {
        "schema_version": "fabops-inference-request-v1",
        "packet": deepcopy(packet),
        "decision_context": deepcopy(decision_context),
        "visualization_plan": deepcopy(visualization_plan),
        "previous_report": deepcopy(previous_report) if previous_report else None,
        "model_versions": {
            str(item["target"]): str(item["model_version"])
            for item in case_predictions
            if item.get("target") and item.get("model_version")
        },
        "uncertainties": list(packet.get("uncertainties", [])),
        "trigger_type": trigger_type,
        "audience": audience,
        "intent": intent,
    }


def persist_completed_inference(repository: Any, job: dict[str, Any], brief: dict[str, Any]) -> bool:
    request_document = job.get("request_document", {})
    if not isinstance(request_document, dict):
        raise ValueError("inference job request_document must be an object")
    packet = request_document.get("packet", {})
    decision_context = request_document.get("decision_context", {})
    visualization_plan = request_document.get("visualization_plan", {})
    previous_report = request_document.get("previous_report")
    trigger_type = str(request_document.get("trigger_type") or job.get("trigger_type") or "material_intelligence_change")
    situation_assessment = build_situation_assessment(
        assessment_id=str(job["assessment_run_id"]),
        case_id=str(job["case_id"]),
        trigger=trigger_type,
        provider=str(brief.get("provider", "deterministic")),
        decision_context=decision_context if isinstance(decision_context, dict) else {},
        brief=brief,
        previous_report=previous_report if isinstance(previous_report, dict) else None,
        model_versions=dict(request_document.get("model_versions", {})),
        visualization_plan=visualization_plan if isinstance(visualization_plan, dict) else {},
        uncertainties=list(request_document.get("uncertainties", [])),
    )
    return repository.append_intelligence_report(
        {
            "assessment_run_id": str(job["assessment_run_id"]),
            "case_id": str(job["case_id"]),
            "material_signature": str(job["material_signature"]),
            "trigger_type": trigger_type,
            "mode": brief.get("mode", "deterministic_fallback"),
            "provider": brief.get("provider", "deterministic"),
            "provider_model": brief.get("provider_model"),
            "latency_ms": brief.get("latency_ms"),
            "previous_report_id": previous_report.get("report_id") if isinstance(previous_report, dict) else None,
            "reused_report_id": previous_report.get("report_id") if brief.get("cache_hit") and isinstance(previous_report, dict) else None,
            "input_context_fingerprint": str(job["input_context_fingerprint"]),
            "brief": brief,
            "situation_assessment": situation_assessment,
            "decision_context": decision_context,
            "visualization_plan": visualization_plan,
            "packet_case_id": packet.get("case_id") if isinstance(packet, dict) else None,
        }
    )
