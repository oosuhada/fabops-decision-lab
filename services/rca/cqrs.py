from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from services.ingestion.ports import CaseRepositoryPort
from services.observability.telemetry import TelemetryRecorder
from services.rca.graph import GraphProjectionPort
from services.rca.projection import RcaProjectionWorker
from services.rca.ranking import TransparentRcaRanker


@dataclass(frozen=True)
class RebuildProjectionCommand:
    requested_by: str


@dataclass(frozen=True)
class TraceAffectedLotsQuery:
    case_id: str


@dataclass(frozen=True)
class RankRootCausesQuery:
    case_id: str


@dataclass(frozen=True)
class ProjectionStatusQuery:
    pass


class RcaCommandHandler:
    def __init__(self, worker: RcaProjectionWorker) -> None:
        self.worker = worker

    def handle(self, command: RebuildProjectionCommand) -> dict[str, Any]:
        status = self.worker.rebuild()
        return {"command": "rebuild_projection", "requested_by": command.requested_by, "status": asdict(status)}


class RcaQueryService:
    def __init__(
        self,
        graph: GraphProjectionPort,
        cases: CaseRepositoryPort,
        worker: RcaProjectionWorker,
        telemetry: TelemetryRecorder | None = None,
    ) -> None:
        self.graph = graph
        self.cases = cases
        self.worker = worker
        self.ranker = TransparentRcaRanker(graph)
        self.telemetry = telemetry

    def execute(self, query: TraceAffectedLotsQuery | RankRootCausesQuery | ProjectionStatusQuery) -> dict[str, Any]:
        if self.telemetry is not None:
            case_id = getattr(query, "case_id", None)
            with self.telemetry.operation("rca.query", case_id=case_id, query_type=type(query).__name__, projection_version=self.worker.status().projection_version):
                return self._execute(query)
        return self._execute(query)

    def _execute(self, query: TraceAffectedLotsQuery | RankRootCausesQuery | ProjectionStatusQuery) -> dict[str, Any]:
        status = asdict(self.worker.status())
        if isinstance(query, ProjectionStatusQuery):
            return {"projection": status}
        case = self.cases.get_case(query.case_id)
        if case is None:
            raise KeyError(query.case_id)
        ensure_lot = getattr(self.worker, "ensure_lot", None)
        if callable(ensure_lot):
            ensure_lot(str(case["lot_id"]))
        if isinstance(query, RankRootCausesQuery):
            return {"case_id": query.case_id, "projection": status, "candidates": self.ranker.rank(case)}
        lot_id = case["lot_id"]
        indexed = getattr(self.graph, "nodes_for_lot", None)
        runs = indexed("ProcessRun", lot_id) if callable(indexed) else [node for node in self.graph.nodes("ProcessRun") if node.properties.get("lot_id") == lot_id]
        path = []
        for run in sorted(runs, key=lambda node: node.properties.get("event_time", "")):
            chamber_edges = self.graph.outgoing("ProcessRun", run.node_id, "USED_CHAMBER")
            equipment_edges = self.graph.outgoing("ProcessRun", run.node_id, "USED")
            path.append(
                {
                    "lot_id": lot_id,
                    "process_run_id": run.node_id,
                    "step_id": run.properties["step_id"],
                    "equipment_id": equipment_edges[0].target_id if equipment_edges else None,
                    "chamber_id": chamber_edges[0].target_id if chamber_edges else None,
                    "recipe_id": run.properties["recipe_id"],
                }
            )
        return {"case_id": query.case_id, "projection": status, "affected_lots": [lot_id], "process_path": path}

