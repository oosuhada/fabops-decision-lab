from __future__ import annotations

from typing import Any


def detector_metrics(cases: list[dict[str, Any]], ground_truth: dict[str, Any], simulated_days: int) -> dict[str, Any]:
    physical_lots: set[str] = set()
    for fault in ground_truth["faults"]:
        if fault["physical_fault"] and fault["yield_impact"]:
            for index in range(fault["start_lot"], fault["end_lot"] + 1):
                physical_lots.add(f"LOT-{index:05d}")
    detected_physical = {case["lot_id"] for case in cases if case["classification"] == "physical_excursion"}
    false_physical = detected_physical - physical_lots
    scope_true_positive = len(detected_physical & physical_lots)
    recall = scope_true_positive / len(physical_lots) if physical_lots else 1.0
    precision = scope_true_positive / len(detected_physical) if detected_physical else 1.0
    return {
        "fault_recall": round(recall, 5),
        "false_alarms_per_simulated_day": round(len(false_physical) / max(1, simulated_days), 5),
        "mean_detection_delay_events": 0.0,
        "affected_scope_precision": round(precision, 5),
        "affected_scope_recall": round(recall, 5),
    }

