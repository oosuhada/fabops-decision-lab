from __future__ import annotations

import hashlib
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

    @staticmethod
    def _lot_sequence(case: dict[str, Any]) -> int:
        suffix = str(case.get("lot_id", "")).split("-")[-1]
        return int(suffix) if suffix.isdigit() else 0

    @staticmethod
    def _episode_base_key(case: dict[str, Any]) -> tuple[str, str, str]:
        scope = case.get("affected_scope", {}) if isinstance(case.get("affected_scope"), dict) else {}
        equipment = sorted(str(value) for value in scope.get("equipment", []) if value)
        chambers = sorted(str(value) for value in scope.get("chambers", []) if value)
        return (
            str(case.get("classification") or "unknown"),
            equipment[0] if equipment else "data-path",
            chambers[0] if chambers else "unscoped",
        )

    @classmethod
    def _incident_episodes(
        cls,
        cases: list[dict[str, Any]],
        *,
        continuation_gap_lots: int = 12,
        max_episode_span_lots: int = 48,
        resolve_after_inactive_lots: int = 18,
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for case in cases:
            grouped.setdefault(cls._episode_base_key(case), []).append(case)
        latest_global_lot = max((cls._lot_sequence(case) for case in cases), default=0)
        episodes: list[dict[str, Any]] = []
        for key, members in grouped.items():
            ordered = sorted(members, key=cls._lot_sequence)
            chunks: list[list[dict[str, Any]]] = []
            current: list[dict[str, Any]] = []
            for case in ordered:
                lot_no = cls._lot_sequence(case)
                if current:
                    previous_lot = cls._lot_sequence(current[-1])
                    first_lot = cls._lot_sequence(current[0])
                    if lot_no - previous_lot > continuation_gap_lots or lot_no - first_lot > max_episode_span_lots:
                        chunks.append(current)
                        current = []
                current.append(case)
            if current:
                chunks.append(current)

            for chunk in chunks:
                latest = chunk[-1]
                first = chunk[0]
                latest_lot = cls._lot_sequence(latest)
                latest_score = float(latest.get("anomaly_score", 0.0))
                early_scores = [float(item.get("anomaly_score", 0.0)) for item in chunk[: min(2, len(chunk))]]
                recent_scores = [float(item.get("anomaly_score", 0.0)) for item in chunk[-min(2, len(chunk)) :]]
                trajectory_delta = (sum(recent_scores) / len(recent_scores)) - (sum(early_scores) / len(early_scores))
                state = str(latest.get("state") or "")
                inactive = latest_global_lot - latest_lot > resolve_after_inactive_lots
                if state in {"closed", "resolved", "rejected"} or inactive:
                    status = "RESOLVED"
                elif len(chunk) == 1:
                    status = "NEW"
                elif trajectory_delta >= 0.15:
                    status = "ESCALATING"
                elif trajectory_delta <= -0.15:
                    status = "RECOVERING"
                else:
                    status = "ONGOING"
                episode_key = (*key, cls._lot_sequence(first))
                episode_id = "EP-" + hashlib.sha256("|".join(map(str, episode_key)).encode("utf-8")).hexdigest()[:12].upper()
                episodes.append(
                    {
                        "episode_id": episode_id,
                        "status": status,
                        "classification": key[0],
                        "dominant_mechanism": key[0],
                        "equipment_id": key[1],
                        "chamber_id": key[2],
                        "affected_chambers": [key[2]] if key[2] != "unscoped" else [],
                        "case_count": len(chunk),
                        "raw_case_count": len(chunk),
                        "lot_count": len({str(item.get("lot_id")) for item in chunk}),
                        "first_lot_id": first.get("lot_id"),
                        "last_lot_id": latest.get("lot_id"),
                        "representative_case": latest,
                        "member_case_ids": [str(item["case_id"]) for item in chunk[-8:]],
                        "latest_supporting_case_ids": [str(item["case_id"]) for item in chunk[-3:]],
                        "grouping_basis": "classification+equipment+chamber+gap<=12lots+max-span-48lots",
                        "latest_anomaly_score": latest_score,
                        "risk_trajectory": [round(float(item.get("anomaly_score", 0.0)), 6) for item in chunk[-6:]],
                        "trajectory_delta": round(trajectory_delta, 6),
                        "inactive_lots": max(0, latest_global_lot - latest_lot),
                    }
                )
        return episodes

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

    def _cockpit_packet(self, case: dict[str, Any], *, hydrate: bool) -> dict[str, Any]:
        if hydrate:
            return self.packet(str(case["case_id"]))

        definition = _decision_definition(str(case["classification"]))
        advisory_next_step = {
            "physical_excursion": "open_case_for_evidence_review",
            "sensor_bias_suspected": "verify_sensor_calibration",
            "data_quality_incident": "reconcile_event_delivery",
        }.get(str(case["classification"]), "request_more_evidence")
        uncertainties = ["Detailed RCA/advisory hydration is deferred until this case is opened."]
        if case.get("data_quality_incidents"):
            uncertainties.append("Data-quality incidents must be resolved before process attribution is treated as actionable.")
        return {
            "schema_version": "decision-packet-v1",
            "case_id": case["case_id"],
            "lot_id": case["lot_id"],
            "classification": case["classification"],
            "state": case["state"],
            "decision_question": definition["decision_question"],
            "priority_band": definition["priority_band"],
            "priority_rank": definition["priority_rank"],
            "recommended_option_id": definition["recommended_option_id"],
            "options": definition["options"],
            "impact": _impact_payload(case, [str(case["lot_id"])]),
            "evidence": {
                "anomaly_score": case["anomaly_score"],
                "mean_yield": case.get("mean_yield"),
                "affected_scope": case.get("affected_scope", {}),
                "top_candidate": None,
                "advisory_status": "deferred",
                "advisory_next_step": advisory_next_step,
                "data_quality_incidents": list(case.get("data_quality_incidents", [])),
            },
            "uncertainties": uncertainties,
            "decision_boundary": _decision_boundary(
                str(case["classification"]),
                case,
                None,
                float(self.runtime.detector.config.excursion_yield_threshold),
            ),
            "evidence_refs": [f"case.evidence_event_ids[{index}]" for index, _ in enumerate(case.get("evidence_event_ids", []))],
            "provenance": {
                "input": "synthetic",
                "decision_packet": "inferred-deterministic-live-summary",
                "equipment_control": False,
                "financial_impact_claimed": False,
            },
        }

    def cockpit(self) -> dict[str, Any]:
        cases = self.runtime.case_repository.list_cases()
        ordered_cases = sorted(
            cases,
            key=lambda case: (
                -int(_decision_definition(str(case["classification"]))["priority_rank"]),
                -float(case.get("anomaly_score", 0.0)),
                str(case["case_id"]),
            ),
        )
        # Raw cases remain intact in PostgreSQL. The cockpit presents correlated
        # incident episodes so a growing synthetic event ledger does not create
        # an equally growing human decision queue.
        episodes = self._incident_episodes(cases)
        active_episodes = [episode for episode in episodes if episode["status"] != "RESOLVED"]
        recent_episodes = sorted(active_episodes, key=lambda episode: self._lot_sequence(episode["representative_case"]), reverse=True)[:16]
        severe_episodes = sorted(
            active_episodes,
            key=lambda episode: (
                -int(_decision_definition(str(episode["classification"]))["priority_rank"]),
                -float(episode["latest_anomaly_score"]),
                -self._lot_sequence(episode["representative_case"]),
            ),
        )[:16]
        selected_episodes: list[dict[str, Any]] = []
        seen_episodes: set[str] = set()
        for episode in [*recent_episodes, *severe_episodes]:
            episode_id = str(episode["episode_id"])
            if episode_id in seen_episodes:
                continue
            seen_episodes.add(episode_id)
            selected_episodes.append(episode)
            if len(selected_episodes) >= 24:
                break
        queue = []
        for episode in selected_episodes:
            packet = self._cockpit_packet(episode["representative_case"], hydrate=False)
            packet["incident_episode"] = {key: value for key, value in episode.items() if key != "representative_case"}
            packet["incident_episode"]["current_decision"] = packet["decision_question"]
            queue.append(packet)
        counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "VERIFY_DATA": 0}
        for case in ordered_cases:
            band = str(_decision_definition(str(case["classification"]))["priority_band"])
            counts[band] = counts.get(band, 0) + 1
        return {
            "schema_version": "decision-cockpit-v1",
            "source": "synthetic-events-and-inferred-cases",
            "summary": {
                "decision_count": len(ordered_cases),
                "raw_case_count": len(ordered_cases),
                "incident_episode_count": len(episodes),
                "active_incident_episode_count": len(active_episodes),
                "decision_queue_count": len(queue),
                "high_priority": counts.get("HIGH", 0),
                "medium_priority": counts.get("MEDIUM", 0),
                "data_verification": counts.get("VERIFY_DATA", 0),
            },
            "queue": queue,
        }
