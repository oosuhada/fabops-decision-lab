from __future__ import annotations

import json
import os
import signal
from threading import Event

from adapters.postgres import PostgresConfig, PostgresRepository
from adapters.redpanda.adapter import RedpandaConfig, RedpandaEventBusAdapter
from simulator.live import LiveFabTwinStream


def main() -> None:
    stop_event = Event()

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    config = RedpandaConfig(
        bootstrap_servers=os.getenv("FABOPS_REDPANDA_BOOTSTRAP", "redpanda:9092"),
        topic=os.getenv("FABOPS_REDPANDA_TOPIC", "fabops.events.v1"),
        dlq_topic=os.getenv("FABOPS_REDPANDA_DLQ_TOPIC", "fabops.events.dlq.v1"),
        group_id="fabops-live-publisher",
    )
    bus = RedpandaEventBusAdapter(config=config)
    lot_base: int | None = None
    postgres_dsn = os.getenv("FABOPS_POSTGRES_DSN")
    if postgres_dsn:
        repository = PostgresRepository(PostgresConfig(postgres_dsn))
        lot_indices: list[int] = []
        for stored in repository.all_events():
            lot_id = str(stored.event.get("lot_id") or "")
            if not lot_id.startswith("LOT-"):
                continue
            try:
                lot_indices.append(int(lot_id.split("-", 1)[1]))
            except ValueError:
                continue
        lot_base = max(lot_indices, default=0)
    stream = LiveFabTwinStream(
        seed=int(os.getenv("FABOPS_LIVE_SEED", "42")),
        profile=os.getenv("FABOPS_LIVE_PROFILE", "test"),
        acceleration=float(os.getenv("FABOPS_LIVE_TIME_ACCELERATION", "720")),
        lot_base=lot_base,
    )
    emitted = 0
    for event in stream.events(stop_event):
        bus.publish(config.topic, event)
        emitted += 1
        if emitted == 1 or emitted % 25 == 0:
            print(
                json.dumps(
                    {
                        "service": "fabops-live-simulator",
                        "emitted": emitted,
                        "event_type": event["event_type"],
                        "lot_id": event.get("lot_id"),
                        "event_time": event["event_time"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()

