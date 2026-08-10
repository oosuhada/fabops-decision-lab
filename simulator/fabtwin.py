from __future__ import annotations

import hashlib
import json
import math
import random
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from simulator.config import SimulatorConfig

GENERATOR_VERSION = "fabtwin-m1.0.0"
SCHEMA_VERSION = 1
NAMESPACE = uuid.UUID("f9fe5ff8-7b35-4c81-9f4e-3b0d0edfa901")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


@dataclass
class GeneratedTrace:
    events: list[dict[str, Any]]
    ground_truth: dict[str, Any]
    config: SimulatorConfig


@dataclass(frozen=True)
class _FaultTruthRecord:
    """Simulator-private hidden truth record.

    Operational packages never import the ``ground_truth`` namespace. The simulator
    emits this record only into the separate evaluation artifact.
    """

    fault_id: str
    family: str
    physical_fault: bool
    yield_impact: bool
    start_lot: int
    end_lot: int
    step_id: str | None
    equipment_id: str | None
    chamber_id: str | None
    product_family: str | None
    expected_defect_pattern: str | None
    causal_parent: str | None
    expected_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FabTwinSimulator:
    def __init__(self, config: SimulatorConfig, seed: int):
        self.config = config
        self.seed = seed
        self.random = random.Random(seed)
        self.sequence = 0
        self.base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.ar_state: dict[tuple[str, str], float] = {}
        self.chamber_effect: dict[str, float] = {}
        self.events: list[dict[str, Any]] = []
        self.faults = self._fault_truth()

    def _fault_truth(self) -> list[_FaultTruthRecord]:
        max_lot = max(12, self.config.lot_count)
        # The first twelve lots are intentionally reserved as deterministic fault
        # fixtures, while larger profiles continue with nominal traffic.
        return [
            _FaultTruthRecord("fault-F1", "F1", True, True, 2, 3, "ETCH", "ETCH-01", "ETCH-01-A", None, "Edge-Loc", "maintenance-calibration", "hold chamber and verify calibration"),
            _FaultTruthRecord("fault-F2", "F2", True, True, 4, 4, "DEPOSITION", "DEPOSITION-01", "DEPOSITION-01-B", None, "Random", "cleaning-overdue", "clean chamber and inspect affected lots"),
            _FaultTruthRecord("fault-F3", "F3", True, True, 5, 5, "ETCH", None, None, "PF-B", "Center", "recipe-version-mismatch", "rollback recipe and identify affected lots"),
            _FaultTruthRecord("fault-F4", "F4", True, True, 6, 6, "ETCH", "ETCH-02", "ETCH-02-B", None, "Scratch", "litho-etch-interaction", "hold combination and request metrology"),
            _FaultTruthRecord("fault-F5", "F5", False, False, 7, 7, "CMP", "CMP-01", "CMP-01-A", None, None, "sensor-calibration-bias", "verify sensor; do not hold equipment"),
            _FaultTruthRecord("fault-F6", "F6", False, False, 8, 8, None, None, None, None, None, "event-delivery-quality", "replay and reconcile; no physical action"),
        ] if max_lot >= 12 else []

    def _id(self, label: str) -> str:
        return str(uuid.uuid5(NAMESPACE, f"{self.config.version}:{self.seed}:{label}"))

    def _equipment(self, step: str, lot_index: int) -> tuple[str, str]:
        equipment_number = (lot_index % self.config.equipment_per_step) + 1
        chamber_number = ((lot_index // self.config.equipment_per_step) % self.config.chambers_per_equipment)
        equipment_id = f"{step}-{equipment_number:02d}"
        chamber_id = f"{equipment_id}-{chr(ord('A') + chamber_number)}"
        # Force the small deterministic fixtures onto their intended scopes.
        overrides = {
            (2, "ETCH"): ("ETCH-01", "ETCH-01-A"),
            (3, "ETCH"): ("ETCH-01", "ETCH-01-A"),
            (4, "DEPOSITION"): ("DEPOSITION-01", "DEPOSITION-01-B"),
            (6, "LITHO"): ("LITHO-01", "LITHO-01-A"),
            (6, "ETCH"): ("ETCH-02", "ETCH-02-B"),
            (7, "CMP"): ("CMP-01", "CMP-01-A"),
        }
        return overrides.get((lot_index, step), (equipment_id, chamber_id))

    def _event(
        self,
        event_type: str,
        minute: int,
        payload: dict[str, Any],
        *,
        trace_id: str,
        lot_id: str | None = None,
        wafer_id: str | None = None,
        equipment_id: str | None = None,
        chamber_id: str | None = None,
        source: str = "fabtwin-sim",
        arrival_delay_seconds: int = 2,
    ) -> dict[str, Any]:
        self.sequence += 1
        event_time = self.base_time + timedelta(minutes=minute)
        event_id = self._id(f"event:{self.sequence}:{event_type}:{trace_id}")
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "event_time": event_time.isoformat().replace("+00:00", "Z"),
            "ingested_at": (event_time + timedelta(seconds=arrival_delay_seconds)).isoformat().replace("+00:00", "Z"),
            "source": source,
            "trace_id": trace_id,
            "lot_id": lot_id,
            "wafer_id": wafer_id,
            "equipment_id": equipment_id,
            "chamber_id": chamber_id,
            "schema_version": SCHEMA_VERSION,
            "data_classification": "synthetic",
            "payload": payload,
        }
        self.events.append(event)
        return event

    def _fault_effect(self, lot_index: int, step: str, equipment_id: str, chamber_id: str, product: str) -> tuple[float, dict[str, float], list[str]]:
        physical = 0.0
        sensor_only: dict[str, float] = {}
        active: list[str] = []
        if lot_index in (2, 3) and step == "ETCH" and chamber_id == "ETCH-01-A":
            physical += 1.0 + 0.45 * (lot_index - 2)
            sensor_only["temperature"] = physical
            active.append("F1")
        if lot_index == 4 and step == "DEPOSITION" and chamber_id == "DEPOSITION-01-B":
            physical += 1.4
            sensor_only["particle_count"] = 2.8
            active.append("F2")
        if lot_index == 5 and step == "ETCH" and product == "PF-B":
            physical += 1.15
            sensor_only["rf_power"] = 1.3
            active.append("F3")
        if lot_index == 6 and step == "ETCH" and equipment_id == "ETCH-02" and chamber_id == "ETCH-02-B":
            physical += 1.65
            sensor_only["pressure"] = 0.9
            active.append("F4")
        if lot_index == 7 and step == "CMP" and chamber_id == "CMP-01-A":
            # F5 is measurement-only: it must never affect physical deviation or yield.
            sensor_only["temperature"] = 2.2
            active.append("F5")
        return physical, sensor_only, active

    def _sensor_value(self, sensor: str, chamber_id: str, recipe_baseline: float, product_index: int, lot_index: int, sensor_fault: float) -> float:
        key = (chamber_id, sensor)
        previous = self.ar_state.get(key, 0.0)
        innovation = self.random.gauss(0.0, self.config.process_noise)
        correlated_common = self.random.gauss(0.0, self.config.process_noise * 0.55)
        ar_value = self.config.ar1_phi * previous + innovation + correlated_common
        self.ar_state[key] = ar_value
        if chamber_id not in self.chamber_effect:
            self.chamber_effect[chamber_id] = self.random.gauss(0.0, self.config.chamber_effect_std)
        product_effect = (product_index - 1) * 0.07
        aging = lot_index * self.config.tool_aging_per_lot
        measurement_noise = self.random.gauss(0.0, self.config.measurement_noise)
        return round(recipe_baseline + product_effect + self.chamber_effect[chamber_id] + aging + ar_value + sensor_fault + measurement_noise, 5)

    def generate(self) -> GeneratedTrace:
        cumulative_risk: dict[str, float] = {}
        lot_minutes = max(30, int((self.config.simulated_days * 24 * 60) / max(1, self.config.lot_count)))

        for lot_index in range(1, self.config.lot_count + 1):
            lot_id = f"LOT-{lot_index:05d}"
            product_index = (lot_index - 1) % len(self.config.product_families)
            product = self.config.product_families[product_index]
            # Ensure the F3 fixture is PF-B regardless of ordinary rotation.
            if lot_index == 5:
                product = "PF-B"
                product_index = self.config.product_families.index(product)
            lot_start = (lot_index - 1) * lot_minutes
            trace_id = self._id(f"trace:{lot_id}")
            wafer_ids = [f"{lot_id}-W{index:02d}" for index in range(1, self.config.wafers_per_lot + 1)]
            self._event(
                "lot.released.v1",
                lot_start,
                {"product_family": product, "wafer_ids": wafer_ids, "provenance": "synthetic"},
                trace_id=trace_id,
                lot_id=lot_id,
            )

            lot_physical_risk = 0.0
            for step_index, step in enumerate(self.config.process_steps):
                equipment_id, chamber_id = self._equipment(step, lot_index)
                run_id = self._id(f"run:{lot_id}:{step}")
                minute = lot_start + step_index * 5 + 1
                expected_recipe = f"{product}-{step}-v2"
                actual_recipe = f"{product}-{step}-v1" if (lot_index == 5 and step == "ETCH") else expected_recipe
                self._event(
                    "process.started.v1",
                    minute,
                    {"process_run_id": run_id, "step_id": step, "recipe_id": actual_recipe, "expected_recipe_id": expected_recipe},
                    trace_id=trace_id,
                    lot_id=lot_id,
                    equipment_id=equipment_id,
                    chamber_id=chamber_id,
                )

                physical_effect, sensor_effects, active_faults = self._fault_effect(lot_index, step, equipment_id, chamber_id, product)
                if physical_effect:
                    lot_physical_risk += physical_effect
                if step != "INSPECTION":
                    for sensor_index, sensor in enumerate(self.config.sensors):
                        baseline = 10.0 + sensor_index * 5.0 + step_index * 0.3
                        sensor_value = self._sensor_value(
                            sensor,
                            chamber_id,
                            baseline,
                            product_index,
                            lot_index,
                            sensor_effects.get(sensor, 0.0),
                        )
                        self._event(
                            "process.measurement.recorded.v1",
                            minute + 1,
                            {
                                "process_run_id": run_id,
                                "step_id": step,
                                "sensor_name": sensor,
                                "value": sensor_value,
                                "unit": "normalized-unit",
                                "recipe_id": actual_recipe,
                            },
                            trace_id=trace_id,
                            lot_id=lot_id,
                            equipment_id=equipment_id,
                            chamber_id=chamber_id,
                        )
                self._event(
                    "process.completed.v1",
                    minute + 3,
                    {"process_run_id": run_id, "step_id": step, "recipe_id": actual_recipe, "status": "completed"},
                    trace_id=trace_id,
                    lot_id=lot_id,
                    equipment_id=equipment_id,
                    chamber_id=chamber_id,
                )

                if active_faults and any(fault in {"F1", "F2", "F5"} for fault in active_faults):
                    self._event(
                        "equipment.alarm.raised.v1",
                        minute + 2,
                        {"alarm_code": f"SIM-{active_faults[0]}", "severity": "warning", "step_id": step, "process_run_id": run_id},
                        trace_id=trace_id,
                        lot_id=lot_id,
                        equipment_id=equipment_id,
                        chamber_id=chamber_id,
                    )

            # Inspections are tied to the lot's completed lineage, while yield is
            # driven only by physical risk. F5/F6 therefore cannot degrade it.
            base_risk = -3.2 + self.random.gauss(0.0, 0.2)
            failure_probability = _sigmoid(base_risk + lot_physical_risk * 1.35)
            cumulative_risk[lot_id] = failure_probability
            for wafer_index, wafer_id in enumerate(wafer_ids, start=1):
                wafer_noise = self.random.random() * 0.04
                failed_die_ratio = min(0.95, max(0.0, failure_probability + wafer_noise))
                yield_value = round(1.0 - failed_die_ratio, 5)
                defect_pattern = "None"
                if lot_index in (2, 3):
                    defect_pattern = "Edge-Loc"
                elif lot_index == 4:
                    defect_pattern = "Random"
                elif lot_index == 5:
                    defect_pattern = "Center"
                elif lot_index == 6:
                    defect_pattern = "Scratch"
                self._event(
                    "inspection.completed.v1",
                    lot_start + len(self.config.process_steps) * 5 + wafer_index,
                    {
                        "inspection_id": self._id(f"inspection:{wafer_id}"),
                        "step_id": "INSPECTION",
                        "yield": yield_value,
                        "failed_die_ratio": round(failed_die_ratio, 5),
                        "defect_pattern": defect_pattern,
                        "pattern_provenance": "synthetic-not-WM811K-lineage",
                    },
                    trace_id=trace_id,
                    lot_id=lot_id,
                    wafer_id=wafer_id,
                )

            if lot_index == 1:
                self._event(
                    "maintenance.completed.v1",
                    lot_start + 28,
                    {"maintenance_id": self._id("maintenance:ETCH-01"), "maintenance_type": "calibration", "result": "completed"},
                    trace_id=trace_id,
                    equipment_id="ETCH-01",
                    chamber_id="ETCH-01-A",
                )

            if lot_index == 8:
                # F6 models delivery path anomalies as explicit quality events; it
                # intentionally does not duplicate canonical event IDs in the trace.
                for offset, incident_type in enumerate(("duplicate_attempt", "late", "out_of_order", "missing_expected_event")):
                    delay = 1800 if incident_type == "late" else 2
                    self._event(
                        "data.quality.incident.v1",
                        lot_start + 35 + offset,
                        {"incident_type": incident_type, "physical_fault": False, "recommended_action": "reconcile_event_stream"},
                        trace_id=trace_id,
                        lot_id=lot_id,
                        arrival_delay_seconds=delay,
                    )

        # Contract fixtures for the governed lifecycle introduced in M1. These are
        # synthetic scenario events, not evidence that actions happened in a real fab.
        lifecycle_trace = self._id("trace:governed-workflow-fixture")
        for index, (event_type, status) in enumerate(
            (
                ("action.proposed.v1", "proposed"),
                ("action.approved.v1", "approved"),
                ("action.rejected.v1", "rejected"),
                ("case.closed.v1", "closed"),
            )
        ):
            self._event(
                event_type,
                self.config.simulated_days * 24 * 60 + index,
                {"case_id": "CASE-SIM-CONTRACT", "status": status, "fixture_only": True},
                trace_id=lifecycle_trace,
                source="fabtwin-sim-contract-fixture",
            )

        truth = {
            "namespace": "ground_truth",
            "evaluation_only": True,
            "seed": self.seed,
            "fault_family": "F1-F6-multi-fault-fixture",
            "config_version": self.config.version,
            "generator_version": GENERATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
            "faults": [fault.to_dict() for fault in self.faults],
            "lot_failure_probability": cumulative_risk,
        }
        return GeneratedTrace(events=self.events, ground_truth=truth, config=self.config)

