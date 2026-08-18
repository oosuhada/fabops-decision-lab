# M8 Mac mini 24-hour burn-in

M8 observes the already deployed FabOps 0.6.0 Mac mini stack. It does not expose
new network ports, modify unrelated services, or collect event payloads or
credentials.

## Collector

`infra/macmini/soak_collector.py` is a Python-standard-library-only one-shot
collector. `infra/macmini/scripts/install-soak.sh` installs a stable copy under
`~/Services/fabops-decision-lab-data/burnin/bin` and registers the user launchd
agent `com.oosu.fabops-burnin` with a 300-second interval.

Each JSONL sample records only operational metadata:

- API readiness and request latency
- Web liveness and request latency
- projection lag
- Redpanda consumer lag
- container running/health state and restart counts
- container CPU and memory usage strings from `docker stats`
- host load average and root-filesystem usage
- counts of recent API/Web log lines matching error-class keywords
- deployed release version/hash/Git SHA

The collector does not persist API bodies, container log text, event payloads,
credentials, tokens, private keys, or host inventory beyond the operational
fields listed above.

## Bounded storage

The active JSONL file rotates at 5 MiB. Rotated files are gzip-compressed, kept
for at most 72 hours, and capped at 12 rotated files. launchd stdout/stderr are
sent to `/dev/null`; collection failures are represented by redacted error-class
fields in the JSON sample instead of unbounded logs.

## Audit boundary

M8-A passes when the launchd collector is installed, loaded, and produces valid
initial samples. M8 overall remains IN PROGRESS until at least 24 hours have
elapsed from `soak_started_at` and the completed sample window plus recovery
checks have been audited. A setup manifest must never be interpreted as a 24-hour
burn-in pass.

## Final audit

`evaluation/m8_final_audit.py` audits a copied, read-only snapshot of the Mac mini
JSONL samples. It never restarts or mutates the official stack and it writes a new
M8-B artifact instead of changing the historical setup gate or soak manifest.

The audit distinguishes product/runtime failure from collector availability.
`ADR-006` defines the deterministic acceptance rule for observation gaps. The
historical audit generated before ADR-006 remains immutable and must not be
rewritten.

### Product/runtime failure

Any observed API non-200/not-ready result, Web non-200/not-alive result, non-zero
projection or broker lag, non-healthy official container state, non-zero official
container restart count, or observed release-identity mismatch makes M8 `failed`.
An operational failure always overrides collector-gap tolerance.

### Collector observation gap

The launchd interval is 300 seconds. An incomplete collector sample is eligible
for `passed_with_observation_gap` only when it is a single isolated failed sample
with healthy direct API/Web probes, complete healthy samples immediately before
and after it, zero neighboring broker/projection lag, zero neighboring restart
counts for API/Web/PostgreSQL/Redpanda/Neo4j, healthy neighboring container
states, and consistent expected release identity before/after.

Each timestamp delta adjacent to the failed sample must be at most 600 seconds.
The complete-metadata window from the preceding valid sample to the following
valid sample must be at most 900 seconds (three configured collector intervals).
Two adjacent failed samples, an excessive cadence gap, missing neighbor proof, or
incomplete required metadata outside that isolated gap is `unverified_gap`.

The 900-second maximum is cadence-derived rather than fitted to the historical
timeout: a single failed scheduled observation normally spans two complete-
metadata intervals, while the third interval is the hard boundary before the
audit treats the history as containing an additional unobserved scheduling
opportunity.

Status meanings are therefore:

- `passed`: clean completed window with no observation gap;
- `passed_with_observation_gap`: completed healthy window where every collector
  gap satisfies ADR-006 and remains explicitly recorded;
- `unverified_gap`: no proven operational failure, but observation evidence is
  insufficient for either pass status;
- `in_progress`: less than the documented 24-hour duration; and
- `failed`: an observed product/runtime regression.
