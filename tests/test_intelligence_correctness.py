from __future__ import annotations

from collections import defaultdict

from services.decision.service import DecisionSupportService
from services.intelligence import build_live_decision_intelligence, build_situation_assessment
from services.intelligence.planner import material_signature, visualization_plan
from services.intelligence.service import FEATURE_SET_VERSION, PREDICTION_CUTOFF, FeatureBuilder
from simulator.config import load_config
from simulator.fabtwin import FabTwinSimulator
from simulator.live import LiveFabTwinStream


def _lot_events(lot_id: str = "LOT-00001") -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for event in FabTwinSimulator(load_config("test"), 42).generate().events:
        if event.get("lot_id"):
            grouped[str(event["lot_id"])].append(event)
    return grouped[lot_id]


def test_post_cmp_features_precede_final_target_and_exclude_lot_proxy() -> None:
    snapshot = FeatureBuilder().build(_lot_events())

    assert snapshot["feature_set_version"] == FEATURE_SET_VERSION
    assert snapshot["prediction_cutoff"] == PREDICTION_CUTOFF
    assert snapshot["feature_timestamp"] < snapshot["target_timestamp"]
    assert "tool_age_proxy" not in snapshot["features"]


def test_live_domain_randomization_is_seed_reproducible_but_cycle_variant() -> None:
    first = LiveFabTwinStream(seed=42, profile="test")
    second = LiveFabTwinStream(seed=42, profile="test")
    inspection = next(
        event
        for event in first.template
        if event.get("event_type") == "inspection.completed.v1" and event.get("lot_id") == "LOT-00001"
    )

    first_cycle_yield = first._rewrite_event(inspection, 0)["payload"]["yield"]
    repeated_first_cycle_yield = second._rewrite_event(inspection, 0)["payload"]["yield"]
    second_cycle_yield = first._rewrite_event(inspection, 1)["payload"]["yield"]

    assert first_cycle_yield == repeated_first_cycle_yield
    assert first_cycle_yield != second_cycle_yield


def test_live_decision_uses_exact_next_lot_semantics_and_composite_priority() -> None:
    packet = {
        "case_id": "CASE-1",
        "lot_id": "LOT-00100",
        "classification": "physical_excursion",
        "evidence": {
            "anomaly_score": 1.8,
            "mean_yield": 0.84,
            "affected_scope": {"equipment": ["CMP-02"], "chambers": ["CMP-02-A"]},
        },
    }
    predictions = [
        {"target": "final_yield", "score": 0.84},
        {"target": "final_excursion_probability", "score": 0.76},
        {"target": "next_lot_excursion_alarm_probability", "score": 0.82},
        {"target": "next_lot_maintenance_attention_probability", "score": 0.61},
    ]

    result = build_live_decision_intelligence(packet, predictions)

    assert result["watch_horizon"] == "next lot"
    assert "future_failure_probability" not in result["predictions"]
    assert "maintenance_probability" not in result["predictions"]
    assert result["predictions"]["next_lot_excursion_alarm_probability"] == 0.82
    assert 0.0 < result["priority_score"] < 1.0
    assert set(result["priority_components"]) >= {"calibrated_risk", "severity", "affected_scope", "human_actionability"}


def test_visualization_spec_is_bound_to_case_and_lot() -> None:
    case = {
        "case_id": "CASE-123",
        "lot_id": "LOT-00123",
        "classification": "physical_excursion",
        "anomaly_score": 1.2,
        "mean_yield": 0.86,
        "affected_scope": {"equipment": ["CMP-02"], "chambers": ["CMP-02-A"]},
    }
    predictions = [{"target": "next_lot_excursion_alarm_probability", "score": 0.81}]
    signature = material_signature(case, predictions)

    plan = visualization_plan(case, predictions, signature)

    assert plan["case_id"] == case["case_id"]
    assert plan["lot_id"] == case["lot_id"]
    assert plan["primary"]["case_id"] == case["case_id"]
    assert plan["primary"]["lot_id"] == case["lot_id"]
    assert plan["primary"]["type"] in plan["allowed_renderer_types"]


def test_incident_episode_clustering_preserves_members_and_reduces_objects() -> None:
    cases = [
        {
            "case_id": f"CASE-{index}",
            "lot_id": f"LOT-{100 + index:05d}",
            "classification": "physical_excursion",
            "state": "investigating",
            "anomaly_score": 1.0 + index * 0.1,
            "affected_scope": {"equipment": ["CMP-02"], "chambers": ["CMP-02-A"]},
        }
        for index in range(3)
    ]

    episodes = DecisionSupportService._incident_episodes(cases)

    assert len(episodes) == 1
    assert episodes[0]["case_count"] == 3
    assert episodes[0]["member_case_ids"] == ["CASE-0", "CASE-1", "CASE-2"]
    assert episodes[0]["status"] in {"ONGOING", "ESCALATING"}


def test_situation_assessment_exposes_prediction_delta_without_extra_claims() -> None:
    current_context = {
        "watch_horizon": "next lot",
        "predictions": {"next_lot_excursion_alarm_probability": 0.82},
        "why_now": ["next-lot excursion/alarm risk rose"],
        "next_actions": [{"action": "inspect RF trend", "target": "CMP-02-A", "purpose": "separate drift from spike"}],
        "trigger_conditions": [{"condition": "risk >= 0.80", "meaning": "review", "current": 0.82, "met": True}],
    }
    previous_report = {"decision_context": {"predictions": {"next_lot_excursion_alarm_probability": 0.61}}}

    assessment = build_situation_assessment(
        assessment_id="assessment-1",
        case_id="CASE-1",
        trigger="material_intelligence_change",
        provider="local-qwen",
        decision_context=current_context,
        brief={"generated_at": "2026-08-25T00:00:00+00:00"},
        previous_report=previous_report,
        model_versions={"next_lot_excursion_alarm_probability": "model-v2"},
        visualization_plan={"decision_question": "why risk changed", "primary": {"type": "timeseries"}, "secondary": {"type": "timeline"}, "rationale": "delta"},
        uncertainties=["synthetic portfolio only"],
    )

    assert assessment["forecast_horizon"] == "next lot"
    assert assessment["risk_trajectory"] == "RISING"
    assert assessment["what_changed"][0]["delta"] == 0.21
    assert assessment["equipment_control"] is False
