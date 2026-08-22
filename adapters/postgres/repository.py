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
