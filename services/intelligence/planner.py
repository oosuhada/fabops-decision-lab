from __future__ import annotations

import hashlib
import json
from typing import Any


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
    excursion = float(by_target.get("excursion_probability", {}).get("score", 0.0))
    maintenance = float(by_target.get("maintenance_probability", {}).get("score", 0.0))
    failure = float(by_target.get("future_failure_probability", {}).get("score", 0.0))
    chamber_count = len(case.get("affected_scope", {}).get("chambers", []))
    if case.get("classification") == "data_quality_incident":
        primary = {"type": "timeline", "x": "event_time", "title": "Delivery integrity timeline"}
        secondary = {"type": "table", "title": "Source evidence ledger"}
        rationale = "Data-quality state makes event ordering and source evidence the dominant question."
    elif maintenance >= 0.65 or failure >= 0.72:
        primary = {"type": "timeseries", "x": "event_time", "y": "value", "group_by": "sensor_name", "title": "Failure precursor trajectory"}
        secondary = {"type": "timeline", "x": "event_time", "title": "Alarm and maintenance sequence"}
        rationale = "Failure or maintenance risk dominates; trend and event sequence carry the most information."
    elif chamber_count >= 2:
        primary = {"type": "heatmap", "x": "chamber_id", "y": "value", "group_by": "sensor_name", "title": "Cross-chamber signal intensity"}
        secondary = {"type": "comparison", "x": "chamber_id", "y": "value", "title": "Chamber comparison"}
        rationale = "The affected scope spans multiple chambers, so spatial comparison is more diagnostic than a single trace."
    elif excursion >= 0.55 or case.get("classification") == "sensor_bias_suspected":
        primary = {"type": "timeseries", "x": "event_time", "y": "value", "group_by": "sensor_name", "title": "Excursion signal and forecast"}
        secondary = {"type": "histogram", "x": "value", "title": "Signal distribution shift"}
        rationale = "Excursion/sensor-bias evidence is dominated by temporal drift and distribution change."
    else:
        primary = {"type": "comparison", "x": "sensor_name", "y": "value", "title": "Current evidence comparison"}
        secondary = {"type": "metric", "y": "value", "title": "Current signal summary"}
        rationale = "No single failure mode dominates; comparison preserves broad situational awareness."
    return {
        "schema_version": "fabops-adaptive-visualization-v1",
        "case_id": case["case_id"],
        "material_signature": signature,
        "primary": primary,
        "secondary": secondary,
        "rationale": rationale,
        "planner": "deterministic-situation-aware-v1",
    }

