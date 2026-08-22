# FabOps Decision Lab — 5 Minute Demo

## Goal

Show the complete decision loop without implying real-fab operation or synthetic-to-real performance.

## 0:00–0:40 — Problem and boundary

Open the README/Workbench and state:

- primary user is a Yield/Process Engineer,
- objective is evidence-grounded excursion triage,
- synthetic FabTwin-Sim data drives the demo,
- PostgreSQL is the production-shaped authority,
- no equipment control exists,
- the deterministic core works with LLM off.

## 0:40–1:30 — Operations Overview

Show the case queue and highlight different classifications:

- physical excursion,
- sensor bias suspected,
- data-quality incident.

State that the deterministic simulator/evaluation keeps all six synthetic fault families **F1–F6** connected to the replay/evaluation story rather than presenting a single cherry-picked case.

Point to source timestamp, projection freshness and provenance labels.

## 1:30–2:20 — Excursion Case and Evidence Graph

Open a physical excursion case. Show:

- detector version/anomaly score,
- affected equipment/chambers,
- ranked RCA candidate,
- supporting evidence,
- contradicting evidence section,
- process lineage and measurement series.

Mention that the negative counter-evidence coverage metric is `0.42857`; the system does not hide that limitation.

## 2:20–3:10 — Advisory and governed workflow

Open Decision & Approval.

Show:

- advisory provider version,
- LLM disabled,
- tool calls capped at five,
- proposal-only safety boundary.

Create a diagnostic proposal and approve it as the configured human role. Emphasize that approval changes the governed case/audit state only; it does not send a command to equipment.

## 3:10–4:10 — Replay, integration and release identity

Open Replay & Operations. Show:

- event/detection/projection checkpoints,
- delivery status,
- PostgreSQL/Redpanda/Neo4j integration state,
- release `0.6.0` and canonical release hash.

Explain that the local container integration suite actually ran against those dependencies and that Neo4j remains a rebuildable projection.

## 4:10–4:45 — Reliability evidence

Show `evidence/m6/incident-projection-outage.json` or the postmortem:

- actual Neo4j stop,
- readiness degraded,
- PostgreSQL remained authoritative,
- recovery measured after restart.

Mention replay completeness `1.0` and duplicate side-effect rate `0.0` for the measured local replay artifact.

## 4:45–5:00 — Close with claims boundary

State explicitly:

- not a real fab,
- not Samsung/internal data,
- no synthetic-to-real claim,
- no actual equipment control,
- external LLM not required.

End on `bash scripts/verify.sh` as the single reproducible release gate.
