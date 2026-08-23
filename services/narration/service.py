from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .providers import NarrationProviderPort, providers_from_env

AUDIENCES = {"manager", "engineer"}


def _deterministic_brief(packet: dict[str, Any], audience: str, *, mode: str, provider: str, fallback_reason: str | None = None) -> dict[str, Any]:
    option = next(option for option in packet["options"] if option["option_id"] == packet["recommended_option_id"])
    top = packet["evidence"].get("top_candidate")
    impact = packet["impact"]
    if audience == "manager":
        headline = f"{packet['priority_band']} decision · {packet['lot_id']}"
        summary = (
            f"{packet['decision_question']} Current deterministic recommendation: {option['label']}. "
            "This is decision support only; no equipment command is executed."
        )
        sections = [
            {
                "section_id": "impact",
                "title": "Operational impact",
                "body": (
                    f"Affected scope: {impact['affected_equipment_count']} equipment / {impact['affected_chamber_count']} chambers / "
                    f"{impact['affected_lot_count']} lots. Synthetic yield gap: "
                    f"{impact['synthetic_yield_gap_percentage_points'] if impact['synthetic_yield_gap_percentage_points'] is not None else 'N/A'} pp."
                ),
                "evidence_refs": ["case.affected_scope", "case.mean_yield"],
            },
            {
                "section_id": "decision",
                "title": "Decision to make",
                "body": option["tradeoff"],
                "evidence_refs": ["decision.recommended_option_id", "decision.options"],
            },
        ]
    else:
        candidate = "No ranked RCA candidate" if top is None else f"Top RCA: {top['candidate_id']} (score {top['score']:.2f})"
        headline = f"Engineering evidence packet · {packet['case_id']}"
        summary = f"{candidate}. Recommended next decision: {option['label']}."
        sections = [
            {
                "section_id": "rca",
                "title": "RCA evidence",
                "body": (
                    "No candidate is available."
                    if top is None
                    else f"Supporting items: {len(top['supporting_evidence'])}; contradicting items: {len(top['contradicting_evidence'])}."
                ),
                "evidence_refs": ["rca.top_candidate", "rca.supporting_evidence", "rca.contradicting_evidence"],
            },
            {
                "section_id": "next",
                "title": "Next check",
                "body": option["tradeoff"],
                "evidence_refs": ["decision.recommended_option_id", "decision.options"],
            },
        ]
    return {
        "schema_version": "decision-brief-v1",
        "case_id": packet["case_id"],
        "audience": audience,
        "mode": mode,
        "provider": provider,
        "fallback_reason": fallback_reason,
        "headline": headline,
        "summary": summary,
        "recommended_option_id": packet["recommended_option_id"],
        "sections": sections,
        "citations": packet["evidence_refs"],
        "uncertainties": packet["uncertainties"],
        "limitations": [
            "Synthetic portfolio evidence only; not a real-fab or synthetic-to-real performance claim.",
            "Narration may reword accepted evidence but cannot change classification, RCA ranking, recommendation authority, or case state.",
            "No equipment control is available.",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _system_prompt(audience: str) -> str:
    focus = (
        "Lead with operational impact, the human decision to make, tradeoffs, and uncertainty. Keep model detail secondary."
        if audience == "manager"
        else "Lead with RCA evidence, supporting/contradicting evidence, uncertainty, and the next engineering check."
    )
    return f"""You generate grounded FabOps decision wording for a {audience}.

{focus}

Rules:
1. Use only the supplied decision_packet. Never invent a number, source, event, completion, root cause, or business cost.
2. Copy case_id and recommended_option_id exactly; you may not change the accepted deterministic recommendation.
3. Treat RCA as a ranked hypothesis. Never claim the root cause is confirmed unless the packet literally says so.
4. Never claim equipment was held, stopped, changed, or controlled.
5. Every section must cite only evidence_refs present in decision_packet.evidence_refs, plus these deterministic decision refs: decision.recommended_option_id and decision.options, case.affected_scope, case.mean_yield.
6. Return one JSON object with keys: schema_version, case_id, audience, headline, summary, recommended_option_id, sections, citations, uncertainties, limitations.
7. schema_version must be decision-brief-v1. sections must be objects with section_id, title, body, evidence_refs.
8. Write human-readable wording in Korean while leaving IDs unchanged.
"""


@dataclass
class NarrationService:
    providers: list[NarrationProviderPort] | None = None
    cache_ttl_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.providers is None:
            self.providers = providers_from_env()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def _cache_key(packet: dict[str, Any], audience: str) -> str:
        payload = json.dumps(
            {"packet": packet, "audience": audience},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def status(self) -> dict[str, Any]:
        return {
            "configured_providers": [provider.name for provider in self.providers or []],
            "fallback": "deterministic",
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "cache_entries": len(self._cache),
            "authority": "wording-only",
        }

    @staticmethod
    def _validate(packet: dict[str, Any], audience: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("schema_version") != "decision-brief-v1":
            raise ValueError("narration schema_version mismatch")
        if payload.get("case_id") != packet["case_id"]:
            raise ValueError("narration changed case_id")
        if payload.get("audience") != audience:
            raise ValueError("narration audience mismatch")
        if payload.get("recommended_option_id") != packet["recommended_option_id"]:
            raise ValueError("narration changed deterministic recommendation")
        allowed = set(packet["evidence_refs"]) | {
            "decision.recommended_option_id",
            "decision.options",
            "case.affected_scope",
            "case.mean_yield",
        }
        referenced = set(payload.get("citations", []))
        for section in payload.get("sections", []):
            referenced.update(section.get("evidence_refs", []))
        unknown = referenced - allowed
        if unknown:
            raise ValueError(f"narration contains unknown evidence refs: {sorted(unknown)}")
        text = " ".join(
            [
                str(payload.get("headline", "")),
                str(payload.get("summary", "")),
                *(str(section.get("body", "")) for section in payload.get("sections", [])),
            ]
        )
        for forbidden in ("자동 정지 완료", "설비 정지 완료", "작업 지시가 실행", "근본 원인이 확정", "고장이 확정"):
            if forbidden in text:
                raise ValueError("narration contains a forbidden operational claim")
        return payload

    def generate(self, packet: dict[str, Any], audience: str) -> dict[str, Any]:
        if audience not in AUDIENCES:
            raise ValueError(f"unsupported audience: {audience}")
        cache_key = self._cache_key(packet, audience)
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached is not None and now - cached[0] <= self.cache_ttl_seconds:
            return {**cached[1], "cache_hit": True}
        failures: list[str] = []
        for provider in self.providers or []:
            try:
                raw = provider.generate_json(_system_prompt(audience), {"decision_packet": packet, "audience": audience})
                payload = self._validate(packet, audience, raw)
                payload.update(
                    {
                        "mode": "llm",
                        "provider": provider.name,
                        "fallback_reason": None,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "cache_hit": False,
                    }
                )
                self._cache[cache_key] = (now, payload)
                return payload
            except Exception as exc:  # noqa: BLE001 - provider/schema/grounding failures fail closed to deterministic wording
                failures.append(f"{provider.name}:{type(exc).__name__}")
        reason = ",".join(failures) if failures else "llm_not_configured"
        payload = _deterministic_brief(packet, audience, mode="deterministic_fallback", provider="deterministic", fallback_reason=reason)
        payload["cache_hit"] = False
        self._cache[cache_key] = (now, payload)
        return payload
