# PostgreSQL operational query profiling

## Problem

Two repository reads are order-sensitive and can become expensive as the event/case tables grow:

- `recent_measurement_events()` filters one event type and asks for the newest sequences.
- `related_cases()` filters one classification and orders by lot/update recency.

The existing single-column indexes did not fully match those filter + order shapes.

## Measurement

`evaluation/postgres_profile.py` creates an isolated benchmark database, applies the real FabOps migrations, seeds **200,000 events** and **80,000 cases**, and runs the repository-equivalent SQL with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`.

Each before/after phase is repeated 15 times. The profiler refuses to seed or drop indexes unless the database name contains `bench` or `test`.

Command used for the committed result:

```bash
uv run python -m evaluation.postgres_profile \
  --dsn postgresql://postgres:postgres@127.0.0.1:55432/fabops_bench \
  --event-rows 200000 \
  --case-rows 80000 \
  --repeats 15
```

The DSN above is a disposable local benchmark database, not a production connection string.

## Change

Migration `008_operational_query_indexes.sql` adds only the two indexes that match measured repository access patterns:

```sql
CREATE INDEX fabops_event_log_event_type_sequence_idx
  ON fabops_event_log(event_type, sequence DESC);

CREATE INDEX fabops_cases_classification_lot_updated_idx
  ON fabops_cases(classification, lot_id DESC, updated_at DESC);
```

No GIN/GiST/partitioning feature was added because these reads do not justify them.

## Result

| Query | Before | After | p50 | p95 | Buffer hits |
|---|---|---|---:|---:|---:|
| recent measurements | `fabops_event_log_pkey` | `fabops_event_log_event_type_sequence_idx` | **10.230 → 0.033 ms** | **10.627 → 0.0413 ms** | **12,078 → 14** |
| related cases | `idx_fabops_cases_lot_id` + incremental sort | `fabops_cases_classification_lot_updated_idx` | **0.162 → 0.018 ms** | **0.1799 → 0.0324 ms** | **2,844 → 46** |

Measured p50 reductions were **99.68%** and **88.89%** respectively on this fixture.

The complete machine-readable result is committed at `evidence/postgres/operational-index-profile.json`.

The CI regression gate runs a smaller isolated fixture with `--strict`; it fails if the intended index is not selected, p50 does not improve, or shared buffer hits do not decrease. The smaller CI fixture is a regression direction check, not the source of the README benchmark numbers above.

## Limitation

- This is a synthetic portfolio fixture using the real schema/query shape, not a production-fab capacity benchmark.
- Measurements are warm-cache runs on one local PostgreSQL 16 instance.
- The experiment isolates read plans; it does not quantify index write amplification, vacuum behavior, or production concurrency.
- The profiler records latency variance, but it is not a substitute for workload-level contention testing.
