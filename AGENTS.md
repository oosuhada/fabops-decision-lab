# FabOps Decision Lab Engineering Rules

## Invariants

- PostgreSQL/event model is future source of truth.
- Ground truth is evaluation-only and never imported by operational code.
- Deterministic simulation requires seed, config version, generator version and artifact hash.
- Agent may explain evidence but cannot own anomaly score, authorization, case state or execution.

## Verification

```bash
uv run pytest
```

## Change discipline

- Prefer ADR for architecture trade-offs.
- Preserve provenance when referencing external projects.
- Never hide failed evaluation results.

