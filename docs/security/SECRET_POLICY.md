# FabOps Decision Lab Secret Policy

## Rules

1. Secrets must never be committed to Git, copied into release evidence, or embedded in container images.
2. `.env` and `.env.*` are ignored by default; only placeholder templates such as `.env.example` may be committed.
3. Deployment environment files are server-only and must use mode `0600`.
4. Logs, traces, postmortems and generated evidence must redact passwords, private keys, API tokens, approval-token material and full credential-bearing connection strings.
5. The deterministic core requires no external LLM credential. Missing LLM credentials are a supported disabled state, not a reason to weaken the core gate.
6. Database/broker/graph ports are private by default. Credentials do not compensate for a public network exposure.

## Rotation

- PostgreSQL/Neo4j application credentials: create a new project-specific credential, update the server-only env file, restart only FabOps services, verify readiness, then revoke the old credential.
- External LLM credential, if later enabled: rotate at the provider, update only the server secret, restart the advisory boundary, verify LLM-off fallback still works, then revoke the old key.
- Approval-token issuer secret: rotate with an explicit policy/version change because previously issued tokens may become unverifiable. Never log either old or new secret values.

## Evidence and log handling

Generated evidence may contain version IDs, hashes, redacted host/runtime facts and measurements. It must not contain user home paths when a relative project path is sufficient, environment dumps, credential values, authorization headers, or raw approval tokens.

## Verification checklist

- `git add -n .` contains no `.env`, private key, runtime DB or transient log.
- `.env.example` contains placeholders only.
- deployment `.env` permission is `0600`.
- telemetry tests assert sensitive fields are absent/redacted.
- canonical verification performs a filename/content candidate audit without echoing secret values.
