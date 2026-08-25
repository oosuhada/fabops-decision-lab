from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _prediction_delta(
    current: dict[str, Any],
    previous: dict[str, Any],
) -> dict[str, dict[str, float | None]]:
    result: dict[str, dict[str, float | None]] = {}
    for target, current_value in current.items():
        previous_value = previous.get(target)
        current_number = float(current_value) if current_value is not None else None
        previous_number = float(previous_value) if previous_value is not None else None
        result[target] = {
            "previous": previous_number,
            "current": current_number,
            "delta": None if current_number is None or previous_number is None else round(current_number - previous_number, 6),
        }
    return result


def build_situation_assessment(
    *,
    assessment_id: str,
    case_id: str,
    trigger: str,
    provider: str,
    decision_context: dict[str, Any],
    brief: dict[str, Any],
    previous_report: dict[str, Any] | None,
    model_versions: dict[str, str],
    visualization_plan: dict[str, Any],
    uncertainties: list[str] | None = None,
) -> dict[str, Any]:
    """Build a grounded change-oriented assessment without asking another LLM."""

    current_predictions = decision_context.get("predictions", {}) if isinstance(decision_context.get("predictions"), dict) else {}
    previous_context = previous_report.get("decision_context", {}) if previous_report and isinstance(previous_report.get("decision_context"), dict) else {}
    previous_predictions = previous_context.get("predictions", {}) if isinstance(previous_context.get("predictions"), dict) else {}
    deltas = _prediction_delta(current_predictions, previous_predictions)
    material_deltas = [
        {"metric": target, **values}
        for target, values in deltas.items()
        if values["delta"] is not None and abs(float(values["delta"])) >= 0.01
    ]
    positive = sum(float(item["delta"] or 0.0) > 0.01 for item in material_deltas)
    negative = sum(float(item["delta"] or 0.0) < -0.01 for item in material_deltas)
    if positive and not negative:
        trajectory = "RISING"
    elif negative and not positive:
        trajectory = "FALLING"
    elif positive and negative:
        trajectory = "MIXED"
    else:
        trajectory = "STABLE_OR_INSUFFICIENT_DELTA"

    next_actions = decision_context.get("next_actions", []) if isinstance(decision_context.get("next_actions"), list) else []
    triggers = decision_context.get("trigger_conditions", []) if isinstance(decision_context.get("trigger_conditions"), list) else []
    why_now = decision_context.get("why_now", []) if isinstance(decision_context.get("why_now"), list) else []
    return {
        "schema_version": "fabops-situation-assessment-v2",
        "assessment_id": assessment_id,
        "case_id": case_id,
        "generated_at": brief.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "trigger": trigger,
        "what_changed": material_deltas if material_deltas else [{"status": "no_material_prediction_delta"}],
        "why_it_changed": why_now[:5],
        "current_risk": current_predictions,
        "risk_trajectory": trajectory,
        "forecast_horizon": decision_context.get("watch_horizon", "next lot"),
        "evidence_for": why_now[:5],
        "evidence_against": list(uncertainties or [])[:5],
        "uncertainties": list(uncertainties or [])[:5],
        "recommended_investigations": next_actions[:4],
        "expected_information_gain": [
            {"action": item.get("action"), "information_gain": item.get("purpose")}
            for item in next_actions[:4]
            if isinstance(item, dict)
        ],
        "escalation_conditions": [item for item in triggers if isinstance(item, dict) and item.get("met")],
        "watch_conditions": [item for item in triggers if isinstance(item, dict) and not item.get("met")],
        "next_review_condition": "material signature changes, explicit manual refresh, or bounded periodic review",
        "model_versions": model_versions,
        "visualization_intent": {
            "decision_question": visualization_plan.get("decision_question"),
            "primary": visualization_plan.get("primary", {}).get("type") if isinstance(visualization_plan.get("primary"), dict) else None,
            "secondary": visualization_plan.get("secondary", {}).get("type") if isinstance(visualization_plan.get("secondary"), dict) else None,
            "reason": visualization_plan.get("rationale"),
        },
        "authority": "decision-support-only",
        "equipment_control": False,
    }
