from __future__ import annotations

import json
import os

from adapters.postgres import PostgresConfig, PostgresRepository
from systems.api.runtime import build_integration_runtime


def main() -> None:
    postgres_dsn = os.environ.get("FABOPS_POSTGRES_DSN")
    if not postgres_dsn:
        raise RuntimeError("FABOPS_POSTGRES_DSN is required for live bootstrap")

    repository = PostgresRepository(PostgresConfig(postgres_dsn))
    counts = repository.counts()
    if counts["events"] > 0:
        print(
            json.dumps(
                {
                    "service": "fabops-live-bootstrap",
                    "mode": "preserve-existing",
                    "event_count": counts["events"],
                    "case_count": counts["cases"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return

    runtime = build_integration_runtime(
        seed=int(os.getenv("FABOPS_LIVE_SEED", "42")),
        profile=os.getenv("FABOPS_LIVE_PROFILE", "test"),
    )
    try:
        if runtime.initialization_error is not None:
            raise RuntimeError(f"live bootstrap failed: {runtime.initialization_error}")
        seeded = runtime.event_repository.counts()
        if seeded["events"] <= 0 or seeded["cases"] <= 0:
            raise RuntimeError("live bootstrap produced no baseline events/cases")
        print(
            json.dumps(
                {
                    "service": "fabops-live-bootstrap",
                    "mode": "seeded-baseline",
                    "event_count": seeded["events"],
                    "case_count": seeded["cases"],
                    "detection_checkpoint": runtime.event_repository.checkpoint("detection"),
                    "projection_checkpoint": runtime.projection.status().projection_checkpoint,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    finally:
        runtime.graph.close()


if __name__ == "__main__":
    main()
