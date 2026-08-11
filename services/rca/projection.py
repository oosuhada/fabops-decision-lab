from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.ingestion.ports import EventRepositoryPort, StoredEvent
from services.observability.telemetry import TelemetryRecorder
from services.rca.graph import GraphProjectionPort

PROJECTION_VERSION = "rca-graph-v1.0.0"


@dataclass(frozen=True)
class ProjectionStatus:
    projection_version: str
    source_checkpoint: int
    projection_checkpoint: int
    lag_events: int
    stale: bool


class RcaProjectionWorker:
    def __init__(
        self,
        event_repository: EventRepositoryPort,
        graph: GraphProjectionPort,
        telemetry: TelemetryRecorder | None = None,
    ) -> None:
        self.events = event_repository
        self.graph = graph
        self.telemetry = telemetry
        self.projection_checkpoint = 0

    def rebuild(self) -> ProjectionStatus:
        if self.telemetry is not None:
            with self.telemetry.operation("projection.rebuild", projection_version=PROJECTION_VERSION):
                return self._rebuild()
        return self._rebuild()

    def _rebuild(self) -> ProjectionStatus:
        self.graph.clear()
        self.projection_checkpoint = 0
        for stored in self.events.all_events():
            self.project_stored(stored)
        return self.status()

    def catch_up(self) -> ProjectionStatus:
        for stored in self.events.all_events():
            if stored.sequence > self.projection_checkpoint:
                self.project_stored(stored)
        return self.status()

    def status(self) -> ProjectionStatus:
        source_checkpoint = len(self.events.all_events())
        lag = max(0, source_checkpoint - self.projection_checkpoint)
        return ProjectionStatus(PROJECTION_VERSION, source_checkpoint, self.projection_checkpoint, lag, lag > 0)

    def project_stored(self, stored: StoredEvent) -> None:
        if self.telemetry is None:
            self._project_event(stored.event)
            self.projection_checkpoint = max(self.projection_checkpoint, stored.sequence)
            return
        causal_trace_id = str(stored.event.get("trace_id") or stored.event["event_id"])
        with self.telemetry.bind_causal_trace(causal_trace_id, causal_trace_id):
            with self.telemetry.operation(
                "projection.project_event",
                event_id=stored.event.get("event_id"),
                projection_version=PROJECTION_VERSION,
                source_sequence=stored.sequence,
            ):
                self._project_event(stored.event)
                self.projection_checkpoint = max(self.projection_checkpoint, stored.sequence)

    def _project_event(self, event: dict[str, Any]) -> None:
        event_type = event["event_type"]
        payload = event["payload"]
        lot_id = event.get("lot_id")
        wafer_id = event.get("wafer_id")
        equipment_id = event.get("equipment_id")
        chamber_id = event.get("chamber_id")

        if lot_id:
            self.graph.upsert_node("Lot", lot_id, {"lot_id": lot_id, "trace_id": event.get("trace_id")})
        if equipment_id:
            self.graph.upsert_node("Equipment", equipment_id, {"equipment_id": equipment_id})
        if chamber_id:
            self.graph.upsert_node("Chamber", chamber_id, {"chamber_id": chamber_id, "equipment_id": equipment_id})
            if equipment_id:
                self.graph.upsert_edge("Equipment", equipment_id, "HAS_CHAMBER", "Chamber", chamber_id)

        if event_type == "lot.released.v1":
            product = str(payload["product_family"])
            self.graph.upsert_node("Product", product, {"product_family": product, "provenance": payload.get("provenance")})
            self.graph.upsert_edge("Lot", lot_id, "OF_PRODUCT", "Product", product)
            for released_wafer in payload["wafer_ids"]:
                self.graph.upsert_node("Wafer", released_wafer, {"wafer_id": released_wafer, "lot_id": lot_id})
                self.graph.upsert_edge("Lot", lot_id, "CONTAINS", "Wafer", released_wafer)
            return

        if event_type == "process.started.v1":
            run_id = str(payload["process_run_id"])
            step_id = str(payload["step_id"])
            recipe_id = str(payload["recipe_id"])
            self.graph.upsert_node(
                "ProcessRun",
                run_id,
                {
                    "process_run_id": run_id,
                    "lot_id": lot_id,
                    "step_id": step_id,
                    "recipe_id": recipe_id,
                    "expected_recipe_id": payload.get("expected_recipe_id"),
                    "event_time": event["event_time"],
                },
            )
            self.graph.upsert_node("ProcessStep", step_id, {"step_id": step_id})
            self.graph.upsert_node("Recipe", recipe_id, {"recipe_id": recipe_id})
            self.graph.upsert_edge("Lot", lot_id, "EXECUTED", "ProcessRun", run_id)
            self.graph.upsert_edge("ProcessRun", run_id, "AT_STEP", "ProcessStep", step_id)
            self.graph.upsert_edge("ProcessRun", run_id, "USED", "Equipment", equipment_id)
            self.graph.upsert_edge("ProcessRun", run_id, "USED_CHAMBER", "Chamber", chamber_id)
            self.graph.upsert_edge("ProcessRun", run_id, "USED_RECIPE", "Recipe", recipe_id)
            return

        if event_type == "process.measurement.recorded.v1":
            measurement_id = event["event_id"]
            run_id = str(payload["process_run_id"])
            self.graph.upsert_node(
                "Measurement",
                measurement_id,
                {
                    "event_id": measurement_id,
                    "lot_id": lot_id,
                    "process_run_id": run_id,
                    "step_id": payload["step_id"],
                    "sensor_name": payload["sensor_name"],
                    "value": payload["value"],
                    "unit": payload["unit"],
                    "equipment_id": equipment_id,
                    "chamber_id": chamber_id,
                    "event_time": event["event_time"],
                },
            )
            self.graph.upsert_edge("ProcessRun", run_id, "PRODUCED", "Measurement", measurement_id)
            return

        if event_type == "equipment.alarm.raised.v1":
            alarm_id = event["event_id"]
            self.graph.upsert_node(
                "Alarm",
                alarm_id,
                {
                    "event_id": alarm_id,
                    "lot_id": lot_id,
                    "alarm_code": payload["alarm_code"],
                    "severity": payload["severity"],
                    "equipment_id": equipment_id,
                    "chamber_id": chamber_id,
                    "event_time": event["event_time"],
                },
            )
            self.graph.upsert_edge("Equipment", equipment_id, "EMITTED", "Alarm", alarm_id)
            return

        if event_type == "maintenance.completed.v1":
            maintenance_id = str(payload["maintenance_id"])
            self.graph.upsert_node(
                "Maintenance",
                maintenance_id,
                {
                    "maintenance_id": maintenance_id,
                    "maintenance_type": payload["maintenance_type"],
                    "result": payload["result"],
                    "equipment_id": equipment_id,
                    "chamber_id": chamber_id,
                    "event_time": event["event_time"],
                },
            )
            self.graph.upsert_edge("Equipment", equipment_id, "HAS_MAINTENANCE", "Maintenance", maintenance_id)
            return

        if event_type == "inspection.completed.v1":
            inspection_id = str(payload["inspection_id"])
            self.graph.upsert_node(
                "Inspection",
                inspection_id,
                {
                    "inspection_id": inspection_id,
                    "lot_id": lot_id,
                    "wafer_id": wafer_id,
                    "yield": payload["yield"],
                    "failed_die_ratio": payload["failed_die_ratio"],
                    "defect_pattern": payload["defect_pattern"],
                    "pattern_provenance": payload["pattern_provenance"],
                    "event_time": event["event_time"],
                },
            )
            self.graph.upsert_edge("Wafer", wafer_id, "HAS_INSPECTION", "Inspection", inspection_id)
            return

        if event_type == "data.quality.incident.v1":
            quality_id = event["event_id"]
            self.graph.upsert_node(
                "DataQualityIncident",
                quality_id,
                {
                    "event_id": quality_id,
                    "lot_id": lot_id,
                    "incident_type": payload["incident_type"],
                    "recommended_action": payload["recommended_action"],
                    "event_time": event["event_time"],
                },
            )

