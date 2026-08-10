from __future__ import annotations

from typing import Any

EXPECTED = {
    "F1": "chamber:ETCH-01-A",
    "F2": "chamber:DEPOSITION-01-B",
    "F3": "recipe:PF-B-ETCH-v1",
    "F4": "interaction:LITHO-01-A+ETCH-02-B",
    "F5": "sensor:temperature:CMP-01-A",
    "F6": "data_quality:event-delivery",
}


def rca_metrics(rankings_by_lot: dict[str, list[dict[str, Any]]], ground_truth: dict[str, Any]) -> dict[str, float]:
    expected_by_lot: dict[str, str] = {}
    family_by_lot: dict[str, str] = {}
    for fault in ground_truth["faults"]:
        for lot_index in range(fault["start_lot"], fault["end_lot"] + 1):
            lot_id = f"LOT-{lot_index:05d}"
            expected_by_lot[lot_id] = EXPECTED[fault["family"]]
            family_by_lot[lot_id] = fault["family"]
    reciprocal: list[float] = []
    top1 = 0
    top3 = 0
    evidence_nonempty = 0
    contradiction_covered = 0
    false_causal = 0
    for lot_id, expected in expected_by_lot.items():
        ranking = rankings_by_lot[lot_id]
        ids = [candidate["candidate_id"] for candidate in ranking]
        if ids and ids[0] == expected:
            top1 += 1
        if expected in ids[:3]:
            top3 += 1
        rank = ids.index(expected) + 1 if expected in ids else 0
        reciprocal.append(1.0 / rank if rank else 0.0)
        if ranking and ranking[0]["supporting_evidence"]:
            evidence_nonempty += 1
        if ranking and ranking[0]["contradicting_evidence"]:
            contradiction_covered += 1
        if family_by_lot[lot_id] in {"F5", "F6"} and ranking and ranking[0]["candidate_type"] in {"equipment", "chamber"}:
            false_causal += 1
    total = len(expected_by_lot)
    return {
        "top1_accuracy": round(top1 / total, 5),
        "top3_accuracy": round(top3 / total, 5),
        "mrr": round(sum(reciprocal) / total, 5),
        "evidence_precision_proxy": round(evidence_nonempty / total, 5),
        "contradicting_evidence_coverage": round(contradiction_covered / total, 5),
        "false_causal_attribution_rate": round(false_causal / total, 5),
    }

