from __future__ import annotations

import hashlib
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Iterator

TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
CORRELATION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


@dataclass(frozen=True)
class TelemetryContext:
    trace_id: str
    span_id: str
    correlation_id: str
    causal_trace_id: str


CURRENT_CONTEXT: ContextVar[TelemetryContext | None] = ContextVar("fabops_telemetry_context", default=None)


def canonical_trace_id(value: str) -> str:
    compact = value.strip().lower().replace("-", "")
    if TRACE_ID_RE.fullmatch(compact) and compact != "0" * 32:
        return compact
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return digest if digest != "0" * 32 else "1" + digest[1:]


def parse_trace_header(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().lower()
    match = TRACEPARENT_RE.fullmatch(candidate)
    if match and match.group(1) != "0" * 32:
        return match.group(1)
    compact = candidate.replace("-", "")
    if TRACE_ID_RE.fullmatch(compact) and compact != "0" * 32:
        return compact
    return None


def normalize_correlation_id(value: str | None, fallback: str) -> str:
    if value and CORRELATION_ID_RE.fullmatch(value.strip()):
        return value.strip()
    digest = hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:24]
    return f"corr-{digest}"


@contextmanager
def bind_context(context: TelemetryContext) -> Iterator[TelemetryContext]:
    token = CURRENT_CONTEXT.set(context)
    try:
        yield context
    finally:
        CURRENT_CONTEXT.reset(token)


@contextmanager
def replace_context(**changes: str) -> Iterator[TelemetryContext | None]:
    current = CURRENT_CONTEXT.get()
    if current is None:
        yield None
        return
    with bind_context(replace(current, **changes)) as updated:
        yield updated
