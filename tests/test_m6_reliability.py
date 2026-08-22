from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from evaluation.m6_evidence import generate
from services.reliability import Bulkhead, BulkheadRejected, CircuitBreaker, CircuitBreakerOpen


def test_circuit_breaker_closed_open_half_open_recovery_with_fake_clock() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=10.0, clock=lambda: now[0])

    def fail() -> None:
        raise RuntimeError("dependency failed")

    assert breaker.snapshot()["state"] == "closed"
    with pytest.raises(RuntimeError):
        breaker.call(fail)
    assert breaker.snapshot()["state"] == "closed"
    with pytest.raises(RuntimeError):
        breaker.call(fail)
    assert breaker.snapshot()["state"] == "open"
    with pytest.raises(CircuitBreakerOpen):
        breaker.call(lambda: "blocked")
    now[0] = 10.0
    assert breaker.snapshot()["state"] == "half_open"
    assert breaker.call(lambda: "recovered") == "recovered"
    assert breaker.snapshot()["state"] == "closed"


def test_external_dependency_bulkhead_rejects_excess_concurrency() -> None:
    bulkhead = Bulkhead(max_concurrency=1, acquire_timeout_seconds=0.01)
    entered = threading.Event()
    release = threading.Event()

    def hold_slot() -> None:
        def work() -> None:
            entered.set()
            assert release.wait(timeout=1.0)

        bulkhead.call(work)

    thread = threading.Thread(target=hold_slot)
    thread.start()
    assert entered.wait(timeout=1.0)
    with pytest.raises(BulkheadRejected):
        bulkhead.call(lambda: None)
    release.set()
    thread.join(timeout=1.0)
    assert not thread.is_alive()


def test_generated_m6_a_evidence_measures_subprocess_replay_and_duplicate_side_effects(tmp_path: Path) -> None:
    result = generate(tmp_path)
    telemetry = result["telemetry"]
    reliability = result["reliability"]
    assert telemetry["required_operations_present"] is True
    assert telemetry["ground_truth_present"] is False
    assert telemetry["approval_token_raw_present"] is False
    assert reliability["restart_harness"] == "fresh Python subprocess"
    assert reliability["case_hash_identical"] is True
    assert reliability["audit_hash_identical"] is True
    assert reliability["closed_case_survived"] is True
    assert reliability["replay_completeness"] == 1.0
    assert reliability["duplicate_attempts"] > 0
    assert reliability["duplicate_noop_results"] == reliability["duplicate_attempts"]
    assert reliability["duplicate_side_effect_rate"] == 0.0
    trace_sample = json.loads((tmp_path / "trace-sample.json").read_text(encoding="utf-8"))
    assert trace_sample
    assert "ground_truth" not in json.dumps(trace_sample)
