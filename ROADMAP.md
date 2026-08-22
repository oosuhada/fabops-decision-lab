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
| M6 Reliability & Portfolio Release | IN PROGRESS | `evidence/m6-gate.json` |

## Execution discipline

Each milestone is implemented as a vertical slice and closes with test → repair →
full regression → generated evidence. External infrastructure is optional for the
core gate: deterministic local adapters are authoritative test doubles, while
Docker-backed integrations remain separately identified until actually executed.

