from __future__ import annotations

import json
import os
import signal
from threading import Event

from systems.api.runtime import build_integration_runtime


def main() -> None:
    stop_event = Event()

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    os.environ.setdefault("FABOPS_REDPANDA_GROUP", "fabops-live-stream-v1")
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

