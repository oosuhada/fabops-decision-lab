from __future__ import annotations

import json
import os

from adapters.postgres import PostgresConfig, PostgresRepository
from services.detection.service import DeterministicDetector
from services.ingestion.service import IngestionService
from simulator.config import load_config
from simulator.fabtwin import FabTwinSimulator


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

    seed = int(os.getenv("FABOPS_LIVE_SEED", "42"))
    profile = os.getenv("FABOPS_LIVE_PROFILE", "test")
    detector = DeterministicDetector(repository)
    ingestion = IngestionService(
        repository,
        repository,
        repository,
        detector.consume,
        transaction_factory=repository.transaction,
    )
    trace = FabTwinSimulator(load_config(profile), seed).generate()
    for event in trace.events:
        ingestion.ingest(event)
    seeded = repository.counts()
    if seeded["events"] <= 0 or seeded["cases"] <= 0:
        raise RuntimeError("live bootstrap produced no baseline events/cases")
    print(
        json.dumps(
            {
                "service": "fabops-live-bootstrap",
                "mode": "seeded-baseline",
                "event_count": seeded["events"],
                "case_count": seeded["cases"],
                "detection_checkpoint": repository.checkpoint("detection"),
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
