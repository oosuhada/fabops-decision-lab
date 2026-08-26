from __future__ import annotations

import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from services.detection.service import SENSOR_INDEX, STEP_INDEX, DetectorConfig

FEATURE_SET_VERSION = "fabops-feature-set-v2"
PREDICTION_CUTOFF = "POST_CMP"
SEMANTIC_V2_TARGETS = {
    "final_yield",
    "final_excursion_probability",
    "next_lot_excursion_alarm_probability",
    "next_lot_maintenance_attention_probability",
}
FEATURE_NAMES = [
    "measurement_density",
    "mean_abs_deviation",
    "max_abs_deviation",
    "signal_volatility",
    "alarm_density",
    "chamber_breadth",
    "equipment_breadth",
    "process_step_coverage",
    "recipe_exposure_diversity",
    "recipe_mismatch_density",
]


def _sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class FeatureBuilder:
    def __init__(self) -> None:
        self.detector_config = DetectorConfig.load()

    @staticmethod
    def _lot_index(lot_id: str) -> int:
        try:
            return int(lot_id.split("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    @staticmethod
    def _volatility(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))

    @staticmethod
    def _expected(sensor: str, step: str) -> float:
        return 10.0 + SENSOR_INDEX.get(sensor, 0) * 5.0 + STEP_INDEX.get(step, 0) * 0.3

    @staticmethod
    def _events_through_cutoff(events: list[dict[str, Any]], prediction_cutoff: str) -> tuple[list[dict[str, Any]], bool]:
        if prediction_cutoff == "LATEST_AVAILABLE":
            return list(events), True
        cutoff_step = prediction_cutoff.removeprefix("POST_")
        for index, event in enumerate(events):
            if event.get("event_type") != "process.completed.v1":
                continue
            if str(event.get("payload", {}).get("step_id", "")) == cutoff_step:
                return list(events[: index + 1]), True
        return [], False

    def build(self, events: list[dict[str, Any]], *, prediction_cutoff: str = PREDICTION_CUTOFF) -> dict[str, Any]:
        if not events:
            raise ValueError("feature build requires events")
        selected, cutoff_reached = self._events_through_cutoff(events, prediction_cutoff)
        lot_id = str(events[-1].get("lot_id") or "unknown")
        if not cutoff_reached:
            return {
                "lot_id": lot_id,
                "feature_set_version": FEATURE_SET_VERSION,
                "prediction_cutoff": prediction_cutoff,
                "cutoff_reached": False,
                "complete": False,
            }

        measurements = [event for event in selected if event.get("event_type") == "process.measurement.recorded.v1"]
        values = [float(event.get("payload", {}).get("value", 0.0)) for event in measurements]
        deviations = [
            abs(float(event["payload"]["value"]) - self._expected(str(event["payload"].get("sensor_name", "")), str(event["payload"].get("step_id", ""))))
            for event in measurements
        ]
        alarms = [event for event in selected if event.get("event_type") == "equipment.alarm.raised.v1"]
        chambers = {str(event.get("chamber_id")) for event in selected if event.get("chamber_id")}
        equipment = {str(event.get("equipment_id")) for event in selected if event.get("equipment_id")}
        completed_steps = {
            str(event.get("payload", {}).get("step_id", ""))
            for event in selected
            if event.get("event_type") == "process.completed.v1" and event.get("payload", {}).get("step_id")
        }
        recipes = {
            str(event.get("payload", {}).get("recipe_id", ""))
            for event in selected
            if event.get("payload", {}).get("recipe_id")
        }
        process_starts = [event for event in selected if event.get("event_type") == "process.started.v1"]
        recipe_mismatches = [
            event
            for event in process_starts
            if event.get("payload", {}).get("recipe_id")
            and event.get("payload", {}).get("expected_recipe_id")
            and event["payload"]["recipe_id"] != event["payload"]["expected_recipe_id"]
        ]
        vector = [
            _clamp(len(measurements) / 20.0),
            _clamp((sum(deviations) / max(1, len(deviations))) / 3.0),
            _clamp((max(deviations) if deviations else 0.0) / 6.0),
            _clamp(self._volatility(values) / 4.0),
            _clamp(len(alarms) / 2.0),
            _clamp(len(chambers) / 5.0),
            _clamp(len(equipment) / 5.0),
            _clamp(len(completed_steps) / 4.0),
            _clamp(len(recipes) / 4.0),
            _clamp(len(recipe_mismatches) / max(1, len(process_starts))),
        ]

        release_event = next((event for event in events if event.get("event_type") == "lot.released.v1"), None)
        release_payload = release_event.get("payload", {}) if isinstance(release_event, dict) else {}
        live_regime = release_payload.get("live_regime") if isinstance(release_payload, dict) else None
        if isinstance(live_regime, dict):
            regime_version = str(live_regime.get("regime_version") or "fabops-live-regime-v2")
            fault_mix = sorted(str(value) for value in live_regime.get("fault_mix", []) if value)
            scenario_family = "+".join(fault_mix) if fault_mix else "benign_randomized"
            regime_id = str(release_payload.get("live_regime_id") or live_regime.get("regime_id") or "unknown")
            live_cycle = release_payload.get("live_cycle")
            domain_randomized = bool(release_payload.get("domain_randomized", True))
        elif release_event and release_event.get("source") == "fabtwin-live":
            regime_version = "legacy-live-repeat-v1"
            scenario_family = "legacy-repeat"
            regime_id = str(release_payload.get("live_regime_id") or "legacy-repeat")
            live_cycle = release_payload.get("live_cycle")
            domain_randomized = False
        else:
            regime_version = "canonical-fixture-v1"
            scenario_family = "canonical-fixture"
            regime_id = "canonical-fixture"
            live_cycle = None
            domain_randomized = False

        inspections = [event for event in events if event.get("event_type") == "inspection.completed.v1"]
        maintenance = [event for event in events if event.get("event_type") == "maintenance.completed.v1"]
        all_alarms = [event for event in events if event.get("event_type") == "equipment.alarm.raised.v1"]
        yields = [float(event["payload"]["yield"]) for event in inspections if event.get("payload", {}).get("yield") is not None]
        feature_timestamp = str(selected[-1].get("event_time"))
        target_timestamp = str(inspections[-1].get("event_time")) if inspections else None
        return {
            "lot_id": lot_id,
            "feature_set_version": FEATURE_SET_VERSION,
            "prediction_cutoff": prediction_cutoff,
            "cutoff_reached": True,
            "feature_timestamp": feature_timestamp,
            "features": {name: round(vector[index], 6) for index, name in enumerate(FEATURE_NAMES)},
            "vector": vector,
            "regime_version": regime_version,
            "regime_id": regime_id,
            "scenario_family": scenario_family,
            "live_cycle": live_cycle,
            "domain_randomized": domain_randomized,
            "yield_value": round(sum(yields) / len(yields), 6) if yields else None,
            "physical_excursion": bool(yields and (sum(yields) / len(yields)) < self.detector_config.excursion_yield_threshold),
            "equipment_alarm": bool(all_alarms),
            "maintenance_observed": bool(maintenance),
            "complete": bool(inspections),
            "target_timestamp": target_timestamp,
            "latest_event_time": str(events[-1].get("event_time")),
        }


class ContinuousIntelligenceService:
    """Closes the live loop with explicit prediction semantics and temporal cutoffs."""

    REQUIRED_MODELS = {
        "final_yield_post_cmp",
        "final_excursion_post_cmp",
        "next_lot_excursion_alarm_risk",
        "next_lot_maintenance_attention_risk",
    }

    @staticmethod
    def semantic_v2_predictions(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            item
            for item in predictions
            if item.get("target") in SEMANTIC_V2_TARGETS
            and item.get("feature_set_version") == FEATURE_SET_VERSION
        ]

    @classmethod
    def semantic_v2_champions(cls, champions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            name: model
            for name, model in champions.items()
            if name in cls.REQUIRED_MODELS and model.get("feature_set_version") == FEATURE_SET_VERSION
        }

    def __init__(self, repository: Any) -> None:
        self.repository = repository
        self.features = FeatureBuilder()

    def lot_snapshots(self, recent_limit: int = 80, recovery_limit: int = 200) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        recent_reader = getattr(self.repository, "recent_lot_ids", None)
        recovery_reader = getattr(self.repository, "unlearned_completed_lot_ids", None)
        lot_event_reader = getattr(self.repository, "events_for_lots", None)
        if callable(recent_reader) and callable(recovery_reader) and callable(lot_event_reader):
            selected_lots = list(dict.fromkeys([*recovery_reader(recovery_limit), *recent_reader(recent_limit)]))
            stored_events = lot_event_reader(selected_lots)
        else:
            stored_events = self.repository.all_events()
        for stored in stored_events:
            event = stored.event
            lot_id = event.get("lot_id")
            if lot_id:
                grouped[str(lot_id)].append(event)
        snapshots = [
            self.features.build(events, prediction_cutoff=PREDICTION_CUTOFF)
            for lot_id, events in sorted(grouped.items(), key=lambda item: FeatureBuilder._lot_index(item[0]))
        ]
        return [snapshot for snapshot in snapshots if snapshot.get("cutoff_reached")]

    def synchronize_outcomes(self, snapshots: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        completed = [snapshot for snapshot in (snapshots if snapshots is not None else self.lot_snapshots()) if snapshot["complete"]]
        existing = {str(item["lot_id"]): item for item in self.repository.learning_outcomes()}
        changed: list[dict[str, Any]] = []
        for snapshot in completed:
            if snapshot.get("target_timestamp") and snapshot.get("feature_timestamp") and snapshot["feature_timestamp"] >= snapshot["target_timestamp"]:
                raise ValueError(f"prediction feature timestamp must precede target timestamp for {snapshot['lot_id']}")
            outcome = {
                "lot_id": snapshot["lot_id"],
                "feature_set_version": FEATURE_SET_VERSION,
                "prediction_cutoff": snapshot["prediction_cutoff"],
                "feature_timestamp": snapshot["feature_timestamp"],
                "target_timestamp": snapshot["target_timestamp"],
                "regime_version": snapshot.get("regime_version"),
                "regime_id": snapshot.get("regime_id"),
                "scenario_family": snapshot.get("scenario_family"),
                "live_cycle": snapshot.get("live_cycle"),
                "domain_randomized": bool(snapshot.get("domain_randomized", False)),
                "yield_value": snapshot["yield_value"],
                "physical_excursion": snapshot["physical_excursion"],
                "equipment_alarm": snapshot["equipment_alarm"],
                "maintenance_observed": snapshot["maintenance_observed"],
                "maintenance_attention": bool(snapshot["maintenance_observed"] or snapshot["equipment_alarm"]),
                "features": snapshot["features"],
                "latest_event_time": snapshot["latest_event_time"],
            }
            previous = existing.get(str(snapshot["lot_id"]))
            if previous is not None and all(
                previous.get(key) == outcome.get(key)
                for key in (
                    "feature_set_version",
                    "prediction_cutoff",
                    "feature_timestamp",
                    "target_timestamp",
                    "regime_version",
                    "regime_id",
                    "scenario_family",
                    "live_cycle",
                    "domain_randomized",
                    "yield_value",
                    "physical_excursion",
                    "equipment_alarm",
                    "maintenance_observed",
                    "features",
                )
            ):
                continue
            self.repository.upsert_learning_outcome(outcome)
            changed.append(snapshot)
        return changed

    @staticmethod
    def _ordered_outcomes(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compatible = [item for item in outcomes if item.get("feature_set_version") == FEATURE_SET_VERSION]
        return sorted(compatible, key=lambda item: FeatureBuilder._lot_index(str(item["lot_id"])))

    @staticmethod
    def _vectors(outcomes: list[dict[str, Any]]) -> list[list[float]]:
        return [[float(outcome["features"].get(name, 0.0)) for name in FEATURE_NAMES] for outcome in outcomes]

    @staticmethod
    def _fit_linear(vectors: list[list[float]], targets: list[float], *, epochs: int = 180, rate: float = 0.055) -> dict[str, Any]:
        weights = [0.0] * len(FEATURE_NAMES)
        bias = sum(targets) / max(1, len(targets))
        for _ in range(epochs):
            for vector, target in zip(vectors, targets, strict=True):
                prediction = _clamp(bias + sum(weight * value for weight, value in zip(weights, vector, strict=True)))
                error = prediction - target
                bias -= rate * error
                for index, value in enumerate(vector):
                    weights[index] -= rate * error * value
        return {"weights": weights, "bias": bias, "kind": "online-linear-sgd", "interval_radius": 0.05}

    @staticmethod
    def _fit_logistic(vectors: list[list[float]], targets: list[float], *, epochs: int = 220, rate: float = 0.07) -> dict[str, Any]:
        weights = [0.0] * len(FEATURE_NAMES)
        positive_rate = (sum(targets) + 1.0) / (len(targets) + 2.0)
        bias = math.log(positive_rate / max(1e-6, 1.0 - positive_rate))
        for _ in range(epochs):
            for vector, target in zip(vectors, targets, strict=True):
                prediction = _sigmoid(bias + sum(weight * value for weight, value in zip(weights, vector, strict=True)))
                error = prediction - target
                bias -= rate * error
                for index, value in enumerate(vector):
                    weights[index] -= rate * error * value
        return {"weights": weights, "bias": bias, "temperature": 1.0, "kind": "online-logistic-sgd"}

    @classmethod
    def _calibrate_temperature(cls, parameters: dict[str, Any], vectors: list[list[float]], targets: list[float]) -> dict[str, Any]:
        if not vectors or parameters.get("kind") != "online-logistic-sgd":
            return parameters
        best_temperature = 1.0
        best_brier = float("inf")
        for temperature in (0.55, 0.7, 0.85, 1.0, 1.2, 1.5, 1.9):
            trial = {**parameters, "temperature": temperature}
            predictions = [cls._predict(trial, vector) for vector in vectors]
            brier = sum((prediction - target) ** 2 for prediction, target in zip(predictions, targets, strict=True)) / len(targets)
            if brier < best_brier:
                best_brier = brier
                best_temperature = temperature
        return {**parameters, "temperature": best_temperature}

    @classmethod
    def _calibrate_interval(cls, parameters: dict[str, Any], vectors: list[list[float]], targets: list[float]) -> dict[str, Any]:
        if not vectors:
            return parameters
        residuals = sorted(abs(cls._predict(parameters, vector) - target) for vector, target in zip(vectors, targets, strict=True))
        index = min(len(residuals) - 1, max(0, math.ceil(len(residuals) * 0.8) - 1))
        return {**parameters, "interval_radius": max(0.01, float(residuals[index]))}

    @staticmethod
    def _predict(parameters: dict[str, Any], vector: list[float]) -> float:
        raw = float(parameters.get("bias", 0.0)) + sum(
            float(weight) * value for weight, value in zip(parameters.get("weights", []), vector, strict=True)
        )
        if parameters.get("kind") == "online-logistic-sgd":
            return _sigmoid(raw / max(0.1, float(parameters.get("temperature", 1.0))))
        return _clamp(raw)

    @staticmethod
    def _average_precision(predictions: list[float], targets: list[float]) -> float:
        positives = sum(target >= 0.5 for target in targets)
        if positives == 0:
            return 0.0
        ranked = sorted(zip(predictions, targets, strict=True), key=lambda item: item[0], reverse=True)
        true_positives = 0
        precision_sum = 0.0
        for rank, (_score, target) in enumerate(ranked, start=1):
            if target >= 0.5:
                true_positives += 1
                precision_sum += true_positives / rank
        return precision_sum / positives

    @staticmethod
    def _calibration_error(predictions: list[float], targets: list[float], bins: int = 5) -> float:
        total = len(predictions)
        if total == 0:
            return 1.0
        error = 0.0
        for index in range(bins):
            low = index / bins
            high = (index + 1) / bins
            members = [(prediction, target) for prediction, target in zip(predictions, targets, strict=True) if low <= prediction < high or (index == bins - 1 and prediction == 1.0)]
            if not members:
                continue
            mean_prediction = sum(item[0] for item in members) / len(members)
            mean_target = sum(item[1] for item in members) / len(members)
            error += (len(members) / total) * abs(mean_prediction - mean_target)
        return error

    @classmethod
    def _classification_metrics(cls, parameters: dict[str, Any], vectors: list[list[float]], targets: list[float]) -> dict[str, float]:
        if not vectors:
            return {"mae": 1.0, "brier": 1.0, "accuracy": 0.0, "auprc": 0.0, "precision": 0.0, "recall": 0.0, "false_positive_rate": 1.0, "calibration_error": 1.0}
        predictions = [cls._predict(parameters, vector) for vector in vectors]
        predicted_labels = [prediction >= 0.5 for prediction in predictions]
        target_labels = [target >= 0.5 for target in targets]
        tp = sum(predicted and actual for predicted, actual in zip(predicted_labels, target_labels, strict=True))
        fp = sum(predicted and not actual for predicted, actual in zip(predicted_labels, target_labels, strict=True))
        tn = sum(not predicted and not actual for predicted, actual in zip(predicted_labels, target_labels, strict=True))
        fn = sum(not predicted and actual for predicted, actual in zip(predicted_labels, target_labels, strict=True))
        mae = sum(abs(prediction - target) for prediction, target in zip(predictions, targets, strict=True)) / len(targets)
        brier = sum((prediction - target) ** 2 for prediction, target in zip(predictions, targets, strict=True)) / len(targets)
        accuracy = (tp + tn) / len(targets)
        return {
            "mae": round(mae, 6),
            "brier": round(brier, 6),
            "accuracy": round(accuracy, 6),
            "auprc": round(cls._average_precision(predictions, targets), 6),
            "precision": round(tp / max(1, tp + fp), 6),
            "recall": round(tp / max(1, tp + fn), 6),
            "false_positive_rate": round(fp / max(1, fp + tn), 6),
            "calibration_error": round(cls._calibration_error(predictions, targets), 6),
        }

    @classmethod
    def _regression_metrics(cls, parameters: dict[str, Any], vectors: list[list[float]], targets: list[float]) -> dict[str, float]:
        if not vectors:
            return {"mae": 1.0, "rmse": 1.0, "bias": 1.0, "interval_coverage": 0.0}
        predictions = [cls._predict(parameters, vector) for vector in vectors]
        errors = [prediction - target for prediction, target in zip(predictions, targets, strict=True)]
        radius = float(parameters.get("interval_radius", 0.05))
        coverage = sum((prediction - radius) <= target <= (prediction + radius) for prediction, target in zip(predictions, targets, strict=True)) / len(targets)
        return {
            "mae": round(sum(abs(error) for error in errors) / len(errors), 6),
            "rmse": round(math.sqrt(sum(error * error for error in errors) / len(errors)), 6),
            "bias": round(sum(errors) / len(errors), 6),
            "interval_coverage": round(coverage, 6),
        }

    @staticmethod
    def _dataset_fingerprint(model_name: str, outcomes: list[dict[str, Any]], targets: list[float]) -> str:
        payload = [
            (
                outcome["lot_id"],
                outcome.get("feature_timestamp"),
                outcome.get("target_timestamp"),
                outcome.get("regime_version"),
                outcome.get("regime_id"),
                outcome.get("scenario_family"),
                outcome.get("features", {}),
                target,
            )
            for outcome, target in zip(outcomes, targets, strict=True)
        ]
        return hashlib.sha256(json.dumps({"model": model_name, "rows": payload}, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _version(model_name: str, rows: int, dataset_fingerprint: str) -> str:
        return f"{model_name}-r{rows}-{dataset_fingerprint[:10]}"

    @staticmethod
    def _quality(model_name: str, metrics: dict[str, Any]) -> float:
        if model_name == "final_yield_post_cmp":
            return 1.0 - float(metrics.get("mae", 1.0))
        return 1.0 - float(metrics.get("brier", 1.0))

    @classmethod
    def _promotion_gate(
        cls,
        *,
        model_name: str,
        candidate_metrics: dict[str, Any],
        incumbent_metrics: dict[str, Any] | None,
    ) -> tuple[bool, dict[str, Any]]:
        """Compare candidate and incumbent on the exact same shadow window.

        Registry metrics from an older champion belong to its historical test
        window and are not directly comparable with a newly trained candidate.
        Promotion therefore re-scores the incumbent parameters on the current
        candidate shadow window before applying non-regression guardrails.
        """

        if incumbent_metrics is None:
            return True, {
                "decision": "initial_champion",
                "minimum_quality_improvement": None,
                "guardrails_met": True,
            }
        candidate_quality = cls._quality(model_name, candidate_metrics)
        incumbent_quality = cls._quality(model_name, incumbent_metrics)
        minimum_improvement = 0.002 if model_name == "final_yield_post_cmp" else 0.003
        quality_delta = candidate_quality - incumbent_quality
        guardrails: dict[str, bool]
        if model_name == "final_yield_post_cmp":
            guardrails = {
                "bias_non_regression": abs(float(candidate_metrics.get("bias", 1.0)))
                <= abs(float(incumbent_metrics.get("bias", 1.0))) + 0.01,
                "interval_coverage_non_regression": float(candidate_metrics.get("interval_coverage", 0.0))
                >= float(incumbent_metrics.get("interval_coverage", 0.0)) - 0.10,
            }
        else:
            guardrails = {
                "auprc_non_regression": float(candidate_metrics.get("auprc", 0.0))
                >= float(incumbent_metrics.get("auprc", 0.0)) - 0.02,
                "false_positive_rate_non_regression": float(candidate_metrics.get("false_positive_rate", 1.0))
                <= float(incumbent_metrics.get("false_positive_rate", 1.0)) + 0.05,
                "calibration_non_regression": float(candidate_metrics.get("calibration_error", 1.0))
                <= float(incumbent_metrics.get("calibration_error", 1.0)) + 0.03,
                "recall_non_regression": float(candidate_metrics.get("recall", 0.0))
                >= float(incumbent_metrics.get("recall", 0.0)) - 0.10,
            }
        guardrails_met = all(guardrails.values())
        promoted = quality_delta >= minimum_improvement and guardrails_met
        return promoted, {
            "decision": "promote" if promoted else "reject",
            "minimum_quality_improvement": minimum_improvement,
            "candidate_quality": round(candidate_quality, 6),
            "incumbent_quality_same_shadow": round(incumbent_quality, 6),
            "quality_delta_same_shadow": round(quality_delta, 6),
            "guardrails": guardrails,
            "guardrails_met": guardrails_met,
        }

    @staticmethod
    def _temporal_split(length: int) -> tuple[int, int]:
        if length < 12:
            raise ValueError("temporal split requires at least 12 rows")
        train_end = max(8, int(length * 0.60))
        calibration_end = max(train_end + 2, int(length * 0.80))
        calibration_end = min(calibration_end, length - 2)
        return train_end, calibration_end

    @classmethod
    def _shadow_metrics_by_group(
        cls,
        *,
        parameters: dict[str, Any],
        vectors: list[list[float]],
        targets: list[float],
        outcomes: list[dict[str, Any]],
        kind: str,
        group_key: str,
    ) -> dict[str, dict[str, Any]]:
        groups: dict[str, list[int]] = defaultdict(list)
        for index, outcome in enumerate(outcomes):
            groups[str(outcome.get(group_key) or "unknown")].append(index)
        result: dict[str, dict[str, Any]] = {}
        for group, indices in sorted(groups.items()):
            group_vectors = [vectors[index] for index in indices]
            group_targets = [targets[index] for index in indices]
            metrics = (
                cls._classification_metrics(parameters, group_vectors, group_targets)
                if kind == "logistic"
                else cls._regression_metrics(parameters, group_vectors, group_targets)
            )
            result[group] = {"rows": len(indices), **metrics}
        return result

    @staticmethod
    def _dataset_mix(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
        regime_counts: dict[str, int] = defaultdict(int)
        scenario_counts: dict[str, int] = defaultdict(int)
        randomized = 0
        for outcome in outcomes:
            regime_counts[str(outcome.get("regime_version") or "unknown")] += 1
            scenario_counts[str(outcome.get("scenario_family") or "unknown")] += 1
            randomized += int(bool(outcome.get("domain_randomized")))
        return {
            "rows": len(outcomes),
            "randomized_rows": randomized,
            "randomized_share": round(randomized / max(1, len(outcomes)), 6),
            "regime_versions": dict(sorted(regime_counts.items())),
            "scenario_families": dict(sorted(scenario_counts.items(), key=lambda item: (-item[1], item[0]))),
        }

    def retrain(self, *, minimum_rows: int = 12) -> dict[str, Any]:
        outcomes = self._ordered_outcomes(self.repository.learning_outcomes())
        if len(outcomes) < minimum_rows:
            return {"trained": False, "reason": "insufficient_v2_outcomes", "training_rows": len(outcomes)}
        champions = self.repository.champion_models()
        definitions = [
            (
                "final_yield_post_cmp",
                "linear",
                outcomes,
                [float(outcome.get("yield_value") or 0.0) for outcome in outcomes],
                "POST_CMP->final-inspection-yield",
                "Final inspection yield for the same lot, predicted strictly at POST_CMP.",
            ),
            (
                "final_excursion_post_cmp",
                "logistic",
                outcomes,
                [1.0 if outcome.get("physical_excursion") else 0.0 for outcome in outcomes],
                "POST_CMP->final-inspection-excursion",
                "Same-lot final inspection excursion risk predicted strictly at POST_CMP.",
            ),
            (
                "next_lot_excursion_alarm_risk",
                "logistic",
                outcomes[:-1],
                [1.0 if next_outcome.get("physical_excursion") or next_outcome.get("equipment_alarm") else 0.0 for next_outcome in outcomes[1:]],
                "POST_CMP(current)->next-lot-excursion-or-equipment-alarm",
                "Risk that the immediately following synthetic lot has a physical excursion or equipment alarm; not equipment failure probability.",
            ),
            (
                "next_lot_maintenance_attention_risk",
                "logistic",
                outcomes[:-1],
                [1.0 if next_outcome.get("maintenance_attention") else 0.0 for next_outcome in outcomes[1:]],
                "POST_CMP(current)->next-lot-maintenance-attention",
                "Next-lot maintenance-attention proxy based on observed maintenance/alarm evidence; not RUL.",
            ),
        ]
        promoted: list[str] = []
        candidates: list[dict[str, Any]] = []
        for model_name, kind, model_outcomes, targets, horizon, target_definition in definitions:
            vectors = self._vectors(model_outcomes)
            if len(vectors) < minimum_rows:
                continue
            train_end, calibration_end = self._temporal_split(len(vectors))
            train_vectors, calibration_vectors, test_vectors = vectors[:train_end], vectors[train_end:calibration_end], vectors[calibration_end:]
            train_targets, calibration_targets, test_targets = targets[:train_end], targets[train_end:calibration_end], targets[calibration_end:]
            test_outcomes = model_outcomes[calibration_end:]
            parameters = self._fit_linear(train_vectors, train_targets) if kind == "linear" else self._fit_logistic(train_vectors, train_targets)
            if kind == "logistic":
                parameters = self._calibrate_temperature(parameters, calibration_vectors, calibration_targets)
                metrics = self._classification_metrics(parameters, test_vectors, test_targets)
            else:
                parameters = self._calibrate_interval(parameters, calibration_vectors, calibration_targets)
                metrics = self._regression_metrics(parameters, test_vectors, test_targets)
            dataset_fingerprint = self._dataset_fingerprint(model_name, model_outcomes, targets)
            version = self._version(model_name, len(model_outcomes), dataset_fingerprint)
            training_window = {
                "start_lot": model_outcomes[0]["lot_id"],
                "end_lot": model_outcomes[train_end - 1]["lot_id"],
            }
            calibration_window = {
                "start_lot": model_outcomes[train_end]["lot_id"],
                "end_lot": model_outcomes[calibration_end - 1]["lot_id"],
            }
            test_window = {
                "start_lot": model_outcomes[calibration_end]["lot_id"],
                "end_lot": model_outcomes[-1]["lot_id"],
            }
            model = {
                "model_name": model_name,
                "model_version": version,
                "training_rows": len(model_outcomes),
                "feature_schema": FEATURE_NAMES,
                "feature_set_version": FEATURE_SET_VERSION,
                "prediction_cutoff": PREDICTION_CUTOFF,
                "training_window": training_window,
                "calibration_window": calibration_window,
                "test_window": test_window,
                "target_definition": target_definition,
                "dataset_fingerprint": dataset_fingerprint,
                "code_git_sha": os.getenv("FABOPS_GIT_SHA", "unknown"),
                "simulator_regime": ",".join(sorted({str(item.get("regime_version") or "unknown") for item in model_outcomes})),
                "parameters": parameters,
                "metrics": {
                    **metrics,
                    "train_rows": len(train_targets),
                    "calibration_rows": len(calibration_targets),
                    "shadow_test_rows": len(test_targets),
                    "horizon": horizon,
                    "shadow_test_by_regime": self._shadow_metrics_by_group(
                        parameters=parameters,
                        vectors=test_vectors,
                        targets=test_targets,
                        outcomes=test_outcomes,
                        kind=kind,
                        group_key="regime_version",
                    ),
                    "shadow_test_by_scenario_family": self._shadow_metrics_by_group(
                        parameters=parameters,
                        vectors=test_vectors,
                        targets=test_targets,
                        outcomes=test_outcomes,
                        kind=kind,
                        group_key="scenario_family",
                    ),
                    "dataset_mix": self._dataset_mix(model_outcomes),
                },
            }
            incumbent = champions.get(model_name)
            incumbent_current_metrics: dict[str, Any] | None = None
            if incumbent is not None:
                incumbent_parameters = dict(incumbent.get("parameters", {}))
                incumbent_current_metrics = (
                    self._classification_metrics(incumbent_parameters, test_vectors, test_targets)
                    if kind == "logistic"
                    else self._regression_metrics(incumbent_parameters, test_vectors, test_targets)
                )
            champion, promotion_gate = self._promotion_gate(
                model_name=model_name,
                candidate_metrics=metrics,
                incumbent_metrics=incumbent_current_metrics,
            )
            candidate_quality = self._quality(model_name, metrics)
            status = "champion" if champion else "rejected"
            promotion_reason = (
                "initial_semantically_valid_champion"
                if incumbent is None
                else f"same_shadow_quality_improved_by_{promotion_gate['quality_delta_same_shadow']:.6f}"
                if champion
                else (
                    f"rejected_same_shadow_required_{promotion_gate['minimum_quality_improvement']:.3f}_"
                    f"actual_{promotion_gate['quality_delta_same_shadow']:.6f}_guardrails_{str(promotion_gate['guardrails_met']).lower()}"
                )
            )
            model["metrics"]["incumbent_same_shadow"] = incumbent_current_metrics
            model["metrics"]["promotion_gate"] = promotion_gate
            model["promotion_reason"] = promotion_reason
            self.repository.register_model(model, status=status)
            if champion:
                promoted.append(model_name)
            candidates.append({**model, "promoted": champion, "quality": round(candidate_quality, 6), "status": status})
        return {"trained": True, "training_rows": len(outcomes), "promoted": promoted, "candidates": candidates}

    def synchronize_prediction_feedback(self) -> int:
        outcomes = self._ordered_outcomes(self.repository.learning_outcomes())
        by_lot = {str(outcome["lot_id"]): outcome for outcome in outcomes}
        next_by_lot = {str(current["lot_id"]): nxt for current, nxt in zip(outcomes[:-1], outcomes[1:], strict=True)}
        evaluated = 0
        for prediction in self.repository.unevaluated_predictions():
            lot_id = str(prediction["lot_id"])
            target = str(prediction["target"])
            current = by_lot.get(lot_id)
            if current is None:
                continue
            actual: float | None = None
            if target == "final_yield" and current.get("yield_value") is not None:
                actual = float(current["yield_value"])
            elif target == "final_excursion_probability":
                actual = 1.0 if current.get("physical_excursion") else 0.0
            elif target == "next_lot_excursion_alarm_probability" and lot_id in next_by_lot:
                nxt = next_by_lot[lot_id]
                actual = 1.0 if nxt.get("physical_excursion") or nxt.get("equipment_alarm") else 0.0
            elif target == "next_lot_maintenance_attention_probability" and lot_id in next_by_lot:
                actual = 1.0 if next_by_lot[lot_id].get("maintenance_attention") else 0.0
            if actual is None:
                continue
            predicted = float(prediction["score"])
            self.repository.append_prediction_feedback(
                {
                    "prediction_id": prediction["prediction_id"],
                    "target": target,
                    "predicted": predicted,
                    "actual": actual,
                    "absolute_error": abs(predicted - actual),
                }
            )
            evaluated += 1
        return evaluated

    @staticmethod
    def _psi(baseline_values: list[float], recent_values: list[float], bins: int = 5) -> float:
        score = 0.0
        for index in range(bins):
            low = index / bins
            high = (index + 1) / bins
            baseline_count = sum(low <= value < high or (index == bins - 1 and value == 1.0) for value in baseline_values)
            recent_count = sum(low <= value < high or (index == bins - 1 and value == 1.0) for value in recent_values)
            baseline_share = max(1e-4, baseline_count / max(1, len(baseline_values)))
            recent_share = max(1e-4, recent_count / max(1, len(recent_values)))
            score += (recent_share - baseline_share) * math.log(recent_share / baseline_share)
        return max(0.0, score)

    def drift_status(self) -> dict[str, Any]:
        outcomes = self._ordered_outcomes(self.repository.learning_outcomes())
        if len(outcomes) < 24:
            return {"status": "warming", "score": 0.0, "recent_rows": min(12, len(outcomes)), "baseline_rows": max(0, len(outcomes) - 12), "drift_types": []}
        baseline = outcomes[-24:-12]
        recent = outcomes[-12:]
        baseline_vectors = self._vectors(baseline)
        recent_vectors = self._vectors(recent)
        shifts = []
        for index, feature in enumerate(FEATURE_NAMES):
            baseline_values = [vector[index] for vector in baseline_vectors]
            recent_values = [vector[index] for vector in recent_vectors]
            baseline_mean = sum(baseline_values) / len(baseline_values)
            recent_mean = sum(recent_values) / len(recent_values)
            shifts.append(
                {
                    "feature": feature,
                    "mean_shift": round(abs(recent_mean - baseline_mean), 6),
                    "psi": round(self._psi(baseline_values, recent_values), 6),
                }
            )
        score = max((item["psi"] for item in shifts), default=0.0)
        return {
            "status": "drift" if score >= 0.25 else "watch" if score >= 0.10 else "stable",
            "score": round(score, 6),
            "recent_rows": 12,
            "baseline_rows": 12,
            "drift_types": ["feature_psi", "feature_mean_shift"],
            "top_shifts": sorted(shifts, key=lambda item: (-item["psi"], -item["mean_shift"]))[:4],
            "retraining_recommended": score >= 0.25,
        }

    def predict_snapshot(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        if snapshot.get("feature_set_version") != FEATURE_SET_VERSION or snapshot.get("prediction_cutoff") != PREDICTION_CUTOFF:
            return []
        champions = self.repository.champion_models()
        vector = [float(snapshot["features"].get(name, 0.0)) for name in FEATURE_NAMES]
        predictions: list[dict[str, Any]] = []
        target_names = {
            "final_yield_post_cmp": "final_yield",
            "final_excursion_post_cmp": "final_excursion_probability",
            "next_lot_excursion_alarm_risk": "next_lot_excursion_alarm_probability",
            "next_lot_maintenance_attention_risk": "next_lot_maintenance_attention_probability",
        }
        for model_name, target in target_names.items():
            model = champions.get(model_name)
            if model is None or model.get("feature_set_version") != FEATURE_SET_VERSION:
                continue
            score = self._predict(model["parameters"], vector)
            prediction = {
                "lot_id": snapshot["lot_id"],
                "model_name": model_name,
                "model_version": model["model_version"],
                "target": target,
                "score": round(score, 6),
                "risk_band": "HIGH" if target != "final_yield" and score >= 0.7 else "WATCH" if target != "final_yield" and score >= 0.4 else "NORMAL",
                "features": snapshot["features"],
                "feature_set_version": FEATURE_SET_VERSION,
                "prediction_cutoff": PREDICTION_CUTOFF,
                "source_event_time": snapshot["feature_timestamp"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "trained_model": True,
                "calibrated": model["parameters"].get("kind") == "online-logistic-sgd" and "temperature" in model["parameters"],
                "target_definition": model.get("target_definition"),
            }
            if target == "final_yield":
                radius = float(model.get("parameters", {}).get("interval_radius", 0.05))
                prediction["interval"] = [round(_clamp(score - radius), 6), round(_clamp(score + radius), 6)]
            predictions.append(prediction)
        return predictions

    def status(self) -> dict[str, Any]:
        champions = self.semantic_v2_champions(self.repository.champion_models())
        outcomes = self._ordered_outcomes(self.repository.learning_outcomes())
        predictions = self.semantic_v2_predictions(self.repository.latest_predictions(48))[:24]
        queue_status_reader = getattr(self.repository, "inference_queue_status", None)
        human_feedback_reader = getattr(self.repository, "human_feedback_summary", None)
        return {
            "schema_version": "fabops-continuous-intelligence-v2",
            "learning_enabled": True,
            "feedback_loop": "cutoff-features->future-outcome->retrain->shadow-test->champion->predict->feedback",
            "feature_set_version": FEATURE_SET_VERSION,
            "prediction_cutoff": PREDICTION_CUTOFF,
            "outcome_count": len(outcomes),
            "dataset_mix": self._dataset_mix(outcomes),
            "champions": champions,
            "latest_predictions": predictions,
            "feedback": self.repository.prediction_feedback_summary(),
            "human_feedback": (
                human_feedback_reader()
                if callable(human_feedback_reader)
                else {"total": 0, "by_type": {}, "training_policy": "persist-for-evaluation-and-curation-only", "automatic_retraining_from_clicks": False}
            ),
            "drift": self.drift_status(),
            "reports": self.repository.latest_intelligence_reports(12),
            "visualization_plans": self.repository.latest_visualization_plans(12),
            "inference_queue": queue_status_reader() if callable(queue_status_reader) else {},
        }
