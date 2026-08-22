from __future__ import annotations

import os
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from threading import Event
from typing import Any, Iterator

from simulator.config import load_config
from simulator.fabtwin import FabTwinSimulator


LIVE_NAMESPACE = uuid.UUID("9136ae43-c790-4c3f-9a93-67364fdff72d")


class LiveFabTwinStream:
    """Continuously replays the deterministic FabTwin scenario as new live lots.

    The existing simulator remains the deterministic scenario authority. This
    adapter turns that finite scenario into an infinite event stream by assigning
    fresh event/trace/object identities on every cycle and emitting each event at
    wall-clock time using an accelerated simulation clock.
    """

    def __init__(
        self,
        *,
        seed: int = 42,
        profile: str = "test",
        acceleration: float | None = None,
        minimum_interval_seconds: float = 0.03,
    ) -> None:
        self.config = load_config(profile)
        self.seed = seed
        self.acceleration = max(1.0, acceleration or float(os.getenv("FABOPS_LIVE_TIME_ACCELERATION", "720")))
        self.minimum_interval_seconds = max(0.0, minimum_interval_seconds)
        generated = FabTwinSimulator(self.config, seed).generate().events
        self.template = [event for event in generated if event.get("source") != "fabtwin-sim-contract-fixture"]

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _stable_uuid(self, cycle: int, kind: str, value: str) -> str:
        return str(uuid.uuid5(LIVE_NAMESPACE, f"{self.seed}:{cycle}:{kind}:{value}"))

    def _live_lot_id(self, cycle: int, value: str | None) -> str | None:
        if not value or not value.startswith("LOT-"):
            return value
        try:
            source_index = int(value.split("-", 1)[1])
        except ValueError:
            return value
        live_index = (cycle + 1) * self.config.lot_count + source_index
        return f"LOT-{live_index:05d}"

    def _live_wafer_id(self, cycle: int, value: str | None) -> str | None:
        if not value or "-W" not in value:
            return value
        lot_id, wafer_suffix = value.rsplit("-W", 1)
        live_lot = self._live_lot_id(cycle, lot_id)
        return f"{live_lot}-W{wafer_suffix}" if live_lot else value

    def _rewrite_payload(self, payload: dict[str, Any], cycle: int) -> dict[str, Any]:
        rewritten = deepcopy(payload)
        if isinstance(rewritten.get("wafer_ids"), list):
            rewritten["wafer_ids"] = [self._live_wafer_id(cycle, str(value)) for value in rewritten["wafer_ids"]]
        for key in ("process_run_id", "inspection_id", "maintenance_id"):
            value = rewritten.get(key)
            if value:
                rewritten[key] = self._stable_uuid(cycle, key, str(value))
        rewritten["live_cycle"] = cycle
        rewritten["simulation_acceleration"] = self.acceleration
        return rewritten

    def _rewrite_event(self, source: dict[str, Any], cycle: int) -> dict[str, Any]:
        event = deepcopy(source)
        event["event_id"] = self._stable_uuid(cycle, "event", str(source["event_id"]))
        event["trace_id"] = self._stable_uuid(cycle, "trace", str(source.get("trace_id") or source["event_id"]))
        event["lot_id"] = self._live_lot_id(cycle, source.get("lot_id"))
        event["wafer_id"] = self._live_wafer_id(cycle, source.get("wafer_id"))
        event["source"] = "fabtwin-live"
        event["payload"] = self._rewrite_payload(dict(source.get("payload", {})), cycle)
        now = self._now()
        event["event_time"] = now
        event["ingested_at"] = now
        return event

    def events(self, stop_event: Event | None = None) -> Iterator[dict[str, Any]]:
        cycle = 0
        while stop_event is None or not stop_event.is_set():
            previous_template_time: datetime | None = None
            for source in self.template:
                if stop_event is not None and stop_event.is_set():
                    return
                template_time = self._parse_time(str(source["event_time"]))
                if previous_template_time is not None:
                    simulated_delta = max(0.0, (template_time - previous_template_time).total_seconds())
                    delay = max(self.minimum_interval_seconds, simulated_delta / self.acceleration)
                    if stop_event is not None:
                        if stop_event.wait(delay):
                            return
                    else:
                        time.sleep(delay)
                previous_template_time = template_time
                yield self._rewrite_event(source, cycle)
            cycle += 1

