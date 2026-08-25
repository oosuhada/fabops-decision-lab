from __future__ import annotations

import json
import os
import signal
import time
from threading import Event

from adapters.postgres import PostgresConfig, PostgresRepository
from services.decision import DecisionSupportService
from services.intelligence import build_live_decision_intelligence
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
    interval = max(10.0, float(os.getenv("FABOPS_INTELLIGENCE_INTERVAL_SECONDS", "30")))
    retrain_every = max(1, int(os.getenv("FABOPS_RETRAIN_EVERY_OUTCOMES", "6")))
    report_interval = max(120.0, float(os.getenv("FABOPS_LLM_REPORT_INTERVAL_SECONDS", "300")))
    report_case_limit = max(1, min(4, int(os.getenv("FABOPS_LLM_REPORT_CASE_LIMIT", "2"))))
    last_training_rows = 0
    prediction_keys: set[tuple[str, str, str]] = set()
    last_report_at: dict[str, float] = {}
    last_report_signature: dict[str, str] = {}
    while not stop_event.is_set():
        try:
            snapshots = service.lot_snapshots()
            completed = service.synchronize_outcomes(snapshots)
            feedback_evaluated = service.synchronize_prediction_feedback()
            outcome_count = len(repository.learning_outcomes())
            champions = repository.champion_models()
            champion_rows = max((int(model.get("training_rows", 0)) for model in champions.values()), default=0)
            drift = service.drift_status()
            should_train = outcome_count >= 12 and (not champions or outcome_count - max(last_training_rows, champion_rows) >= retrain_every or drift.get("status") == "drift")
            training = service.retrain() if should_train else {"trained": False, "reason": "cadence", "training_rows": outcome_count}
            if training.get("trained"):
                last_training_rows = outcome_count

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
            report_candidates: list[tuple[float, dict[str, object], list[dict[str, object]], str, dict[str, object]]] = []
            if cases:
                recent_cases = sorted(cases, key=lambda item: str(item.get("lot_id", "")), reverse=True)[:16]
                predictions_by_lot = repository.latest_predictions_for_lots([str(case["lot_id"]) for case in recent_cases])
                reports_by_case = repository.latest_intelligence_reports_for_cases([str(case["case_id"]) for case in recent_cases])
                for case in recent_cases:
                    case_predictions = list(predictions_by_lot.get(str(case["lot_id"]), []))
                    packet_seed = {
                        "case_id": case["case_id"],
                        "lot_id": case["lot_id"],
                        "classification": case["classification"],
                        "evidence": {
                            "anomaly_score": case.get("anomaly_score", 0.0),
                            "mean_yield": case.get("mean_yield"),
                            "affected_scope": case.get("affected_scope", {}),
                        },
                    }
                    existing_report = reports_by_case.get(str(case["case_id"]))
                    context = build_live_decision_intelligence(packet_seed, case_predictions, existing_report)
                    signature = material_signature(case, case_predictions)
                    report_candidates.append((float(context["priority_score"]), case, case_predictions, signature, context))

            due_candidates: list[tuple[float, dict[str, object], list[dict[str, object]], str, dict[str, object]]] = []
            now = time.monotonic()
            for candidate in sorted(report_candidates, key=lambda item: (-item[0], str(item[1].get("case_id", ""))))[:report_case_limit]:
                _priority, case, _predictions, signature, _context = candidate
                case_id = str(case["case_id"])
                signature_changed = last_report_signature.get(case_id) != signature
                interval_elapsed = now - last_report_at.get(case_id, 0.0) >= report_interval
                if signature_changed or interval_elapsed:
                    due_candidates.append(candidate)

            if due_candidates:
                runtime = build_database_readonly_runtime()
                try:
                    for _priority, case, case_predictions, signature, context in due_candidates:
                        case_id = str(case["case_id"])
                        plan = visualization_plan(case, case_predictions, signature)
                        repository.append_visualization_plan(plan)
                        packet = DecisionSupportService(runtime).packet(case_id)
                        packet["predictive_intelligence"] = {
                            item["target"]: {
                                "score": item["score"],
                                "model_version": item["model_version"],
                                "calibrated": item.get("calibrated", False),
                            }
                            for item in case_predictions
                        }
                        packet["live_decision_context"] = context
                        packet["evidence_refs"] = sorted(set(packet.get("evidence_refs", [])) | {f"prediction.{item['target']}" for item in case_predictions})
                        brief = narration.generate(packet, "engineer", intent="situation_update")
                        repository.append_intelligence_report(
                            {
                                "case_id": case_id,
                                "material_signature": signature,
                                "trigger_type": "periodic_risk_review" if last_report_signature.get(case_id) == signature else "material_intelligence_change",
                                "mode": brief.get("mode", "deterministic_fallback"),
                                "provider": brief.get("provider", "deterministic"),
                                "brief": brief,
                                "decision_context": context,
                                "visualization_plan": plan,
                            }
                        )
                        last_report_at[case_id] = now
                        last_report_signature[case_id] = signature
                finally:
                    close_graph = getattr(runtime.graph, "close", None)
                    if callable(close_graph):
                        close_graph()
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
                        "periodic_reports": len(due_candidates),
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
