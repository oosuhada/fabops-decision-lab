# FabOps Decision Lab Engineering Rules

## Invariants

- PostgreSQL/event model is future source of truth.
- Ground truth is evaluation-only and never imported by operational code.
- Deterministic simulation requires seed, config version, generator version and artifact hash.
- Agent may explain evidence but cannot own anomaly score, authorization, case state or execution.

## Verification

```bash
bash scripts/verify.sh
```

This is the canonical release gate. It runs Python sync/lint/regression, held-out
evaluation, frontend install/test/build/audit, Chromium E2E, architecture fitness,
release-manifest consistency, clean-source setup, and Docker integration when the
daemon plus the local server-only `infra/.env` are available. Docker absence is
reported as UNVERIFIED rather than passed.

## Change discipline

- Prefer ADR for architecture trade-offs.
- Preserve provenance when referencing external projects.
- Never hide failed evaluation results.

