from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from services.detection.service import DetectorConfig, SENSOR_INDEX, STEP_INDEX


FEATURE_NAMES = [
    "measurement_density",
    "mean_abs_deviation",
    "max_abs_deviation",
    "signal_volatility",
    "alarm_density",
    "maintenance_density",
    "chamber_breadth",
    "equipment_breadth",
    "process_progress",
    "tool_age_proxy",
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

    def build(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        if not events:
            raise ValueError("feature build requires events")
        lot_id = str(events[-1].get("lot_id") or "unknown")
        measurements = [event for event in events if event.get("event_type") == "process.measurement.recorded.v1"]
        values = [float(event.get("payload", {}).get("value", 0.0)) for event in measurements]
        deviations = [
            abs(float(event["payload"]["value"]) - self._expected(str(event["payload"].get("sensor_name", "")), str(event["payload"].get("step_id", ""))))
            for event in measurements
        ]
        alarms = [event for event in events if event.get("event_type") == "equipment.alarm.raised.v1"]
        maintenance = [event for event in events if event.get("event_type") == "maintenance.completed.v1"]
        inspections = [event for event in events if event.get("event_type") == "inspection.completed.v1"]
        process_completed = sum(event.get("event_type") == "process.completed.v1" for event in events)
        chambers = {str(event.get("chamber_id")) for event in events if event.get("chamber_id")}
        equipment = {str(event.get("equipment_id")) for event in events if event.get("equipment_id")}
        vector = [
            _clamp(len(measurements) / 32.0),
            _clamp((sum(deviations) / max(1, len(deviations))) / 3.0),
            _clamp((max(deviations) if deviations else 0.0) / 6.0),
            _clamp(self._volatility(values) / 4.0),
            _clamp(len(alarms) / 2.0),
            _clamp(len(maintenance) / 2.0),
            _clamp(len(chambers) / 5.0),
            _clamp(len(equipment) / 5.0),
            _clamp(process_completed / 5.0),
            _clamp((self._lot_index(lot_id) % 100) / 100.0),
        ]
        yields = [float(event["payload"]["yield"]) for event in inspections if event.get("payload", {}).get("yield") is not None]
        return {
            "lot_id": lot_id,
            "features": {name: round(vector[index], 6) for index, name in enumerate(FEATURE_NAMES)},
            "vector": vector,
            "yield_value": round(sum(yields) / len(yields), 6) if yields else None,
            "physical_excursion": bool(yields and (sum(yields) / len(yields)) < self.detector_config.excursion_yield_threshold),
            "equipment_alarm": bool(alarms),
            "maintenance_observed": bool(maintenance),
            "complete": bool(inspections),
            "latest_event_time": str(events[-1].get("event_time")),
        }


class ContinuousIntelligenceService:
    """Closes the live loop: outcomes -> retraining -> champion -> predictions."""

    def __init__(self, repository: Any) -> None:
        self.repository = repository
        self.features = FeatureBuilder()

    def lot_snapshots(self, recent_limit: int = 80, recovery_limit: int = 200) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        recent_reader = getattr(self.repository, "recent_lot_ids", None)
        recovery_reader = getattr(self.repository, "unlearned_completed_lot_ids", None)
        lot_event_reader = getattr(self.repository, "events_for_lots", None)
        if callable(recent_reader) and callable(recovery_reader) and callable(lot_event_reader):
            selected_lots = list(dict.fromkeys([
                *recovery_reader(recovery_limit),
                *recent_reader(recent_limit),
            ]))
            stored_events = lot_event_reader(selected_lots)
        else:
            stored_events = self.repository.all_events()
        for stored in stored_events:
            event = stored.event
            lot_id = event.get("lot_id")
            if lot_id:
                grouped[str(lot_id)].append(event)
        snapshots = [self.features.build(events) for _, events in sorted(grouped.items())]
        return snapshots

    def synchronize_outcomes(self, snapshots: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        completed = [snapshot for snapshot in (snapshots if snapshots is not None else self.lot_snapshots()) if snapshot["complete"]]
        existing = {str(item["lot_id"]): item for item in self.repository.learning_outcomes()}
        changed: list[dict[str, Any]] = []
        for snapshot in completed:
            outcome = {
                "lot_id": snapshot["lot_id"],
                "yield_value": snapshot["yield_value"],
                "physical_excursion": snapshot["physical_excursion"],
                "equipment_alarm": snapshot["equipment_alarm"],
                "maintenance_observed": snapshot["maintenance_observed"],
                "maintenance_need": bool(snapshot["maintenance_observed"] or snapshot["equipment_alarm"]),
                "features": snapshot["features"],
                "latest_event_time": snapshot["latest_event_time"],
            }
            previous = existing.get(str(snapshot["lot_id"]))
            if previous is not None and (
                previous.get("latest_event_time") == outcome["latest_event_time"]
                and previous.get("features") == outcome["features"]
                and previous.get("yield_value") == outcome["yield_value"]
                and bool(previous.get("physical_excursion")) == bool(outcome["physical_excursion"])
                and bool(previous.get("equipment_alarm")) == bool(outcome["equipment_alarm"])
                and bool(previous.get("maintenance_observed")) == bool(outcome["maintenance_observed"])
            ):
                continue
            self.repository.upsert_learning_outcome(outcome)
            changed.append(snapshot)
        return changed

    @staticmethod
    def _vectors(outcomes: list[dict[str, Any]]) -> list[list[float]]:
        return [[float(outcome["features"].get(name, 0.0)) for name in FEATURE_NAMES] for outcome in outcomes]

    @staticmethod
    def _fit_linear(vectors: list[list[float]], targets: list[float], *, epochs: int = 180, rate: float = 0.055) -> dict[str, Any]:
        weights = [0.0] * len(FEATURE_NAMES)
        bias = sum(targets) / max(1, len(targets))
        for _ in range(epochs):
            for vector, target in zip(vectors, targets):
                prediction = _clamp(bias + sum(weight * value for weight, value in zip(weights, vector)))
                error = prediction - target
                bias -= rate * error
                for index, value in enumerate(vector):
                    weights[index] -= rate * error * value
        return {"weights": weights, "bias": bias, "kind": "online-linear-sgd"}

    @staticmethod
    def _fit_logistic(vectors: list[list[float]], targets: list[float], *, epochs: int = 220, rate: float = 0.07) -> dict[str, Any]:
        weights = [0.0] * len(FEATURE_NAMES)
        positive_rate = (sum(targets) + 1.0) / (len(targets) + 2.0)
        bias = math.log(positive_rate / max(1e-6, 1.0 - positive_rate))
        for _ in range(epochs):
            for vector, target in zip(vectors, targets):
                prediction = _sigmoid(bias + sum(weight * value for weight, value in zip(weights, vector)))
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
            brier = sum((prediction - target) ** 2 for prediction, target in zip(predictions, targets)) / len(targets)
            if brier < best_brier:
                best_brier = brier
                best_temperature = temperature
        return {**parameters, "temperature": best_temperature}

    @staticmethod
    def _predict(parameters: dict[str, Any], vector: list[float]) -> float:
        raw = float(parameters.get("bias", 0.0)) + sum(
            float(weight) * value for weight, value in zip(parameters.get("weights", []), vector)
        )
        if parameters.get("kind") == "online-logistic-sgd":
            return _sigmoid(raw / max(0.1, float(parameters.get("temperature", 1.0))))
        return _clamp(raw)

    @classmethod
    def _metrics(cls, parameters: dict[str, Any], vectors: list[list[float]], targets: list[float]) -> dict[str, float]:
        if not vectors:
            return {"mae": 1.0, "brier": 1.0, "accuracy": 0.0}
        predictions = [cls._predict(parameters, vector) for vector in vectors]
        mae = sum(abs(prediction - target) for prediction, target in zip(predictions, targets)) / len(targets)
        brier = sum((prediction - target) ** 2 for prediction, target in zip(predictions, targets)) / len(targets)
        accuracy = sum((prediction >= 0.5) == bool(target) for prediction, target in zip(predictions, targets)) / len(targets)
        return {"mae": round(mae, 6), "brier": round(brier, 6), "accuracy": round(accuracy, 6)}

    @staticmethod
    def _version(model_name: str, rows: int, outcomes: list[dict[str, Any]]) -> str:
        fingerprint = hashlib.sha256(
            json.dumps([(outcome["lot_id"], outcome.get("yield_value"), outcome.get("physical_excursion")) for outcome in outcomes], sort_keys=True).encode()
        ).hexdigest()[:10]
        return f"{model_name}-r{rows}-{fingerprint}"

    @staticmethod
    def _quality(model_name: str, metrics: dict[str, Any]) -> float:
        if model_name == "yield_forecast":
            return 1.0 - float(metrics.get("mae", 1.0))
        return 1.0 - float(metrics.get("brier", 1.0))

    def retrain(self, *, minimum_rows: int = 12) -> dict[str, Any]:
        outcomes = self.repository.learning_outcomes()
        if len(outcomes) < minimum_rows:
            return {"trained": False, "reason": "insufficient_outcomes", "training_rows": len(outcomes)}
        champions = self.repository.champion_models()
        definitions = [
            ("yield_forecast", "linear", outcomes, [float(outcome.get("yield_value") or 0.0) for outcome in outcomes], "same-lot-final-yield"),
            ("excursion_risk", "logistic", outcomes, [1.0 if outcome.get("physical_excursion") else 0.0 for outcome in outcomes], "same-lot-excursion"),
            (
                "future_failure", "logistic", outcomes[:-1],
                [1.0 if next_outcome.get("physical_excursion") or next_outcome.get("equipment_alarm") else 0.0 for next_outcome in outcomes[1:]],
                "next-lot-failure",
            ),
            (
                "maintenance_risk", "logistic", outcomes[:-1],
                [1.0 if next_outcome.get("maintenance_need") else 0.0 for next_outcome in outcomes[1:]],
                "next-lot-maintenance-need",
            ),
        ]
        promoted: list[str] = []
        candidates: list[dict[str, Any]] = []
        for model_name, kind, model_outcomes, targets, horizon in definitions:
            vectors = self._vectors(model_outcomes)
            if len(vectors) < minimum_rows - 1:
                continue
            split = max(8, int(len(vectors) * 0.8))
            split = min(split, len(vectors) - 1)
            train_vectors, validation_vectors = vectors[:split], vectors[split:]
            train_targets, validation_targets = targets[:split], targets[split:]
            parameters = self._fit_linear(train_vectors, train_targets) if kind == "linear" else self._fit_logistic(train_vectors, train_targets)
            if kind == "logistic":
                parameters = self._calibrate_temperature(parameters, validation_vectors, validation_targets)
            metrics = self._metrics(parameters, validation_vectors, validation_targets)
            version = self._version(model_name, len(model_outcomes), model_outcomes)
            model = {
                "model_name": model_name,
                "model_version": version,
                "training_rows": len(model_outcomes),
                "feature_schema": FEATURE_NAMES,
                "parameters": parameters,
                "metrics": {**metrics, "validation_rows": len(validation_targets), "trained_rows": len(train_targets), "horizon": horizon},
            }
            incumbent = champions.get(model_name)
            candidate_quality = self._quality(model_name, metrics)
            incumbent_quality = self._quality(model_name, incumbent.get("metrics", {})) if incumbent else -1.0
            champion = incumbent is None or candidate_quality >= incumbent_quality - 0.002
            self.repository.register_model(model, champion=champion)
            if champion:
                promoted.append(model_name)
            candidates.append({**model, "promoted": champion, "quality": round(candidate_quality, 6)})
        return {"trained": True, "training_rows": len(outcomes), "promoted": promoted, "candidates": candidates}

    def synchronize_prediction_feedback(self) -> int:
        outcomes = self.repository.learning_outcomes()
        by_lot = {str(outcome["lot_id"]): outcome for outcome in outcomes}
        ordered = sorted(outcomes, key=lambda item: FeatureBuilder._lot_index(str(item["lot_id"])))
        next_by_lot = {str(current["lot_id"]): nxt for current, nxt in zip(ordered, ordered[1:])}
        evaluated = 0
        for prediction in self.repository.unevaluated_predictions():
            lot_id = str(prediction["lot_id"])
            target = str(prediction["target"])
            current = by_lot.get(lot_id)
            if current is None:
                continue
            actual: float | None = None
            if target == "yield" and current.get("yield_value") is not None:
                actual = float(current["yield_value"])
            elif target == "excursion_probability":
                actual = 1.0 if current.get("physical_excursion") else 0.0
            elif target == "future_failure_probability" and lot_id in next_by_lot:
                nxt = next_by_lot[lot_id]
                actual = 1.0 if nxt.get("physical_excursion") or nxt.get("equipment_alarm") else 0.0
            elif target == "maintenance_probability" and lot_id in next_by_lot:
                actual = 1.0 if next_by_lot[lot_id].get("maintenance_need") else 0.0
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

    def drift_status(self) -> dict[str, Any]:
        outcomes = self.repository.learning_outcomes()
        if len(outcomes) < 24:
            return {"status": "warming", "score": 0.0, "recent_rows": min(12, len(outcomes)), "baseline_rows": max(0, len(outcomes) - 12)}
        baseline = outcomes[-24:-12]
        recent = outcomes[-12:]
        baseline_vectors = self._vectors(baseline)
        recent_vectors = self._vectors(recent)
        shifts = []
        for index, feature in enumerate(FEATURE_NAMES):
            baseline_mean = sum(vector[index] for vector in baseline_vectors) / len(baseline_vectors)
            recent_mean = sum(vector[index] for vector in recent_vectors) / len(recent_vectors)
            shifts.append({"feature": feature, "shift": round(abs(recent_mean - baseline_mean), 6)})
        score = sum(item["shift"] for item in shifts) / len(shifts)
        return {"status": "drift" if score >= 0.12 else "stable", "score": round(score, 6), "recent_rows": 12, "baseline_rows": 12, "top_shifts": sorted(shifts, key=lambda item: -item["shift"])[:4]}

    def predict_snapshot(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        champions = self.repository.champion_models()
        vector = [float(snapshot["features"].get(name, 0.0)) for name in FEATURE_NAMES]
        predictions: list[dict[str, Any]] = []
        target_names = {
            "yield_forecast": "yield",
            "excursion_risk": "excursion_probability",
            "future_failure": "future_failure_probability",
            "maintenance_risk": "maintenance_probability",
        }
        for model_name, target in target_names.items():
            model = champions.get(model_name)
            if model is None:
                continue
            score = self._predict(model["parameters"], vector)
            prediction = {
                "lot_id": snapshot["lot_id"],
                "model_name": model_name,
                "model_version": model["model_version"],
                "target": target,
                "score": round(score, 6),
                "risk_band": "HIGH" if target != "yield" and score >= 0.7 else "WATCH" if target != "yield" and score >= 0.4 else "NORMAL",
                "features": snapshot["features"],
                "source_event_time": snapshot["latest_event_time"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "trained_model": True,
                "calibrated": model["parameters"].get("kind") == "online-logistic-sgd" and "temperature" in model["parameters"],
            }
            if target == "yield":
                residual = float(model.get("metrics", {}).get("mae", 0.05))
                prediction["interval"] = [round(_clamp(score - residual), 6), round(_clamp(score + residual), 6)]
            predictions.append(prediction)
        return predictions

    def status(self) -> dict[str, Any]:
        champions = self.repository.champion_models()
        outcomes = self.repository.learning_outcomes()
        predictions = self.repository.latest_predictions(24)
        return {
            "schema_version": "fabops-continuous-intelligence-v1",
            "learning_enabled": True,
            "feedback_loop": "outcome->retrain->champion->predict->outcome",
            "outcome_count": len(outcomes),
            "champions": champions,
            "latest_predictions": predictions,
            "feedback": self.repository.prediction_feedback_summary(),
            "drift": self.drift_status(),
            "reports": self.repository.latest_intelligence_reports(8),
            "visualization_plans": self.repository.latest_visualization_plans(8),
        }

