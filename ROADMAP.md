# FabOps Decision Lab Delivery Roadmap

This file is the persistent execution ledger for the portfolio release. Exactly one
milestone is marked `IN PROGRESS` while implementation is active.

| Milestone | Status | Exit evidence |
|---|---|---|
| M0 Foundation audit/regression | PASSED | `evidence/m0-gate.json` |
| M1 FabTwin-Sim | PASSED | `evidence/m1-gate.json` |
| M2 Stream, Persistence & Detection | PASSED | `evidence/m2-gate.json` |
| M3 Traceability, CQRS & RCA | PASSED | `evidence/m3-gate.json` |
| M4 Governed Workflow & Workbench | PASSED | `evidence/m4-gate.json` |
| M5 Evaluation & Release Gates | PASSED | `evidence/m5-gate.json` |
| M6 Reliability & Portfolio Release | PASSED | `evidence/m6-gate.json` |
| M7 Mac mini Deployment | PASSED | `evidence/m7-gate.json` |
| M8 Burn-in & Recovery Proof | IN PROGRESS | `evidence/m8/soak-manifest.json` |

### M6 execution ledger

| Sub-gate | Status | Evidence |
|---|---|---|
| M6-A Telemetry & Reliability Core | PASSED | `evidence/m6/telemetry-summary.json`, `evidence/m6/reliability-summary.json`, `evidence/m6/trace-sample.json` |
| M6-B Performance, SLI/SLO & Recovery | PASSED | `evidence/m6/performance-summary.json`, `evidence/m6/recovery-summary.json`, `docs/operations/SLO.md` |
| M6-C Runnable Stack & Infrastructure | PASSED | `evidence/m6/integration-summary.json` |
| M6-D Security, Fitness & Operations | PASSED | `evidence/m6/architecture-fitness-summary.json`, `evidence/m6/attribution-audit.json`, `evidence/m6/incident-projection-outage.json` |
| M6-E Portfolio Release | PASSED | `evidence/release/release-manifest.json`, `evidence/m6/canonical-verification.json` |
| M6-F Git Hygiene & Final Local Gate | PASSED | `evidence/m6-gate.json` |

### M7 execution ledger

| Sub-gate | Status | Evidence |
|---|---|---|
| M7-A Mac mini Remote Preflight | PASSED | `evidence/m7/host-inventory.redacted.json` |
| M7-B Deployment Package | PASSED | `docs/operations/MAC_MINI_DEPLOYMENT.md`, `infra/macmini/docker-compose.yml` |
| M7-C Actual Deployment & Runtime Verification | PASSED | `evidence/m7/deployment-summary.json`, `evidence/m7/container-integration-summary.json`, `evidence/m7/existing-services-impact.json` |
| M7-D Backup / Restore / Rollback | PASSED | `evidence/m7/backup-restore-summary.json`, `evidence/m7/rollback-summary.json`, `evidence/m7-gate.json` |

### M8 execution ledger

| Sub-gate | Status | Evidence |
|---|---|---|
| M8-A 24h Burn-in Collector Setup | IN PROGRESS | `evidence/m8/soak-manifest.json` |
| M8-B 24h Burn-in Audit & Recovery Proof | NOT STARTED | future completed soak summary and recovery audit evidence |

## Execution discipline

Each milestone is implemented as a vertical slice and closes with test → repair →
full regression → generated evidence. External infrastructure is optional for the
core gate: deterministic local adapters are authoritative test doubles, while
Docker-backed integrations remain separately identified until actually executed.

