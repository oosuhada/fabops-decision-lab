# FabOps Decision Lab — Local Portfolio SLI/SLO

## Scope / 범위

This SLO is a **local deterministic portfolio profile**, not a production fab SLO. PostgreSQL/Redpanda/Neo4j container results are reported separately and are never inferred from these numbers.

이 문서의 수치는 로컬 synthetic test profile에서 측정한 값이며 실제 Fab, Samsung, 또는 synthetic-to-real 성능을 의미하지 않는다.

## SLI definitions

| SLI | Definition | Proposed local SLO | Measured |
|---|---|---:|---:|
| Ingestion throughput | accepted synthetic events / wall-clock ingestion seconds | >= 1,000 events/s | 23754.76 events/s |
| Ingest→detector p95 | wall-clock duration from ingest entry through deterministic detector callback | <= 5 ms | 0.0518 ms |
| Ingest→detector p99 | same SLI, 99th percentile | <= 10 ms | 0.1037 ms |
| Projection lag after rebuild | source checkpoint minus projection checkpoint | 0 events | 0 events |
| Replay completeness | recovered projection checkpoint / source event count | 1.0 | 1.00000 |
| Duplicate side-effect rate | observed state/outbox/audit growth / duplicate attempts | 0.0 | 0.00000 |
| Local recovery RTO p95 | fresh Python process snapshot restore + projection rebuild | <= 2,000 ms | 69.537 ms |
| Local source-log RPO | persisted snapshot events missing after recovery | 0 events | 0 events |

## Error budget interpretation

For this bounded test profile, a target is considered exhausted when a measured release benchmark exceeds its stated latency/RTO bound or when completeness/duplicate/RPO invariants are violated. A miss remains visible in generated evidence; the benchmark does not rewrite or discard samples.

## Capacity assumptions

- Single local Python process, deterministic in-memory event/case adapters.
- `373` events per sample, `5` measured samples after warmup.
- No external LLM is required.
- The local benchmark is CPU/storage-cache sensitive and is intended for regression evidence, not capacity planning for a real fab.

## Limitations

- Local in-memory source-of-truth timing is **not** PostgreSQL timing.
- Local projection rebuild is **not** Neo4j server recovery unless container integration evidence explicitly says so.
- Local replay RTO measures a fresh Python process restoring a serialized local source snapshot and rebuilding the read model.
- RPO=0 is scoped to events already present in that snapshot; it is not a claim about host power-loss durability.
- Container and remote deployment measurements, if available, are maintained in separate M6/M7 evidence.
