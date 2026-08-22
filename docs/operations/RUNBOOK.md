# FabOps Decision Lab Operations Runbook

## Operating boundary

FabOps is decision support only. No runbook action sends holds, recipe changes or equipment commands to a real fab. PostgreSQL is authoritative; Neo4j is disposable/rebuildable projection state; Redpanda is transport. Never replace a failed production dependency with SQLite or hidden in-memory state.

## Local M6 Compose

Create a local server-only `infra/.env` from `infra/.env.example`, replace placeholders, and set `chmod 0600 infra/.env`.

```bash
docker info
docker compose --env-file infra/.env -f infra/docker-compose.yml config --quiet
docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --build
curl -fsS http://127.0.0.1:18000/health/live
curl -fsS http://127.0.0.1:18000/health/ready
docker compose --env-file infra/.env -f infra/docker-compose.yml ps
```

Stop only this project stack:

```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml down
```

Do not add `-v` during normal stop/restart because authoritative local test state may be needed for recovery exercises.

## Readiness interpretation

- `ready=true`: source checkpoint, projection freshness, advisory registry and configured integration dependencies are healthy.
- `status=degraded`: inspect `source_of_truth`, `projection`, and `integration` separately. A running FastAPI process alone is not readiness.
- `equipment_control_enabled` must always be `false`.

## Projection outage

If Neo4j is unavailable, do not mutate PostgreSQL to compensate and do not claim RCA freshness. Restore Neo4j, then rebuild the projection from PostgreSQL through the projection worker/integration verification path. The M6 reproducible exercise is:

```bash
uv run python -m evaluation.m6_incident --output evidence/m6/incident-projection-outage.json
```

Expected behavior: readiness becomes degraded while PostgreSQL remains configured as source of truth, then returns ready after Neo4j recovery. The evidence records measured detection/recovery durations.

## Broker incident

When Redpanda is unavailable, readiness must report the dependency degraded. After restart, reconsume with the same event IDs; PostgreSQL idempotency must keep duplicate case/audit side effects at zero. Invalid events go to quarantine/DLQ according to the adapter boundary.

## API restart and replay

Use the project-specific Compose service restart and then verify `/health/ready`. Local subprocess replay evidence is not equivalent to PostgreSQL process recovery; container-backed claims are made only when the integration harness actually ran.

## Logs and secrets

Prefer structured API logs and project-scoped `docker compose logs`. Never paste environment dumps or credential-bearing DSNs into tickets/evidence. Approval-token raw material is sensitive even in a local portfolio environment.

## Escalation

Stop the FabOps stack and preserve evidence if authoritative PostgreSQL integrity is uncertain, if duplicate side effects are observed, if `ground_truth` appears in operational output, or if equipment-control behavior is ever introduced. Those are release-blocking invariant failures, not degradations to work around.
