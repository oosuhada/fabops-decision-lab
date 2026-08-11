from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from evaluation.m6_replay_worker import canonical_hash
from services.detection.service import DeterministicDetector
from services.ingestion.adapters import InMemoryCaseRepository, InMemoryEventRepository, InMemoryQuarantine
from services.ingestion.service import IngestionService
from services.rca.graph import InMemoryGraphProjection
from services.rca.projection import RcaProjectionWorker
from simulator.config import load_config
from simulator.fabtwin import GENERATOR_VERSION, FabTwinSimulator

BENCHMARK_VERSION = "m6-local-benchmark-v1"
DEFAULT_SEEDS = (42, 43, 44)


def percentile(samples: Iterable[float], percentile_value: float) -> float:
    values = sorted(float(item) for item in samples)
    if not values:
        raise ValueError("percentile requires at least one sample")
    if not 0 <= percentile_value <= 100:
        raise ValueError("percentile must be between 0 and 100")
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * (percentile_value / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return values[lower]
    weight = rank - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _release_identity() -> dict[str, Any] | None:
    path = Path("evidence/release/release-manifest.json")
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"release_version": data.get("release_version"), "release_hash": data.get("release_hash")}


def _exercise_once(seed: int) -> dict[str, Any]:
    config = load_config("test")
    trace = FabTwinSimulator(config, seed).generate()
    events = InMemoryEventRepository()
    cases = InMemoryCaseRepository()
    quarantine = InMemoryQuarantine()
    detector = DeterministicDetector(cases)
    ingestion = IngestionService(events, cases, quarantine, detector.consume)

    latency_ms: list[float] = []
    ingest_start = time.perf_counter_ns()
    for event in trace.events:
        started = time.perf_counter_ns()
        ingestion.ingest(event)
        latency_ms.append((time.perf_counter_ns() - started) / 1_000_000)
    ingest_duration_seconds = (time.perf_counter_ns() - ingest_start) / 1_000_000_000

    graph = InMemoryGraphProjection()
    projection = RcaProjectionWorker(events, graph)
    lag_before = len(events.all_events()) - projection.projection_checkpoint
    projection_started = time.perf_counter_ns()
    projection_status = projection.rebuild()
    projection_duration_ms = (time.perf_counter_ns() - projection_started) / 1_000_000

    before_duplicate = {
        "events": len(events.all_events()),
        "outbox": len(events.outbox()),
        "cases": len(cases.list_cases()),
        "audit": len(cases.audit_log()),
    }
    duplicate_results = [ingestion.ingest(item.event) for item in events.all_events()]
    after_duplicate = {
        "events": len(events.all_events()),
        "outbox": len(events.outbox()),
        "cases": len(cases.list_cases()),
        "audit": len(cases.audit_log()),
    }
    duplicate_side_effect_delta = sum(max(0, after_duplicate[key] - before_duplicate[key]) for key in after_duplicate)

    with tempfile.TemporaryDirectory(prefix="fabops-m6-benchmark-") as temp_dir:
        temp = Path(temp_dir)
        input_path = temp / "snapshot.json"
        output_path = temp / "recovered.json"
        input_path.write_text(
            json.dumps({"event_repository": events.snapshot(), "case_repository": cases.snapshot()}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        recovery_started = time.perf_counter_ns()
        subprocess.run(
            [sys.executable, "-m", "evaluation.m6_replay_worker", "--input", str(input_path), "--output", str(output_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        recovery_duration_ms = (time.perf_counter_ns() - recovery_started) / 1_000_000
        recovered = json.loads(output_path.read_text(encoding="utf-8"))

    event_count = len(events.all_events())
    replay_completeness = recovered["projection"]["projection_checkpoint"] / event_count if event_count else 1.0
    duplicate_side_effect_rate = duplicate_side_effect_delta / len(duplicate_results) if duplicate_results else 0.0
    return {
        "seed": seed,
        "event_count": event_count,
        "ingest_duration_seconds": ingest_duration_seconds,
        "throughput_events_per_second": event_count / ingest_duration_seconds,
        "ingest_to_detection_latency_ms": latency_ms,
        "projection_lag_events_before_rebuild": lag_before,
        "projection_lag_events_after_rebuild": projection_status.lag_events,
        "projection_rebuild_duration_ms": projection_duration_ms,
        "replay_completeness": replay_completeness,
        "duplicate_attempts": len(duplicate_results),
        "duplicate_noop_results": sum(result == "duplicate_noop" for result in duplicate_results),
        "duplicate_side_effect_delta": duplicate_side_effect_delta,
        "duplicate_side_effect_rate": duplicate_side_effect_rate,
        "recovery_duration_ms": recovery_duration_ms,
        "recovered_event_count": recovered["event_count"],
        "rpo_lost_events": max(0, event_count - recovered["event_count"]),
        "case_hash": canonical_hash(cases.list_cases()),
        "recovered_case_hash": recovered["case_hash"],
    }


def _write_slo_doc(path: Path, performance: dict[str, Any], recovery: dict[str, Any]) -> None:
    latency = performance["ingest_to_detection_latency_ms"]
    content = f"""# FabOps Decision Lab — Local Portfolio SLI/SLO

## Scope / 범위

This SLO is a **local deterministic portfolio profile**, not a production fab SLO. PostgreSQL/Redpanda/Neo4j container results are reported separately and are never inferred from these numbers.

이 문서의 수치는 로컬 synthetic test profile에서 측정한 값이며 실제 Fab, Samsung, 또는 synthetic-to-real 성능을 의미하지 않는다.

## SLI definitions

| SLI | Definition | Proposed local SLO | Measured |
|---|---|---:|---:|
| Ingestion throughput | accepted synthetic events / wall-clock ingestion seconds | >= 1,000 events/s | {performance['throughput_events_per_second']:.2f} events/s |
| Ingest→detector p95 | wall-clock duration from ingest entry through deterministic detector callback | <= 5 ms | {latency['p95']:.4f} ms |
| Ingest→detector p99 | same SLI, 99th percentile | <= 10 ms | {latency['p99']:.4f} ms |
| Projection lag after rebuild | source checkpoint minus projection checkpoint | 0 events | {performance['projection_lag_events']['after_rebuild']} events |
| Replay completeness | recovered projection checkpoint / source event count | 1.0 | {performance['replay_completeness']:.5f} |
| Duplicate side-effect rate | observed state/outbox/audit growth / duplicate attempts | 0.0 | {performance['duplicate_side_effect_rate']:.5f} |
| Local recovery RTO p95 | fresh Python process snapshot restore + projection rebuild | <= 2,000 ms | {recovery['rto_ms']['p95']:.3f} ms |
| Local source-log RPO | persisted snapshot events missing after recovery | 0 events | {recovery['rpo_events']['max']} events |

## Error budget interpretation

For this bounded test profile, a target is considered exhausted when a measured release benchmark exceeds its stated latency/RTO bound or when completeness/duplicate/RPO invariants are violated. A miss remains visible in generated evidence; the benchmark does not rewrite or discard samples.

## Capacity assumptions

- Single local Python process, deterministic in-memory event/case adapters.
- `{performance['event_count_per_sample']}` events per sample, `{performance['sample_count']}` measured samples after warmup.
- No external LLM is required.
- The local benchmark is CPU/storage-cache sensitive and is intended for regression evidence, not capacity planning for a real fab.

## Limitations

- Local in-memory source-of-truth timing is **not** PostgreSQL timing.
- Local projection rebuild is **not** Neo4j server recovery unless container integration evidence explicitly says so.
- Local replay RTO measures a fresh Python process restoring a serialized local source snapshot and rebuilding the read model.
- RPO=0 is scoped to events already present in that snapshot; it is not a claim about host power-loss durability.
- Container and remote deployment measurements, if available, are maintained in separate M6/M7 evidence.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def generate(
    output_dir: Path,
    sample_count: int = 5,
    *,
    slo_path: Path = Path("docs/operations/SLO.md"),
) -> tuple[dict[str, Any], dict[str, Any]]:
    if sample_count < 2:
        raise ValueError("sample_count must be >= 2")
    config = load_config("test")
    FabTwinSimulator(config, DEFAULT_SEEDS[0]).generate()
    _exercise_once(DEFAULT_SEEDS[0])

    samples = [_exercise_once(DEFAULT_SEEDS[index % len(DEFAULT_SEEDS)]) for index in range(sample_count)]
    latencies = [value for sample in samples for value in sample["ingest_to_detection_latency_ms"]]
    throughputs = [sample["throughput_events_per_second"] for sample in samples]
    recovery_samples = [sample["recovery_duration_ms"] for sample in samples]
    generated_at = datetime.now(timezone.utc).isoformat()
    common = {
        "benchmark_version": BENCHMARK_VERSION,
        "generated_at": generated_at,
        "simulator_version": GENERATOR_VERSION,
        "simulator_config_version": config.version,
        "profile": config.profile,
        "seeds": [sample["seed"] for sample in samples],
        "python_version": platform.python_version(),
        "machine_architecture": platform.machine(),
        "platform_system": platform.system(),
        "sample_count": sample_count,
        "event_count_per_sample": samples[0]["event_count"],
        "command": f"uv run python -m evaluation.m6_benchmark --output-dir evidence/m6 --samples {sample_count}",
        "release_candidate": _release_identity(),
    }
    performance = {
        **common,
        "throughput_events_per_second": sum(sample["event_count"] for sample in samples) / sum(sample["ingest_duration_seconds"] for sample in samples),
        "throughput_samples_events_per_second": throughputs,
        "ingest_to_detection_latency_ms": {
            "definition": "wall-clock ingest entry through deterministic detector callback completion",
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "samples": latencies,
        },
        "projection_lag_events": {
            "before_rebuild_samples": [sample["projection_lag_events_before_rebuild"] for sample in samples],
            "after_rebuild": max(sample["projection_lag_events_after_rebuild"] for sample in samples),
        },
        "projection_rebuild_duration_ms_samples": [sample["projection_rebuild_duration_ms"] for sample in samples],
        "replay_completeness": min(sample["replay_completeness"] for sample in samples),
        "duplicate_side_effect_rate": max(sample["duplicate_side_effect_rate"] for sample in samples),
        "raw_samples": samples,
    }
    recovery = {
        **common,
        "measurement_scope": "fresh Python process restoring local deterministic snapshot and rebuilding in-memory projection",
        "rto_ms": {
            "definition": "subprocess start through recovered snapshot parse after projection rebuild",
            "p50": percentile(recovery_samples, 50),
            "p95": percentile(recovery_samples, 95),
            "p99": percentile(recovery_samples, 99),
            "samples": recovery_samples,
        },
        "rpo_events": {
            "definition": "events present in persisted local snapshot but absent after recovery",
            "samples": [sample["rpo_lost_events"] for sample in samples],
            "max": max(sample["rpo_lost_events"] for sample in samples),
        },
        "postgres_process_recovery_measured": False,
        "neo4j_process_recovery_measured": False,
        "redpanda_process_recovery_measured": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "performance-summary.json").write_text(json.dumps(performance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "recovery-summary.json").write_text(json.dumps(recovery, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_slo_doc(slo_path, performance, recovery)
    return performance, recovery


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reproducible FabOps M6 local benchmark.")
    parser.add_argument("--output-dir", type=Path, default=Path("evidence/m6"))
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    performance, recovery = generate(args.output_dir, args.samples)
    if args.check:
        if performance["replay_completeness"] != 1.0 or performance["duplicate_side_effect_rate"] != 0.0:
            raise SystemExit("M6 benchmark replay/duplicate invariant failed")
        if recovery["rpo_events"]["max"] != 0:
            raise SystemExit("M6 benchmark local snapshot RPO invariant failed")


if __name__ == "__main__":
    main()
