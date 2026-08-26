from __future__ import annotations

import hashlib
import json
from typing import Any

ALLOWED_RENDERER_TYPES = ["timeseries", "heatmap", "histogram", "comparison", "timeline", "graph", "table", "metric"]


def material_signature(case: dict[str, Any], predictions: list[dict[str, Any]]) -> str:
    payload = {
        "case_id": case["case_id"],
        "classification": case["classification"],
        "anomaly_bucket": round(float(case.get("anomaly_score", 0.0)), 1),
        "yield_bucket": round(float(case.get("mean_yield") or 0.0), 2),
        "predictions": sorted((item["target"], round(float(item["score"]), 1)) for item in predictions),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def visualization_plan(case: dict[str, Any], predictions: list[dict[str, Any]], signature: str) -> dict[str, Any]:
    by_target = {item["target"]: item for item in predictions}
    excursion = float(by_target.get("final_excursion_probability", {}).get("score", 0.0))
    maintenance = float(by_target.get("next_lot_maintenance_attention_probability", {}).get("score", 0.0))
    excursion_alarm = float(by_target.get("next_lot_excursion_alarm_probability", {}).get("score", 0.0))
    chamber_count = len(case.get("affected_scope", {}).get("chambers", []))
    case_id = str(case["case_id"])
    lot_id = str(case.get("lot_id") or "unknown")
    common = {
        "case_id": case_id,
        "lot_id": lot_id,
        "time_window": "current lot through POST_CMP plus bounded recent baseline",
        "evidence_refs": [f"case.{case_id}", f"lot.{lot_id}"],
    }
    if case.get("classification") == "data_quality_incident":
        question = "Is the apparent process issue actually a data-delivery integrity problem?"
        primary = {**common, "type": "timeline", "x": "event_time", "title": "Delivery integrity timeline"}
        secondary = {**common, "type": "table", "title": "Source evidence ledger"}
        rationale = "Data-quality state makes event ordering and source evidence the dominant question."
    elif maintenance >= 0.65 or excursion_alarm >= 0.72:
        question = "Why did next-lot excursion/alarm or maintenance-attention risk increase?"
        primary = {**common, "type": "timeseries", "x": "event_time", "y": "value", "group_by": "sensor_name", "title": "Excursion/alarm precursor trajectory"}
        secondary = {**common, "type": "timeline", "x": "event_time", "title": "Alarm and maintenance evidence sequence"}
        rationale = "Next-lot excursion/alarm or maintenance-attention risk dominates; trend and event sequence carry the most information without implying equipment failure or RUL."
    elif chamber_count >= 2:
        question = "Is the evidence isolated to one chamber or shared across the affected scope?"
        primary = {**common, "type": "heatmap", "x": "chamber_id", "y": "value", "group_by": "sensor_name", "title": "Cross-chamber signal intensity"}
        secondary = {**common, "type": "comparison", "x": "chamber_id", "y": "value", "title": "Chamber comparison"}
        rationale = "The affected scope spans multiple chambers, so spatial comparison is more diagnostic than a single trace."
    elif excursion >= 0.55 or case.get("classification") == "sensor_bias_suspected":
        question = "Did the process signal drift over time or did its distribution shift?"
        primary = {**common, "type": "timeseries", "x": "event_time", "y": "value", "group_by": "sensor_name", "title": "Excursion signal trajectory"}
        secondary = {**common, "type": "histogram", "x": "value", "title": "Signal distribution shift"}
        rationale = "Excursion/sensor-bias evidence is dominated by temporal drift and distribution change."
    else:
        question = "Which current evidence dimension best separates this case from its recent baseline?"
        primary = {**common, "type": "comparison", "x": "sensor_name", "y": "value", "title": "Current evidence comparison"}
        secondary = {**common, "type": "metric", "y": "value", "title": "Current signal summary"}
        rationale = "No single failure mode dominates; comparison preserves broad situational awareness."
    return {
        "schema_version": "fabops-visualization-spec-v2",
        "case_id": case_id,
        "lot_id": lot_id,
        "material_signature": signature,
        "decision_question": question,
        "primary": primary,
        "secondary": secondary,
        "rationale": rationale,
        "planner": "deterministic-situation-aware-v1",
        "allowed_renderer_types": ALLOWED_RENDERER_TYPES,
    }


def validated_llm_visualization_plan(base_plan: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    """Apply a bounded LLM visualization proposal to deterministic data bindings.

    The LLM may choose the decision question and renderer pair only. It cannot
    provide HTML/JS, arbitrary fields, case identity, evidence references, or
    data coordinates. Those are reconstructed here from the deterministic plan.
    Invalid proposals fall back to the deterministic plan unchanged.
    """

    proposal = brief.get("visualization_proposal")
    if not isinstance(proposal, dict):
        return base_plan
    primary_type = str(proposal.get("primary_type") or "")
    secondary_type = str(proposal.get("secondary_type") or "")
    if primary_type not in ALLOWED_RENDERER_TYPES or secondary_type not in ALLOWED_RENDERER_TYPES:
        return {**base_plan, "proposal_validation": "fallback_invalid_renderer"}
    question = str(proposal.get("decision_question") or "").strip()
    reason = str(proposal.get("reason") or "").strip()
    if not question or not reason or len(question) > 180 or len(reason) > 320:
        return {**base_plan, "proposal_validation": "fallback_invalid_text"}

    common_source = base_plan.get("primary", {}) if isinstance(base_plan.get("primary"), dict) else {}
    common = {
        "case_id": base_plan.get("case_id"),
        "lot_id": base_plan.get("lot_id"),
        "time_window": common_source.get("time_window", "current lot through POST_CMP plus bounded recent baseline"),
        "evidence_refs": list(common_source.get("evidence_refs", [])),
    }
    registry: dict[str, dict[str, Any]] = {
        "timeseries": {"type": "timeseries", "x": "event_time", "y": "value", "group_by": "sensor_name", "title": "Evidence trajectory"},
        "heatmap": {"type": "heatmap", "x": "chamber_id", "y": "value", "group_by": "sensor_name", "title": "Cross-chamber evidence"},
        "histogram": {"type": "histogram", "x": "value", "title": "Recent vs baseline distribution"},
        "comparison": {"type": "comparison", "x": "sensor_name", "y": "value", "title": "Evidence comparison"},
        "timeline": {"type": "timeline", "x": "event_time", "title": "Evidence event sequence"},
        "graph": {"type": "graph", "title": "RCA evidence relationships"},
        "table": {"type": "table", "title": "Source evidence ledger"},
        "metric": {"type": "metric", "y": "value", "title": "Current signal summary"},
    }
    return {
        **base_plan,
        "decision_question": question,
        "primary": {**common, **registry[primary_type]},
        "secondary": {**common, **registry[secondary_type]},
        "rationale": reason,
        "planner": "llm-proposed-validated-v1",
        "proposal_provider": brief.get("provider"),
        "proposal_validation": "accepted",
        "allowed_renderer_types": ALLOWED_RENDERER_TYPES,
    }

