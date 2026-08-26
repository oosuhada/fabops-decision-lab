from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    lag_seconds: float | None = None
    last_successful_projection: str | None = None
    slo_state: str = "UNKNOWN"


class RcaProjectionWorker:
    def __init__(
        self,
        event_repository: EventRepositoryPort,
        graph: GraphProjectionPort,
        telemetry: TelemetryRecorder | None = None,
        window_lots: int | None = None,
    ) -> None:
        self.events = event_repository
        self.graph = graph
        self.telemetry = telemetry
        persisted_checkpoint = getattr(graph, "projection_checkpoint", None)
        self.projection_checkpoint = int(persisted_checkpoint()) if callable(persisted_checkpoint) else 0
        self.window_lots = window_lots

    @property
    def projection_version(self) -> str:
        return str(getattr(self.graph, "projection_version", PROJECTION_VERSION))

    def _persist_checkpoint(self) -> None:
        writer = getattr(self.graph, "set_projection_checkpoint", None)
        if callable(writer):
            writer(self.projection_checkpoint)

    def _refresh_checkpoint(self) -> None:
        reader = getattr(self.graph, "projection_checkpoint", None)
        if callable(reader):
            self.projection_checkpoint = int(reader())

    def rebuild(self) -> ProjectionStatus:
        if self.telemetry is not None:
            with self.telemetry.operation("projection.rebuild", projection_version=self.projection_version):
                return self._rebuild()
        return self._rebuild()

    def _rebuild(self) -> ProjectionStatus:
        self.graph.clear()
        self.projection_checkpoint = 0
        for stored in self.events.all_events():
            self.project_stored(stored)
        self._persist_checkpoint()
        return self.status()

    def rebuild_recent(self) -> ProjectionStatus:
        recent_reader = getattr(self.events, "recent_lot_ids", None)
        lot_event_reader = getattr(self.events, "events_for_lots", None)
        latest_reader = getattr(self.events, "latest_event", None)
        if not self.window_lots or not callable(recent_reader) or not callable(lot_event_reader):
            return self.rebuild()
        self.graph.clear()
        recent_lots = recent_reader(self.window_lots)
        for stored in lot_event_reader(recent_lots):
            self.project_stored(stored)
        latest = latest_reader() if callable(latest_reader) else None
        if latest is not None:
            self.projection_checkpoint = max(self.projection_checkpoint, latest.sequence)
        self._persist_checkpoint()
        return self.status()

    def _prune_window(self) -> None:
        if not self.window_lots:
            return
        recent_reader = getattr(self.events, "recent_lot_ids", None)
        prune = getattr(self.graph, "prune_to_lots", None)
        if callable(recent_reader) and callable(prune):
            prune(set(recent_reader(self.window_lots)))

    def catch_up(self) -> ProjectionStatus:
        incremental = getattr(self.events, "events_after", None)
        projected_any = False
        if callable(incremental):
            while True:
                batch = incremental(self.projection_checkpoint, 2000)
                if not batch:
                    break
                for stored in batch:
                    self.project_stored(stored)
                    projected_any = True
                self._persist_checkpoint()
                if len(batch) < 2000:
                    break
        else:
            for stored in self.events.all_events():
                if stored.sequence > self.projection_checkpoint:
                    self.project_stored(stored)
                    projected_any = True
            self._persist_checkpoint()
        if projected_any:
            self._prune_window()
        return self.status()

    def ensure_lot(self, lot_id: str) -> None:
        nodes_for_lot = getattr(self.graph, "nodes_for_lot", None)
        if callable(nodes_for_lot) and nodes_for_lot("Lot", lot_id):
            return
        if getattr(self.graph, "writable", True) is False:
            return
        lot_event_reader = getattr(self.events, "events_for_lots", None)
        if not callable(lot_event_reader):
            return
        for stored in lot_event_reader([lot_id]):
            # Ad-hoc historical hydration must not move the live source
            # checkpoint backwards or forwards; it only materializes this lot.
            previous_checkpoint = self.projection_checkpoint
            self.project_stored(stored)
            self.projection_checkpoint = previous_checkpoint

    def status(self) -> ProjectionStatus:
        self._refresh_checkpoint()
        counter = getattr(self.events, "event_count", None)
        source_checkpoint = int(counter()) if callable(counter) else len(self.events.all_events())
        lag = max(0, source_checkpoint - self.projection_checkpoint)
        updated_reader = getattr(self.graph, "projection_updated_at", None)
        updated_at = updated_reader() if callable(updated_reader) else None
        lag_seconds: float | None = None
        last_successful_projection: str | None = None
        if updated_at is not None:
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            lag_seconds = max(0.0, (datetime.now(timezone.utc) - updated_at).total_seconds())
            last_successful_projection = updated_at.isoformat()
        max_lag_events = 25
        max_lag_seconds = 30.0
        slo_state = "MET" if lag <= max_lag_events and (lag_seconds is None or lag_seconds <= max_lag_seconds or lag == 0) else "BREACHED"
        return ProjectionStatus(
            self.projection_version,
            source_checkpoint,
            self.projection_checkpoint,
            lag,
            lag > 0,
            round(lag_seconds, 3) if lag_seconds is not None else None,
            last_successful_projection,
            slo_state,
        )

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
                projection_version=self.projection_version,
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
                    "lot_id": lot_id,
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

