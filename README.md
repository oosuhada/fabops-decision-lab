# FabOps Decision Lab — Evidence-Grounded Yield Excursion Triage

반도체 수율 이상 대응을 위한 **evidence-grounded engineering decision platform** 포트폴리오입니다. 재현 가능한 synthetic fab 이벤트를 기반으로 ingest → deterministic detection → RCA projection → advisory → human approval → audit/replay/evaluation을 하나의 검증 가능한 의사결정 루프로 연결합니다.

FabOps Decision Lab is a portfolio-scale engineering decision platform for yield-excursion triage. It connects deterministic synthetic events, source-of-truth persistence, explainable RCA, human-governed workflow, replay, observability and release evidence without requiring an external LLM.

> **Live Demo — GOVERNED PUBLIC CANDIDATE:** https://fabops-preview.oosu.dev  
> The public UI is a **v0.7 candidate** running beside the still-authoritative `0.6.0` M8 soak target. Portfolio data is synthetic. GET/HEAD decision data is cache-only/deterministic and workflow mutation remains blocked at ingress. Live AI wording is available only through predefined bounded demo intents with signed anonymous sessions, application/edge rate limits, provider concurrency and daily budgets. AI wording cannot change the deterministic recommendation, and the demo exposes **NO TOOL CONTROL** or equipment execution. v0.7 is not an official release yet.

<!-- RELEASE_IDENTITY_START -->
> Release `0.6.0` · canonical release hash `ab8b20a696b9b1996495f23a3e413cc33a67b6861efa184c64742e0f310c6326` · source commit `6824ca11198a`
> Generated from `evidence/release/release-manifest.json`; this block is updated by `python -m evaluation.release_manifest`.
<!-- RELEASE_IDENTITY_END -->

## Problem / 문제

Primary user: **Yield / Process Engineer** responding to an excursion under time pressure.

The platform is designed to help answer four questions within a compact engineering workflow:

1. Is this a physical process excursion, sensor/data-quality problem, or insufficient evidence?
2. Which Lot / Wafer / Step / Equipment / Chamber is affected?
3. What evidence supports or contradicts each RCA candidate?
4. What diagnostic or containment proposal should a human approve, reject, or defer?

## Decision loop / 의사결정 루프

```text
FabTwin-Sim synthetic events
        ↓
Schema validation + idempotent ingestion
        ↓
PostgreSQL authoritative event/case/audit state
        ↓
Deterministic SPC/EWMA detection
        ↓
Neo4j rebuildable RCA projection
        ↓
Evidence-grounded RCA + five-tool advisory layer
        ↓
Human proposal / approval / rejection / close
        ↓
Append-only audit + replay + evaluation + telemetry
```

Redpanda/Kafka is the at-least-once transport boundary. PostgreSQL remains authoritative. Neo4j is a rebuildable read projection and is never treated as source of truth.

## Architecture / 아키텍처

| Layer | Responsibility | Authority |
|---|---|---|
| Simulator | deterministic synthetic F1–F6 event traces | synthetic source only |
| Ingestion | schema validation, quarantine, idempotency, outbox/checkpoints | persists authoritative inputs |
| PostgreSQL | event log, cases, audit, outbox, quarantine, checkpoints | **production source of truth** |
| Detection | deterministic SPC/EWMA anomaly logic | owns anomaly score/classification |
| Redpanda | publish/consume/reconsume transport | non-authoritative transport |
| Neo4j | traceability/RCA graph | rebuildable projection |
| Advisory | evidence retrieval and recommendation | advisory only |
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
| M8 Burn-in & Recovery Proof | IN PROGRESS |

The detailed execution ledger is in `ROADMAP.md`.

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

docker compose --env-file infra/.env -f infra/docker-compose.yml config --quiet
docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --build
curl -fsS http://127.0.0.1:8000/health/ready
docker compose --env-file infra/.env -f infra/docker-compose.yml down
```

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

## Topics

[`semiconductor`](https://github.com/topics/semiconductor) · [`semiconductor-manufacturing`](https://github.com/topics/semiconductor-manufacturing) · [`industrial-ai`](https://github.com/topics/industrial-ai) · [`yield-analysis`](https://github.com/topics/yield-analysis) · [`root-cause-analysis`](https://github.com/topics/root-cause-analysis) · [`decision-support`](https://github.com/topics/decision-support) · [`evidence-based`](https://github.com/topics/evidence-based) · [`event-driven-architecture`](https://github.com/topics/event-driven-architecture) · [`cqrs`](https://github.com/topics/cqrs) · [`postgresql`](https://github.com/topics/postgresql) · [`neo4j`](https://github.com/topics/neo4j) · [`redpanda`](https://github.com/topics/redpanda) · [`fastapi`](https://github.com/topics/fastapi) · [`react`](https://github.com/topics/react) · [`python`](https://github.com/topics/python) · [`typescript`](https://github.com/topics/typescript) · [`observability`](https://github.com/topics/observability) · [`human-in-the-loop`](https://github.com/topics/human-in-the-loop) · [`digital-twin`](https://github.com/topics/digital-twin) · [`anomaly-detection`](https://github.com/topics/anomaly-detection)
