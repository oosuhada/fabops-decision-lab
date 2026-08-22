# FabOps Continuous Runtime

## Purpose

The live profile turns the deterministic FabTwin portfolio fixture into a continuously changing operational demo without replacing PostgreSQL authority, deterministic detection, RCA traceability, or the human decision boundary.

The default Compose stack remains unchanged unless the `live` profile is explicitly enabled.

## Runtime flow

```text
FabTwin deterministic scenario
        ↓ accelerated wall-clock adapter
live-simulator
        ↓
Redpanda
        ↓
stream-worker
        ├── PostgreSQL event/case authority
        ├── online SPC/EWMA detection
        └── incremental Neo4j projection
        ↓
API live status + transparent forecast baseline
        ↓
Server-Sent Events
        ↓
React Decision Cockpit / Operations Queue
```

## Enable

Use the normal server-only environment and explicitly opt in to the live profile:

```bash
FABOPS_LIVE_ENABLED=true docker compose --profile live --env-file infra/macmini/.env -f infra/macmini/docker-compose.yml up -d live-simulator stream-worker api web
```

The default acceleration is `720`, which maps roughly two simulated days to four wall-clock minutes. Override `FABOPS_LIVE_TIME_ACCELERATION` to slow down or speed up the demo.

## New API surfaces

- `GET /api/live/status` — live/snapshot mode, latest event, projection state, and predictive snapshot.
- `GET /api/live/stream` — SSE updates whenever event/case/projection/predictive state changes.
- `GET /api/predictions` — transparent sensor drift forecasts and case risk scores.

## Prediction semantics

`transparent-online-risk-v1.0.0` is intentionally not represented as a trained or calibrated ML model. It exposes rolling trend, EWMA deviation, volatility, yield gap, and anomaly components with `trained_model=false`, `calibrated=false`, and `probability=false`.

A separately trained forecasting/classification model can later replace or augment this baseline behind the same API contract after offline evaluation and calibration evidence exist.

## Safety boundary

- Equipment control remains disabled.
- Public workflow mutations remain independently governed by the preview boundary.
- The existing official stack does not start live workers unless the `live` profile is explicitly enabled.
- Public preview can consume the changing PostgreSQL source in read-only mode and incrementally catch its own in-memory projection up on reads.
