from __future__ import annotations

import json
import os
import signal
import time
from threading import Event

from adapters.postgres import PostgresConfig, PostgresRepository
from services.decision import DecisionSupportService
from services.intelligence.planner import material_signature, visualization_plan
from services.intelligence.service import ContinuousIntelligenceService
from services.narration import NarrationService
from systems.api.runtime import build_database_readonly_runtime


def main() -> None:
    dsn = os.getenv("FABOPS_POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("FABOPS_POSTGRES_DSN is required")
    stop_event = Event()

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    repository = PostgresRepository(PostgresConfig(dsn))
    service = ContinuousIntelligenceService(repository)
    narration = NarrationService()
    interval = max(3.0, float(os.getenv("FABOPS_INTELLIGENCE_INTERVAL_SECONDS", "12")))
    retrain_every = max(1, int(os.getenv("FABOPS_RETRAIN_EVERY_OUTCOMES", "6")))
    last_training_rows = 0
    prediction_keys: set[tuple[str, str, str]] = set()
    while not stop_event.is_set():
        try:
            completed = service.synchronize_outcomes()
            feedback_evaluated = service.synchronize_prediction_feedback()
            outcome_count = len(repository.learning_outcomes())
            champions = repository.champion_models()
            champion_rows = max((int(model.get("training_rows", 0)) for model in champions.values()), default=0)
            drift = service.drift_status()
            should_train = outcome_count >= 12 and (not champions or outcome_count - max(last_training_rows, champion_rows) >= retrain_every or drift.get("status") == "drift")
            training = service.retrain() if should_train else {"trained": False, "reason": "cadence", "training_rows": outcome_count}
            if training.get("trained"):
                last_training_rows = outcome_count

            snapshots = service.lot_snapshots()
            latest = snapshots[-1] if snapshots else None
            latest_predictions: list[dict[str, object]] = []
            if latest is not None:
                latest_predictions = service.predict_snapshot(latest)
                for prediction in latest_predictions:
                    key = (str(prediction["lot_id"]), str(prediction["model_name"]), str(prediction["model_version"]))
                    if key not in prediction_keys:
                        repository.append_prediction(prediction)
                        prediction_keys.add(key)

            cases = repository.list_cases()
            if cases:
                latest_case = max(cases, key=lambda item: str(item.get("lot_id", "")))
                case_predictions = [item for item in service.predict_snapshot(next((snapshot for snapshot in snapshots if snapshot["lot_id"] == latest_case["lot_id"]), latest or snapshots[-1]))] if snapshots else []
                signature = material_signature(latest_case, case_predictions)
                plan = visualization_plan(latest_case, case_predictions, signature)
                plan_added = repository.append_visualization_plan(plan)
                if plan_added:
                    runtime = build_database_readonly_runtime()
                    try:
                        packet = DecisionSupportService(runtime).packet(str(latest_case["case_id"]))
                        packet["predictive_intelligence"] = {
                            item["target"]: {
                                "score": item["score"],
                                "model_version": item["model_version"],
                                "calibrated": item.get("calibrated", False),
                            }
                            for item in case_predictions
                        }
                        packet["evidence_refs"] = sorted(set(packet.get("evidence_refs", [])) | {f"prediction.{item['target']}" for item in case_predictions})
                        brief = narration.generate(packet, "engineer", intent="engineer_checklist")
                        repository.append_intelligence_report(
                            {
                                "case_id": latest_case["case_id"],
                                "material_signature": signature,
                                "trigger_type": "material_intelligence_change",
                                "mode": brief.get("mode", "deterministic_fallback"),
                                "provider": brief.get("provider", "deterministic"),
                                "brief": brief,
                                "visualization_plan": plan,
                            }
                        )
                    finally:
                        runtime.graph.close()
            print(
                json.dumps(
                    {
                        "service": "fabops-intelligence-worker",
                        "outcomes": outcome_count,
                        "completed_snapshots": len(completed),
                        "trained": bool(training.get("trained")),
                        "feedback_evaluated": feedback_evaluated,
                        "drift": drift.get("status"),
                        "champions": sorted(repository.champion_models()),
                        "latest_lot": latest.get("lot_id") if latest else None,
                        "predictions": len(latest_predictions),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - long-lived worker reports and retries
            print(json.dumps({"service": "fabops-intelligence-worker", "error": type(exc).__name__, "detail": str(exc)[:240]}), flush=True)
        stop_event.wait(interval)


if __name__ == "__main__":
    main()
