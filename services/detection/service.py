from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.ingestion.ports import CaseRepositoryPort
from services.observability.telemetry import TelemetryRecorder

STEP_INDEX = {"LITHO": 0, "ETCH": 1, "DEPOSITION": 2, "CMP": 3, "INSPECTION": 4}
SENSOR_INDEX = {"temperature": 0, "particle_count": 1, "rf_power": 2, "pressure": 3, "gas_flow": 4, "vibration": 5, "voltage": 6, "current": 7}


@dataclass(frozen=True)
class DetectorConfig:
    version: str
    shewhart_delta: float
    ewma_lambda: float
    ewma_delta: float
    excursion_yield_threshold: float
    sensor_bias_min_anomalies: int

    @classmethod
    def load(cls, path: str | Path = "services/detection/detector-config.v1.json") -> "DetectorConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


class DeterministicDetector:
    def __init__(
        self,
        case_repository: CaseRepositoryPort,
        config: DetectorConfig | None = None,
        telemetry: TelemetryRecorder | None = None,
    ) -> None:
        self.cases = case_repository
        self.config = config or DetectorConfig.load()
        self.telemetry = telemetry
        self.ewma: dict[tuple[str, str], float] = {}
        self.lot_anomalies: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.lot_scope: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"equipment": set(), "chambers": set()})
        self.lot_inspections: dict[str, list[float]] = defaultdict(list)
        self.quality_incidents: dict[str, list[str]] = defaultdict(list)
        self.alarm_codes: dict[str, list[str]] = defaultdict(list)
        self.lot_trace_ids: dict[str, str] = {}

    def _case_id(self, lot_id: str, classification: str) -> str:
        digest = hashlib.sha256(f"{self.config.version}:{lot_id}:{classification}".encode()).hexdigest()[:16]
        return f"CASE-{digest.upper()}"

    def _expected(self, sensor: str, step: str) -> float:
        return 10.0 + SENSOR_INDEX.get(sensor, 0) * 5.0 + STEP_INDEX.get(step, 0) * 0.3

    def consume(self, event: dict[str, Any]) -> None:
        if self.telemetry is not None:
            with self.telemetry.operation(
                "detection.consume",
                event_id=event.get("event_id"),
                event_type=event.get("event_type"),
                detector_version=self.config.version,
            ):
                self._consume(event)
            return
        self._consume(event)

    def _consume(self, event: dict[str, Any]) -> None:
        event_type = event["event_type"]
        lot_id = event.get("lot_id")
        if not lot_id:
            return
        if event.get("trace_id"):
            self.lot_trace_ids[str(lot_id)] = str(event["trace_id"])
        if event.get("equipment_id"):
            self.lot_scope[lot_id]["equipment"].add(event["equipment_id"])
        if event.get("chamber_id"):
            self.lot_scope[lot_id]["chambers"].add(event["chamber_id"])

        if event_type == "process.measurement.recorded.v1":
            sensor = event["payload"]["sensor_name"]
            step = event["payload"]["step_id"]
            value = float(event["payload"]["value"])
            expected = self._expected(sensor, step)
            delta = value - expected
            key = (str(event.get("chamber_id")), sensor)
            previous = self.ewma.get(key, expected)
            current = self.config.ewma_lambda * value + (1 - self.config.ewma_lambda) * previous
            self.ewma[key] = current
            shewhart = abs(delta) >= self.config.shewhart_delta
            ewma_excursion = abs(current - expected) >= self.config.ewma_delta
            if shewhart or ewma_excursion:
                self.lot_anomalies[lot_id].append(
                    {
                        "event_id": event["event_id"],
                        "sensor": sensor,
                        "step": step,
                        "delta": round(delta, 5),
                        "shewhart": shewhart,
                        "ewma": round(current, 5),
                    }
                )
            return

        if event_type == "equipment.alarm.raised.v1":
            self.alarm_codes[lot_id].append(str(event["payload"]["alarm_code"]))
            return

        if event_type == "data.quality.incident.v1":
            self.quality_incidents[lot_id].append(str(event["payload"]["incident_type"]))
            self._materialize(lot_id, classification="data_quality_incident", force=True)
            return

        if event_type == "inspection.completed.v1":
            self.lot_inspections[lot_id].append(float(event["payload"]["yield"]))
            self._materialize(lot_id)

    def _materialize(self, lot_id: str, classification: str | None = None, force: bool = False) -> None:
        yields = self.lot_inspections.get(lot_id, [])
        mean_yield = sum(yields) / len(yields) if yields else None
        anomalies = self.lot_anomalies.get(lot_id, [])
        if classification is None:
            if mean_yield is not None and mean_yield < self.config.excursion_yield_threshold:
                classification = "physical_excursion"
            elif len(anomalies) >= self.config.sensor_bias_min_anomalies and mean_yield is not None and mean_yield >= self.config.excursion_yield_threshold:
                classification = "sensor_bias_suspected"
            else:
                return
        if not force and classification == "sensor_bias_suspected" and not any(code == "SIM-F5" for code in self.alarm_codes.get(lot_id, [])):
            return

        case_id = self._case_id(lot_id, classification)
        score = 0.0
        if mean_yield is not None:
            score += max(0.0, (self.config.excursion_yield_threshold - mean_yield) * 10.0)
        score += min(2.0, len(anomalies) * 0.15)
        if classification == "data_quality_incident":
            score = 1.0
        case = {
            "case_id": case_id,
            "lot_id": lot_id,
            "classification": classification,
            "detector_version": self.config.version,
            "anomaly_score": round(score, 5),
            "mean_yield": round(mean_yield, 5) if mean_yield is not None else None,
            "affected_scope": {
                "equipment": sorted(self.lot_scope[lot_id]["equipment"]),
                "chambers": sorted(self.lot_scope[lot_id]["chambers"]),
            },
            "evidence_event_ids": sorted(item["event_id"] for item in anomalies),
            "data_quality_incidents": sorted(set(self.quality_incidents.get(lot_id, []))),
            "causal_trace_id": self.lot_trace_ids.get(lot_id),
            "state": "detected",
        }
        created = self.cases.upsert_case(case)
        if created:
            self.cases.append_audit({"case_id": case_id, "event": "case.detected", "detector_version": self.config.version, "classification": classification})
            if self.telemetry is not None:
                self.telemetry.emit(
                    "case.materialized",
                    case_id=case_id,
                    detector_version=self.config.version,
                    event_id=case["evidence_event_ids"][0] if case["evidence_event_ids"] else None,
                    outcome="created",
                )

