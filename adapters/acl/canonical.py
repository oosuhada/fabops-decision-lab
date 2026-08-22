from __future__ import annotations

from copy import deepcopy
from typing import Any


class CanonicalInputAdapter:
    @staticmethod
    def simulator_event(event: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(event)
        normalized["data_classification"] = "synthetic"
        normalized["payload"].setdefault("source_semantics", "fabtwin-sim")
        return normalized

    @staticmethod
    def public_record(dataset: str, record_id: str, features: dict[str, Any]) -> dict[str, Any]:
        # Anonymous features are deliberately preserved as anonymous identifiers.
        return {
            "record_id": record_id,
            "dataset": dataset,
            "data_classification": "real-public",
            "features": deepcopy(features),
            "semantics_policy": "preserve-source-names; do-not-invent-process-meaning",
        }

    @staticmethod
    def mes_like_event(event: dict[str, Any], source_system: str) -> dict[str, Any]:
        normalized = deepcopy(event)
        normalized["source"] = source_system
        normalized.setdefault("payload", {})["source_semantics"] = "external-mes-like"
        return normalized

