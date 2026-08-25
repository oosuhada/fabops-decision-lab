from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


class ProviderBlockedError(RuntimeError):
    """Raised when provider governance rejects a generation before network I/O."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ProviderPolicy:
    max_requests_per_minute: int = 30
    max_concurrency: int = 2
    daily_request_limit: int = 500
    daily_estimated_token_limit: int = 1_000_000
    circuit_failure_threshold: int = 3
    circuit_cooldown_seconds: float = 60.0
    max_output_tokens: int = 900


@dataclass
class _ProviderState:
    minute_requests: deque[float] = field(default_factory=deque)
    active_requests: int = 0
    daily_date: str = ""
    daily_requests: int = 0
    daily_estimated_tokens: int = 0
    consecutive_failures: int = 0
    circuit_open_until: float = 0.0
    last_block_reason: str | None = None
    last_failure: str | None = None
    total_requests_started: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_busy_responses: int = 0
    circuit_openings: int = 0
    block_counts: dict[str, int] = field(default_factory=dict)


class ProviderGovernor:
    """In-process fail-fast provider controls.

    The governor intentionally never queues unbounded work. If a provider is at
    concurrency/rate/budget capacity, narration immediately falls through to the
    next provider or deterministic wording.
    """

    def __init__(self, policies: dict[str, ProviderPolicy] | None = None) -> None:
        self._policies = policies or {}
        self._states: dict[str, _ProviderState] = {}
        self._lock = threading.Lock()

    @staticmethod
    def estimate_tokens(payload: Any) -> int:
        # Conservative dependency-free approximation. The budget is a safety
        # ceiling, not a billing statement.
        return max(1, (len(str(payload)) + 3) // 4)

    def _policy(self, provider_name: str) -> ProviderPolicy:
        return self._policies.get(provider_name, ProviderPolicy())

    def _state(self, provider_name: str) -> _ProviderState:
        return self._states.setdefault(provider_name, _ProviderState())

    @staticmethod
    def _utc_date() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _reset_day_if_needed(self, state: _ProviderState) -> None:
        today = self._utc_date()
        if state.daily_date != today:
            state.daily_date = today
            state.daily_requests = 0
            state.daily_estimated_tokens = 0

    def run(
        self,
        provider_name: str,
        estimated_input_tokens: int,
        call: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        policy = self._policy(provider_name)
        now = time.monotonic()
        estimated_total_tokens = estimated_input_tokens + policy.max_output_tokens
        with self._lock:
            state = self._state(provider_name)
            self._reset_day_if_needed(state)
            while state.minute_requests and now - state.minute_requests[0] >= 60.0:
                state.minute_requests.popleft()

            reason: str | None = None
            if state.circuit_open_until > now:
                reason = "circuit_open"
            elif state.active_requests >= policy.max_concurrency:
                reason = "concurrency_exhausted"
            elif len(state.minute_requests) >= policy.max_requests_per_minute:
                reason = "rate_limit_exhausted"
            elif state.daily_requests >= policy.daily_request_limit:
                reason = "daily_request_budget_exhausted"
            elif state.daily_estimated_tokens + estimated_total_tokens > policy.daily_estimated_token_limit:
                reason = "daily_token_budget_exhausted"

            if reason is not None:
                state.last_block_reason = reason
                state.block_counts[reason] = state.block_counts.get(reason, 0) + 1
                raise ProviderBlockedError(reason)

            state.active_requests += 1
            state.minute_requests.append(now)
            state.daily_requests += 1
            state.daily_estimated_tokens += estimated_total_tokens
            state.total_requests_started += 1
            state.last_block_reason = None

        try:
            result = call()
        except Exception as exc:
            with self._lock:
                state = self._state(provider_name)
                if bool(getattr(exc, "provider_busy", False)):
                    state.total_busy_responses += 1
                    state.last_failure = None
                    raise
                state.consecutive_failures += 1
                state.total_failures += 1
                state.last_failure = type(exc).__name__
                if state.consecutive_failures >= policy.circuit_failure_threshold:
                    if state.circuit_open_until <= time.monotonic():
                        state.circuit_openings += 1
                    state.circuit_open_until = time.monotonic() + policy.circuit_cooldown_seconds
            raise
        else:
            with self._lock:
                state = self._state(provider_name)
                state.consecutive_failures = 0
                state.circuit_open_until = 0.0
                state.last_failure = None
                state.total_successes += 1
            return result
        finally:
            with self._lock:
                state = self._state(provider_name)
                state.active_requests = max(0, state.active_requests - 1)

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            provider_names = sorted(set(self._policies) | set(self._states))
            result: dict[str, Any] = {}
            for name in provider_names:
                policy = self._policy(name)
                state = self._state(name)
                self._reset_day_if_needed(state)
                while state.minute_requests and now - state.minute_requests[0] >= 60.0:
                    state.minute_requests.popleft()
                provider_state = "circuit_open" if state.circuit_open_until > now else "degraded" if state.consecutive_failures else "available"
                result[name] = {
                    "state": provider_state,
                    "active_requests": state.active_requests,
                    "requests_last_minute": len(state.minute_requests),
                    "max_requests_per_minute": policy.max_requests_per_minute,
                    "max_concurrency": policy.max_concurrency,
                    "daily_requests": state.daily_requests,
                    "daily_request_limit": policy.daily_request_limit,
                    "daily_estimated_tokens": state.daily_estimated_tokens,
                    "daily_estimated_token_limit": policy.daily_estimated_token_limit,
                    "last_block_reason": state.last_block_reason,
                    "last_failure": state.last_failure,
                    "consecutive_failures": state.consecutive_failures,
                    "total_requests_started": state.total_requests_started,
                    "total_successes": state.total_successes,
                    "total_failures": state.total_failures,
                    "total_busy_responses": state.total_busy_responses,
                    "circuit_openings": state.circuit_openings,
                    "block_counts": dict(sorted(state.block_counts.items())),
                }
            return result


def _env_int(name: str, default: int) -> int:
    return max(1, int(os.getenv(name, str(default))))


def _env_float(name: str, default: float) -> float:
    return max(0.1, float(os.getenv(name, str(default))))


def governor_from_env(provider_names: list[str]) -> ProviderGovernor:
    policies: dict[str, ProviderPolicy] = {}
    for provider_name in provider_names:
        prefix = "FABOPS_VERTEX" if provider_name == "vertex-ai-gemini" else "FABOPS_LOCAL_LLM"
        policies[provider_name] = ProviderPolicy(
            max_requests_per_minute=_env_int(f"{prefix}_MAX_RPM", 12 if provider_name == "vertex-ai-gemini" else 30),
            max_concurrency=_env_int(f"{prefix}_MAX_CONCURRENCY", 1 if provider_name == "vertex-ai-gemini" else 2),
            daily_request_limit=_env_int(f"{prefix}_DAILY_REQUEST_LIMIT", 100 if provider_name == "vertex-ai-gemini" else 1000),
            daily_estimated_token_limit=_env_int(
                f"{prefix}_DAILY_ESTIMATED_TOKEN_LIMIT",
                250_000 if provider_name == "vertex-ai-gemini" else 2_000_000,
            ),
            circuit_failure_threshold=_env_int(f"{prefix}_CIRCUIT_FAILURE_THRESHOLD", 3),
            circuit_cooldown_seconds=_env_float(f"{prefix}_CIRCUIT_COOLDOWN_SECONDS", 60.0),
            max_output_tokens=_env_int(f"{prefix}_MAX_OUTPUT_TOKENS", 700),
        )
    return ProviderGovernor(policies)
