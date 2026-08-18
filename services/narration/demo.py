from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

DEMO_INTENTS = {
    "manager_summary",
    "engineer_checklist",
    "tradeoff_compare",
    "counter_evidence",
}


class DemoPolicyError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass
class DemoSessionPolicy:
    secret: str
    ttl_seconds: int = 1800
    max_generations_per_session: int = 5
    max_generations_per_ip_hour: int = 15

    def __post_init__(self) -> None:
        if len(self.secret) < 24:
            raise ValueError("demo session secret must contain at least 24 characters")
        self._lock = threading.Lock()
        self._session_counts: dict[str, tuple[float, int]] = {}
        self._ip_counts: dict[str, tuple[float, int]] = {}
        self._issued_sessions = 0
        self._accepted_generations = 0
        self._rejections: dict[str, int] = {}

    def _record_rejection(self, reason: str) -> None:
        with self._lock:
            self._rejections[reason] = self._rejections.get(reason, 0) + 1

    def issue(self) -> dict[str, Any]:
        now = int(time.time())
        payload = {
            "sid": secrets.token_urlsafe(12),
            "iat": now,
            "exp": now + self.ttl_seconds,
            "scope": "public-demo-narration",
        }
        encoded = _b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signature = _b64encode(hmac.new(self.secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
        result = {
            "token": f"{encoded}.{signature}",
            "expires_at": datetime.fromtimestamp(payload["exp"], tz=timezone.utc).isoformat(),
            "generation_limit": self.max_generations_per_session,
            "allowed_intents": sorted(DEMO_INTENTS),
        }
        with self._lock:
            self._issued_sessions += 1
        return result

    def _verify(self, token: str) -> dict[str, Any]:
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected = _b64encode(hmac.new(self.secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
            if not hmac.compare_digest(supplied_signature, expected):
                raise DemoPolicyError("invalid_session")
            payload = json.loads(_b64decode(encoded))
        except DemoPolicyError:
            raise
        except Exception as exc:  # noqa: BLE001 - malformed public token is an authorization failure
            raise DemoPolicyError("invalid_session") from exc
        if payload.get("scope") != "public-demo-narration" or int(payload.get("exp", 0)) <= int(time.time()):
            raise DemoPolicyError("expired_session")
        return payload

    def consume(self, token: str, client_id: str, intent: str) -> str:
        if intent not in DEMO_INTENTS:
            self._record_rejection("unsupported_intent")
            raise DemoPolicyError("unsupported_intent")
        try:
            payload = self._verify(token)
        except DemoPolicyError as exc:
            self._record_rejection(exc.reason)
            raise
        session_id = str(payload["sid"])
        now = time.monotonic()
        with self._lock:
            session_started, session_count = self._session_counts.get(session_id, (now, 0))
            if now - session_started >= self.ttl_seconds:
                session_started, session_count = now, 0
            ip_started, ip_count = self._ip_counts.get(client_id, (now, 0))
            if now - ip_started >= 3600:
                ip_started, ip_count = now, 0
            if session_count >= self.max_generations_per_session:
                self._rejections["session_generation_limit"] = self._rejections.get("session_generation_limit", 0) + 1
                raise DemoPolicyError("session_generation_limit")
            if ip_count >= self.max_generations_per_ip_hour:
                self._rejections["client_hourly_limit"] = self._rejections.get("client_hourly_limit", 0) + 1
                raise DemoPolicyError("client_hourly_limit")
            self._session_counts[session_id] = (session_started, session_count + 1)
            self._ip_counts[client_id] = (ip_started, ip_count + 1)
            self._accepted_generations += 1
        return session_id

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "session_ttl_seconds": self.ttl_seconds,
            "max_generations_per_session": self.max_generations_per_session,
            "max_generations_per_ip_hour": self.max_generations_per_ip_hour,
            "allowed_intents": sorted(DEMO_INTENTS),
            "issued_sessions": self._issued_sessions,
            "accepted_generations": self._accepted_generations,
            "rejections": dict(sorted(self._rejections.items())),
        }


def demo_policy_from_env() -> DemoSessionPolicy | None:
    if os.getenv("FABOPS_PUBLIC_AI_DEMO_ENABLED", "false").strip().lower() not in {"1", "true", "yes"}:
        return None
    secret = os.getenv("FABOPS_DEMO_SESSION_SECRET", "").strip()
    if not secret:
        raise RuntimeError("FABOPS_DEMO_SESSION_SECRET is required when public AI demo is enabled")
    return DemoSessionPolicy(
        secret=secret,
        ttl_seconds=int(os.getenv("FABOPS_DEMO_SESSION_TTL_SECONDS", "1800")),
        max_generations_per_session=int(os.getenv("FABOPS_DEMO_MAX_GENERATIONS_PER_SESSION", "5")),
        max_generations_per_ip_hour=int(os.getenv("FABOPS_DEMO_MAX_GENERATIONS_PER_IP_HOUR", "15")),
    )
