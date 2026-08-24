from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from services.detection.service import DetectorConfig, SENSOR_INDEX, STEP_INDEX


PREDICTION_VERSION = "transparent-online-risk-v1.0.0"


class PredictiveIntelligenceService:
    """Explainable, non-trained forecasting baseline for the live portfolio.

    This intentionally does not claim calibrated probabilities. It turns recent
    sensor trend, EWMA deviation, volatility, current anomaly score, and yield gap
    into bounded risk scores so that FabOps has an operational predictive layer
    before a trained model is introduced.
    """

    def __init__(self, event_repository: Any, case_repository: Any) -> None:
        self.events = event_repository
        self.cases = case_repository
        self.detector_config = DetectorConfig.load()

    @staticmethod
    def _linear_slope(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        count = float(len(values))
        mean_x = (count - 1.0) / 2.0
        mean_y = sum(values) / count
        numerator = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
        denominator = sum((index - mean_x) ** 2 for index in range(len(values)))
        return numerator / denominator if denominator else 0.0

    @staticmethod
    def _volatility(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))

    def _expected(self, sensor: str, step: str) -> float:
        return 10.0 + SENSOR_INDEX.get(sensor, 0) * 5.0 + STEP_INDEX.get(step, 0) * 0.3

    def _sensor_forecasts(self) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        recent = getattr(self.events, "recent_measurement_events", None)
        stored_events = recent(768) if callable(recent) else self.events.all_events()
        for stored in stored_events:
            event = stored.event
            if event.get("event_type") != "process.measurement.recorded.v1":
                continue
            payload = event.get("payload", {})
            chamber_id = str(event.get("chamber_id") or "unknown")
            sensor = str(payload.get("sensor_name") or "unknown")
            grouped[(chamber_id, sensor)].append(event)

        forecasts: list[dict[str, Any]] = []
        for (chamber_id, sensor), records in grouped.items():
            window = records[-8:]
            values = [float(record["payload"]["value"]) for record in window]
            if not values:
                continue
            step = str(window[-1]["payload"].get("step_id") or "")
            expected = self._expected(sensor, step)
            slope = self._linear_slope(values)
            volatility = self._volatility(values)
            ewma = expected
            for value in values:
                ewma = self.detector_config.ewma_lambda * value + (1.0 - self.detector_config.ewma_lambda) * ewma
            deviation_ratio = abs(ewma - expected) / max(0.001, self.detector_config.ewma_delta)
            slope_ratio = abs(slope) / max(0.001, self.detector_config.ewma_delta)
            volatility_ratio = volatility / max(0.001, self.detector_config.shewhart_delta)
            risk_score = min(1.0, 0.62 * deviation_ratio + 0.28 * slope_ratio + 0.10 * volatility_ratio)
            forecasts.append(
                {
                    "chamber_id": chamber_id,
                    "sensor_name": sensor,
                    "step_id": step,
                    "observations": len(values),
                    "last_value": round(values[-1], 5),
                    "expected_value": round(expected, 5),
                    "ewma": round(ewma, 5),
                    "trend_per_measurement": round(slope, 5),
                    "volatility": round(volatility, 5),
                    "forecast_next": [round(values[-1] + slope * horizon, 5) for horizon in range(1, 4)],
                    "drift_direction": "up" if slope > 0.01 else "down" if slope < -0.01 else "stable",
                    "risk_score": round(risk_score, 5),
                    "risk_band": "HIGH" if risk_score >= 0.7 else "WATCH" if risk_score >= 0.4 else "NORMAL",
                    "latest_event_time": window[-1]["event_time"],
                }
            )
        return sorted(forecasts, key=lambda item: (-float(item["risk_score"]), str(item["chamber_id"]), str(item["sensor_name"])))

    def snapshot(self) -> dict[str, Any]:
        sensor_forecasts = self._sensor_forecasts()
        sensor_risk_by_chamber: dict[str, float] = defaultdict(float)
        for item in sensor_forecasts:
            chamber_id = str(item["chamber_id"])
            sensor_risk_by_chamber[chamber_id] = max(sensor_risk_by_chamber[chamber_id], float(item["risk_score"]))

        case_risks: list[dict[str, Any]] = []
        for case in self.cases.list_cases():
            mean_yield = case.get("mean_yield")
            yield_gap = max(0.0, 0.9 - float(mean_yield)) if mean_yield is not None else 0.0
            anomaly_component = min(1.0, float(case.get("anomaly_score", 0.0)) / 3.0)
            chamber_component = max(
                [sensor_risk_by_chamber.get(str(chamber), 0.0) for chamber in case.get("affected_scope", {}).get("chambers", [])]
                or [0.0]
            )
            yield_component = min(1.0, yield_gap / 0.3)
            risk_score = min(1.0, 0.45 * anomaly_component + 0.35 * yield_component + 0.20 * chamber_component)
            case_risks.append(
                {
                    "case_id": case["case_id"],
                    "lot_id": case["lot_id"],
                    "classification": case["classification"],
                    "risk_score": round(risk_score, 5),
                    "risk_band": "HIGH" if risk_score >= 0.7 else "WATCH" if risk_score >= 0.4 else "NORMAL",
                    "components": {
                        "anomaly": round(anomaly_component, 5),
                        "yield_gap": round(yield_component, 5),
                        "sensor_drift": round(chamber_component, 5),
                    },
                }
            )
        case_risks.sort(key=lambda item: (-float(item["risk_score"]), str(item["case_id"])))
        return {
            "schema_version": "fabops-predictive-intelligence-v1",
            "model": {
                "version": PREDICTION_VERSION,
                "kind": "transparent-online-baseline",
                "trained_model": False,
                "calibrated": False,
                "probability": False,
                "forecast_horizon_measurements": 3,
            },
            "top_sensor_forecasts": sensor_forecasts[:8],
            "case_risks": case_risks[:10],
        }

