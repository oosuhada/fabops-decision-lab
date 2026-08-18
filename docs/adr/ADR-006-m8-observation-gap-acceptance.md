# ADR-006: M8 collector observation-gap acceptance

## Status

Accepted — 2026-08-24.

## Context

M8 is a sampled reliability observation of the already-deployed FabOps 0.6.0
Mac mini stack. The launchd collector runs every 300 seconds and records two
different classes of evidence:

1. direct product probes that do not require Docker metadata: API HTTP/readiness,
   Web HTTP/liveness, and the API-reported projection lag; and
2. collector-side operational metadata: container state/restart counts, Redpanda
   consumer lag, resource data, and OCI release labels.

The completed M8 history contains one sample at
`2026-08-23T02:24:10.918050+00:00` where the direct API/Web probes were healthy
but Docker/broker collection raised `TimeoutExpired`. The historical artifact
`evidence/m8/final-audit-20260823T233943+0900.json` correctly reported
`unverified_gap` because no acceptance rule existed at that time. That artifact
is immutable and remains valid evidence of the rule that existed when it was
generated.

An observation gap is not equivalent to a product/runtime failure. It also must
not be silently treated as a clean sample, because restart, broker-lag, container
state, and release-label metadata were not directly observed during that sample.

## Decision

### 1. Operational failure always wins

M8 is `failed` if any observed sample proves an actual runtime regression,
including any of the following:

- API HTTP status is not 200;
- API readiness is not true;
- Web HTTP status is not 200;
- Web liveness is not true;
- observed projection lag is non-zero;
- observed broker lag is non-zero;
- any observed official container state is not `running|healthy`;
- any observed official container restart count is non-zero; or
- release version, deployed Git SHA, or release hash is present and mismatches the
  authoritative M8 release identity.

No collector-gap tolerance can override one of these facts.

### 2. Consecutive observation gap

The configured launchd `StartInterval` is 300 seconds. A collector sample with
`collector_ok != true` is an incomplete observation. Two adjacent incomplete
samples are a consecutive observation gap and are never accepted as an isolated
collector gap.

An adjacent sample timestamp delta greater than two configured intervals
(`600` seconds) is also an observation-cadence gap. The collector is a one-shot
process whose configured command/HTTP timeouts are individually bounded below
one launchd interval, so a delta beyond two intervals cannot be treated as a
normal single scheduled observation without additional proof.

### 3. Maximum acceptable missing-metadata window

An isolated collector-only failure may be accepted only when the complete
metadata snapshot immediately before and the complete metadata snapshot
immediately after it are no more than three collector intervals apart:

`3 × 300 seconds = 900 seconds`.

This 900-second ceiling is not derived from the observed 2026-08-23 timeout.
It follows the sampling semantics: one failed scheduled observation normally
creates a two-interval complete-metadata blind window; the third interval is the
hard boundary separating that isolated execution failure from an additional
unobserved scheduling opportunity. Each side of the failed sample must also be
within the 600-second adjacent-sample bound above.

### 4. Required proof for `passed_with_observation_gap`

Every incomplete collector sample in the completed window must satisfy all of
the following objective criteria:

1. the failed sample itself still proves API 200/readiness true and Web
   200/liveness true;
2. API-reported projection lag in that sample is either zero or unavailable only
   when the direct API response does not expose it; a non-zero value fails M8;
3. the immediately previous and next samples both exist and have
   `collector_ok == true`;
4. both neighbors contain complete broker, container state, restart-count, and
   release identity metadata;
5. both neighbors show broker lag zero, all five official restart counts zero,
   all five official container states `running|healthy`, and the expected release
   identity;
6. both neighbors expose the same expected release identity, preventing missing
   release metadata in the failed sample from being interpreted as a release
   change;
7. each adjacent timestamp delta is at most 600 seconds;
8. the complete-metadata observation window from the previous valid sample to the
   next valid sample is at most 900 seconds; and
9. there is no independent operational failure anywhere in the audited 24-hour
   window.

Restart consistency before/after is meaningful because Docker restart counters
are cumulative for the observed container instance. It narrows the gap but does
not make the missing sample equivalent to continuous telemetry. Therefore the
status remains explicitly qualified.

### 5. Status semantics

- `passed`: the completed M8 window contains no operational regression, no
  incomplete collector sample, no excessive cadence gap, and no incomplete
  required metadata on otherwise healthy collector samples.
- `passed_with_observation_gap`: the window is complete and operationally healthy,
  and every collector-only gap satisfies all criteria in section 4. The gap is
  retained in the audit artifact and `passed` is true only with this explicit
  qualified status.
- `unverified_gap`: the product probes do not prove a failure, but at least one
  observation gap is consecutive, excessive, unbracketed, missing required
  neighbor proof, or otherwise outside the rule above.
- `in_progress`: the declared 24-hour evidence window is not complete.
- `failed`: an observed operational/runtime regression exists. Failure overrides
  all observation-gap tolerance.

## Consequences

- Historical M8 evidence is never edited to retroactively claim a pass.
- Re-audits run the new deterministic rule and create a new artifact.
- A collector timeout can no longer be conflated with an API/Web outage, while a
  missing restart/broker/release observation can no longer be silently ignored.
- Future changes to the 300-second launchd interval require this ADR and audit
  constants to be reviewed together rather than implicitly changing tolerance.

