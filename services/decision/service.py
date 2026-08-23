from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.rca.cqrs import RankRootCausesQuery, TraceAffectedLotsQuery


def _impact_payload(case: dict[str, Any], affected_lots: list[str]) -> dict[str, Any]:
    mean_yield = case.get("mean_yield")
    yield_gap = None if mean_yield is None else round(max(0.0, 1.0 - float(mean_yield)) * 100.0, 2)
    equipment = list(case.get("affected_scope", {}).get("equipment", []))
    chambers = list(case.get("affected_scope", {}).get("chambers", []))
    return {
        "synthetic_yield_gap_percentage_points": yield_gap,
        "affected_equipment_count": len(equipment),
        "affected_chamber_count": len(chambers),
        "affected_lot_count": len(set(affected_lots or [case["lot_id"]])),
        "basis": "synthetic inspection yield and inferred affected scope; not a financial-loss estimate",
    }


def _decision_definition(classification: str) -> dict[str, Any]:
    if classification == "data_quality_incident":
        return {
            "priority_band": "VERIFY_DATA",
            "priority_rank": 1,
            "decision_question": "Should the team reconcile/replay delivery or verify the source data before any process conclusion?",
            "recommended_option_id": "reconcile_replay",
            "options": [
                {
                    "option_id": "reconcile_replay",
                    "label": "Reconcile and replay delivery",
                    "stance": "recommended",
                    "tradeoff": "Restores a trustworthy event sequence before diagnosis; may delay process triage.",
                    "requires_human_approval": False,
                },
                {
                    "option_id": "verify_source_data",
                    "label": "Verify source data path",
                    "stance": "alternative",
                    "tradeoff": "Checks upstream integrity when replay alone cannot explain the incident.",
                    "requires_human_approval": False,
                },
                {
                    "option_id": "no_equipment_action",
                    "label": "No equipment containment action",
                    "stance": "guardrail",
                    "tradeoff": "Avoids acting on untrusted evidence while data quality is unresolved.",
                    "requires_human_approval": False,
                },
            ],
        }
    if classification == "sensor_bias_suspected":
        return {
            "priority_band": "MEDIUM",
            "priority_rank": 2,
            "decision_question": "Should the team verify sensor calibration first or request independent metrology before containment review?",
            "recommended_option_id": "verify_calibration",
            "options": [
                {
                    "option_id": "verify_calibration",
                    "label": "Verify sensor calibration",
                    "stance": "recommended",
                    "tradeoff": "Tests the non-physical explanation quickly before widening the response.",
                    "requires_human_approval": False,
                },
                {
                    "option_id": "independent_metrology",
                    "label": "Request independent metrology",
                    "stance": "alternative",
                    "tradeoff": "Adds stronger confirming evidence but costs additional diagnostic time.",
                    "requires_human_approval": False,
                },
                {
                    "option_id": "containment_review",
                    "label": "Prepare containment review",
                    "stance": "conditional",
                    "tradeoff": "Escalate only if independent evidence supports a physical excursion.",
                    "requires_human_approval": True,
                },
            ],
        }
    return {
        "priority_band": "HIGH",
        "priority_rank": 3,
        "decision_question": "Should the team collect confirming evidence first or prepare a governed containment review for this excursion?",
        "recommended_option_id": "confirm_evidence",
        "options": [
            {
                "option_id": "confirm_evidence",
                "label": "Collect confirming metrology",
                "stance": "recommended",
                "tradeoff": "Reduces false containment risk while preserving the current RCA hypothesis.",
                "requires_human_approval": False,
            },
            {
                "option_id": "containment_review",
                "label": "Prepare containment review",
                "stance": "conditional",
                "tradeoff": "Moves faster when evidence is strong, but still requires a human decision and performs no equipment control.",
                "requires_human_approval": True,
            },
            {
                "option_id": "monitor_only",
                "label": "Monitor and defer",
                "stance": "alternative",
                "tradeoff": "Avoids unnecessary intervention but accepts additional excursion exposure while evidence accumulates.",
                "requires_human_approval": False,
            },
        ],
    }


@dataclass
class DecisionSupportService:
    runtime: Any

    def packet(self, case_id: str) -> dict[str, Any]:
        case = self.runtime.case_repository.get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        ranking = self.runtime.queries.execute(RankRootCausesQuery(case_id))
        trace = self.runtime.queries.execute(TraceAffectedLotsQuery(case_id))
        advisory = self.runtime.advisory.advise(case_id)
        top = ranking.get("candidates", [None])[0]
        definition = _decision_definition(str(case["classification"]))
        support = list((top or {}).get("supporting_evidence", []))
        contradiction = list((top or {}).get("contradicting_evidence", []))
        uncertainties: list[str] = []
        if not contradiction:
            uncertainties.append("No explicit contradicting evidence is recorded for the top RCA candidate.")
        if case.get("mean_yield") is None:
            uncertainties.append("No synthetic inspection yield is available for this case.")
        if case.get("data_quality_incidents"):
            uncertainties.append("Data-quality incidents must be resolved before process attribution is treated as actionable.")

        refs = [f"case.evidence_event_ids[{index}]" for index, _ in enumerate(case.get("evidence_event_ids", []))]
        if top:
            refs.extend(["rca.top_candidate", "rca.supporting_evidence", "rca.contradicting_evidence"])
        packet = {
            "schema_version": "decision-packet-v1",
            "case_id": case_id,
            "lot_id": case["lot_id"],
            "classification": case["classification"],
            "state": case["state"],
            "decision_question": definition["decision_question"],
            "priority_band": definition["priority_band"],
            "priority_rank": definition["priority_rank"],
            "recommended_option_id": definition["recommended_option_id"],
            "options": definition["options"],
            "impact": _impact_payload(case, list(trace.get("affected_lots", []))),
            "evidence": {
                "anomaly_score": case["anomaly_score"],
                "mean_yield": case.get("mean_yield"),
                "affected_scope": case.get("affected_scope", {}),
                "top_candidate": None
                if top is None
                else {
                    "candidate_id": top["candidate_id"],
                    "candidate_type": top["candidate_type"],
                    "score": top["score"],
                    "supporting_evidence": support,
                    "contradicting_evidence": contradiction,
                },
                "advisory_status": advisory.get("status"),
                "advisory_next_step": advisory.get("recommended_next_step"),
                "data_quality_incidents": list(case.get("data_quality_incidents", [])),
            },
            "uncertainties": uncertainties,
            "evidence_refs": sorted(set(refs)),
            "provenance": {
                "input": "synthetic",
                "decision_packet": "inferred-deterministic",
                "equipment_control": False,
                "financial_impact_claimed": False,
            },
        }
        return packet

    def cockpit(self) -> dict[str, Any]:
        packets = [self.packet(case["case_id"]) for case in self.runtime.case_repository.list_cases()]
        queue = sorted(
            packets,
            key=lambda packet: (
                -int(packet["priority_rank"]),
                -(float(packet["evidence"]["anomaly_score"])),
                str(packet["case_id"]),
            ),
        )
        counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "VERIFY_DATA": 0}
        for packet in queue:
            counts[packet["priority_band"]] = counts.get(packet["priority_band"], 0) + 1
        return {
            "schema_version": "decision-cockpit-v1",
            "source": "synthetic-events-and-inferred-cases",
            "summary": {
                "decision_count": len(queue),
                "high_priority": counts.get("HIGH", 0),
                "medium_priority": counts.get("MEDIUM", 0),
                "data_verification": counts.get("VERIFY_DATA", 0),
            },
            "queue": queue,
        }
