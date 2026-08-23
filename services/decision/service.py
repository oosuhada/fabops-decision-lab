from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.rca.cqrs import RankRootCausesQuery, TraceAffectedLotsQuery


_RCA_COMPONENT_ORDER = (
    "temporal_proximity",
    "affected_scope_overlap",
    "chamber_specific_deviation",
    "change_or_maintenance",
    "defect_pattern_compatibility",
    "contradicting_evidence",
)


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


def _score_explanation(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    components = dict(candidate.get("score_components", {}))
    items: list[dict[str, Any]] = []
    reconstructed_score = 0.0
    for component_id in _RCA_COMPONENT_ORDER:
        raw_value = float(components.get(component_id, 0.0))
        signed_value = -raw_value if component_id == "contradicting_evidence" else raw_value
        reconstructed_score += signed_value
        items.append(
            {
                "component_id": component_id,
                "direction": "contradict" if component_id == "contradicting_evidence" else ("support" if raw_value > 0 else "neutral"),
                "raw_value": round(raw_value, 5),
                "signed_value": round(signed_value, 5),
            }
        )
    reconstructed_score = round(reconstructed_score, 5)
    reported_score = round(float(candidate.get("score", 0.0)), 5)
    return {
        "contract_version": "rca-score-explanation-v1",
        "formula": "temporal_proximity + affected_scope_overlap + chamber_specific_deviation + change_or_maintenance + defect_pattern_compatibility - contradicting_evidence",
        "components": items,
        "reconstructed_score": reconstructed_score,
        "reported_score": reported_score,
        "faithful": reconstructed_score == reported_score,
        "probability": False,
    }


def _decision_boundary(
    classification: str,
    case: dict[str, Any],
    candidate: dict[str, Any] | None,
    excursion_yield_threshold: float,
) -> dict[str, Any]:
    support = list((candidate or {}).get("supporting_evidence", []))
    contradiction = list((candidate or {}).get("contradicting_evidence", []))
    mean_yield = case.get("mean_yield")
    data_quality_incidents = list(case.get("data_quality_incidents", []))

    if classification == "physical_excursion":
        conditions = [
            {
                "condition_id": "physical_classification",
                "label": "Detector classifies the case as a physical excursion",
                "status": "met",
                "current_value": classification,
                "required": "physical_excursion",
                "evidence_refs": ["case.classification"],
            },
            {
                "condition_id": "yield_confirmation",
                "label": "Synthetic inspection yield remains below the detector excursion threshold",
                "status": "met" if mean_yield is not None and float(mean_yield) < excursion_yield_threshold else "unmet",
                "current_value": mean_yield,
                "required": f"< {excursion_yield_threshold}",
                "evidence_refs": ["case.mean_yield", "detector.excursion_yield_threshold"],
            },
            {
                "condition_id": "support_breadth",
                "label": "Top RCA candidate has at least three explicit supporting records",
                "status": "met" if len(support) >= 3 else "unmet",
                "current_value": len(support),
                "required": ">= 3",
                "evidence_refs": ["rca.supporting_evidence"],
            },
            {
                "condition_id": "no_explicit_contradiction",
                "label": "No explicit contradicting record is attached to the top RCA candidate",
                "status": "met" if not contradiction else "unmet",
                "current_value": len(contradiction),
                "required": "0",
                "evidence_refs": ["rca.contradicting_evidence"],
            },
            {
                "condition_id": "data_quality_clear",
                "label": "No unresolved data-quality incident contaminates the decision packet",
                "status": "met" if not data_quality_incidents else "unmet",
                "current_value": len(data_quality_incidents),
                "required": "0",
                "evidence_refs": ["case.data_quality_incidents"],
            },
        ]
        target_option_id = "containment_review"
        policy_statement = "A bounded containment review becomes the deterministic recommendation only when all listed evidence conditions are met; equipment action still requires a human decision and is never executed by FabOps."
    elif classification == "sensor_bias_suspected":
        conditions = [
            {
                "condition_id": "physical_confirmation",
                "label": "Independent physical evidence would need to contradict the current sensor-bias interpretation",
                "status": "met" if mean_yield is not None and float(mean_yield) < excursion_yield_threshold else "unmet",
                "current_value": mean_yield,
                "required": f"< {excursion_yield_threshold}",
                "evidence_refs": ["case.mean_yield", "detector.excursion_yield_threshold"],
            },
            {
                "condition_id": "sensor_hypothesis_weakened",
                "label": "The top sensor hypothesis would need to lose its explicit supporting evidence",
                "status": "met" if not support else "unmet",
                "current_value": len(support),
                "required": "0 supporting records",
                "evidence_refs": ["rca.supporting_evidence"],
            },
            {
                "condition_id": "data_quality_clear",
                "label": "No unresolved data-quality incident contaminates the comparison",
                "status": "met" if not data_quality_incidents else "unmet",
                "current_value": len(data_quality_incidents),
                "required": "0",
                "evidence_refs": ["case.data_quality_incidents"],
            },
        ]
        target_option_id = "independent_metrology"
        policy_statement = "The policy stays with calibration verification until the current sensor explanation is weakened by source-linked physical evidence."
    else:
        conditions = [
            {
                "condition_id": "replay_outcome_required",
                "label": "A completed reconcile/replay outcome is required before the policy can prefer source-path verification",
                "status": "unknown",
                "current_value": None,
                "required": "post-replay result",
                "evidence_refs": ["case.data_quality_incidents"],
            }
        ]
        target_option_id = "verify_source_data"
        policy_statement = "Data-quality cases do not escalate from missing replay evidence. The boundary remains explicitly unknown until replay evidence exists."

    all_met = bool(conditions) and all(item["status"] == "met" for item in conditions)
    return {
        "contract_version": "decision-boundary-v1",
        "confidence_semantics": "evidence conditions, not probability",
        "target_option_id": target_option_id,
        "all_conditions_met": all_met,
        "conditions": conditions,
        "policy_statement": policy_statement,
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
        decision_boundary = _decision_boundary(
            str(case["classification"]),
            case,
            top,
            float(self.runtime.detector.config.excursion_yield_threshold),
        )
        recommended_option_id = (
            decision_boundary["target_option_id"]
            if decision_boundary["all_conditions_met"]
            and decision_boundary["target_option_id"] in {option["option_id"] for option in definition["options"]}
            else definition["recommended_option_id"]
        )
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
            "recommended_option_id": recommended_option_id,
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
                    "score_components": dict(top.get("score_components", {})),
                    "score_explanation": _score_explanation(top),
                    "supporting_evidence": support,
                    "contradicting_evidence": contradiction,
                },
                "advisory_status": advisory.get("status"),
                "advisory_next_step": advisory.get("recommended_next_step"),
                "data_quality_incidents": list(case.get("data_quality_incidents", [])),
            },
            "uncertainties": uncertainties,
            "decision_boundary": decision_boundary,
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
