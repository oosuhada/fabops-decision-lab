# FabOps Decision Lab — Architecture Case Study

## 1. Problem

FabOps Decision Lab explores a narrow engineering decision problem: when a yield excursion appears, how can an engineer distinguish a physical process issue from sensor/data-quality behavior, trace affected scope, inspect supporting and contradicting evidence, and make a governed decision without allowing an AI layer to become the authority?

The project is intentionally not a real fab implementation. It is a portfolio system for demonstrating architecture, deterministic reasoning, evaluation discipline, reliability boundaries and honest claim management.

## 2. Primary user and decision pressure

The primary user is a Yield/Process Engineer. The interface is organized around an engineering decision loop rather than generic dashboards:

1. detect the excursion,
2. inspect scope and lineage,
3. rank RCA candidates,
4. inspect support and contradiction,
5. request more evidence or propose a diagnostic action,
6. require a human approval/rejection transition,
7. preserve the audit/replay record.

## 3. Constraints

The project imposed several non-negotiable architecture constraints:

- deterministic core behavior must work with the external LLM disabled,
- operational code must not import hidden `ground_truth`,
- PostgreSQL is the production-shaped source of truth,
- Redpanda/Kafka is transport rather than authority,
- Neo4j is a rebuildable projection rather than authority,
- the advisory agent cannot own anomaly score, authorization, case state or equipment execution,
- there is no production SQLite substitute,
- there is no actual equipment-control route,
- negative evaluation results remain visible.

## 4. Architecture decisions

### Modular monolith first

The domain/application logic remains a modular monolith. External-system boundaries are adapters rather than independently deployed microservices. This keeps evaluation and replay deterministic while preserving realistic production composition points.

### PostgreSQL as authoritative state

Event log, cases, append-only decision audit, outbox, quarantine and checkpoints are persisted through the PostgreSQL runtime adapter in integration mode. There is no silent fallback from failed production dependencies to SQLite/in-memory state.

### Redpanda for at-least-once transport

Redpanda carries event IDs as keys, supports consume/reconsume and exercises duplicate delivery behavior. The source-side idempotency contract prevents repeated case/audit side effects.

### Neo4j as disposable RCA projection

The graph projection can be deleted/rebuilt from PostgreSQL event state. Projection checkpoint/lag appears in readiness and the UI. A graph outage therefore degrades RCA/readiness rather than changing source-of-truth semantics.

### Deterministic advisory layer

The advisory layer is constrained to five tools. It retrieves evidence and recommends a next step, but it cannot mutate authoritative state. External LLM transport remains optional; the release gate works LLM-off.

## 5. Implementation slices

### M0–M1 — Foundation and deterministic simulation

Established source isolation, event contracts and FabTwin-Sim. Synthetic events preserve seed/config/generator identity, while hidden ground truth remains evaluation-only.

### M2 — Ingestion and detection

Added schema validation, quarantine, idempotent event reservation, outbox/checkpoints and deterministic SPC/EWMA detection.

### M3 — Traceability and RCA

Added the rebuildable graph projection, CQRS-style read path, transparent ranking and explicit supporting/contradicting evidence.

### M4 — Governed workflow and Workbench

Added evidence-grounded advisory, proposal/approval/rejection/close workflow, append-only audit and React Workbench screens.

### M5 — Evaluation gates

Added development/validation/held-out seed splits, unseen evidence-gap abstention behavior and checked-in release metrics.

### M6 — Reliability and portfolio release

Added trace/correlation telemetry, readiness, external-boundary circuit breaker/bulkhead, subprocess replay proof, measured local benchmark, PostgreSQL/Redpanda/Neo4j container integration, architecture fitness, security/operations documents, incident exercise and release identity tooling.

## 6. Measurements

### Held-out evaluation

- detector fault recall: `1.0`
- RCA Top-1: `1.0`
- tool selection accuracy: `1.0`
- unsupported claim rate: `0.0`
- unsafe action proposal rate: `0.0`

### Known negative result

RCA contradicting-evidence coverage is `0.42857`. The fixture often provides enough support to rank the correct candidate but does not provide explicit counter-evidence for every candidate. The project keeps this visible because hiding the result would make the portfolio less credible.

### Local reliability/performance profile

- ingestion throughput: about `25,104 events/s`
- ingest→detection p95: about `0.0489 ms`
- replay completeness: `1.0`
- duplicate side-effect rate: `0.0`
- local subprocess recovery RTO p95: about `64.176 ms`
- local snapshot-scope RPO: `0 events`

These are developer-machine measurements of a bounded synthetic test profile, not real-fab or production-capacity claims.

### Container integration

An isolated local Compose run actually verified PostgreSQL, Redpanda and Neo4j runtime adapters and recorded `4 passed` for the container integration suite. An API restart was also verified.

### Executed incident

Neo4j was actually stopped in the project stack. Readiness degraded while PostgreSQL remained authoritative; after Neo4j restart, readiness recovered in `11.805 s` in that measured run.

## 7. Failure/negative-result handling

This project treats failure evidence as part of the artifact:

- the first Redpanda init command failed because the image entrypoint interpreted shell flags as `rpk` flags; Compose was corrected and rerun,
- the first Neo4j incident harness used the wrong host API port and failed before injection; it was corrected and rerun rather than reported as success,
- architecture tests discovered that the benchmark unit test was rewriting canonical `SLO.md`; the generator gained an explicit `slo_path` so tests write only to temporary paths,
- the 0.42857 contradicting-evidence coverage remains a documented negative result.

## 8. Security and fitness

Executable architecture fitness checks verify:

- no direct/transitive operational `ground_truth` import,
- PostgreSQL production repository wiring,
- Neo4j rebuildability/non-authority,
- advisory state-mutation prohibition,
- no equipment-execution route,
- five-tool maximum,
- no release UI/API ground-truth exposure,
- no production SQLite adapter,
- explicit provenance labels.

The threat model additionally covers invalid input, replay abuse, prompt/tool misuse, approval-token misuse, stale projection, dependency outage, secret/telemetry leakage, dependency compromise and future ingress boundaries.

## 9. Provenance and claim boundaries

UCI SECOM, WM-811K and AI4I are reality anchors rather than embedded release-scoring data. Anonymous SECOM features are not assigned invented fab semantics. Synthetic inspection/sensor traces do not claim real WM-811K lineage. Palantir/Foundry is an interaction-grammar reference only, not branded/pixel/source-code copying. No Samsung/internal fab data is claimed or used.

## 10. Remaining limitations

- Synthetic test profiles cannot demonstrate synthetic-to-real transfer.
- M6 local performance timing is not PostgreSQL/Redpanda/Neo4j production capacity.
- Multi-node broker/database/graph HA is not implemented or measured.
- Public ingress is intentionally deferred to deployment work.
- External LLM quality/security is not a release dependency because the core runs LLM-off.
- Real semiconductor process-physics fidelity is outside the portfolio scope.

## 11. What this case study is intended to show

The strongest portfolio signal is not a single metric. It is the connected system of architecture decisions, explicit authority boundaries, deterministic replay, evaluation discipline, runtime adapters, measured failure/recovery behavior, security/fitness checks and visible limitations.
