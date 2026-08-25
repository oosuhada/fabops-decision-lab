from __future__ import annotations

import hashlib
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
    """Continuously emits reproducible, domain-randomized live FabTwin lots.

    The existing simulator remains the deterministic scenario authority. This
    adapter turns that finite scenario into an infinite event stream by assigning
    fresh identities and applying bounded seed-derived process variation. The
    canonical deterministic fixture is therefore unchanged while the live
    learning stream does not merely repeat identical measurements and outcomes.
    """

    def __init__(
        self,
        *,
        seed: int = 42,
        profile: str = "test",
        acceleration: float | None = None,
        minimum_interval_seconds: float = 0.03,
        lot_base: int | None = None,
    ) -> None:
        self.config = load_config(profile)
        self.seed = seed
        self.acceleration = max(1.0, acceleration or float(os.getenv("FABOPS_LIVE_TIME_ACCELERATION", "720")))
        self.minimum_interval_seconds = max(0.0, minimum_interval_seconds)
        self.lot_base = self.config.lot_count if lot_base is None else max(0, lot_base)
        generated = FabTwinSimulator(self.config, seed).generate().events
        self.template = [event for event in generated if event.get("source") != "fabtwin-sim-contract-fixture"]

    @staticmethod
    def _parse_time(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _stable_uuid(self, cycle: int, kind: str, value: str) -> str:
        return str(uuid.uuid5(LIVE_NAMESPACE, f"{self.seed}:{self.lot_base}:{cycle}:{kind}:{value}"))

    def _unit(self, cycle: int, key: str) -> float:
        digest = hashlib.sha256(f"{self.seed}:{self.lot_base}:{cycle}:{key}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") / float((1 << 64) - 1)

    def _signed(self, cycle: int, key: str) -> float:
        return self._unit(cycle, key) * 2.0 - 1.0

    def _regime(self, cycle: int, lot_id: str | None) -> dict[str, float | str | list[str]]:
        lot_key = lot_id or "unscoped"
        degradation = 0.02 + self._unit(cycle, f"{lot_key}:degradation") * 0.12
        latent_fault_strength = max(0.0, self._unit(cycle, f"{lot_key}:latent-fault") - 0.72) / 0.28
        fault_mix: list[str] = []
        if abs(self._signed(cycle, f"{lot_key}:pressure")) > 0.58:
            fault_mix.append("pressure_drift")
        if abs(self._signed(cycle, f"{lot_key}:rf")) > 0.62:
            fault_mix.append("rf_instability")
        if self._unit(cycle, f"{lot_key}:particles") > 0.68:
            fault_mix.append("particle_excursion")
        if latent_fault_strength > 0.0:
            fault_mix.append("latent_degradation")
        return {
            "regime_version": "fabops-live-regime-v2",
            "regime_id": hashlib.sha256(f"{self.seed}:{cycle}:{lot_key}".encode("utf-8")).hexdigest()[:12],
            "degradation_index": round(degradation, 6),
            "sensor_bias": round(self._signed(cycle, f"{lot_key}:sensor-bias") * 0.28, 6),
            "pressure_drift": round(self._signed(cycle, f"{lot_key}:pressure") * 0.75, 6),
            "rf_instability": round(self._signed(cycle, f"{lot_key}:rf") * 0.9, 6),
            "particle_excursion": round(self._unit(cycle, f"{lot_key}:particles") * 1.25, 6),
            "recipe_sensitivity": round(0.85 + self._unit(cycle, f"{lot_key}:recipe") * 0.35, 6),
            "maintenance_effectiveness": round(0.45 + self._unit(cycle, f"{lot_key}:maintenance") * 0.5, 6),
            "latent_fault_strength": round(latent_fault_strength, 6),
            "fault_mix": fault_mix,
        }

    def _live_lot_id(self, cycle: int, value: str | None) -> str | None:
        if not value or not value.startswith("LOT-"):
            return value
        try:
            source_index = int(value.split("-", 1)[1])
        except ValueError:
            return value
        live_index = self.lot_base + cycle * self.config.lot_count + source_index
        return f"LOT-{live_index:05d}"

    def _live_wafer_id(self, cycle: int, value: str | None) -> str | None:
        if not value or "-W" not in value:
            return value
        lot_id, wafer_suffix = value.rsplit("-W", 1)
        live_lot = self._live_lot_id(cycle, lot_id)
        return f"{live_lot}-W{wafer_suffix}" if live_lot else value

    def _rewrite_payload(self, source: dict[str, Any], cycle: int) -> dict[str, Any]:
        payload = dict(source.get("payload", {}))
        rewritten = deepcopy(payload)
        lot_id = str(source.get("lot_id")) if source.get("lot_id") else None
        regime = self._regime(cycle, lot_id)
        if isinstance(rewritten.get("wafer_ids"), list):
            rewritten["wafer_ids"] = [self._live_wafer_id(cycle, str(value)) for value in rewritten["wafer_ids"]]
        for key in ("process_run_id", "inspection_id", "maintenance_id"):
            value = rewritten.get(key)
            if value:
                rewritten[key] = self._stable_uuid(cycle, key, str(value))

        event_type = str(source.get("event_type") or "")
        if event_type == "process.measurement.recorded.v1" and rewritten.get("value") is not None:
            sensor = str(rewritten.get("sensor_name") or "")
            step = str(rewritten.get("step_id") or "")
            recipe_factor = float(regime["recipe_sensitivity"])
            perturbation = float(regime["sensor_bias"])
            if sensor == "pressure":
                perturbation += float(regime["pressure_drift"])
            elif sensor == "rf_power":
                perturbation += float(regime["rf_instability"])
            elif sensor == "particle_count":
                perturbation += float(regime["particle_excursion"])
            elif sensor == "temperature":
                perturbation += float(regime["degradation_index"]) * 1.8
            perturbation *= recipe_factor
            perturbation += self._signed(cycle, f"{lot_id}:{step}:{sensor}:noise") * 0.16
            rewritten["value"] = round(float(rewritten["value"]) + perturbation, 5)

        if event_type == "inspection.completed.v1" and rewritten.get("yield") is not None:
            latent_penalty = float(regime["latent_fault_strength"]) * 0.085
            degradation_penalty = float(regime["degradation_index"]) * 0.16
            particle_penalty = max(0.0, float(regime["particle_excursion"]) - 0.82) * 0.025
            wafer_noise = self._signed(cycle, f"{lot_id}:{source.get('wafer_id')}:yield") * 0.012
            randomized_yield = max(
                0.55,
                min(0.99, float(rewritten["yield"]) - latent_penalty - degradation_penalty - particle_penalty + wafer_noise),
            )
            rewritten["yield"] = round(randomized_yield, 5)
            rewritten["failed_die_ratio"] = round(1.0 - randomized_yield, 5)

        if event_type == "equipment.alarm.raised.v1":
            rewritten["domain_randomized_severity_index"] = round(
                min(1.0, float(regime["degradation_index"]) * 2.5 + float(regime["latent_fault_strength"]) * 0.55),
                6,
            )

        if event_type == "maintenance.completed.v1":
            rewritten["maintenance_effectiveness"] = regime["maintenance_effectiveness"]

        if event_type == "lot.released.v1":
            rewritten["live_regime"] = regime
        rewritten["live_cycle"] = cycle
        rewritten["live_regime_id"] = regime["regime_id"]
        rewritten["domain_randomized"] = True
        rewritten["simulation_acceleration"] = self.acceleration
        return rewritten

    def _rewrite_event(self, source: dict[str, Any], cycle: int) -> dict[str, Any]:
        event = deepcopy(source)
        event["event_id"] = self._stable_uuid(cycle, "event", str(source["event_id"]))
        event["trace_id"] = self._stable_uuid(cycle, "trace", str(source.get("trace_id") or source["event_id"]))
        event["lot_id"] = self._live_lot_id(cycle, source.get("lot_id"))
        event["wafer_id"] = self._live_wafer_id(cycle, source.get("wafer_id"))
        event["source"] = "fabtwin-live"
        event["payload"] = self._rewrite_payload(source, cycle)
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

