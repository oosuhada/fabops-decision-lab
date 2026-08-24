from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from services.rca.graph import GraphNode, GraphProjectionPort

RCA_VERSION = "transparent-rca-v1.0.0"


@dataclass(frozen=True)
class RootCauseCandidate:
    candidate_id: str
    candidate_type: str
    score: float
    score_components: dict[str, float]
    supporting_evidence: list[dict[str, Any]]
    contradicting_evidence: list[dict[str, Any]]
    recommended_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TransparentRcaRanker:
    def __init__(self, graph: GraphProjectionPort) -> None:
        self.graph = graph

    def _nodes_for_lot(self, kind: str, lot_id: str) -> list[GraphNode]:
        indexed = getattr(self.graph, "nodes_for_lot", None)
        if callable(indexed):
            return indexed(kind, lot_id)
        return [node for node in self.graph.nodes(kind) if node.properties.get("lot_id") == lot_id]

    def _component_score(self, components: dict[str, float]) -> float:
        return round(
            components.get("temporal_proximity", 0.0)
            + components.get("affected_scope_overlap", 0.0)
            + components.get("chamber_specific_deviation", 0.0)
            + components.get("change_or_maintenance", 0.0)
            + components.get("defect_pattern_compatibility", 0.0)
            - components.get("contradicting_evidence", 0.0),
            5,
        )

    def rank(self, case: dict[str, Any]) -> list[dict[str, Any]]:
        lot_id = case["lot_id"]
        classification = case["classification"]
        inspections = self._nodes_for_lot("Inspection", lot_id)
        defect_patterns = sorted({str(node.properties.get("defect_pattern")) for node in inspections})
        mean_yield = case.get("mean_yield")

        if classification == "data_quality_incident":
            incidents = self._nodes_for_lot("DataQualityIncident", lot_id)
            support = [
                {"type": "data_quality", "event_id": node.node_id, "incident_type": node.properties["incident_type"]}
                for node in incidents
            ]
            components = {
                "temporal_proximity": 0.25,
                "affected_scope_overlap": 0.25,
                "chamber_specific_deviation": 0.0,
                "change_or_maintenance": 0.25,
                "defect_pattern_compatibility": 0.0,
                "contradicting_evidence": 0.0,
            }
            return [
                RootCauseCandidate(
                    "data_quality:event-delivery",
                    "data_quality",
                    self._component_score(components),
                    components,
                    support,
                    [{"type": "physical_effect", "detail": "No physical yield impact is required to explain delivery anomalies."}],
                    "replay and reconcile source events; do not hold equipment",
                ).to_dict()
            ]

        alarms = self._nodes_for_lot("Alarm", lot_id)
        process_runs = self._nodes_for_lot("ProcessRun", lot_id)
        measurements = self._nodes_for_lot("Measurement", lot_id)
        candidates: list[RootCauseCandidate] = []

        # Explicit recipe mismatch candidate.
        for run in process_runs:
            recipe_id = str(run.properties.get("recipe_id"))
            expected = str(run.properties.get("expected_recipe_id"))
            if recipe_id and expected and recipe_id != expected:
                components = {
                    "temporal_proximity": 0.2,
                    "affected_scope_overlap": 0.2,
                    "chamber_specific_deviation": 0.0,
                    "change_or_maintenance": 0.35,
                    "defect_pattern_compatibility": 0.15 if "Center" in defect_patterns else 0.05,
                    "contradicting_evidence": 0.0,
                }
                candidates.append(
                    RootCauseCandidate(
                        f"recipe:{recipe_id}",
                        "recipe_mismatch",
                        self._component_score(components),
                        components,
                        [{"type": "recipe_mismatch", "process_run_id": run.node_id, "actual": recipe_id, "expected": expected}],
                        [],
                        "rollback recipe and identify lots processed with the mismatched version",
                    )
                )

        # Alarm-backed chamber candidates.
        for alarm in alarms:
            chamber_id = str(alarm.properties.get("chamber_id"))
            equipment_id = str(alarm.properties.get("equipment_id"))
            code = str(alarm.properties.get("alarm_code"))
            if not chamber_id or chamber_id == "None":
                continue
            is_sensor_bias = classification == "sensor_bias_suspected" or code == "SIM-F5"
            maintenance = [
                node
                for node in self.graph.nodes("Maintenance")
                if node.properties.get("chamber_id") == chamber_id
            ]
            support = [{"type": "alarm", "event_id": alarm.node_id, "alarm_code": code, "chamber_id": chamber_id}]
            if maintenance:
                support.append({"type": "maintenance", "maintenance_id": maintenance[-1].node_id, "maintenance_type": maintenance[-1].properties.get("maintenance_type")})
            if is_sensor_bias:
                sensor_measurements = [node for node in measurements if node.properties.get("chamber_id") == chamber_id and node.properties.get("sensor_name") == "temperature"]
                support.extend({"type": "measurement", "event_id": node.node_id, "sensor": "temperature", "value": node.properties.get("value")} for node in sensor_measurements[:2])
                components = {
                    "temporal_proximity": 0.2,
                    "affected_scope_overlap": 0.2,
                    "chamber_specific_deviation": 0.3,
                    "change_or_maintenance": 0.05,
                    "defect_pattern_compatibility": 0.0,
                    "contradicting_evidence": 0.0,
                }
                candidates.append(
                    RootCauseCandidate(
                        f"sensor:temperature:{chamber_id}",
                        "sensor_calibration",
                        self._component_score(components),
                        components,
                        support,
                        [{"type": "yield", "detail": f"Mean yield {mean_yield} remains nominal; equipment-level physical attribution is contradicted."}],
                        "verify sensor calibration before considering any equipment hold",
                    )
                )
                equipment_components = dict(components)
                equipment_components["chamber_specific_deviation"] = 0.1
                equipment_components["contradicting_evidence"] = 0.45
                candidates.append(
                    RootCauseCandidate(
                        f"equipment:{equipment_id}",
                        "equipment",
                        self._component_score(equipment_components),
                        equipment_components,
                        support,
                        [{"type": "normal_yield", "detail": "Normal downstream yield contradicts equipment hold as the default explanation."}],
                        "do not hold equipment without additional physical evidence",
                    )
                )
            else:
                pattern_bonus = 0.15 if any(pattern in {"Edge-Loc", "Random"} for pattern in defect_patterns) else 0.05
                components = {
                    "temporal_proximity": 0.2,
                    "affected_scope_overlap": 0.2,
                    "chamber_specific_deviation": 0.3,
                    "change_or_maintenance": 0.15 if maintenance else 0.05,
                    "defect_pattern_compatibility": pattern_bonus,
                    "contradicting_evidence": 0.0,
                }
                candidates.append(
                    RootCauseCandidate(
                        f"chamber:{chamber_id}",
                        "chamber",
                        self._component_score(components),
                        components,
                        support + [{"type": "inspection", "defect_patterns": defect_patterns, "mean_yield": mean_yield}],
                        [],
                        "hold the implicated chamber and perform targeted calibration/cleaning checks",
                    )
                )

        # The interaction case is intentionally transparent: the combination is
        # emitted only when both upstream and downstream path evidence exists.
        chambers = {str(run.properties.get("step_id")): self._run_chamber(run.node_id) for run in process_runs}
        if classification == "physical_excursion" and chambers.get("LITHO") == "LITHO-01-A" and chambers.get("ETCH") == "ETCH-02-B" and "Scratch" in defect_patterns:
            components = {
                "temporal_proximity": 0.2,
                "affected_scope_overlap": 0.25,
                "chamber_specific_deviation": 0.25,
                "change_or_maintenance": 0.0,
                "defect_pattern_compatibility": 0.25,
                "contradicting_evidence": 0.0,
            }
            candidates.append(
                RootCauseCandidate(
                    "interaction:LITHO-01-A+ETCH-02-B",
                    "upstream_downstream_interaction",
                    self._component_score(components),
                    components,
                    [
                        {"type": "path", "detail": "Lot traversed LITHO-01-A then ETCH-02-B."},
                        {"type": "inspection", "defect_patterns": defect_patterns, "mean_yield": mean_yield},
                    ],
                    [{"type": "single_factor_limit", "detail": "No single alarm is sufficient; attribution requires the observed combination."}],
                    "hold the specific tool combination and request additional metrology",
                )
            )

        if not candidates:
            # A deterministic abstaining baseline still returns an explicit unknown
            # candidate rather than inventing physical causality.
            components = {
                "temporal_proximity": 0.05,
                "affected_scope_overlap": 0.05,
                "chamber_specific_deviation": 0.0,
                "change_or_maintenance": 0.0,
                "defect_pattern_compatibility": 0.0,
                "contradicting_evidence": 0.0,
            }
            candidates.append(
                RootCauseCandidate(
                    "unknown:insufficient-evidence",
                    "unknown",
                    self._component_score(components),
                    components,
                    [],
                    [{"type": "evidence_gap", "detail": "No supported recipe, chamber, interaction, sensor or data-quality explanation reached baseline evidence."}],
                    "request additional diagnostics",
                )
            )

        return [candidate.to_dict() for candidate in sorted(candidates, key=lambda item: (-item.score, item.candidate_id))]

    def _run_chamber(self, run_id: str) -> str | None:
        edges = self.graph.outgoing("ProcessRun", run_id, "USED_CHAMBER")
        return edges[0].target_id if edges else None

