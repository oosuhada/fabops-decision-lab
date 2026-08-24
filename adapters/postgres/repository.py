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

    def register_model(self, model: dict[str, Any], *, champion: bool) -> None:
        with self._connection() as connection:
            if champion:
                connection.execute(
                    "UPDATE fabops_model_registry SET status = 'retired' WHERE model_name = %s AND status = 'champion'",
                    (model["model_name"],),
                )
            connection.execute(
                """
                INSERT INTO fabops_model_registry(
                    model_name, model_version, status, training_rows, feature_schema,
                    parameters, metrics
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (model_name, model_version) DO UPDATE SET
                    status = EXCLUDED.status,
                    training_rows = EXCLUDED.training_rows,
                    feature_schema = EXCLUDED.feature_schema,
                    parameters = EXCLUDED.parameters,
                    metrics = EXCLUDED.metrics,
                    trained_at = now()
                """,
                (
                    model["model_name"], model["model_version"], "champion" if champion else "candidate",
                    int(model["training_rows"]), Jsonb(model["feature_schema"]), Jsonb(model["parameters"]),
                    Jsonb(model["metrics"]),
                ),
            )

    def champion_models(self) -> dict[str, dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT model_name, model_version, training_rows, feature_schema, parameters, metrics, trained_at
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
                "SELECT prediction_document FROM fabops_predictions ORDER BY prediction_id DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [deepcopy(row["prediction_document"]) for row in rows]

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

    def append_intelligence_report(self, report: dict[str, Any]) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                INSERT INTO fabops_intelligence_reports(
                    case_id, material_signature, trigger_type, mode, provider, report_document
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (case_id, material_signature) DO NOTHING RETURNING report_id
                """,
                (
                    report["case_id"], report["material_signature"], report["trigger_type"],
                    report["mode"], report["provider"], Jsonb(report),
                ),
            ).fetchone()
        return row is not None

    def latest_intelligence_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT report_document FROM fabops_intelligence_reports ORDER BY report_id DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [deepcopy(row["report_document"]) for row in rows]

    def append_visualization_plan(self, plan: dict[str, Any]) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                INSERT INTO fabops_visualization_plans(case_id, material_signature, plan_document)
                VALUES (%s, %s, %s)
                ON CONFLICT (case_id, material_signature) DO NOTHING RETURNING plan_id
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
