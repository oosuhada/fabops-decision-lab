# M6 Incident Exercise — Neo4j Projection Outage

## Summary

On 2026-08-22, the isolated M6 Compose environment executed a real dependency-outage exercise by stopping only the FabOps Neo4j container. This was a portfolio reliability exercise, not a real-fab incident. PostgreSQL remained the configured authoritative source of truth throughout the exercise, and no equipment-control capability existed or was affected.

Generated evidence: `evidence/m6/incident-projection-outage.json`.

## What was executed

1. Started the isolated FabOps M6 Compose stack and confirmed `ready=true`.
2. Executed the project-scoped equivalent of `docker compose ... stop neo4j`.
3. Polled API readiness until it reported degraded and `neo4j_runtime_verified=false`.
4. Confirmed PostgreSQL remained configured as authoritative source of truth.
5. Started the same Neo4j service again.
6. Polled until API readiness returned to `ready=true`.
7. Shut down only the isolated FabOps M6 Compose stack.

## Measured behavior

- Healthy before injection: `true`
- Degraded state detected: `true`
- Neo4j verified during outage: `false`
- PostgreSQL remained authoritative: `true`
- Source-of-truth affected: `false`
- Outage detection after stop completed: `0.053 s`
- Recovery after Neo4j start: `11.805 s`
- Equipment control affected: `false`

These timings are local M6 measurements on the developer machine. They are not production RTO measurements and are not claims about a real semiconductor fab.

## Expected safety property

Neo4j is a rebuildable read projection. Its outage must make RCA/readiness visibly degraded rather than causing the application to pretend that the projection is fresh or silently switch production authority to an in-memory/SQLite store. The exercise observed that expected behavior.

## Detection and diagnosis

The `/health/ready` response exposed the failed Neo4j integration check. The API process itself remained live, demonstrating why liveness alone is not sufficient for release readiness.

## Recovery

Recovery required restoring the projection dependency. The adapter re-established health after the Neo4j service became available and readiness returned without changing the PostgreSQL authority model.

## Follow-up controls

- Keep projection freshness and dependency health in canonical verification and future burn-in collection.
- Keep PostgreSQL authoritative and Neo4j rebuildable in architecture fitness tests.
- Do not classify a graph outage as an excuse for silent local fallback.
- Re-run the exercise after deployment changes that affect Neo4j driver, health checks, Compose dependency ordering or runtime composition.
