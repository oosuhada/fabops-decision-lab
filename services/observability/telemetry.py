from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from services.observability.context import (
    CURRENT_CONTEXT,
    TelemetryContext,
    bind_context,
    canonical_trace_id,
    normalize_correlation_id,
    parse_trace_header,
)

SENSITIVE_KEY_MARKERS = ("ground_truth", "password", "secret", "credential", "authorization", "approval_token", "api_key")


def _safe_value(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in SENSITIVE_KEY_MARKERS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _safe_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class TelemetryRecorder:
    def __init__(
        self,
        service_name: str = "fabops-api",
        clock: Callable[[], datetime] | None = None,
        file_path: str | Path | None = None,
    ) -> None:
        self.service_name = service_name
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.file_path = Path(file_path) if file_path is not None else None
        self._records: list[dict[str, Any]] = []
        self._counter = 0
        self._lock = threading.Lock()

    def _next_span_id(self, trace_id: str, correlation_id: str, operation: str) -> str:
        with self._lock:
            self._counter += 1
            counter = self._counter
        digest = hashlib.sha256(f"{trace_id}:{correlation_id}:{operation}:{counter}".encode("utf-8")).hexdigest()[:16]
        return digest if digest != "0" * 16 else "1" + digest[1:]

    def current(self) -> TelemetryContext | None:
        return CURRENT_CONTEXT.get()

    @contextmanager
    def bind_causal_trace(self, causal_trace_id: str, correlation_id: str | None = None) -> Iterator[TelemetryContext]:
        trace_id = canonical_trace_id(causal_trace_id)
        current = self.current()
        correlation = normalize_correlation_id(
            correlation_id or (current.correlation_id if current else None),
            fallback=causal_trace_id,
        )
        context = TelemetryContext(trace_id, self._next_span_id(trace_id, correlation, "context"), correlation, causal_trace_id)
        with bind_context(context):
            yield context

    @contextmanager
    def bind_request(
        self,
        trace_header: str | None,
        correlation_header: str | None,
        fallback: str,
    ) -> Iterator[TelemetryContext]:
        trace_id = parse_trace_header(trace_header) or canonical_trace_id(fallback)
        correlation = normalize_correlation_id(correlation_header, fallback=fallback)
        context = TelemetryContext(trace_id, self._next_span_id(trace_id, correlation, "request"), correlation, fallback)
        with bind_context(context):
            yield context

    @contextmanager
    def operation(self, operation: str, **attributes: Any) -> Iterator[TelemetryContext]:
        current = self.current()
        if current is None:
            fallback = f"{self.service_name}:{operation}"
            trace_id = canonical_trace_id(fallback)
            correlation = normalize_correlation_id(None, fallback)
            current = TelemetryContext(trace_id, self._next_span_id(trace_id, correlation, "root"), correlation, fallback)
        child = TelemetryContext(
            current.trace_id,
            self._next_span_id(current.trace_id, current.correlation_id, operation),
            current.correlation_id,
            current.causal_trace_id,
        )
        with bind_context(child):
            try:
                yield child
            except Exception as exc:
                self.emit(operation, severity="ERROR", outcome="error", error_classification=type(exc).__name__, **attributes)
                raise
            else:
                self.emit(operation, severity="INFO", outcome="ok", **attributes)

    def emit(self, operation: str, severity: str = "INFO", outcome: str = "ok", **attributes: Any) -> dict[str, Any]:
        current = self.current()
        if current is None:
            fallback = f"{self.service_name}:{operation}"
            trace_id = canonical_trace_id(fallback)
            correlation = normalize_correlation_id(None, fallback)
            current = TelemetryContext(trace_id, self._next_span_id(trace_id, correlation, operation), correlation, fallback)
        record: dict[str, Any] = {
            "timestamp": self.clock().astimezone(timezone.utc).isoformat(),
            "severity": severity,
            "service.name": self.service_name,
            "operation": operation,
            "trace_id": current.trace_id,
            "span_id": current.span_id,
            "correlation_id": current.correlation_id,
            "causal_trace_id": current.causal_trace_id,
            "outcome": outcome,
        }
        record.update({key: _safe_value(value, key) for key, value in attributes.items()})
        with self._lock:
            self._records.append(record)
            if self.file_path is not None:
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                with self.file_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        return deepcopy(record)

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def export(self, path: str | Path, limit: int | None = None) -> None:
        records = self.records()
        if limit is not None:
            records = records[:limit]
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
