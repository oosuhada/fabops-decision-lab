# FabOps Decision Lab — 30 Minute Architecture Deep Dive

## 0–3 min — Problem framing

Explain the excursion-triage decision: classify physical vs data-quality behavior, determine affected scope, evaluate RCA evidence, recommend the next diagnostic step and require human governance.

Clarify the portfolio claim boundary immediately: synthetic event generation, no real-fab data/control, no Samsung/internal data, no synthetic-to-real benchmark claim.

## 3–7 min — Domain and authority boundaries

Walk through the modular-monolith architecture and the authority model:

- PostgreSQL: authoritative event/case/audit/outbox/quarantine/checkpoint state,
- Redpanda: at-least-once transport,
- Neo4j: rebuildable projection,
- deterministic detector: anomaly score/classification owner,
- advisory: evidence retrieval/recommendation only,
- workflow: governed human transitions,
- Workbench: presentation, provenance and operational state.

Explain why a failed production dependency never silently falls back to SQLite/in-memory production state.

## 7–11 min — Determinism and simulator design

Show seed/config/generator identity and the F1–F6 trace families. Explain why hidden ground truth is isolated from operational code and only used for evaluation.

Discuss the difference between:

- causal/event `trace_id`,
- operational request/workflow `correlation_id`.

## 11–15 min — Ingestion, detection and replay

Trace one event through:

1. schema validation,
2. idempotent reservation,
3. event persistence,
4. deterministic detector callback,
5. checkpoint/outbox,
6. case materialization/audit.

Show replay evidence: case/audit hash identity, replay completeness `1.0`, duplicate side-effect rate `0.0` and fresh subprocess recovery rather than a same-process fake restart.

## 15–19 min — RCA projection and advisory governance

Show how the graph is rebuilt from source events and how RCA rankings expose supporting and contradicting evidence. Explain the five-tool advisory limit and the prohibited capabilities list.

Discuss the known negative result: contradicting-evidence coverage `0.42857`. Explain why it remains visible and what additional fixture diversity would be required to improve it legitimately.

## 19–22 min — Production-shaped adapters and Compose

Show:

- PostgreSQL migrations/repository,
- Redpanda publish/subscribe lifecycle,
- Neo4j driver projection,
- explicit integration runtime composition,
- health/readiness behavior,
- private dependency ports and localhost API/Web binds.

Mention that the container integration test actually passed against all three dependencies.

## 22–25 min — Observability and incident behavior

Show structured telemetry fields and redaction rules. Explain circuit breaker/bulkhead placement only at external boundaries.

Then show the executed Neo4j outage incident:

- graph service stopped,
- readiness degraded,
- PostgreSQL authority preserved,
- graph restarted,
- readiness recovered.

Contrast liveness with readiness.

## 25–27 min — Performance and SLO interpretation

Review the local benchmark and carefully scope it:

- ~23.8k events/s local deterministic ingestion,
- sub-millisecond ingest→detector latency,
- 0-event projection lag after rebuild,
- local subprocess RTO p95 ~69.5 ms,
- snapshot-scope RPO 0.

Explicitly state that these are not production database/broker/graph capacity metrics.

## 27–29 min — Security, provenance and release identity

Show the architecture fitness summary and attribution audit. Cover:

- ground-truth import isolation,
- no equipment execution route,
- no production SQLite adapter,
- provenance labels,
- dependency license metadata,
- SECOM/WM-811K/AI4I reference-only role,
- Palantir/Foundry interaction-grammar reference only.

Show the release manifest's canonical hash definition and why the manifest bytes/generated timestamp are excluded from the release hash to avoid self-reference.

## 29–30 min — Verification and remaining limitations

Close with `bash scripts/verify.sh` and the remaining limitations:

- synthetic-only evaluation,
- no multi-node HA proof,
- no real-fab physics fidelity,
- public ingress/deployment handled separately,
- external LLM remains optional.

The review criterion is whether the architecture/evidence supports the stated claims, not whether the portfolio imitates a real fab UI or claims inaccessible production data.
