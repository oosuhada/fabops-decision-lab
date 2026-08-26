from __future__ import annotations

from collections import defaultdict

from services.decision.service import DecisionSupportService
from services.intelligence import build_live_decision_intelligence, build_situation_assessment
from services.intelligence.planner import material_signature, validated_llm_visualization_plan, visualization_plan
from services.intelligence.service import FEATURE_SET_VERSION, PREDICTION_CUTOFF, ContinuousIntelligenceService, FeatureBuilder
from services.narration import gateway
from services.narration.governance import ProviderGovernor, ProviderPolicy
from services.narration.providers import ProviderBusyError
from services.narration.queue import build_inference_job, queue_policy
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


def test_randomized_live_regime_provenance_reaches_feature_snapshot() -> None:
    stream = LiveFabTwinStream(seed=42, profile="test")
    lot_events = [stream._rewrite_event(event, 7) for event in stream.template if event.get("lot_id") == "LOT-00001"]

    snapshot = FeatureBuilder().build(lot_events)

    assert snapshot["regime_version"] == "fabops-live-regime-v2"
    assert snapshot["domain_randomized"] is True
    assert snapshot["live_cycle"] == 7
    assert snapshot["scenario_family"]
    assert snapshot["regime_id"] != "legacy-repeat"


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


def test_llm_visualization_proposal_changes_renderer_but_not_case_or_evidence_binding() -> None:
    case = {
        "case_id": "CASE-VIZ",
        "lot_id": "LOT-00124",
        "classification": "physical_excursion",
        "anomaly_score": 1.1,
        "mean_yield": 0.84,
        "affected_scope": {"equipment": ["CMP-02"], "chambers": ["CMP-02-A"]},
    }
    base = visualization_plan(case, [{"target": "final_excursion_probability", "score": 0.72}], "sig-viz")
    brief = {
        "provider": "local-qwen",
        "visualization_proposal": {
            "decision_question": "Did the distribution shift after the latest precursor drift?",
            "primary_type": "histogram",
            "secondary_type": "timeline",
            "reason": "Compare the recent distribution with the bounded baseline, then align the change with source events.",
        },
    }

    proposed = validated_llm_visualization_plan(base, brief)

    assert proposed["planner"] == "llm-proposed-validated-v1"
    assert proposed["primary"]["type"] == "histogram"
    assert proposed["secondary"]["type"] == "timeline"
    assert proposed["case_id"] == base["case_id"]
    assert proposed["lot_id"] == base["lot_id"]
    assert proposed["primary"]["evidence_refs"] == base["primary"]["evidence_refs"]
    assert proposed["primary"]["case_id"] == base["case_id"]


def test_invalid_llm_visualization_renderer_falls_back_to_deterministic_plan() -> None:
    case = {
        "case_id": "CASE-VIZ-INVALID",
        "lot_id": "LOT-00125",
        "classification": "physical_excursion",
        "anomaly_score": 1.1,
        "mean_yield": 0.84,
        "affected_scope": {"equipment": ["CMP-02"], "chambers": ["CMP-02-A"]},
    }
    base = visualization_plan(case, [], "sig-invalid")
    proposed = validated_llm_visualization_plan(
        base,
        {
            "provider": "local-qwen",
            "visualization_proposal": {
                "decision_question": "Render arbitrary code",
                "primary_type": "html",
                "secondary_type": "timeline",
                "reason": "unsupported renderer",
            },
        },
    )

    assert proposed["planner"] == "deterministic-situation-aware-v1"
    assert proposed["proposal_validation"] == "fallback_invalid_renderer"
    assert proposed["primary"] == base["primary"]


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


def test_incident_episode_clustering_continues_recurrence_but_splits_long_gap() -> None:
    cases = [
        {
            "case_id": f"CASE-{lot}",
            "lot_id": f"LOT-{lot:05d}",
            "classification": "physical_excursion",
            "state": "detected",
            "anomaly_score": 1.0,
            "affected_scope": {"equipment": ["CMP-01"], "chambers": ["CMP-01-B"]},
        }
        for lot in (100, 104, 112, 124, 160)
    ]

    episodes = DecisionSupportService._incident_episodes(cases)

    assert len(episodes) == 2
    assert episodes[0]["raw_case_count"] == 4
    assert episodes[0]["grouping_basis"].endswith("gap<=12lots+max-span-48lots")
    assert episodes[1]["raw_case_count"] == 1


def test_semantic_v2_status_filters_legacy_predictions_and_champions() -> None:
    predictions = [
        {"target": "future_failure_probability", "feature_set_version": "legacy-v1"},
        {"target": "next_lot_excursion_alarm_probability", "feature_set_version": FEATURE_SET_VERSION},
        {"target": "maintenance_probability", "feature_set_version": "legacy-v1"},
        {"target": "final_yield", "feature_set_version": FEATURE_SET_VERSION},
    ]
    champions = {
        "future_failure": {"feature_set_version": "legacy-v1"},
        "final_yield_post_cmp": {"feature_set_version": FEATURE_SET_VERSION},
        "next_lot_excursion_alarm_risk": {"feature_set_version": FEATURE_SET_VERSION},
    }

    filtered_predictions = ContinuousIntelligenceService.semantic_v2_predictions(predictions)
    filtered_champions = ContinuousIntelligenceService.semantic_v2_champions(champions)

    assert [item["target"] for item in filtered_predictions] == ["next_lot_excursion_alarm_probability", "final_yield"]
    assert set(filtered_champions) == {"final_yield_post_cmp", "next_lot_excursion_alarm_risk"}


def test_champion_promotion_uses_same_shadow_window_and_guardrails() -> None:
    promoted, gate = ContinuousIntelligenceService._promotion_gate(
        model_name="next_lot_excursion_alarm_risk",
        candidate_metrics={
            "brier": 0.09,
            "auprc": 0.91,
            "false_positive_rate": 0.04,
            "calibration_error": 0.08,
            "recall": 0.82,
        },
        incumbent_metrics={
            "brier": 0.10,
            "auprc": 0.90,
            "false_positive_rate": 0.03,
            "calibration_error": 0.07,
            "recall": 0.84,
        },
    )

    assert promoted is True
    assert gate["quality_delta_same_shadow"] == 0.01
    assert gate["guardrails_met"] is True

    rejected, rejected_gate = ContinuousIntelligenceService._promotion_gate(
        model_name="next_lot_excursion_alarm_risk",
        candidate_metrics={
            "brier": 0.08,
            "auprc": 0.91,
            "false_positive_rate": 0.04,
            "calibration_error": 0.08,
            "recall": 0.60,
        },
        incumbent_metrics={
            "brier": 0.10,
            "auprc": 0.90,
            "false_positive_rate": 0.03,
            "calibration_error": 0.07,
            "recall": 0.84,
        },
    )

    assert rejected is False
    assert rejected_gate["quality_delta_same_shadow"] == 0.02
    assert rejected_gate["guardrails"]["recall_non_regression"] is False


def test_inference_queue_policy_never_uses_vertex_for_normal_auto_busy_state() -> None:
    normal = queue_policy("material_intelligence_change", "NORMAL")
    high = queue_policy("material_intelligence_change", "HIGH")
    manual = queue_policy("manual_user_refresh", "HIGH")

    assert normal["allow_vertex_fallback"] is False
    assert normal["max_queue_age_seconds"] == 900
    assert high["allow_vertex_fallback"] is True
    assert high["fallback_after_seconds"] == 180
    assert manual["priority"] > high["priority"] > normal["priority"]

    job = build_inference_job(
        case_id="CASE-QUEUE",
        material_signature="sig-1",
        trigger_type="material_intelligence_change",
        urgency="NORMAL",
        request_document={"intent": "situation_update", "packet": {"case_id": "CASE-QUEUE"}},
    )
    assert job["allow_vertex_fallback"] is False
    assert job["provider_preference"] == "local-qwen"


def test_provider_busy_does_not_open_local_failure_circuit() -> None:
    governor = ProviderGovernor(
        {
            "local-qwen": ProviderPolicy(
                max_requests_per_minute=20,
                max_concurrency=1,
                daily_request_limit=100,
                daily_estimated_token_limit=100_000,
                circuit_failure_threshold=2,
                circuit_cooldown_seconds=60,
            )
        }
    )

    for _ in range(3):
        try:
            governor.run("local-qwen", 10, lambda: (_ for _ in ()).throw(ProviderBusyError("busy")))
        except ProviderBusyError:
            pass

    status = governor.status()["local-qwen"]
    assert status["state"] == "available"
    assert status["consecutive_failures"] == 0
    assert status["total_failures"] == 0
    assert status["total_busy_responses"] == 3


def test_cpu_histogram_challenger_can_win_on_nonlinear_calibration_pattern() -> None:
    train_vectors = []
    train_targets = []
    calibration_vectors = []
    calibration_targets = []
    for index in range(48):
        value = (index % 16) / 15
        vector = [value, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        target = 1.0 if 0.25 < value < 0.75 else 0.0
        if index < 32:
            train_vectors.append(vector)
            train_targets.append(target)
        else:
            calibration_vectors.append(vector)
            calibration_targets.append(target)

    selected, comparison = ContinuousIntelligenceService._select_baseline_or_challenger(
        kind="logistic",
        train_vectors=train_vectors,
        train_targets=train_targets,
        calibration_vectors=calibration_vectors,
        calibration_targets=calibration_targets,
    )

    assert comparison["selection_window"] == "CALIBRATION"
    assert comparison["challenger_algorithm"] == "histogram-stump-boosting-logistic"
    assert comparison["selected_algorithm"] == "histogram-stump-boosting-logistic"
    assert comparison["challenger_metrics"]["brier"] < comparison["baseline_metrics"]["brier"]
    assert selected["kind"] == "histogram-stump-boosting-logistic"


def test_gateway_detects_active_loopback_lmstudio_connection(monkeypatch) -> None:
    class Completed:
        returncode = 0
        stdout = "\n".join(
            [
                "p2080",
                "n127.0.0.1:1234->127.0.0.1:61705",
                "p90647",
                "n127.0.0.1:61705->127.0.0.1:1234",
            ]
        )

    monkeypatch.setenv("FABOPS_GATEWAY_UPSTREAM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setattr(gateway.subprocess, "run", lambda *_args, **_kwargs: Completed())

    assert gateway._active_upstream_connections() == 1
    assert gateway._interactive_inference_busy() is True


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
