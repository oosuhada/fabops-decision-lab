from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker

from services.ingestion.ports import CaseRepositoryPort, EventRepositoryPort, QuarantinePort


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class IngestionService:
    def __init__(
        self,
        event_repository: EventRepositoryPort,
        case_repository: CaseRepositoryPort,
        quarantine: QuarantinePort,
        projector: Callable[[dict[str, Any]], None],
        *,
        late_after_seconds: int = 900,
        out_of_order_tolerance_seconds: int = 0,
    ) -> None:
        schema = json.loads(Path("contracts/events/event-envelope.schema.json").read_text(encoding="utf-8"))
        self.validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.events = event_repository
        self.cases = case_repository
        self.quarantine = quarantine
        self.projector = projector
        self.late_after_seconds = late_after_seconds
        self.out_of_order_tolerance_seconds = out_of_order_tolerance_seconds
        self.last_event_time_by_trace: dict[str, datetime] = {}

    def ingest(self, raw_event: dict[str, Any]) -> str:
        errors = sorted(self.validator.iter_errors(raw_event), key=lambda item: list(item.path))
        if errors:
            self.quarantine.put(raw_event, "; ".join(error.message for error in errors))
            return "quarantined"
        event_id = str(raw_event["event_id"])
        if not self.events.reserve_event_id(event_id):
            return "duplicate_noop"

        event_time = _parse_time(str(raw_event["event_time"]))
        ingested_at = _parse_time(str(raw_event.get("ingested_at", raw_event["event_time"])))
        trace_id = str(raw_event.get("trace_id") or "untraced")
        previous = self.last_event_time_by_trace.get(trace_id)
        delivery_status = "on_time"
        if (ingested_at - event_time).total_seconds() > self.late_after_seconds:
            delivery_status = "late"
        if previous and (previous - event_time).total_seconds() > self.out_of_order_tolerance_seconds:
            delivery_status = "out_of_order"
        if previous is None or event_time > previous:
            self.last_event_time_by_trace[trace_id] = event_time

        stored = self.events.append_event(raw_event, delivery_status)
        self.projector(raw_event)
        self.events.set_checkpoint("detection", stored.sequence)
        self.events.append_outbox("fabops.events.accepted", {"event_id": event_id, "sequence": stored.sequence, "delivery_status": delivery_status})
        return delivery_status

    def replay(self) -> None:
        for stored in self.events.all_events():
            self.projector(stored.event)
            self.events.set_checkpoint("detection", stored.sequence)

