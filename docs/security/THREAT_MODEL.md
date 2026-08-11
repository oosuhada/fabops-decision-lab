# FabOps Decision Lab Threat Model

## Scope and trust boundary

FabOps Decision Lab is a portfolio decision-support system, not a manufacturing control plane. The production-shaped composition has PostgreSQL as authoritative event/case/audit state, Redpanda/Kafka as at-least-once transport, Neo4j as a rebuildable RCA projection, a FastAPI backend, and a browser workbench. The deterministic core works with the optional external LLM disabled. There is no route or service that executes physical equipment commands.

The public-ingress boundary, if one is configured in a later deployment milestone, terminates before the application. PostgreSQL, Redpanda and Neo4j must remain private to the application network. M6 local Compose binds only API/Web to `127.0.0.1`.

## Assets

- Authoritative event log, cases, append-only decision audit, outbox, quarantine records and checkpoints.
- Approval decisions and their audit history. Approval tokens are credentials and must never be logged or placed in evidence.
- Projection freshness and provenance labels used to prevent stale or misleading RCA conclusions.
- Release/evaluation evidence and version identity.
- Deployment credentials supplied only through server-side environment files.

## Threats and controls

| Threat | Failure mode | Primary controls | Residual risk |
|---|---|---|---|
| Malicious or invalid event input | Schema bypass, malformed payload, poisoned state | JSON Schema validation, quarantine, idempotent event reservation, explicit provenance | Valid-but-misleading values still require domain validation beyond this portfolio |
| Replay / duplicate abuse | Duplicate cases, audit or outbox side effects | Unique event IDs, idempotent reservation, measured replay completeness and duplicate side-effect rate | Broker-level denial of service is not load-tested at production scale |
| Prompt/tool misuse | Agent fabricates RCA or acts outside authority | Deterministic tool registry capped at five, advisory-only provider, evidence-required claims, external LLM optional | A future external LLM integration needs separate prompt-injection testing |
| Approval-token misuse | Credential replay or disclosure | Server-side issuer, policy version binding, secret redaction, no raw token telemetry/evidence | Current local fixture issuer is explicitly non-production |
| Stale projection | Reviewer acts on incomplete Neo4j read model | Projection checkpoint/lag, readiness degradation, rebuild from PostgreSQL | Cross-region lag is outside M6 scope |
| Broker outage | Delayed ingestion / reconsume | At-least-once handling, idempotency, DLQ contract, readiness state | Multi-broker HA is not measured in M6 |
| Database outage | Authoritative state unavailable | No silent fallback to SQLite/in-memory production mode, readiness fails closed | Production HA/failover is not claimed |
| Graph outage | RCA view unavailable while source remains safe | Neo4j non-authoritative, health/readiness degrade, executable outage/recovery incident test | RCA is temporarily unavailable until projection recovers |
| Secret leakage | Credentials enter Git, logs or evidence | `.gitignore`, server-only `.env`, redaction, placeholder `.env.example`, candidate audit | Host compromise is outside application controls |
| Telemetry leakage | Sensitive fields copied into spans/logs | Allow-listed structured fields, recursive redaction, tests proving no `ground_truth` or approval-token material | New fields require continuing schema review |
| Dependency compromise | Malicious package or image | Locked Python/npm dependencies, npm audit, image/version pinning, dependency license inventory | Full SBOM/signature verification remains future hardening |
| Public ingress abuse | Unauthorized Internet access | No M6 public ingress; later deployment must expose only API/Web through existing controlled ingress | WAF/rate-limit policy is deployment-specific |

## Abuse cases explicitly rejected

- An advisory agent cannot own anomaly score, authorization, case state or equipment execution.
- A failed production dependency must not trigger an in-memory or SQLite production fallback.
- `ground_truth` is evaluation-only and cannot be imported by operational code or exposed through release UI/API.
- Synthetic data must not be presented as Samsung/internal-fab data or as synthetic-to-real performance evidence.

## Verification

Run `uv run python -m evaluation.m6_fitness --output-dir evidence/m6`. The generated `architecture-fitness-summary.json` is the executable control evidence for the architectural invariants above.
