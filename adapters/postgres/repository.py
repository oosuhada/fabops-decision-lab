from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from services.ingestion.ports import QuarantinedEvent, StoredEvent

_ACTIVE_CONNECTION: ContextVar[Connection[Any] | None] = ContextVar("fabops_postgres_connection", default=None)


@dataclass(frozen=True)
class PostgresConfig:
    dsn: str


class PostgresRepository:
    """PostgreSQL source-of-truth adapter for events, cases, audit, outbox and recovery checkpoints."""

    def __init__(self, config: PostgresConfig) -> None:
        self.config = config

    @contextmanager
    def transaction(self) -> Iterator[Connection[Any]]:
        active = _ACTIVE_CONNECTION.get()
        if active is not None:
            yield active
            return
        with psycopg.connect(self.config.dsn, row_factory=dict_row) as connection:
            token = _ACTIVE_CONNECTION.set(connection)
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                _ACTIVE_CONNECTION.reset(token)

    @contextmanager
    def _connection(self) -> Iterator[Connection[Any]]:
        active = _ACTIVE_CONNECTION.get()
        if active is not None:
            yield active
            return
        with self.transaction() as connection:
            yield connection

    def healthcheck(self) -> bool:
        try:
            with self._connection() as connection:
                row = connection.execute("SELECT 1 AS ok").fetchone()
            return bool(row and row["ok"] == 1)
        except psycopg.Error:
            return False

    def reserve_event_id(self, event_id: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "INSERT INTO fabops_event_reservations(event_id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING event_id",
                (event_id,),
            ).fetchone()
        return row is not None

    def append_event(self, event: dict[str, Any], delivery_status: str) -> StoredEvent:
        payload = event.get("payload", {})
        with self._connection() as connection:
            row = connection.execute(
                """
                INSERT INTO fabops_event_log(
                    event_id, event_type, event_time, ingested_at, trace_id, lot_id,
                    equipment_id, chamber_id, schema_version, delivery_status, envelope
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING sequence
                """,
                (
                    event["event_id"],
                    event["event_type"],
                    event["event_time"],
                    event.get("ingested_at", event["event_time"]),
                    event.get("trace_id"),
                    event.get("lot_id"),
                    event.get("equipment_id"),
                    event.get("chamber_id"),
                    int(event.get("schema_version", 1)),
                    delivery_status,
                    Jsonb(event),
                ),
            ).fetchone()
            if event["event_type"] == "process.measurement.recorded.v1":
                connection.execute(
                    """
                    INSERT INTO fabops_measurements(
                        event_id, lot_id, process_run_id, step_id, equipment_id, chamber_id,
                        sensor_name, value, unit
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (
                        event["event_id"],
                        event["lot_id"],
                        payload["process_run_id"],
                        payload["step_id"],
                        event["equipment_id"],
                        event["chamber_id"],
                        payload["sensor_name"],
                        float(payload["value"]),
                        payload["unit"],
                    ),
                )
        if row is None:
            raise RuntimeError("event insert did not return a sequence")
        return StoredEvent(deepcopy(event), delivery_status, int(row["sequence"]))

    def all_events(self) -> list[StoredEvent]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT sequence, envelope, delivery_status FROM fabops_event_log ORDER BY sequence"
            ).fetchall()
        return [StoredEvent(deepcopy(row["envelope"]), str(row["delivery_status"]), int(row["sequence"])) for row in rows]

    def events_after(self, sequence: int, limit: int = 5000) -> list[StoredEvent]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT sequence, envelope, delivery_status
                FROM fabops_event_log
                WHERE sequence > %s
                ORDER BY sequence
                LIMIT %s
                """,
                (int(sequence), int(limit)),
            ).fetchall()
        return [StoredEvent(deepcopy(row["envelope"]), str(row["delivery_status"]), int(row["sequence"])) for row in rows]

    def event_count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT count(*) AS count FROM fabops_event_log").fetchone()
        return int(row["count"])

    def latest_event(self) -> StoredEvent | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT sequence, envelope, delivery_status FROM fabops_event_log ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return StoredEvent(deepcopy(row["envelope"]), str(row["delivery_status"]), int(row["sequence"]))

    def recent_measurement_events(self, limit: int = 512) -> list[StoredEvent]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT sequence, envelope, delivery_status
                FROM fabops_event_log
                WHERE event_type = 'process.measurement.recorded.v1'
                ORDER BY sequence DESC
                LIMIT %s
                """,
                (int(limit),),
            ).fetchall()
        rows.reverse()
        return [StoredEvent(deepcopy(row["envelope"]), str(row["delivery_status"]), int(row["sequence"])) for row in rows]

    def recent_lot_ids(self, limit: int = 250) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT lot_id, max(sequence) AS latest_sequence
                FROM fabops_event_log
                WHERE lot_id IS NOT NULL
                GROUP BY lot_id
                ORDER BY latest_sequence DESC
                LIMIT %s
                """,
                (int(limit),),
            ).fetchall()
        return [str(row["lot_id"]) for row in rows]

    def unlearned_completed_lot_ids(self, limit: int = 200) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT e.lot_id, min(e.sequence) AS first_sequence
                FROM fabops_event_log e
                LEFT JOIN fabops_learning_outcomes o ON o.lot_id = e.lot_id
                WHERE e.event_type = 'inspection.completed.v1'
                  AND e.lot_id IS NOT NULL
                  AND o.lot_id IS NULL
                GROUP BY e.lot_id
                ORDER BY first_sequence
                LIMIT %s
                """,
                (int(limit),),
            ).fetchall()
        return [str(row["lot_id"]) for row in rows]

    def events_for_lots(self, lot_ids: list[str]) -> list[StoredEvent]:
        if not lot_ids:
            return []
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT sequence, envelope, delivery_status
                FROM fabops_event_log
                WHERE lot_id = ANY(%s)
                ORDER BY sequence
                """,
                (lot_ids,),
            ).fetchall()
        return [StoredEvent(deepcopy(row["envelope"]), str(row["delivery_status"]), int(row["sequence"])) for row in rows]

    def delivery_status_counts(self) -> dict[str, int]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT delivery_status, count(*) AS count FROM fabops_event_log GROUP BY delivery_status"
            ).fetchall()
        result = {"on_time": 0, "late": 0, "out_of_order": 0}
        for row in rows:
            result[str(row["delivery_status"])] = int(row["count"])
        return result

    def append_outbox(self, topic: str, payload: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute("INSERT INTO fabops_outbox(topic, payload) VALUES (%s, %s)", (topic, Jsonb(payload)))

    def outbox(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT outbox_id, topic, payload, published_at FROM fabops_outbox ORDER BY outbox_id"
            ).fetchall()
        return [
            {
                "sequence": int(row["outbox_id"]),
                "topic": str(row["topic"]),
                "payload": deepcopy(row["payload"]),
                "published": row["published_at"] is not None,
            }
            for row in rows
        ]

    def set_checkpoint(self, consumer: str, sequence: int) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO fabops_consumer_checkpoint(consumer, source_sequence)
                VALUES (%s, %s)
                ON CONFLICT (consumer) DO UPDATE
                SET source_sequence = EXCLUDED.source_sequence, updated_at = now()
                """,
                (consumer, sequence),
            )

    def checkpoint(self, consumer: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT source_sequence FROM fabops_consumer_checkpoint WHERE consumer = %s",
                (consumer,),
            ).fetchone()
        return int(row["source_sequence"]) if row else 0

    def upsert_case(self, case: dict[str, Any]) -> bool:
        with self._connection() as connection:
            inserted = connection.execute(
                """
                INSERT INTO fabops_cases(case_id, lot_id, classification, state, anomaly_score, detector_version, case_document)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (case_id) DO NOTHING
                RETURNING case_id
                """,
                (
                    case["case_id"],
                    case["lot_id"],
                    case["classification"],
                    case["state"],
                    float(case["anomaly_score"]),
                    case["detector_version"],
                    Jsonb(case),
                ),
            ).fetchone()
            created = inserted is not None
            if not created:
                connection.execute(
                    """
                    UPDATE fabops_cases
                    SET lot_id = %s, classification = %s, state = %s, anomaly_score = %s,
                        detector_version = %s, case_document = %s, updated_at = now()
                    WHERE case_id = %s
                    """,
                    (
                        case["lot_id"],
                        case["classification"],
                        case["state"],
                        float(case["anomaly_score"]),
                        case["detector_version"],
                        Jsonb(case),
                        case["case_id"],
                    ),
                )
        return created

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT case_document FROM fabops_cases WHERE case_id = %s", (case_id,)).fetchone()
        return deepcopy(row["case_document"]) if row else None

    def list_cases(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT case_document FROM fabops_cases ORDER BY case_id").fetchall()
        return [deepcopy(row["case_document"]) for row in rows]

    def overview_case_window(self, limit: int = 120) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), 500))
        with self._connection() as connection:
            summary = connection.execute(
                """
                SELECT
                    count(*) AS total_cases,
                    count(*) FILTER (WHERE state <> 'closed') AS active_cases,
                    count(*) FILTER (WHERE classification = 'physical_excursion') AS physical_excursions,
                    count(*) FILTER (WHERE classification = 'sensor_bias_suspected') AS sensor_bias_cases,
                    count(*) FILTER (WHERE classification = 'data_quality_incident') AS data_quality_cases
                FROM fabops_cases
                """
            ).fetchone()
            rows = connection.execute(
                """
                SELECT case_document
                FROM fabops_cases
                ORDER BY lot_id DESC, updated_at DESC, case_id DESC
                LIMIT %s
                """,
                (bounded_limit,),
            ).fetchall()
        return {
            "cases": [deepcopy(row["case_document"]) for row in rows],
            "total_cases": int(summary["total_cases"] if summary else 0),
            "metrics": {
                "active_cases": int(summary["active_cases"] if summary else 0),
                "physical_excursions": int(summary["physical_excursions"] if summary else 0),
                "sensor_bias_cases": int(summary["sensor_bias_cases"] if summary else 0),
                "data_quality_cases": int(summary["data_quality_cases"] if summary else 0),
            },
        }

    def append_audit(self, record: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO fabops_decision_audit(case_id, event_type, actor_id, record) VALUES (%s, %s, %s, %s)",
                (record["case_id"], record.get("event", "unknown"), record.get("actor_id"), Jsonb(record)),
            )

    def audit_log(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT audit_sequence, record FROM fabops_decision_audit ORDER BY audit_sequence"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            record = deepcopy(row["record"])
            record["audit_sequence"] = int(row["audit_sequence"])
            result.append(record)
        return result

    def audit_for_case(self, case_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT audit_sequence, record
                FROM fabops_decision_audit
                WHERE case_id = %s
                ORDER BY audit_sequence
                """,
                (case_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            record = deepcopy(row["record"])
            record["audit_sequence"] = int(row["audit_sequence"])
            result.append(record)
        return result

    def related_cases(self, classification: str, exclude_case_id: str, limit: int = 3) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT case_document
                FROM fabops_cases
                WHERE classification = %s AND case_id <> %s
                ORDER BY lot_id DESC, updated_at DESC
                LIMIT %s
                """,
                (classification, exclude_case_id, max(1, int(limit))),
            ).fetchall()
        return [deepcopy(row["case_document"]) for row in rows]

    def put(self, raw_event: dict[str, Any], reason: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO fabops_quarantine(raw_event, reason) VALUES (%s, %s)",
                (Jsonb(raw_event), reason),
            )

    def all(self) -> list[QuarantinedEvent]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT raw_event, reason FROM fabops_quarantine ORDER BY quarantine_id"
            ).fetchall()
        return [QuarantinedEvent(deepcopy(row["raw_event"]), str(row["reason"])) for row in rows]

    def counts(self) -> dict[str, int]:
        tables = {
            "events": "fabops_event_log",
            "cases": "fabops_cases",
            "audit": "fabops_decision_audit",
            "outbox": "fabops_outbox",
            "quarantine": "fabops_quarantine",
        }
        result: dict[str, int] = {}
        with self._connection() as connection:
            for name, table in tables.items():
                row = connection.execute(f"SELECT count(*) AS count FROM {table}").fetchone()
                result[name] = int(row["count"])
        return result

    def upsert_learning_outcome(self, outcome: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO fabops_learning_outcomes(
                    lot_id, yield_value, physical_excursion, equipment_alarm,
                    maintenance_observed, features, outcome_document
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (lot_id) DO UPDATE SET
                    yield_value = EXCLUDED.yield_value,
                    physical_excursion = EXCLUDED.physical_excursion,
                    equipment_alarm = EXCLUDED.equipment_alarm,
                    maintenance_observed = EXCLUDED.maintenance_observed,
                    features = EXCLUDED.features,
                    outcome_document = EXCLUDED.outcome_document,
                    updated_at = now()
                """,
                (
                    outcome["lot_id"], outcome.get("yield_value"), bool(outcome["physical_excursion"]),
                    bool(outcome["equipment_alarm"]), bool(outcome["maintenance_observed"]),
                    Jsonb(outcome["features"]), Jsonb(outcome),
                ),
            )

    def learning_outcomes(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT outcome_document FROM fabops_learning_outcomes ORDER BY updated_at, lot_id"
            ).fetchall()
        return [deepcopy(row["outcome_document"]) for row in rows]

    def register_model(self, model: dict[str, Any], *, status: str) -> None:
        if status not in {"candidate", "champion", "rejected"}:
            raise ValueError(f"unsupported model registry status: {status}")
        with self._connection() as connection:
            if status == "champion":
                connection.execute(
                    "UPDATE fabops_model_registry SET status = 'retired' WHERE model_name = %s AND status = 'champion'",
                    (model["model_name"],),
                )
            connection.execute(
                """
                INSERT INTO fabops_model_registry(
                    model_name, model_version, status, training_rows, feature_schema,
                    parameters, metrics, feature_set_version, prediction_cutoff,
                    training_window, calibration_window, test_window, target_definition,
                    dataset_fingerprint, code_git_sha, simulator_regime, promotion_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (model_name, model_version) DO UPDATE SET
                    status = EXCLUDED.status,
                    training_rows = EXCLUDED.training_rows,
                    feature_schema = EXCLUDED.feature_schema,
                    parameters = EXCLUDED.parameters,
                    metrics = EXCLUDED.metrics,
                    feature_set_version = EXCLUDED.feature_set_version,
                    prediction_cutoff = EXCLUDED.prediction_cutoff,
                    training_window = EXCLUDED.training_window,
                    calibration_window = EXCLUDED.calibration_window,
                    test_window = EXCLUDED.test_window,
                    target_definition = EXCLUDED.target_definition,
                    dataset_fingerprint = EXCLUDED.dataset_fingerprint,
                    code_git_sha = EXCLUDED.code_git_sha,
                    simulator_regime = EXCLUDED.simulator_regime,
                    promotion_reason = EXCLUDED.promotion_reason,
                    trained_at = now()
                """,
                (
                    model["model_name"], model["model_version"], status,
                    int(model["training_rows"]), Jsonb(model["feature_schema"]), Jsonb(model["parameters"]),
                    Jsonb(model["metrics"]), model.get("feature_set_version"), model.get("prediction_cutoff"),
                    Jsonb(model.get("training_window", {})), Jsonb(model.get("calibration_window", {})),
                    Jsonb(model.get("test_window", {})), model.get("target_definition"),
                    model.get("dataset_fingerprint"), model.get("code_git_sha"), model.get("simulator_regime"),
                    model.get("promotion_reason"),
                ),
            )

    def champion_models(self) -> dict[str, dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT model_name, model_version, training_rows, feature_schema, parameters, metrics, trained_at,
                       feature_set_version, prediction_cutoff, training_window, calibration_window, test_window,
                       target_definition, dataset_fingerprint, code_git_sha, simulator_regime, promotion_reason
                FROM fabops_model_registry WHERE status = 'champion' ORDER BY model_name
                """
            ).fetchall()
        return {
            str(row["model_name"]): {
                "model_name": str(row["model_name"]),
                "model_version": str(row["model_version"]),
                "training_rows": int(row["training_rows"]),
                "feature_schema": deepcopy(row["feature_schema"]),
                "parameters": deepcopy(row["parameters"]),
                "metrics": deepcopy(row["metrics"]),
                "feature_set_version": row["feature_set_version"],
                "prediction_cutoff": row["prediction_cutoff"],
                "training_window": deepcopy(row["training_window"]),
                "calibration_window": deepcopy(row["calibration_window"]),
                "test_window": deepcopy(row["test_window"]),
                "target_definition": row["target_definition"],
                "dataset_fingerprint": row["dataset_fingerprint"],
                "code_git_sha": row["code_git_sha"],
                "simulator_regime": row["simulator_regime"],
                "promotion_reason": row["promotion_reason"],
                "trained_at": row["trained_at"].isoformat(),
            }
            for row in rows
        }

    def append_prediction(self, prediction: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO fabops_predictions(lot_id, model_name, model_version, target, score, prediction_document)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    prediction["lot_id"], prediction["model_name"], prediction["model_version"],
                    prediction["target"], float(prediction["score"]), Jsonb(prediction),
                ),
            )

    def latest_predictions(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT prediction_id, prediction_document FROM fabops_predictions ORDER BY prediction_id DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [{"prediction_id": int(row["prediction_id"]), **deepcopy(row["prediction_document"])} for row in rows]

    def latest_predictions_for_lots(self, lot_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not lot_ids:
            return {}
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (lot_id, target) prediction_id, lot_id, target, prediction_document
                FROM fabops_predictions
                WHERE lot_id = ANY(%s)
                ORDER BY lot_id, target, prediction_id DESC
                """,
                (lot_ids,),
            ).fetchall()
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            result.setdefault(str(row["lot_id"]), []).append(
                {"prediction_id": int(row["prediction_id"]), **deepcopy(row["prediction_document"])}
            )
        return result

    def unevaluated_predictions(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT p.prediction_id, p.prediction_document
                FROM fabops_predictions p
                LEFT JOIN fabops_prediction_feedback f ON f.prediction_id = p.prediction_id
                WHERE f.prediction_id IS NULL
                ORDER BY p.prediction_id
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [{"prediction_id": int(row["prediction_id"]), **deepcopy(row["prediction_document"])} for row in rows]

    def append_prediction_feedback(self, feedback: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO fabops_prediction_feedback(prediction_id, target, predicted, actual, absolute_error)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (prediction_id) DO NOTHING
                """,
                (
                    int(feedback["prediction_id"]), feedback["target"], float(feedback["predicted"]),
                    float(feedback["actual"]), float(feedback["absolute_error"]),
                ),
            )

    def prediction_feedback_summary(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT target, count(*) AS samples, avg(absolute_error) AS mae,
                       avg((predicted - actual) * (predicted - actual)) AS mse
                FROM fabops_prediction_feedback
                GROUP BY target ORDER BY target
                """
            ).fetchall()
        return {
            str(row["target"]): {
                "samples": int(row["samples"]),
                "mae": round(float(row["mae"]), 6),
                "mse": round(float(row["mse"]), 6),
            }
            for row in rows
        }

    def append_human_feedback(self, feedback: dict[str, Any]) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                """
                INSERT INTO fabops_human_feedback(
                    case_id, prediction_id, feedback_type, prediction_target,
                    actor, actor_role, note, feedback_document
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING feedback_id, created_at
                """,
                (
                    feedback["case_id"],
                    feedback.get("prediction_id"),
                    feedback["feedback_type"],
                    feedback.get("prediction_target"),
                    feedback["actor"],
                    feedback["actor_role"],
                    feedback.get("note"),
                    Jsonb(feedback),
                ),
            ).fetchone()
        return {
            **deepcopy(feedback),
            "feedback_id": int(row["feedback_id"]),
            "created_at": row["created_at"].isoformat(),
        }

    def human_feedback_for_case(self, case_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT feedback_id, created_at, feedback_document
                FROM fabops_human_feedback
                WHERE case_id = %s
                ORDER BY created_at DESC, feedback_id DESC
                LIMIT %s
                """,
                (case_id, limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            document = deepcopy(row["feedback_document"])
            document.update(
                {
                    "feedback_id": int(row["feedback_id"]),
                    "created_at": row["created_at"].isoformat(),
                }
            )
            result.append(document)
        return result

    def human_feedback_summary(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT feedback_type, count(*) AS count
                FROM fabops_human_feedback
                GROUP BY feedback_type
                ORDER BY feedback_type
                """
            ).fetchall()
        by_type = {str(row["feedback_type"]): int(row["count"]) for row in rows}
        return {
            "total": sum(by_type.values()),
            "by_type": by_type,
            "training_policy": "persist-for-evaluation-and-curation-only",
            "automatic_retraining_from_clicks": False,
        }

    def append_intelligence_report(self, report: dict[str, Any]) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                INSERT INTO fabops_intelligence_reports(
                    case_id, material_signature, trigger_type, mode, provider, report_document,
                    assessment_run_id, previous_report_id, reused_report_id, review_skipped_reason,
                    unchanged_since, input_context_fingerprint, provider_model, latency_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, gen_random_uuid()), %s, %s, %s, %s, %s, %s, %s)
                RETURNING report_id, assessment_run_id, created_at
                """,
                (
                    report["case_id"], report["material_signature"], report["trigger_type"],
                    report["mode"], report["provider"], Jsonb(report), report.get("assessment_run_id"),
                    report.get("previous_report_id"), report.get("reused_report_id"), report.get("review_skipped_reason"),
                    report.get("unchanged_since"), report.get("input_context_fingerprint"), report.get("provider_model"),
                    report.get("latency_ms"),
                ),
            ).fetchone()
        return row is not None

    def latest_intelligence_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT report_id, assessment_run_id, previous_report_id, reused_report_id, review_skipped_reason,
                       unchanged_since, provider_model, latency_ms, created_at, report_document
                FROM fabops_intelligence_reports
                ORDER BY created_at DESC, report_id DESC LIMIT %s
                """,
                (limit,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            document = deepcopy(row["report_document"])
            document.update(
                {
                    "report_id": int(row["report_id"]),
                    "assessment_run_id": str(row["assessment_run_id"]) if row["assessment_run_id"] else None,
                    "previous_report_id": int(row["previous_report_id"]) if row["previous_report_id"] else None,
                    "reused_report_id": int(row["reused_report_id"]) if row["reused_report_id"] else None,
                    "review_skipped_reason": row["review_skipped_reason"],
                    "unchanged_since": row["unchanged_since"].isoformat() if row["unchanged_since"] else None,
                    "provider_model": row["provider_model"],
                    "latency_ms": float(row["latency_ms"]) if row["latency_ms"] is not None else None,
                    "created_at": row["created_at"].isoformat(),
                }
            )
            result.append(document)
        return result

    def latest_intelligence_reports_for_cases(self, case_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not case_ids:
            return {}
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (case_id) case_id, report_id, assessment_run_id, created_at, report_document
                FROM fabops_intelligence_reports
                WHERE case_id = ANY(%s)
                ORDER BY case_id, created_at DESC, report_id DESC
                """,
                (case_ids,),
            ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            document = deepcopy(row["report_document"])
            document.update(
                {
                    "report_id": int(row["report_id"]),
                    "assessment_run_id": str(row["assessment_run_id"]) if row["assessment_run_id"] else None,
                    "created_at": row["created_at"].isoformat(),
                }
            )
            result[str(row["case_id"])] = document
        return result

    def latest_intelligence_report_for_case(self, case_id: str) -> dict[str, Any] | None:
        reports = self.latest_intelligence_reports_for_cases([case_id])
        return reports.get(case_id)

    def append_visualization_plan(self, plan: dict[str, Any]) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                INSERT INTO fabops_visualization_plans(case_id, material_signature, plan_document)
                VALUES (%s, %s, %s)
                ON CONFLICT (case_id, material_signature) DO UPDATE SET
                    plan_document = EXCLUDED.plan_document,
                    created_at = now()
                RETURNING plan_id
                """,
                (plan["case_id"], plan["material_signature"], Jsonb(plan)),
            ).fetchone()
        return row is not None

    def latest_visualization_plans(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT plan_document FROM fabops_visualization_plans ORDER BY plan_id DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [deepcopy(row["plan_document"]) for row in rows]

    @staticmethod
    def _inference_job_payload(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        payload = dict(row)
        for key in (
            "job_id",
            "assessment_run_id",
        ):
            if payload.get(key) is not None:
                payload[key] = str(payload[key])
        for key in (
            "created_at",
            "not_before",
            "expires_at",
            "started_at",
            "completed_at",
            "lease_expires_at",
            "updated_at",
        ):
            if payload.get(key) is not None:
                payload[key] = payload[key].isoformat()
        for key in ("request_document", "result_document"):
            if payload.get(key) is not None:
                payload[key] = deepcopy(payload[key])
        return payload

    def enqueue_inference_job(self, job: dict[str, Any]) -> dict[str, Any]:
        """Persist a durable low-volume inference request with active-job dedupe."""

        max_queue_age_seconds = job.get("max_queue_age_seconds")
        with self._connection() as connection:
            row = connection.execute(
                """
                INSERT INTO fabops_inference_jobs(
                    case_id, assessment_run_id, intent, trigger_type, priority, status,
                    not_before, expires_at, max_attempts, input_context_fingerprint,
                    material_signature, provider_preference, allow_vertex_fallback,
                    fallback_after_seconds, dedupe_key, request_document
                ) VALUES (
                    %s, COALESCE(%s, gen_random_uuid()), %s, %s, %s, 'QUEUED', now(),
                    CASE WHEN %s IS NULL THEN NULL ELSE now() + (%s * interval '1 second') END,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                (
                    job["case_id"],
                    job.get("assessment_run_id"),
                    job["intent"],
                    job["trigger_type"],
                    int(job["priority"]),
                    max_queue_age_seconds,
                    max_queue_age_seconds,
                    int(job.get("max_attempts", 3)),
                    job["input_context_fingerprint"],
                    job["material_signature"],
                    job.get("provider_preference", "local-qwen"),
                    bool(job.get("allow_vertex_fallback", False)),
                    job.get("fallback_after_seconds"),
                    job["dedupe_key"],
                    Jsonb(job["request_document"]),
                ),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    SELECT * FROM fabops_inference_jobs
                    WHERE dedupe_key = %s
                      AND status IN ('QUEUED', 'WAITING_FOR_LOCAL', 'RUNNING', 'RETRY')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (job["dedupe_key"],),
                ).fetchone()
        payload = self._inference_job_payload(row)
        if payload is None:
            raise RuntimeError("inference job enqueue did not return a job")
        return payload

    def expire_inference_jobs(self) -> int:
        with self._connection() as connection:
            rows = connection.execute(
                """
                UPDATE fabops_inference_jobs
                SET status = 'EXPIRED', completed_at = now(), lease_owner = NULL,
                    lease_expires_at = NULL, updated_at = now(),
                    error_class = COALESCE(error_class, 'QueueExpired'),
                    error_detail_bounded = COALESCE(error_detail_bounded, 'local inference queue age exceeded')
                WHERE status IN ('QUEUED', 'WAITING_FOR_LOCAL', 'RETRY')
                  AND expires_at IS NOT NULL
                  AND expires_at <= now()
                RETURNING job_id
                """
            ).fetchall()
        return len(rows)

    def recover_expired_inference_leases(self) -> int:
        """Return abandoned RUNNING jobs to RETRY after their worker lease expires."""

        with self._connection() as connection:
            rows = connection.execute(
                """
                UPDATE fabops_inference_jobs
                SET status = 'RETRY',
                    not_before = now(),
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_class = 'LeaseExpired',
                    error_detail_bounded = 'inference worker lease expired before terminal completion',
                    updated_at = now()
                WHERE status = 'RUNNING'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= now()
                  AND (expires_at IS NULL OR expires_at > now())
                RETURNING job_id
                """
            ).fetchall()
        return len(rows)

    def claim_inference_job(self, lease_owner: str, *, lease_seconds: int = 90) -> dict[str, Any] | None:
        self.recover_expired_inference_leases()
        self.expire_inference_jobs()
        with self._connection() as connection:
            row = connection.execute(
                """
                WITH candidate AS (
                    SELECT job_id
                    FROM fabops_inference_jobs
                    WHERE status IN ('QUEUED', 'WAITING_FOR_LOCAL', 'RETRY')
                      AND not_before <= now()
                      AND (expires_at IS NULL OR expires_at > now())
                      AND (lease_expires_at IS NULL OR lease_expires_at <= now())
                    ORDER BY priority DESC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE fabops_inference_jobs j
                SET status = 'RUNNING',
                    lease_owner = %s,
                    lease_expires_at = now() + (%s * interval '1 second'),
                    started_at = COALESCE(started_at, now()),
                    attempt_count = attempt_count + 1,
                    updated_at = now()
                FROM candidate
                WHERE j.job_id = candidate.job_id
                RETURNING j.*
                """,
                (lease_owner, max(10, int(lease_seconds))),
            ).fetchone()
        return self._inference_job_payload(row)

    def requeue_inference_job(
        self,
        job_id: str,
        *,
        status: str,
        backoff_seconds: float,
        error_class: str | None = None,
        error_detail_bounded: str | None = None,
        busy: bool = False,
    ) -> dict[str, Any] | None:
        if status not in {"WAITING_FOR_LOCAL", "RETRY"}:
            raise ValueError(f"invalid inference requeue status: {status}")
        with self._connection() as connection:
            row = connection.execute(
                """
                UPDATE fabops_inference_jobs
                SET status = %s,
                    not_before = now() + (%s * interval '1 second'),
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    busy_count = busy_count + %s,
                    failure_count = failure_count + %s,
                    error_class = %s,
                    error_detail_bounded = %s,
                    updated_at = now()
                WHERE job_id = %s
                RETURNING *
                """,
                (
                    status,
                    max(0.2, float(backoff_seconds)),
                    1 if busy else 0,
                    0 if busy else 1,
                    error_class,
                    (error_detail_bounded or "")[:240] or None,
                    job_id,
                ),
            ).fetchone()
        return self._inference_job_payload(row)

    def finish_inference_job(
        self,
        job_id: str,
        *,
        status: str,
        result_document: dict[str, Any] | None,
        error_class: str | None = None,
        error_detail_bounded: str | None = None,
    ) -> dict[str, Any] | None:
        if status not in {"COMPLETED", "FALLBACK", "FAILED", "CANCELLED", "EXPIRED"}:
            raise ValueError(f"invalid inference terminal status: {status}")
        with self._connection() as connection:
            row = connection.execute(
                """
                UPDATE fabops_inference_jobs
                SET status = %s,
                    result_document = %s,
                    completed_at = now(),
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_class = %s,
                    error_detail_bounded = %s,
                    updated_at = now()
                WHERE job_id = %s
                RETURNING *
                """,
                (
                    status,
                    Jsonb(result_document) if result_document is not None else None,
                    error_class,
                    (error_detail_bounded or "")[:240] or None,
                    job_id,
                ),
            ).fetchone()
        return self._inference_job_payload(row)

    def inference_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM fabops_inference_jobs WHERE job_id = %s", (job_id,)).fetchone()
        return self._inference_job_payload(row)

    def inference_queue_status(self) -> dict[str, Any]:
        with self._connection() as connection:
            aggregate = connection.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status IN ('QUEUED', 'WAITING_FOR_LOCAL', 'RETRY')) AS queued,
                    count(*) FILTER (WHERE status = 'RUNNING') AS running,
                    count(*) FILTER (WHERE status = 'WAITING_FOR_LOCAL') AS waiting_for_local,
                    COALESCE(max(EXTRACT(EPOCH FROM (now() - created_at))) FILTER (
                        WHERE status IN ('QUEUED', 'WAITING_FOR_LOCAL', 'RETRY')
                    ), 0) AS oldest_queue_age_seconds,
                    COALESCE(sum(busy_count), 0) AS local_busy_count,
                    COALESCE(sum(failure_count), 0) AS local_failure_count,
                    COALESCE(sum(attempt_count), 0) AS local_attempt_count,
                    count(*) FILTER (
                        WHERE status IN ('COMPLETED', 'FALLBACK')
                          AND result_document#>>'{brief,provider}' = 'local-qwen'
                    ) AS local_success_count,
                    count(*) FILTER (
                        WHERE status = 'FALLBACK'
                          AND result_document#>>'{brief,provider}' = 'vertex-ai-gemini'
                    ) AS vertex_fallback_after_wait_count,
                    avg(EXTRACT(EPOCH FROM (started_at - created_at)) * 1000.0) FILTER (
                        WHERE started_at IS NOT NULL
                    ) AS average_queue_wait_ms
                FROM fabops_inference_jobs
                """
            ).fetchone()
            runtime_rows = connection.execute(
                "SELECT provider, state, model, model_loaded, active_jobs, provider_metadata, last_success_at, last_error_class, updated_at FROM fabops_inference_runtime_state"
            ).fetchall()
            queued_rows = connection.execute(
                """
                SELECT job_id, case_id, status, priority, created_at,
                       EXTRACT(EPOCH FROM (now() - created_at)) AS age_seconds
                FROM fabops_inference_jobs
                WHERE status IN ('QUEUED', 'WAITING_FOR_LOCAL', 'RUNNING', 'RETRY')
                ORDER BY priority DESC, created_at ASC
                LIMIT 8
                """
            ).fetchall()
        providers = {
            str(row["provider"]): {
                "state": str(row["state"]),
                "model": row["model"],
                "loaded": row["model_loaded"],
                "active_jobs": int(row["active_jobs"]),
                "metadata": deepcopy(row["provider_metadata"]),
                "last_success_at": row["last_success_at"].isoformat() if row["last_success_at"] else None,
                "last_error_class": row["last_error_class"],
                "updated_at": row["updated_at"].isoformat(),
            }
            for row in runtime_rows
        }
        queue = [
            {
                "job_id": str(row["job_id"]),
                "case_id": str(row["case_id"]),
                "status": str(row["status"]),
                "priority": int(row["priority"]),
                "created_at": row["created_at"].isoformat(),
                "age_seconds": round(float(row["age_seconds"]), 3),
                "position": index + 1,
            }
            for index, row in enumerate(queued_rows)
        ]
        return {
            "queue_depth": int(aggregate["queued"]),
            "running": int(aggregate["running"]),
            "waiting_for_local": int(aggregate["waiting_for_local"]),
            "oldest_queue_age_seconds": round(float(aggregate["oldest_queue_age_seconds"]), 3),
            "local_busy_count": int(aggregate["local_busy_count"]),
            "local_failure_count": int(aggregate["local_failure_count"]),
            "local_attempt_count": int(aggregate["local_attempt_count"]),
            "local_success_count": int(aggregate["local_success_count"]),
            "vertex_fallback_after_wait_count": int(aggregate["vertex_fallback_after_wait_count"]),
            "average_queue_wait_ms": round(float(aggregate["average_queue_wait_ms"]), 3) if aggregate["average_queue_wait_ms"] is not None else None,
            "providers": providers,
            "jobs": queue,
        }

    def update_inference_runtime_state(
        self,
        provider: str,
        *,
        state: str,
        model: str | None,
        model_loaded: bool | None,
        active_jobs: int,
        metadata: dict[str, Any],
        success: bool = False,
        error_class: str | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO fabops_inference_runtime_state(
                    provider, state, model, model_loaded, active_jobs, provider_metadata,
                    last_success_at, last_error_class
                ) VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s THEN now() ELSE NULL END, %s)
                ON CONFLICT (provider) DO UPDATE SET
                    state = EXCLUDED.state,
                    model = EXCLUDED.model,
                    model_loaded = EXCLUDED.model_loaded,
                    active_jobs = EXCLUDED.active_jobs,
                    provider_metadata = EXCLUDED.provider_metadata,
                    last_success_at = CASE WHEN %s THEN now() ELSE fabops_inference_runtime_state.last_success_at END,
                    last_error_class = EXCLUDED.last_error_class,
                    updated_at = now()
                """,
                (
                    provider,
                    state,
                    model,
                    model_loaded,
                    int(active_jobs),
                    Jsonb(metadata),
                    bool(success),
                    error_class,
                    bool(success),
                ),
            )


class ReadOnlyPostgresRepository(PostgresRepository):
    """PostgreSQL adapter that enforces read-only transactions at the server boundary.

    This is intentionally stricter than simply relying on the public proxy to block
    mutation routes. Even if a write-capable repository method is called accidentally,
    PostgreSQL rejects the statement inside a READ ONLY transaction.
    """

    @contextmanager
    def transaction(self) -> Iterator[Connection[Any]]:
        active = _ACTIVE_CONNECTION.get()
        if active is not None:
            yield active
            return
        with psycopg.connect(self.config.dsn, row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            token = _ACTIVE_CONNECTION.set(connection)
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                _ACTIVE_CONNECTION.reset(token)
