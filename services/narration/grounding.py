from __future__ import annotations

from typing import Any

DETERMINISTIC_EVIDENCE_REFS = {
    "decision.recommended_option_id",
    "decision.options",
    "case.affected_scope",
    "case.mean_yield",
    "case.impact",
}


def allowed_evidence_refs(packet: dict[str, Any]) -> list[str]:
    allowed = {
        str(reference)
        for reference in packet.get("evidence_refs", [])
        if isinstance(reference, str) and reference
    }
    allowed.update(DETERMINISTIC_EVIDENCE_REFS)
    allowed.update(f"decision.options[{index}]" for index, _ in enumerate(packet.get("options", [])))
    predictive = packet.get("predictive_intelligence", {})
    if isinstance(predictive, dict):
        allowed.update(f"prediction.{target}" for target in predictive)
    return sorted(allowed)


def reference_allowed(packet: dict[str, Any], reference: str) -> bool:
    return reference in set(allowed_evidence_refs(packet))
