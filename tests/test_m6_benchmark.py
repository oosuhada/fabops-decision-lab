from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.m6_benchmark import generate, percentile


def test_percentile_is_derived_from_samples() -> None:
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(samples, 50) == 3.0
    assert percentile(samples, 95) == pytest.approx(4.8)
    assert percentile(samples, 99) == pytest.approx(4.96)


def test_m6_benchmark_emits_raw_samples_and_scoped_recovery_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    output = tmp_path / "m6"
    performance, recovery = generate(output, sample_count=2)
    latency = performance["ingest_to_detection_latency_ms"]
    assert latency["samples"]
    assert latency["p50"] == pytest.approx(percentile(latency["samples"], 50))
    assert latency["p95"] == pytest.approx(percentile(latency["samples"], 95))
    assert latency["p99"] == pytest.approx(percentile(latency["samples"], 99))
    assert performance["replay_completeness"] == 1.0
    assert performance["duplicate_side_effect_rate"] == 0.0
    assert recovery["rpo_events"]["max"] == 0
    assert recovery["postgres_process_recovery_measured"] is False
    persisted = json.loads((output / "performance-summary.json").read_text(encoding="utf-8"))
    assert persisted["benchmark_version"] == performance["benchmark_version"]
