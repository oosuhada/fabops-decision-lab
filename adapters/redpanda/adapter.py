from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RedpandaConfig:
    bootstrap_servers: str = "localhost:19092"
    topic: str = "fabops.events.v1"
    dlq_topic: str = "fabops.events.dlq.v1"


class RedpandaEventBusAdapter:
    """Transport adapter that can wrap confluent-kafka/aiokafka without coupling core code.

    The injected ``send`` callable is used by contract tests. A real producer can be
    supplied by an integration fixture when Docker/Redpanda is available.
    """

    def __init__(self, send: Callable[[str, bytes, bytes], None], config: RedpandaConfig | None = None) -> None:
        self.send = send
        self.config = config or RedpandaConfig()

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        key = str(event["event_id"]).encode("utf-8")
        value = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send(topic, key, value)

    def subscribe(self, topic: str, handler: Callable[[dict[str, Any]], None]) -> None:
        raise NotImplementedError("Consumer lifecycle is exercised only by the Docker integration profile; core tests use DeterministicLocalEventBus")

