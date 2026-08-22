from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from adapters.neo4j import Neo4jConfig, Neo4jDriverProjectionAdapter
from adapters.postgres import PostgresConfig, PostgresRepository, ReadOnlyPostgresRepository
from adapters.redpanda.adapter import RedpandaConfig, RedpandaEventBusAdapter
from services.detection.service import DeterministicDetector
from services.ingestion.service import IngestionService
from services.rca.projection import RcaProjectionWorker

pytestmark = pytest.mark.skipif(
    os.environ.get("FABOPS_CONTAINER_INTEGRATION") != "1",
    reason="requires isolated Docker Compose integration stack",
)


def _postgres() -> PostgresRepository:
    return PostgresRepository(PostgresConfig(os.environ["FABOPS_POSTGRES_DSN"]))


def _neo4j() -> Neo4jDriverProjectionAdapter:
    return Neo4jDriverProjectionAdapter(
        Neo4jConfig(
            os.environ["FABOPS_NEO4J_URI"],
            os.environ.get("FABOPS_NEO4J_USER", "neo4j"),
            os.environ["FABOPS_NEO4J_PASSWORD"],
        )
    )


def _ingestion(repository: PostgresRepository) -> IngestionService:
    detector = DeterministicDetector(repository)
    return IngestionService(
        repository,
        repository,
        repository,
        detector.consume,
        transaction_factory=repository.transaction,
    )


def test_postgres_is_authoritative_and_duplicate_delivery_has_zero_case_audit_outbox_side_effects() -> None:
    repository = _postgres()
    assert repository.healthcheck() is True
    before = repository.counts()
    assert before["events"] == 373
    assert before["cases"] == 7
    event = repository.all_events()[0].event
    result = _ingestion(repository).ingest(event)
    after = repository.counts()
    assert result == "duplicate_noop"
    assert after == before


def test_read_only_postgres_adapter_rejects_mutation_at_database_boundary() -> None:
    repository = ReadOnlyPostgresRepository(PostgresConfig(os.environ["FABOPS_POSTGRES_DSN"]))
    assert repository.healthcheck() is True
    before = repository.counts()
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        repository.append_audit(
            {
                "case_id": "READ-ONLY-PROBE",
                "event": "preview.read_only_probe",
                "actor_id": "integration-test",
            }
        )
    assert repository.counts() == before


def test_postgres_quarantine_write_is_transactional() -> None:
    repository = _postgres()
    ingestion = _ingestion(repository)
    before = repository.counts()["quarantine"]

    class RollbackProbe(RuntimeError):
        pass

    with pytest.raises(RollbackProbe):
        with repository.transaction():
            assert ingestion.ingest({"event_id": "not-a-valid-envelope"}) == "quarantined"
            assert repository.counts()["quarantine"] == before + 1
            raise RollbackProbe("rollback integration probe")
    assert repository.counts()["quarantine"] == before


def test_neo4j_projection_is_rebuilt_from_postgres_source() -> None:
    repository = _postgres()
    graph = _neo4j()
    try:
        assert graph.healthcheck() is True
        worker = RcaProjectionWorker(repository, graph)
        status = worker.rebuild()
        assert status.source_checkpoint == 373
        assert status.projection_checkpoint == 373
        assert status.lag_events == 0
        assert len(graph.nodes()) > 0
        assert len(graph.edges()) > 0
    finally:
        graph.close()


def test_redpanda_publish_consume_key_reconsume_and_dlq_preserve_idempotency() -> None:
    repository = _postgres()
    ingestion = _ingestion(repository)
    bootstrap = os.environ["FABOPS_REDPANDA_BOOTSTRAP"]
    event = repository.all_events()[0].event
    event_id = str(event["event_id"])
    suffix = uuid.uuid4().hex[:10]
    topic = f"fabops.m6.integration.{suffix}"
    dlq_topic = f"fabops.m6.integration.dlq.{suffix}"
    group_id = f"fabops-m6-{suffix}"
    before = repository.counts()

    producer = RedpandaEventBusAdapter(
        config=RedpandaConfig(bootstrap_servers=bootstrap, topic=topic, dlq_topic=dlq_topic, group_id=group_id)
    )
    assert producer.healthcheck() is True
    producer.publish(topic, event)
    producer.publish(topic, event)
    consumer = RedpandaEventBusAdapter(
        config=RedpandaConfig(
            bootstrap_servers=bootstrap,
            topic=topic,
            dlq_topic=dlq_topic,
            group_id=group_id,
            idle_timeout_seconds=0.5,
            max_messages=2,
        )
    )
    results: list[str] = []
    consumer.subscribe(topic, lambda item: results.append(ingestion.ingest(item)))
    assert results == ["duplicate_noop", "duplicate_noop"]
    assert consumer.consumed_keys == [event_id, event_id]
    assert repository.counts() == before

    restart_topic = f"fabops.m6.restart.{suffix}"
    restart_group = f"fabops-m6-restart-{suffix}"
    producer.publish(restart_topic, event)
    first = RedpandaEventBusAdapter(
        config=RedpandaConfig(
            bootstrap_servers=bootstrap,
            topic=restart_topic,
            dlq_topic=dlq_topic,
            group_id=restart_group,
            idle_timeout_seconds=0.5,
            max_messages=1,
            commit_on_success=False,
        )
    )
    first_results: list[str] = []
    first.subscribe(restart_topic, lambda item: first_results.append(ingestion.ingest(item)))
    second = RedpandaEventBusAdapter(
        config=RedpandaConfig(
            bootstrap_servers=bootstrap,
            topic=restart_topic,
            dlq_topic=dlq_topic,
            group_id=restart_group,
            idle_timeout_seconds=0.5,
            max_messages=1,
            commit_on_success=True,
        )
    )
    second_results: list[str] = []
    second.subscribe(restart_topic, lambda item: second_results.append(ingestion.ingest(item)))
    assert first_results == ["duplicate_noop"]
    assert second_results == ["duplicate_noop"]
    assert repository.counts() == before

    failure_topic = f"fabops.m6.failure.{suffix}"
    producer.publish(failure_topic, event)
    failing = RedpandaEventBusAdapter(
        config=RedpandaConfig(
            bootstrap_servers=bootstrap,
            topic=failure_topic,
            dlq_topic=dlq_topic,
            group_id=f"fabops-m6-failure-{suffix}",
            idle_timeout_seconds=0.5,
            max_messages=1,
            max_attempts=2,
        )
    )

    def fail_handler(_: dict[str, object]) -> None:
        raise RuntimeError("integration handler failure")

    failing.subscribe(failure_topic, fail_handler)
    assert failing.dlq_published_count == 1
