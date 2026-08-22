from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from confluent_kafka import Consumer, KafkaError, Producer
from confluent_kafka.admin import AdminClient


@dataclass(frozen=True)
class RedpandaConfig:
    bootstrap_servers: str = "localhost:19092"
    topic: str = "fabops.events.v1"
    dlq_topic: str = "fabops.events.dlq.v1"
    group_id: str = "fabops-api-v1"
    auto_offset_reset: str = "earliest"
    idle_timeout_seconds: float = 1.0
    max_messages: int = 10_000
    max_attempts: int = 3
    commit_on_success: bool = True


class RedpandaEventBusAdapter:
    """Kafka-compatible production transport with a deterministic injected publish seam for unit tests."""

    def __init__(self, send: Callable[[str, bytes, bytes], None] | None = None, config: RedpandaConfig | None = None) -> None:
        self.send = send
        self.config = config or RedpandaConfig()
        self._producer = None if send is not None else Producer({"bootstrap.servers": self.config.bootstrap_servers})
        self.consumed_keys: list[str | None] = []
        self.last_consume_count = 0
        self.dlq_published_count = 0

    def healthcheck(self) -> bool:
        try:
            AdminClient({"bootstrap.servers": self.config.bootstrap_servers}).list_topics(timeout=2.0)
            return True
        except Exception:  # noqa: BLE001 - transport health is collapsed to ready/not-ready
            return False

    def _publish_bytes(self, topic: str, key: bytes, value: bytes) -> None:
        if self.send is not None:
            self.send(topic, key, value)
            return
        if self._producer is None:
            raise RuntimeError("Redpanda producer is not configured")
        self._producer.produce(topic, key=key, value=value)
        remaining = self._producer.flush(5.0)
        if remaining:
            raise RuntimeError(f"Redpanda producer flush left {remaining} message(s) pending")

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        key = str(event["event_id"]).encode("utf-8")
        value = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._publish_bytes(topic, key, value)

    def subscribe(self, topic: str, handler: Callable[[dict[str, Any]], None]) -> None:
        consumer = Consumer(
            {
                "bootstrap.servers": self.config.bootstrap_servers,
                "group.id": self.config.group_id,
                "auto.offset.reset": self.config.auto_offset_reset,
                "enable.auto.commit": False,
            }
        )
        consumed = 0
        idle_started = time.monotonic()
        consumer.subscribe([topic])
        try:
            while consumed < self.config.max_messages:
                message = consumer.poll(0.1)
                if message is None:
                    if time.monotonic() - idle_started >= self.config.idle_timeout_seconds:
                        break
                    continue
                if message.error():
                    if message.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise RuntimeError(f"Redpanda consumer error: {message.error()}")
                idle_started = time.monotonic()
                raw_key = message.key()
                self.consumed_keys.append(raw_key.decode("utf-8") if raw_key else None)
                try:
                    event = json.loads(message.value().decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._publish_bytes(self.config.dlq_topic, raw_key or b"invalid", message.value())
                    self.dlq_published_count += 1
                    consumer.commit(message=message, asynchronous=False)
                    consumed += 1
                    continue
                failure: Exception | None = None
                for _attempt in range(self.config.max_attempts):
                    try:
                        handler(event)
                        failure = None
                        break
                    except Exception as exc:  # noqa: BLE001 - retry/DLQ contract intentionally handles dependency failures
                        failure = exc
                if failure is not None:
                    self._publish_bytes(self.config.dlq_topic, raw_key or b"failed", message.value())
                    self.dlq_published_count += 1
                elif self.config.commit_on_success:
                    consumer.commit(message=message, asynchronous=False)
                consumed += 1
        finally:
            consumer.close()
            self.last_consume_count = consumed

