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

The audit distinguishes product availability from collector availability. If a
sample has healthy API/Web responses but collector-side Docker or broker metadata
is incomplete, that sample remains in the evidence and its neighboring recovery
samples are recorded. Because the original M8 runbook did not define a tolerance
or pass/fail rule for such a collector-only timeout, a completed soak containing
one is reported conservatively as `UNVERIFIED / GAP`, not inferred as `PASSED`.
