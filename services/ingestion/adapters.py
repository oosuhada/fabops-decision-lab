from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from services.ingestion.ports import QuarantinedEvent, StoredEvent


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._reserved: set[str] = set()
        self._events: list[StoredEvent] = []
        self._outbox: list[dict[str, Any]] = []
        self._checkpoints: dict[str, int] = {}

    def reserve_event_id(self, event_id: str) -> bool:
        if event_id in self._reserved:
            return False
        self._reserved.add(event_id)
        return True

    def append_event(self, event: dict[str, Any], delivery_status: str) -> StoredEvent:
        stored = StoredEvent(deepcopy(event), delivery_status, len(self._events) + 1)
        self._events.append(stored)
        return stored

    def all_events(self) -> list[StoredEvent]:
        return deepcopy(self._events)

    def trace_id_for_lot(self, lot_id: str) -> str | None:
        for stored in self._events:
            event = stored.event
            if str(event.get("lot_id") or "") == lot_id and event.get("trace_id"):
                return str(event["trace_id"])
        return None

    def append_outbox(self, topic: str, payload: dict[str, Any]) -> None:
        self._outbox.append({"sequence": len(self._outbox) + 1, "topic": topic, "payload": deepcopy(payload), "published": False})

    def outbox(self) -> list[dict[str, Any]]:
        return deepcopy(self._outbox)

    def set_checkpoint(self, consumer: str, sequence: int) -> None:
        self._checkpoints[consumer] = sequence

    def checkpoint(self, consumer: str) -> int:
        return self._checkpoints.get(consumer, 0)

    def snapshot(self) -> dict[str, Any]:
        return {
            "reserved": sorted(self._reserved),
            "events": [
                {"event": deepcopy(item.event), "delivery_status": item.delivery_status, "sequence": item.sequence}
                for item in self._events
            ],
            "outbox": deepcopy(self._outbox),
            "checkpoints": deepcopy(self._checkpoints),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        self._reserved = set(str(item) for item in snapshot.get("reserved", []))
        self._events = [
            StoredEvent(deepcopy(item["event"]), str(item["delivery_status"]), int(item["sequence"]))
            for item in snapshot.get("events", [])
        ]
        self._outbox = deepcopy(snapshot.get("outbox", []))
        self._checkpoints = {str(key): int(value) for key, value in snapshot.get("checkpoints", {}).items()}


class InMemoryCaseRepository:
    def __init__(self) -> None:
        self._cases: dict[str, dict[str, Any]] = {}
        self._audit: list[dict[str, Any]] = []

    def upsert_case(self, case: dict[str, Any]) -> bool:
        case_id = str(case["case_id"])
        created = case_id not in self._cases
        self._cases[case_id] = deepcopy(case)
        return created

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        value = self._cases.get(case_id)
        return deepcopy(value) if value is not None else None

    def list_cases(self) -> list[dict[str, Any]]:
        return [deepcopy(self._cases[key]) for key in sorted(self._cases)]

    def append_audit(self, record: dict[str, Any]) -> None:
        item = deepcopy(record)
        item["audit_sequence"] = len(self._audit) + 1
        self._audit.append(item)

    def audit_log(self) -> list[dict[str, Any]]:
        return deepcopy(self._audit)

    def audit_for_case(self, case_id: str) -> list[dict[str, Any]]:
        return [deepcopy(record) for record in self._audit if record.get("case_id") == case_id]

    def related_cases(self, classification: str, exclude_case_id: str, limit: int = 3) -> list[dict[str, Any]]:
        matches = [
            deepcopy(case)
            for case in self._cases.values()
            if case.get("classification") == classification and case.get("case_id") != exclude_case_id
        ]
        matches.sort(key=lambda case: str(case.get("lot_id", "")), reverse=True)
        return matches[: max(1, int(limit))]

    def snapshot(self) -> dict[str, Any]:
        return {"cases": deepcopy(self._cases), "audit": deepcopy(self._audit)}

    def restore(self, snapshot: dict[str, Any]) -> None:
        self._cases = {str(key): deepcopy(value) for key, value in snapshot.get("cases", {}).items()}
        self._audit = deepcopy(snapshot.get("audit", []))


class InMemoryQuarantine:
    def __init__(self) -> None:
        self._items: list[QuarantinedEvent] = []

    def put(self, raw_event: dict[str, Any], reason: str) -> None:
        self._items.append(QuarantinedEvent(deepcopy(raw_event), reason))

    def all(self) -> list[QuarantinedEvent]:
        return deepcopy(self._items)


class DeterministicLocalEventBus:
    """Synchronous local adapter with explicit retry/DLQ behavior."""

    def __init__(self, max_attempts: int = 3) -> None:
        self._handlers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self.max_attempts = max_attempts
        self.dlq: list[dict[str, Any]] = []

    def subscribe(self, topic: str, handler: Callable[[dict[str, Any]], None]) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        for handler in self._handlers.get(topic, []):
            last_error: Exception | None = None
            for _attempt in range(1, self.max_attempts + 1):
                try:
                    handler(deepcopy(event))
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001 - adapter records explicit retry contract
                    last_error = exc
            if last_error is not None:
                self.dlq.append({"topic": topic, "event": deepcopy(event), "attempts": self.max_attempts, "error": type(last_error).__name__})

