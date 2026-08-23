from __future__ import annotations

import json
import os
import signal
from threading import Event

from adapters.postgres import PostgresConfig, PostgresRepository
from adapters.redpanda.adapter import RedpandaConfig, RedpandaEventBusAdapter
from services.detection.service import DeterministicDetector
from services.ingestion.service import IngestionService
from systems.api.runtime import build_integration_runtime


def main() -> None:
    stop_event = Event()

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    os.environ.setdefault("FABOPS_REDPANDA_GROUP", "fabops-live-stream-v1")
    projection_mode = os.getenv("FABOPS_STREAM_PROJECTION_MODE", "neo4j").strip().lower()
    if projection_mode == "postgres-only":
        postgres_dsn = os.getenv("FABOPS_POSTGRES_DSN")
        if not postgres_dsn:
            raise RuntimeError("FABOPS_POSTGRES_DSN is required for postgres-only stream mode")
        repository = PostgresRepository(PostgresConfig(postgres_dsn))
        detector = DeterministicDetector(repository)
        ingestion = IngestionService(
            repository,
            repository,
            repository,
            detector.consume,
            transaction_factory=repository.transaction,
        )
        for stored in repository.all_events():
            detector.consume(stored.event)
        bus = RedpandaEventBusAdapter(
            config=RedpandaConfig(
                bootstrap_servers=os.getenv("FABOPS_REDPANDA_BOOTSTRAP", "redpanda:9092"),
                topic=os.getenv("FABOPS_REDPANDA_TOPIC", "fabops.events.v1"),
                dlq_topic=os.getenv("FABOPS_REDPANDA_DLQ_TOPIC", "fabops.events.dlq.v1"),
                group_id=os.getenv("FABOPS_REDPANDA_GROUP", "fabops-live-stream-v1"),
                idle_timeout_seconds=float(os.getenv("FABOPS_REDPANDA_IDLE_TIMEOUT", "1.0")),
            )
        )
        processed = 0

        def handle_postgres_only(event: dict[str, object]) -> None:
            nonlocal processed
            result = ingestion.ingest(event)
            processed += 1
            if processed == 1 or processed % 25 == 0:
                counts = repository.counts()
                print(
                    json.dumps(
                        {
                            "service": "fabops-stream-worker",
                            "projection_mode": "api-in-memory",
                            "processed": processed,
                            "ingestion_result": result,
                            "event_count": counts["events"],
                            "case_count": counts["cases"],
                            "detection_checkpoint": repository.checkpoint("detection"),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )

        bus.subscribe_forever(bus.config.topic, handle_postgres_only, stop_event.is_set)
        return

    runtime = build_integration_runtime(
        seed=int(os.getenv("FABOPS_LIVE_SEED", "42")),
        profile=os.getenv("FABOPS_LIVE_PROFILE", "test"),
    )
    if runtime.initialization_error is not None:
        raise RuntimeError(f"stream worker initialization failed: {runtime.initialization_error}")

    # Reconstruct the online detector's EWMA/anomaly state from authoritative
    # PostgreSQL before consuming new events. Existing case upserts are idempotent.
    for stored in runtime.event_repository.all_events():
        runtime.detector.consume(stored.event)
    runtime.projection.catch_up()

    processed = 0

    def handle(event: dict[str, object]) -> None:
        nonlocal processed
        result = runtime.ingestion.ingest(event)
        if result not in {"duplicate_noop", "quarantined"}:
            runtime.projection.catch_up()
        processed += 1
        if processed == 1 or processed % 25 == 0:
            print(
                json.dumps(
                    {
                        "service": "fabops-stream-worker",
                        "processed": processed,
                        "ingestion_result": result,
                        "event_count": runtime.event_repository.counts()["events"],
                        "case_count": runtime.event_repository.counts()["cases"],
                        "projection_checkpoint": runtime.projection.status().projection_checkpoint,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    try:
        runtime.event_bus.subscribe_forever(runtime.event_bus.config.topic, handle, stop_event.is_set)
    finally:
        runtime.graph.close()


if __name__ == "__main__":
    main()

