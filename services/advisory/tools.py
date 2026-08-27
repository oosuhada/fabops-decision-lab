from __future__ import annotations

from statistics import mean
from typing import Any, Callable

from services.ingestion.ports import CaseRepositoryPort
from services.observability.telemetry import TelemetryRecorder
from services.rca.cqrs import RankRootCausesQuery, RcaQueryService, TraceAffectedLotsQuery
from services.rca.graph import GraphProjectionPort

Tool = Callable[[str], dict[str, Any]]


class ToolRegistry:
    def __init__(
        self,
        cases: CaseRepositoryPort,
        graph: GraphProjectionPort,
        queries: RcaQueryService,
        telemetry: TelemetryRecorder | None = None,
    ) -> None:
        self.cases = cases
        self.graph = graph
        self.queries = queries
        self.telemetry = telemetry
        self._tools: dict[str, Tool] = {
            "get_excursion_summary": self.get_excursion_summary,
            "compare_chamber_baselines": self.compare_chamber_baselines,
            "trace_affected_lots": self.trace_affected_lots,
            "find_related_alarms_and_changes": self.find_related_alarms_and_changes,
            "retrieve_sop_and_past_cases": self.retrieve_sop_and_past_cases,
        }
        if len(self._tools) > 5:
            raise ValueError("advisory tool registry is intentionally capped at five tools")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def call(self, name: str, case_id: str) -> dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"unsupported advisory tool: {name}")
        if self.telemetry is not None:
            with self.telemetry.operation("advisory.tool_call", case_id=case_id, tool=name):
                return self._tools[name](case_id)
        return self._tools[name](case_id)

    def _case(self, case_id: str) -> dict[str, Any]:
        case = self.cases.get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        return case

    def get_excursion_summary(self, case_id: str) -> dict[str, Any]:
        case = self._case(case_id)
        ranking = self.queries.execute(RankRootCausesQuery(case_id))
        return {
            "tool": "get_excursion_summary",
            "case_id": case_id,
            "classification": case["classification"],
            "anomaly_score": case["anomaly_score"],
            "mean_yield": case.get("mean_yield"),
            "top_candidate": ranking["candidates"][0] if ranking["candidates"] else None,
            "projection": ranking["projection"],
        }

    def compare_chamber_baselines(self, case_id: str) -> dict[str, Any]:
        case = self._case(case_id)
        lot_id = case["lot_id"]
        indexed = getattr(self.graph, "nodes_for_lot", None)
        target_measurements = indexed("Measurement", lot_id) if callable(indexed) else [
            node for node in self.graph.nodes("Measurement") if node.properties.get("lot_id") == lot_id
        ]
        all_measurements = self.graph.nodes("Measurement")
        by_sensor: dict[str, dict[str, Any]] = {}
        for sensor in sorted({str(node.properties["sensor_name"]) for node in target_measurements}):
            target_values = [float(node.properties["value"]) for node in target_measurements if node.properties["sensor_name"] == sensor]
            baseline_values = [
                float(node.properties["value"])
                for node in all_measurements
                if node.properties["sensor_name"] == sensor and node.properties.get("lot_id") != lot_id
            ]
            by_sensor[sensor] = {
                "target_mean": round(mean(target_values), 5) if target_values else None,
                "reference_mean": round(mean(baseline_values), 5) if baseline_values else None,
                "target_count": len(target_values),
                "reference_count": len(baseline_values),
            }
        return {"tool": "compare_chamber_baselines", "case_id": case_id, "sensors": by_sensor}

    def trace_affected_lots(self, case_id: str) -> dict[str, Any]:
        return {"tool": "trace_affected_lots", **self.queries.execute(TraceAffectedLotsQuery(case_id))}

    def find_related_alarms_and_changes(self, case_id: str) -> dict[str, Any]:
        case = self._case(case_id)
        lot_id = case["lot_id"]
        indexed = getattr(self.graph, "nodes_for_lot", None)
        alarm_nodes = indexed("Alarm", lot_id) if callable(indexed) else [
            node for node in self.graph.nodes("Alarm") if node.properties.get("lot_id") == lot_id
        ]
        run_nodes = indexed("ProcessRun", lot_id) if callable(indexed) else [
            node for node in self.graph.nodes("ProcessRun") if node.properties.get("lot_id") == lot_id
        ]
        alarms = [node.properties for node in alarm_nodes]
        runs = [node.properties for node in run_nodes]
        mismatches = [
            {"process_run_id": run["process_run_id"], "actual": run["recipe_id"], "expected": run["expected_recipe_id"]}
            for run in runs
            if run.get("recipe_id") != run.get("expected_recipe_id")
        ]
        chambers = {run.get("step_id"): run.get("process_run_id") for run in runs}
        return {
            "tool": "find_related_alarms_and_changes",
            "case_id": case_id,
            "alarms": alarms,
            "recipe_mismatches": mismatches,
            "process_runs_by_step": chambers,
        }

    def retrieve_sop_and_past_cases(self, case_id: str) -> dict[str, Any]:
        case = self._case(case_id)
        classification = case["classification"]
        sop = {
            "physical_excursion": "SOP-SYN-EXCURSION-01: contain scope, verify metrology, require human approval before any hold proposal.",
            "sensor_bias_suspected": "SOP-SYN-SENSOR-02: verify calibration against independent measurement before equipment attribution.",
            "data_quality_incident": "SOP-SYN-DQ-03: reconcile/replay event stream; do not initiate physical containment from data-quality evidence alone.",
        }.get(classification, "SOP-SYN-GENERAL-00: request additional evidence.")
        related_reader = getattr(self.cases, "related_cases", None)
        related_cases = related_reader(classification, case_id, 3) if callable(related_reader) else [
            item
            for item in self.cases.list_cases()
            if item["case_id"] != case_id and item["classification"] == classification
        ][:3]
        related = [
            {"case_id": item["case_id"], "lot_id": item["lot_id"], "classification": item["classification"], "state": item["state"]}
            for item in related_cases
        ]
        return {
            "tool": "retrieve_sop_and_past_cases",
            "case_id": case_id,
            "sop": sop,
            "sop_provenance": "synthetic-local-fixture",
            "past_cases": related,
        }

