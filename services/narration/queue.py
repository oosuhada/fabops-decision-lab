from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

MANUAL_PRIORITY = 100
AUTO_HIGH_PRIORITY = 60
AUTO_MATERIAL_PRIORITY = 30

TERMINAL_JOB_STATUSES = {"COMPLETED", "FALLBACK", "FAILED", "EXPIRED", "CANCELLED"}


def queue_policy(trigger_type: str, urgency: str) -> dict[str, Any]:
    """Return bounded queue/fallback policy for one assessment request."""

    if trigger_type == "manual_user_refresh":
        return {
            "priority": MANUAL_PRIORITY,
            "max_queue_age_seconds": 300,
            "fallback_after_seconds": 45,
            "allow_vertex_fallback": True,
            "max_attempts": 4,
        }
    if urgency == "HIGH":
        return {
            "priority": AUTO_HIGH_PRIORITY,
            "max_queue_age_seconds": 300,
            "fallback_after_seconds": 180,
            "allow_vertex_fallback": True,
            "max_attempts": 4,
        }
    return {
        "priority": AUTO_MATERIAL_PRIORITY,
        "max_queue_age_seconds": 900,
        "fallback_after_seconds": None,
        "allow_vertex_fallback": False,
        "max_attempts": 5,
    }


def request_fingerprint(request_document: dict[str, Any]) -> str:
    encoded = json.dumps(request_document, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_inference_job(
    *,
    case_id: str,
    material_signature: str,
    trigger_type: str,
    urgency: str,
    request_document: dict[str, Any],
) -> dict[str, Any]:
    policy = queue_policy(trigger_type, urgency)
    assessment_run_id = str(uuid.uuid4())
    fingerprint = request_fingerprint(request_document)
    dedupe_scope = "manual" if trigger_type == "manual_user_refresh" else "auto"
    return {
        "assessment_run_id": assessment_run_id,
        "case_id": case_id,
        "intent": str(request_document.get("intent") or "situation_update"),
        "trigger_type": trigger_type,
        "priority": policy["priority"],
        "max_queue_age_seconds": policy["max_queue_age_seconds"],
        "max_attempts": policy["max_attempts"],
        "input_context_fingerprint": fingerprint,
        "material_signature": material_signature,
        "provider_preference": "local-qwen",
        "allow_vertex_fallback": policy["allow_vertex_fallback"],
        "fallback_after_seconds": policy["fallback_after_seconds"],
        "dedupe_key": f"{dedupe_scope}:{case_id}:{material_signature}",
        "request_document": request_document,
    }


def retry_backoff_seconds(attempt_count: int, *, busy: bool) -> float:
    if busy:
        return float(min(15, max(2, 2 ** min(3, max(1, attempt_count)))))
    return float(min(60, max(5, 5 * max(1, attempt_count))))
