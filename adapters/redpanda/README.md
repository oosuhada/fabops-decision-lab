# Redpanda integration contract

Core regression uses the deterministic in-memory bus. The production-facing adapter
keeps Kafka-compatible key/value serialization isolated from domain code.

When Docker is available, run the separately marked integration profile after
starting `infra/docker-compose.yml`. The event key is `event_id`, which preserves a
stable partitioning key for duplicate/replay behavior. Invalid records are routed to
`fabops.events.dlq.v1`; core quarantine remains persisted in PostgreSQL.

