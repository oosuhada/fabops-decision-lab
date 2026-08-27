# FabOps Decision Lab — Evidence-Grounded Yield Excursion Triage

**Live demo / 라이브 데모:** https://fabops-preview.oosu.dev

반도체 수율 이상 대응을 위한 **evidence-grounded engineering decision platform** 포트폴리오입니다. 재현 가능한 synthetic fab 이벤트를 기반으로 ingest → deterministic detection → persistent RCA projection → learned prediction → situation assessment → human approval → audit/replay/evaluation을 하나의 검증 가능한 의사결정 루프로 연결합니다.

FabOps Decision Lab is a portfolio-scale decision-intelligence workbench for semiconductor yield-excursion triage. The current public candidate combines deterministic evidence, temporal prediction semantics, incident-level prioritization, a durable local-LLM queue, bounded adaptive visualization and human-governed decisions without giving AI equipment-control authority.

> **Governed public candidate:** `0.6.0-v0.9-intelligence-candidate` runs beside the authoritative `0.6.0` release line. Portfolio data and measured model results are synthetic. AI wording cannot change deterministic recommendation identity, workflow authority remains human, and the public preview exposes **NO EQUIPMENT CONTROL**.

<!-- RELEASE_IDENTITY_START -->
> Release `0.6.0` · canonical release hash `ab8b20a696b9b1996495f23a3e413cc33a67b6861efa184c64742e0f310c6326` · source commit `6824ca11198a`
> Generated from `evidence/release/release-manifest.json`; this block is updated by `python -m evaluation.release_manifest`.
<!-- RELEASE_IDENTITY_END -->

## Overview / 개요

The workbench is organized around three operating questions rather than around model output alone:

- **Ⅰ Decide** — what needs a human decision now, and what deterministic guardrails bound that decision?
- **Ⅱ Investigate** — which source-linked measurements, process steps, alarms and RCA relationships explain the case?
- **Ⅲ Trust** — is the projection fresh, which model/evidence version produced the output, and what is still uncertain?

The candidate keeps source truth, deterministic computation, learned prediction, AI wording and human authority visibly separate. It also keeps legacy model history for audit while exposing only semantic-v2 predictions in the current operational API/UI.

## Product walkthrough / 제품 화면

### 1. Decision Cockpit — raw cases to a small set of human decisions

![FabOps Decision Cockpit](docs/screenshots/01-decision-cockpit.png)

The cockpit combines incident/episode clustering, composite decision priority, POST_CMP learned predictions, projection freshness and the `HUMAN / NO EQUIPMENT CONTROL` boundary. Recurrent raw cases are correlated into operational episodes before entering the ranked decision queue.

### 2. Case Investigation — evidence before recommendation

![FabOps Case Investigation](docs/screenshots/02-case-investigation.png)

Case Investigation separates deterministic RCA hypotheses from supporting and contradicting evidence. Case detail is loaded first; advisory/replay context hydrates independently so secondary context no longer blocks the primary investigation surface.

### 3. Evidence Graph — bounded source-linked RCA projection

![FabOps Evidence Graph](docs/screenshots/03-evidence-graph.png)

The graph traces Lot → process run → chamber → measurement/alarm/inspection evidence through the rebuildable RCA read model. A dedicated projection worker persists a bounded live graph and checkpoint while older cases can still hydrate their lot-specific graph on demand.

### 4. Analysis Workbench — reproducible, read-only evidence analysis

![FabOps Analysis Workbench](docs/screenshots/04-analysis-workbench.png)

The analysis canvas builds a reproducible path from a locked input case through bounded filter, comparison, aggregation, chart and evidence-verification blocks. It cannot execute arbitrary SQL/code, mutate RCA ranking or change workflow state. The layout responds to the **actual work-surface width**, including when both side panes are pinned.

### 5. Decision & Approval — AI wording around deterministic guardrails

![FabOps Decision and Approval](docs/screenshots/05-decision-approval.png)

Decision & Approval keeps recommendation identity and action boundaries deterministic while allowing a bounded narration layer to explain the evidence for manager/engineer audiences. Final proposal/approval/rejection authority remains human-governed.

### 6. Model & Evidence — semantic-v2 provenance and promotion governance

![FabOps Model and Evidence](docs/screenshots/06-model-evidence.png)

The learned-intelligence view exposes feature-set/cutoff provenance, temporal TRAIN → CALIBRATION → SHADOW TEST partitions, calibration metrics and champion promotion decisions. Current prediction contracts are `final_yield`, `final_excursion_probability`, `next_lot_excursion_alarm_probability` and `next_lot_maintenance_attention_probability`; the last two are explicitly **not** equipment-failure probability or RUL.

### 7. System Health — projection, queue and runtime truthfulness

![FabOps System Health](docs/screenshots/07-system-health.png)

System Health surfaces persistent projection checkpoint/SLO state, runtime identity and local inference status without exposing credentials or private user prompts. Local Qwen availability is treated as READY/BUSY/WAITING rather than turning normal contention into a provider failure.

### 8. Guided case hydration — onboarding instead of a blank wait state

![FabOps guided case hydration](docs/screenshots/08-guided-case-hydration.png)

When a case is genuinely still loading, the workbench shows approximate staged progress plus rotating mini-previews of the screens the user can explore next. In-flight case-detail requests are deduplicated and cached across navigation, so already-hydrated cases switch between investigation surfaces without repeating the same network work.

## Current candidate capabilities / 현재 후보 기능

| Capability | Current implementation |
|---|---|
| Prediction semantics | `fabops-feature-set-v2`, explicit `POST_CMP` cutoff, `feature_timestamp < target_timestamp`, exact next-lot targets |
| Model governance | temporal TRAIN/CALIBRATION/SHADOW split, calibration metrics, same-shadow incumbent comparison, guarded champion promotion, CPU histogram challenger |
| Live simulation | seeded domain randomization on the live stream only; canonical deterministic fixtures remain unchanged |
| Incident intelligence | recurrent raw cases correlated into NEW/ONGOING/ESCALATING/RECOVERING/RESOLVED episodes before decision ranking |
| Situation intelligence | append-only `SituationAssessment` history with deltas, uncertainty, next investigations and validated visualization intent |
| Local AI | PostgreSQL durable inference queue → MacBook Pro gateway → LM Studio/Qwen3 Coder Next, concurrency 1, BUSY means wait rather than fail |
| Cloud fallback | automatic non-HIGH stays local-only; HIGH/manual can use bounded Vertex fallback only after the configured local wait/failure policy |
| Projection | dedicated projection worker → persistent bounded PostgreSQL RCA read model + checkpoint/SLO; API is a read-side consumer |
| Human feedback | prediction / human assessment / actual outcome persisted separately; feedback does not trigger ungoverned automatic retraining |
| UX/runtime | bounded overview/cockpit payloads, indexed case hydration, replay-by-lot lookup, in-flight request reuse, guided loading and work-surface container queries |

## Problem / 문제

Primary user: **Yield / Process Engineer** responding to an excursion under time pressure.

The platform is designed to help answer four questions within a compact engineering workflow:

1. Is this a physical process excursion, sensor/data-quality problem, or insufficient evidence?
2. Which Lot / Wafer / Step / Equipment / Chamber is affected?
3. What evidence supports or contradicts each RCA candidate?
4. What diagnostic or containment proposal should a human approve, reject, or defer?

## Decision loop / 의사결정 루프

```text
FabTwin-Sim synthetic + seeded live-regime events
        ↓
Schema validation + idempotent ingestion
        ↓
PostgreSQL authoritative event/case/audit state
        ↓
Deterministic SPC/EWMA detection
        ↓
Dedicated projection worker → persistent bounded RCA read model
        ↓
Evidence-grounded RCA + temporal feature/prediction loop
        ↓
Incident clustering + composite decision priority
        ↓
SituationAssessment + durable local-Qwen inference queue
        ↓
Human proposal / approval / rejection / close
        ↓
Append-only audit + replay + evaluation + telemetry
```

Redpanda/Kafka remains the at-least-once transport boundary and PostgreSQL remains authoritative. The current candidate uses a persistent bounded PostgreSQL RCA read model written by a dedicated projection worker; the Neo4j adapter remains part of the earlier release/integration verification surface and is still non-authoritative.

## Architecture / 아키텍처

| Layer | Responsibility | Authority |
|---|---|---|
| Simulator | deterministic synthetic F1–F6 event traces | synthetic source only |
| Ingestion | schema validation, quarantine, idempotency, outbox/checkpoints | persists authoritative inputs |
| PostgreSQL | event log, cases, audit, outbox, quarantine, checkpoints | **production source of truth** |
| Detection | deterministic SPC/EWMA anomaly logic | owns anomaly score/classification |
| Redpanda | publish/consume/reconsume transport | non-authoritative transport |
| Projection worker | incrementally materializes the bounded live RCA graph + checkpoint/SLO | rebuildable read model only |
| PostgreSQL RCA read model | current candidate traceability/RCA projection | non-authoritative projection |
| Neo4j adapter | retained release/integration projection path | non-authoritative projection |
| Advisory | evidence retrieval and recommendation | advisory only |
| Local inference queue | durable local-Qwen scheduling, BUSY/backoff/fallback state | wording/assessment only |
| Workflow | proposal/approval/rejection/close | human-governed state transition |
| Workbench | evidence, provenance, release/integration state | presentation only |

The advisory agent cannot own anomaly score, authorization, case state or equipment execution. The tool registry remains capped at five tools unless an ADR explicitly changes that boundary.

## Milestone status

| Milestone | Status |
|---|---|
| M0 Foundation audit/regression | PASSED |
| M1 FabTwin-Sim | PASSED |
| M2 Stream, Persistence & Detection | PASSED |
| M3 Traceability, CQRS & RCA | PASSED |
| M4 Governed Workflow & Workbench | PASSED |
| M5 Evaluation & Release Gates | PASSED |
| M6 Reliability & Portfolio Release | PASSED |
| M7 Mac mini Deployment | PASSED |
| M8 Burn-in & Recovery Proof | UNVERIFIED / GAP |

The detailed execution ledger is in `ROADMAP.md`.

M8 collected more than 24 hours of healthy API/Web availability with zero observed service restarts, zero projection lag and zero broker lag. One collector-only `TimeoutExpired` sample lacked Docker/container metadata while API and Web remained healthy and the immediately adjacent samples recovered normally. Because the pre-existing M8 runbook did not define a tolerance rule for that condition, the deterministic final audit records `UNVERIFIED / GAP` instead of inventing a PASS criterion. See `evidence/m8/final-audit-20260823T233943+0900.json`.

## Quick start / 빠른 시작

Requirements:

- Python 3.13 compatible environment
- `uv`
- Node.js 22+
- npm
- Chromium for Playwright E2E
- Docker only for container-backed PostgreSQL/Redpanda/Neo4j verification

```bash
uv sync --locked --dev
uv run pytest -q

cd systems/web
npm ci
npm run test
npm run build
cd ../..
```

Generate a deterministic synthetic trace:

```bash
uv run python -m simulator.generate --seed 42 --output evidence/sample
```

## Local Workbench

Fast local mode uses deterministic in-memory adapters while preserving the same domain boundaries:

```bash
uv run uvicorn systems.api.app:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd systems/web
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`.

The Workbench shows current projection freshness, container verification state, release version/hash, evaluation limitations, governed decision state and an explicit `NO EQUIPMENT CONTROL` boundary.

## Container-backed integration

M6 has actually verified the isolated local Compose stack with:

- PostgreSQL runtime adapter: verified
- Redpanda publish/consume/reconsume: verified
- Neo4j runtime projection and rebuild: verified
- API restart after integration initialization: verified
- container integration test: `4 passed`

PostgreSQL, Redpanda and Neo4j do not bind public host ports in the M6 Compose file. API/Web bind only to `127.0.0.1`.

Local setup:

```bash
cp infra/.env.example infra/.env
chmod 0600 infra/.env
# Replace placeholder values in infra/.env without committing the file.
# If 8000/5173 are already occupied, set FABOPS_API_PORT/FABOPS_WEB_PORT to free loopback ports.

docker compose --env-file infra/.env -f infra/docker-compose.yml config --quiet
uv run python -m evaluation.m6_integration --output /tmp/fabops-m6-container-integration.json --check
```

The M6 integration verifier reads only the non-secret `FABOPS_API_PORT` setting needed for its loopback readiness probe and defaults to `8000` for backward compatibility. It never copies `infra/.env` contents into evidence. Canonical verification also injects isolated free `FABOPS_E2E_API_PORT` / `FABOPS_E2E_WEB_PORT` values into Playwright so unrelated listeners on the normal development ports are not reused or stopped. Direct `npm run test:e2e` behavior remains unchanged and still defaults to `8000/5173` unless those E2E variables are provided.

## Canonical verification

The project has one release verification entry point:

```bash
bash scripts/verify.sh
```

It runs, at minimum:

- `uv sync --locked --dev`
- Ruff
- full Python regression
- held-out M5 release evaluation in a temporary output directory
- frontend `npm ci`, component tests, production build and dependency audit
- Chromium Playwright E2E
- M6 architecture fitness
- release-manifest consistency
- Docker integration when the daemon and local server-only env file are available; otherwise that boundary is reported explicitly as UNVERIFIED rather than passed
- clean-source-snapshot setup verification

Generated result: `evidence/m6/canonical-verification.json`.

## Evaluation / 평가

Held-out release evidence: `evidence/release/evaluation-summary.json`.

Current M5 held-out metrics:

| Metric | Result |
|---|---:|
| Detector fault recall | 1.0 |
| RCA Top-1 | 1.0 |
| RCA Top-3 | 1.0 |
| MRR | 1.0 |
| Tool selection accuracy | 1.0 |
| Required evidence retrieval | 1.0 |
| Unsupported claim rate | 0.0 |
| Unsafe action proposal rate | 0.0 |

### Known negative result — intentionally preserved

**RCA contradicting-evidence coverage = `0.42857`.**

The compact synthetic fixture does not provide explicit counter-evidence for every correct top candidate. This result is not hidden, rounded into a pass, or replaced by a subjective claim. It remains visible in M3/M5 evidence and the release documentation.

## Observability, performance and recovery

M6 telemetry uses a deterministic local structured recorder with OpenTelemetry-compatible trace/span identifiers and request correlation. `trace_id` is the causal/event identity; `correlation_id` is the operational request/workflow identity. Sensitive fields such as `ground_truth`, credentials and raw approval-token material are excluded/redacted.

Latest checked local portfolio benchmark:

| Measurement | Result | Scope |
|---|---:|---|
| Ingestion throughput | ~23,755 events/s | local deterministic in-memory profile |
| ingest→detection p50 | ~0.0391 ms | local deterministic callback timing |
| ingest→detection p95 | ~0.0518 ms | local deterministic callback timing |
| ingest→detection p99 | ~0.1037 ms | local deterministic callback timing |
| Projection lag after rebuild | 0 events | local projection rebuild |
| Replay completeness | 1.0 | local subprocess snapshot/replay |
| Duplicate side-effect rate | 0.0 | measured duplicate attempts |
| Local recovery RTO p95 | ~69.537 ms | fresh Python process + snapshot restore + projection rebuild |
| Local source-log RPO | 0 events | events already persisted in the measured snapshot |

These numbers are **not** PostgreSQL/Neo4j/Redpanda production capacity claims. Detailed definitions and limits are in `docs/operations/SLO.md`.

### Executed incident exercise

The M6 Neo4j dependency outage exercise actually stopped the project Neo4j container, observed degraded readiness, restarted it, and observed recovery:

- outage detection after stop completed: `0.053 s`
- recovery after Neo4j start: `11.805 s`
- PostgreSQL remained authoritative: `true`
- equipment control affected: `false`

Evidence: `evidence/m6/incident-projection-outage.json` and `docs/postmortems/M6_NEO4J_PROJECTION_OUTAGE.md`.

## Provenance / 데이터 출처 경계

### What is real

- Public-project/dataset reality anchors such as UCI SECOM, WM-811K and AI4I are used only as external context/reality anchors.
- Standard open-source runtime/dependency behavior is real software behavior and is tracked by package metadata/lock files.

No public dataset bytes are embedded in the release-scoring fixtures.

### What is synthetic

- FabTwin-Sim process, sensor, alarm, maintenance, inspection and delivery events.
- F1–F6 fault-family traces generated from explicit seed/config/generator versions.
- Synthetic SOP/past-case fixtures used by the advisory tools.

### What is inferred

- Detection classifications and anomaly scores.
- RCA ranking/supporting/contradicting evidence.
- Advisory text and recommendations.
- Evaluation metrics calculated from synthetic held-out fixtures.

### What is NOT claimed

- This is **not a real semiconductor fab**.
- This is **not Samsung data** and does not use Samsung/internal-fab data.
- There is **no synthetic-to-real performance claim**.
- There is **no real WM-811K ↔ synthetic sensor lineage**.
- Anonymous SECOM features are **not assigned invented semiconductor process semantics**.
- Palantir/Foundry influenced interaction grammar only; there is no branded, pixel-level or source-code copy claim.
- There is **no actual equipment control**, automatic recipe change, physical tool mutation or production MES actuation route.
- The core workflow does **not require an external LLM**.

## Security and operations

- Threat model: `docs/security/THREAT_MODEL.md`
- Secret policy: `docs/security/SECRET_POLICY.md`
- Local/container runbook: `docs/operations/RUNBOOK.md`
- SLI/SLO definitions: `docs/operations/SLO.md`
- Architecture fitness evidence: `evidence/m6/architecture-fitness-summary.json`
- Attribution audit: `evidence/m6/attribution-audit.json`

## Portfolio case-study material

- `docs/portfolio/ARCHITECTURE_CASE_STUDY.md`
- `docs/portfolio/DEMO_5_MIN.md`
- `docs/portfolio/ARCHITECTURE_DEEP_DIVE_30_MIN.md`

These documents are designed so a reviewer can trace problem → constraints → architecture decisions → implementation → negative results → measurements → remaining limitations without treating synthetic evidence as a production-fab claim.

## Repository map

```text
services/       deterministic domain/application services
adapters/       PostgreSQL, Redpanda and Neo4j boundaries
systems/api/    FastAPI runtime composition and HTTP boundary
systems/web/    React engineering workbench
simulator/      deterministic FabTwin-Sim
evaluation/     release evaluation, M6 benchmark/fitness/release tooling
infra/          isolated local Compose/Dockerfiles
docs/           ADR, security, operations, portfolio case study
evidence/       generated gate/release evidence
tests/          deterministic regression and architecture gates
```

## License / attribution note

Dependency and reference attribution state is generated in `evidence/m6/attribution-audit.json`. This repository does not claim third-party dataset ownership or proprietary fab lineage.

## Architecture & Topics / 아키텍처 및 주제

**Architecture / 아키텍처**<br>
[`modular-monolith`](https://github.com/topics/modular-monolith) · [`event-driven-architecture`](https://github.com/topics/event-driven-architecture) · [`cqrs`](https://github.com/topics/cqrs) · [`hexagonal-architecture`](https://github.com/topics/hexagonal-architecture) · [`adapter-pattern`](https://github.com/topics/adapter-pattern) · [`repository-pattern`](https://github.com/topics/repository-pattern) · [`transactional-outbox`](https://github.com/topics/transactional-outbox) · [`idempotency`](https://github.com/topics/idempotency) · [`rebuildable-projection`](https://github.com/topics/rebuildable-projection) · [`polyglot-persistence`](https://github.com/topics/polyglot-persistence) · [`state-machine`](https://github.com/topics/state-machine) · [`circuit-breaker`](https://github.com/topics/circuit-breaker) · [`bulkhead-pattern`](https://github.com/topics/bulkhead-pattern) · [`human-in-the-loop`](https://github.com/topics/human-in-the-loop) · [`observability`](https://github.com/topics/observability) · [`architecture-fitness-functions`](https://github.com/topics/architecture-fitness-functions)

**Core technologies / 핵심 기술**<br>
[`neo4j`](https://github.com/topics/neo4j) · [`redpanda`](https://github.com/topics/redpanda)

**Project context / 프로젝트 맥락**<br>
[`anomaly-detection`](https://github.com/topics/anomaly-detection) · [`decision-support`](https://github.com/topics/decision-support) · [`digital-twin`](https://github.com/topics/digital-twin) · [`evidence-based`](https://github.com/topics/evidence-based) · [`industrial-ai`](https://github.com/topics/industrial-ai) · [`root-cause-analysis`](https://github.com/topics/root-cause-analysis) · [`semiconductor`](https://github.com/topics/semiconductor) · [`semiconductor-manufacturing`](https://github.com/topics/semiconductor-manufacturing) · [`yield-analysis`](https://github.com/topics/yield-analysis)

**Implementation stack / 구현 스택**<br>
[`fastapi`](https://github.com/topics/fastapi) · [`postgresql`](https://github.com/topics/postgresql) · [`python`](https://github.com/topics/python) · [`react`](https://github.com/topics/react) · [`typescript`](https://github.com/topics/typescript)
