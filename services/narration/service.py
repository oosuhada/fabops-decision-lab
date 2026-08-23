from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .demo import DEMO_INTENTS
from .governance import ProviderBlockedError, ProviderGovernor, governor_from_env
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


def _system_prompt(audience: str, intent: str = "decision_brief") -> str:
    focus = (
        "Lead with operational impact, the human decision to make, tradeoffs, and uncertainty. Keep model detail secondary."
        if audience == "manager"
        else "Lead with RCA evidence, supporting/contradicting evidence, uncertainty, and the next engineering check."
    )
    intent_focus = {
        "decision_brief": "Produce a balanced decision brief.",
        "manager_summary": "Produce a concise manager-facing decision summary with impact, recommendation, alternatives, and uncertainty.",
        "engineer_checklist": "Produce an engineer-facing diagnostic checklist using only grounded evidence and next checks.",
        "tradeoff_compare": "Emphasize comparison of the supplied decision options and their stated tradeoffs.",
        "counter_evidence": "Emphasize contradicting evidence, missing evidence, and what would reduce uncertainty.",
    }.get(intent, "Produce a balanced decision brief.")
    return f"""You generate grounded FabOps decision wording for a {audience}.

{focus}
{intent_focus}

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
    governor: ProviderGovernor | None = None

    def __post_init__(self) -> None:
        if self.providers is None:
            self.providers = providers_from_env()
        if self.governor is None:
            self.governor = governor_from_env([provider.name for provider in self.providers or []])
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._stats_lock = threading.Lock()
        self._cache_only_reads = 0
        self._live_generation_requests = 0
        self._cache_hits = 0
        self._fallback_count = 0
        self._validation_rejections = 0
        self._provider_selections: dict[str, int] = {}
        self._latencies_ms: deque[float] = deque(maxlen=500)
        self._last_narration_source = "deterministic_fallback"

    @staticmethod
    def _cache_key(packet: dict[str, Any], audience: str, intent: str = "decision_brief") -> str:
        payload = json.dumps(
            {"packet": packet, "audience": audience, "intent": intent},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def status(self) -> dict[str, Any]:
        governance = self.governor.status() if self.governor else {}
        configured = {provider.name for provider in self.providers or []}
        local_governance = governance.get("local-qwen", {})
        vertex_governance = governance.get("vertex-ai-gemini", {})
        local_state = "offline"
        if "local-qwen" in configured:
            local_state = "circuit_open" if local_governance.get("state") == "circuit_open" else "degraded" if local_governance.get("state") == "degraded" else "healthy"
        vertex_project = os.getenv("FABOPS_VERTEX_PROJECT", "").strip()
        vertex_enabled = os.getenv("FABOPS_VERTEX_ENABLED", "true").strip().lower() in {"1", "true", "yes"}
        narration_mode = os.getenv("FABOPS_NARRATION_MODE", "deterministic").strip().lower()
        if "vertex-ai-gemini" in configured:
            if vertex_governance.get("state") == "circuit_open":
                vertex_state = "circuit_open"
            elif str(vertex_governance.get("last_block_reason", "")).startswith("daily_"):
                vertex_state = "budget_exhausted"
            else:
                vertex_state = "healthy"
        elif not vertex_project:
            vertex_state = "unconfigured"
        elif not vertex_enabled or narration_mode not in {"auto", "vertex"}:
            vertex_state = "disabled"
        else:
            vertex_state = "unconfigured"
        with self._stats_lock:
            latencies = sorted(self._latencies_ms)
            metrics = {
                "cache_only_reads": self._cache_only_reads,
                "live_generation_requests": self._live_generation_requests,
                "cache_hits": self._cache_hits,
                "fallback_count": self._fallback_count,
                "validation_rejections": self._validation_rejections,
                "provider_selections": dict(sorted(self._provider_selections.items())),
                "generation_latency_ms": {
                    "samples": len(latencies),
                    "p50": self._percentile(latencies, 0.50),
                    "p95": self._percentile(latencies, 0.95),
                    "p99": self._percentile(latencies, 0.99),
                },
            }
            last_source = self._last_narration_source
        return {
            "configured_providers": [provider.name for provider in self.providers or []],
            "fallback": "deterministic",
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "cache_entries": len(self._cache),
            "authority": "wording-only",
            "provider_health": {"local_llm": local_state, "vertex": vertex_state},
            "narration": {"last_source": last_source},
            "metrics": metrics,
            "provider_governance": governance,
        }

    @staticmethod
    def _percentile(values: list[float], fraction: float) -> float | None:
        if not values:
            return None
        index = min(len(values) - 1, max(0, round((len(values) - 1) * fraction)))
        return round(values[index], 3)

    def _record_live_result(self, payload: dict[str, Any], elapsed_ms: float) -> None:
        source = "cached" if payload.get("cache_hit") else "deterministic_fallback" if payload.get("mode") == "deterministic_fallback" else "vertex" if payload.get("provider") == "vertex-ai-gemini" else "local"
        with self._stats_lock:
            self._live_generation_requests += 1
            self._latencies_ms.append(elapsed_ms)
            if payload.get("cache_hit"):
                self._cache_hits += 1
            elif payload.get("mode") == "deterministic_fallback":
                self._fallback_count += 1
            else:
                provider = str(payload.get("provider") or "unknown")
                self._provider_selections[provider] = self._provider_selections.get(provider, 0) + 1
            self._last_narration_source = source

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

    def cached_or_deterministic(self, packet: dict[str, Any], audience: str, *, intent: str = "decision_brief") -> dict[str, Any]:
        if audience not in AUDIENCES:
            raise ValueError(f"unsupported audience: {audience}")
        with self._stats_lock:
            self._cache_only_reads += 1
        cache_key = self._cache_key(packet, audience, intent)
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached is not None and now - cached[0] <= self.cache_ttl_seconds:
            with self._stats_lock:
                self._cache_hits += 1
                self._last_narration_source = "cached"
            return {**cached[1], "cache_hit": True}
        payload = _deterministic_brief(
            packet,
            audience,
            mode="deterministic_fallback",
            provider="deterministic",
            fallback_reason="public_cache_miss",
        )
        payload["cache_hit"] = False
        payload["intent"] = intent
        return payload

    def generate(self, packet: dict[str, Any], audience: str, *, intent: str = "decision_brief") -> dict[str, Any]:
        if audience not in AUDIENCES:
            raise ValueError(f"unsupported audience: {audience}")
        if intent != "decision_brief" and intent not in DEMO_INTENTS:
            raise ValueError(f"unsupported narration intent: {intent}")
        started = time.perf_counter()
        cache_key = self._cache_key(packet, audience, intent)
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached is not None and now - cached[0] <= self.cache_ttl_seconds:
            payload = {**cached[1], "cache_hit": True}
            self._record_live_result(payload, (time.perf_counter() - started) * 1000)
            return payload
        failures: list[str] = []
        prompt_payload = {"decision_packet": packet, "audience": audience, "intent": intent}
        estimated_input_tokens = self.governor.estimate_tokens(prompt_payload) if self.governor else 1
        for provider in self.providers or []:
            try:
                if self.governor:
                    raw = self.governor.run(
                        provider.name,
                        estimated_input_tokens,
                        lambda provider=provider: provider.generate_json(_system_prompt(audience, intent), prompt_payload),
                    )
                else:
                    raw = provider.generate_json(_system_prompt(audience, intent), prompt_payload)
                payload = self._validate(packet, audience, raw)
                payload.update(
                    {
                        "mode": "llm",
                        "provider": provider.name,
                        "fallback_reason": None,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "cache_hit": False,
                        "intent": intent,
                        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    }
                )
                self._cache[cache_key] = (now, payload)
                self._record_live_result(payload, float(payload["latency_ms"]))
                return payload
            except ProviderBlockedError as exc:
                failures.append(f"{provider.name}:{exc.reason}")
            except Exception as exc:  # noqa: BLE001 - provider/schema/grounding failures fail closed to deterministic wording
                if isinstance(exc, ValueError):
                    with self._stats_lock:
                        self._validation_rejections += 1
                failures.append(f"{provider.name}:{type(exc).__name__}")
        reason = ",".join(failures) if failures else "llm_not_configured"
        payload = _deterministic_brief(packet, audience, mode="deterministic_fallback", provider="deterministic", fallback_reason=reason)
        payload["cache_hit"] = False
        payload["intent"] = intent
        payload["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        self._cache[cache_key] = (now, payload)
        self._record_live_result(payload, float(payload["latency_ms"]))
        return payload
