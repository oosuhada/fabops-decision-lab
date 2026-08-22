from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from services.advisory.tools import ToolRegistry

ADVISORY_VERSION = "deterministic-advisory-v1.1.0"

TOOL_PLAN: dict[str, tuple[str, ...]] = {
    "physical_excursion": (
        "get_excursion_summary",
        "trace_affected_lots",
        "find_related_alarms_and_changes",
        "compare_chamber_baselines",
    ),
    "sensor_bias_suspected": (
        "get_excursion_summary",
        "compare_chamber_baselines",
        "find_related_alarms_and_changes",
        "retrieve_sop_and_past_cases",
    ),
    "data_quality_incident": (
        "get_excursion_summary",
        "trace_affected_lots",
        "retrieve_sop_and_past_cases",
    ),
}


class AdvisoryProviderPort(Protocol):
    def advise(self, case_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ExternalLlmConfig:
    provider: str
    model: str
    api_key_present: bool


class ExternalLlmAdvisoryProvider:
    """Optional provider boundary; no credential is required for the core workflow."""

    def __init__(self, config: ExternalLlmConfig) -> None:
        self.config = config

    def advise(self, case_id: str) -> dict[str, Any]:
        if not self.config.api_key_present:
            raise RuntimeError("external LLM provider is disabled: no credential configured")
        raise NotImplementedError("external LLM transport is intentionally not invoked by the local portfolio gate")


class DeterministicAdvisoryProvider:
    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    def advise(self, case_id: str) -> dict[str, Any]:
        tool_calls: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        def call(name: str) -> dict[str, Any] | None:
            try:
                result = self.tools.call(name, case_id)
                tool_calls.append({"tool": name, "status": "ok", "result": result})
                return result
            except Exception as exc:  # noqa: BLE001 - tool errors are advisory evidence, not hidden
                errors.append({"tool": name, "error": type(exc).__name__, "detail": str(exc)})
                tool_calls.append({"tool": name, "status": "error"})
                return None

        summary = call("get_excursion_summary")
        if summary is None:
            return {
                "provider": ADVISORY_VERSION,
                "status": "abstain",
                "case_id": case_id,
                "tool_calls": tool_calls,
                "errors": errors,
                "claims": [],
                "recommended_next_step": "request_more_evidence",
                "reason": "required excursion summary tool failed",
            }

        candidate = summary.get("top_candidate")
        if candidate is None or not candidate.get("supporting_evidence"):
            return {
                "provider": ADVISORY_VERSION,
                "status": "abstain",
                "case_id": case_id,
                "tool_calls": tool_calls,
                "errors": errors,
                "claims": [],
                "recommended_next_step": "request_more_evidence",
                "reason": "root-cause candidate lacks supporting evidence",
            }

        classification = summary["classification"]
        results: dict[str, dict[str, Any] | None] = {"get_excursion_summary": summary}
        for tool_name in TOOL_PLAN.get(classification, ("get_excursion_summary",))[1:]:
            results[tool_name] = call(tool_name)

        claims = [
            {
                "claim": f"Top deterministic candidate is {candidate['candidate_id']}.",
                "supported_by": [evidence for evidence in candidate["supporting_evidence"]],
                "contradicted_by": [evidence for evidence in candidate["contradicting_evidence"]],
            }
        ]
        if classification == "data_quality_incident":
            recommendation = "reconcile and replay event delivery; do not propose equipment hold"
        elif classification == "sensor_bias_suspected":
            recommendation = "verify sensor calibration and request independent evidence before equipment containment"
        else:
            recommendation = candidate["recommended_action"]
        if errors:
            status = "degraded"
            recommendation = "request_more_evidence"
        else:
            status = "ready"
        return {
            "provider": ADVISORY_VERSION,
            "status": status,
            "case_id": case_id,
            "classification": classification,
            "tool_calls": tool_calls,
            "errors": errors,
            "claims": claims,
            "counter_evidence": candidate["contradicting_evidence"],
            "recommended_next_step": recommendation,
            "prohibited_capabilities": ["anomaly_score", "affected_scope_authority", "authorization", "case_state_mutation", "equipment_execution"],
            "evidence_snapshot": {
                "trace_available": results.get("trace_affected_lots") is not None,
                "related_changes_available": results.get("find_related_alarms_and_changes") is not None,
                "baselines_available": results.get("compare_chamber_baselines") is not None,
                "sop_available": results.get("retrieve_sop_and_past_cases") is not None,
            },
        }

