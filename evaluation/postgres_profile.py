from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg

from adapters.postgres.migrate import apply_migrations

EVENT_INDEX = "fabops_event_log_event_type_sequence_idx"
CASE_INDEX = "fabops_cases_classification_lot_updated_idx"


@dataclass(frozen=True)
class PhaseResult:
    p50_ms: float
    p95_ms: float
    mean_ms: float
    variance_ms2: float
    plan_nodes: list[str]
    index_names: list[str]
    shared_hit_blocks: int
    shared_read_blocks: int


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _plan_nodes(plan: dict[str, Any]) -> list[str]:
    nodes = [str(plan.get("Node Type", "unknown"))]
    for child in plan.get("Plans", []):
        nodes.extend(_plan_nodes(child))
    return nodes


def _index_names(plan: dict[str, Any]) -> list[str]:
    names: list[str] = []
    index_name = plan.get("Index Name")
    if index_name:
        names.append(str(index_name))
    for child in plan.get("Plans", []):
        names.extend(_index_names(child))
    return names


def _buffer_total(plan: dict[str, Any], key: str) -> int:
    total = int(plan.get(key, 0) or 0)
    for child in plan.get("Plans", []):
        total += _buffer_total(child, key)
    return total


def _explain_runs(connection: psycopg.Connection[Any], sql: str, params: tuple[Any, ...], repeats: int) -> PhaseResult:
    execution_times: list[float] = []
    last_plan: dict[str, Any] = {}
    for _ in range(repeats):
        row = connection.execute(
            f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}",
            params,
        ).fetchone()
        payload = row[0][0]
        last_plan = payload["Plan"]
        execution_times.append(float(payload["Execution Time"]))

    return PhaseResult(
        p50_ms=round(_percentile(execution_times, 0.50), 4),
        p95_ms=round(_percentile(execution_times, 0.95), 4),
        mean_ms=round(statistics.mean(execution_times), 4),
        variance_ms2=round(statistics.pvariance(execution_times), 6),
        plan_nodes=_plan_nodes(last_plan),
        index_names=_index_names(last_plan),
        shared_hit_blocks=_buffer_total(last_plan, "Shared Hit Blocks"),
        shared_read_blocks=_buffer_total(last_plan, "Shared Read Blocks"),
    )


def _safe_benchmark_database(dsn: str) -> str:
    database = urlparse(dsn).path.lstrip("/")
    if not database or not any(marker in database.lower() for marker in ("bench", "test")):
        raise SystemExit(
            "Refusing to seed/drop indexes outside a database whose name contains 'bench' or 'test'."
        )
    return database


def _seed_fixture(connection: psycopg.Connection[Any], event_rows: int, case_rows: int) -> None:
    connection.execute(
        "TRUNCATE fabops_decision_audit, fabops_cases, fabops_measurements, fabops_event_log CASCADE"
    )
    connection.execute(
        """
        INSERT INTO fabops_event_log(
            event_id, event_type, event_time, ingested_at, trace_id, lot_id,
            equipment_id, chamber_id, schema_version, delivery_status, envelope
        )
        SELECT
            md5('event-' || g::text)::uuid,
            CASE WHEN g <= GREATEST(512, %s / 100) THEN 'process.measurement.recorded.v1'
                 ELSE 'process.step.completed.v1' END,
            now() - (g || ' milliseconds')::interval,
            now(),
            'trace-' || (g %% 2000)::text,
            'LOT-' || lpad((g %% 5000)::text, 5, '0'),
            'EQ-' || (g %% 40)::text,
            'CH-' || (g %% 8)::text,
            1,
            'on_time',
            jsonb_build_object('event_id', g, 'fixture', true)
        FROM generate_series(1, %s) AS g
        """,
        (event_rows, event_rows),
    )
    connection.execute(
        """
        INSERT INTO fabops_cases(
            case_id, lot_id, classification, state, anomaly_score,
            detector_version, case_document, updated_at
        )
        SELECT
            'CASE-' || lpad(g::text, 7, '0'),
            'LOT-' || lpad((g %% 5000)::text, 5, '0'),
            CASE WHEN g %% 20 = 0 THEN 'physical_excursion'
                 WHEN g %% 5 = 0 THEN 'sensor_bias_suspected'
                 ELSE 'data_quality_incident' END,
            'open',
            (g %% 100)::double precision / 100.0,
            'profile-fixture-v1',
            jsonb_build_object('case_id', g, 'fixture', true),
            now() - (g || ' milliseconds')::interval
        FROM generate_series(1, %s) AS g
        """,
        (case_rows,),
    )
    connection.execute("ANALYZE fabops_event_log")
    connection.execute("ANALYZE fabops_cases")


def _profile_one(
    connection: psycopg.Connection[Any],
    *,
    index_name: str,
    create_index_sql: str,
    query_sql: str,
    params: tuple[Any, ...],
    repeats: int,
) -> dict[str, Any]:
    connection.execute(f'DROP INDEX IF EXISTS "{index_name}"')
    connection.execute("DISCARD PLANS")
    before = _explain_runs(connection, query_sql, params, repeats)

    connection.execute(create_index_sql)
    connection.execute("ANALYZE fabops_event_log")
    connection.execute("ANALYZE fabops_cases")
    connection.execute("DISCARD PLANS")
    after = _explain_runs(connection, query_sql, params, repeats)

    improvement = None
    if before.p50_ms > 0:
        improvement = round((before.p50_ms - after.p50_ms) / before.p50_ms * 100.0, 2)
    return {
        "index": index_name,
        "before": asdict(before),
        "after": asdict(after),
        "p50_improvement_percent": improvement,
    }


def run_profile(dsn: str, *, event_rows: int, case_rows: int, repeats: int) -> dict[str, Any]:
    database = _safe_benchmark_database(dsn)
    apply_migrations(dsn)
    with psycopg.connect(dsn, autocommit=True) as connection:
        _seed_fixture(connection, event_rows, case_rows)
        recent_measurements = _profile_one(
            connection,
            index_name=EVENT_INDEX,
            create_index_sql=(
                "CREATE INDEX fabops_event_log_event_type_sequence_idx "
                "ON fabops_event_log(event_type, sequence DESC)"
            ),
            query_sql=(
                "SELECT sequence, envelope, delivery_status FROM fabops_event_log "
                "WHERE event_type = 'process.measurement.recorded.v1' "
                "ORDER BY sequence DESC LIMIT %s"
            ),
            params=(128,),
            repeats=repeats,
        )
        related_cases = _profile_one(
            connection,
            index_name=CASE_INDEX,
            create_index_sql=(
                "CREATE INDEX fabops_cases_classification_lot_updated_idx "
                "ON fabops_cases(classification, lot_id DESC, updated_at DESC)"
            ),
            query_sql=(
                "SELECT case_document FROM fabops_cases "
                "WHERE classification = %s AND case_id <> %s "
                "ORDER BY lot_id DESC, updated_at DESC LIMIT %s"
            ),
            params=("physical_excursion", "CASE-0000001", 20),
            repeats=repeats,
        )
    return {
        "experiment": "fabops-postgresql-operational-index-profile-v1",
        "database": database,
        "fixture": {"event_rows": event_rows, "case_rows": case_rows},
        "repeats_per_phase": repeats,
        "queries": {
            "recent_measurement_events": recent_measurements,
            "related_cases": related_cases,
        },
        "limitations": [
            "Synthetic portfolio fixture; results are not a production-fab capacity claim.",
            "Warm-cache EXPLAIN ANALYZE runs on one local PostgreSQL instance.",
            "The benchmark isolates read-plan effects and does not quantify index write amplification.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile FabOps PostgreSQL repository query plans before/after selected indexes.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--event-rows", type=int, default=200_000)
    parser.add_argument("--case-rows", type=int, default=80_000)
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    result = run_profile(
        args.dsn,
        event_rows=max(10_000, args.event_rows),
        case_rows=max(10_000, args.case_rows),
        repeats=max(3, args.repeats),
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    if args.strict:
        for query_name, query_result in result["queries"].items():
            expected_index = query_result["index"]
            before = query_result["before"]
            after = query_result["after"]
            if expected_index not in after["index_names"]:
                raise SystemExit(f"{query_name}: expected index not used after migration")
            if after["p50_ms"] >= before["p50_ms"]:
                raise SystemExit(f"{query_name}: p50 did not improve")
            if after["shared_hit_blocks"] >= before["shared_hit_blocks"]:
                raise SystemExit(f"{query_name}: shared buffer hits did not decrease")


if __name__ == "__main__":
    main()
