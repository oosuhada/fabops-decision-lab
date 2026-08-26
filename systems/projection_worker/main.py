from __future__ import annotations

import json
import os
import signal
import time
from threading import Event

from adapters.postgres import PostgresConfig, PostgresGraphProjection, PostgresRepository
from services.rca.projection import RcaProjectionWorker


def main() -> None:
    dsn = os.getenv("FABOPS_POSTGRES_DSN", "").strip()
    if not dsn:
        raise RuntimeError("FABOPS_POSTGRES_DSN is required")
    window_lots = max(50, int(os.getenv("FABOPS_GRAPH_WINDOW_LOTS", "250")))
    interval = max(0.25, float(os.getenv("FABOPS_PROJECTION_INTERVAL_SECONDS", "1.0")))
    repository = PostgresRepository(PostgresConfig(dsn))
    graph = PostgresGraphProjection(dsn, writable=True)
    worker = RcaProjectionWorker(repository, graph, window_lots=window_lots)
    stop_event = Event()

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    cycles = 0
    try:
        if graph.projection_checkpoint() == 0:
            status = worker.rebuild_recent()
            print(
                json.dumps(
                    {
                        "service": "fabops-projection-worker",
                        "phase": "initial-rebuild",
                        "source_checkpoint": status.source_checkpoint,
                        "projection_checkpoint": status.projection_checkpoint,
                        "lag_events": status.lag_events,
                        "window_lots": window_lots,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        while not stop_event.is_set():
            started = time.perf_counter()
            status = worker.catch_up()
            cycles += 1
            if cycles == 1 or cycles % 30 == 0 or status.lag_events > 0:
                print(
                    json.dumps(
                        {
                            "service": "fabops-projection-worker",
                            "phase": "incremental",
                            "source_checkpoint": status.source_checkpoint,
                            "projection_checkpoint": status.projection_checkpoint,
                            "lag_events": status.lag_events,
                            "lag_seconds": status.lag_seconds,
                            "slo_state": status.slo_state,
                            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            stop_event.wait(interval)
    finally:
        graph.close()


if __name__ == "__main__":
    main()
