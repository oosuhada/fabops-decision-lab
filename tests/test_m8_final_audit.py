from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from evaluation.m8_final_audit import build_audit

START = datetime(2026, 8, 22, 14, 25, 23, 719448, tzinfo=timezone.utc)


def _manifest() -> dict:
    return {
        "soak_started_at_utc": START.isoformat(),
        "target_duration_hours": 24,
        "release": {
            "release_version": "0.6.0",
            "deployed_git_sha": "release-sha",
            "release_hash": "release-hash",
        },
    }


def _sample(minutes: int) -> dict:
    return {
        "captured_at": (START + timedelta(minutes=minutes)).isoformat(),
        "collector_ok": True,
        "api": {"http_status": 200, "ready": True, "projection_lag_events": 0},
        "web": {"http_status": 200, "alive": True},
        "broker": {"total_lag": 0, "error_class": None},
        "containers": {
            "restart_counts": {"api": 0, "web": 0, "postgres": 0, "redpanda": 0, "neo4j": 0},
            "states": {"api": "running|healthy"},
        },
        "release": {"release_version": "0.6.0", "deployed_git_sha": "release-sha", "release_hash": "release-hash"},
    }


def test_final_audit_stays_in_progress_before_full_sample_window() -> None:
    audit = build_audit(manifest=_manifest(), samples=[_sample(0), _sample(1435)])
    assert audit["status"] == "in_progress"
    assert audit["passed"] is False
    assert audit["facts"]["window_complete"] is False


def test_final_audit_records_collector_only_timeout_as_gap_with_recovery() -> None:
    samples = [_sample(0), _sample(715), _sample(720), _sample(725), _sample(1445)]
    failed = deepcopy(samples[2])
    failed["collector_ok"] = False
    failed["broker"] = {"total_lag": None, "error_class": "TimeoutExpired"}
    failed["containers"] = {"restart_counts": {}, "states": {}}
    failed["release"] = {}
    samples[2] = failed

    audit = build_audit(manifest=_manifest(), samples=samples)

    assert audit["status"] == "unverified_gap"
    assert audit["passed"] is False
    assert audit["facts"]["window_complete"] is True
    assert audit["facts"]["collector_failure_count"] == 1
    assert audit["facts"]["api_non_200_samples"] == 0
    assert audit["facts"]["web_non_200_samples"] == 0
    assert audit["facts"]["release_identity_mismatch_count_when_metadata_present"] == 0
    assert audit["collector_failures"][0]["collector_error_class"] == "TimeoutExpired"
    assert audit["collector_failures"][0]["before"]["collector_ok"] is True
    assert audit["collector_failures"][0]["after"]["collector_ok"] is True
    assert audit["audit_boundary"]["pre_existing_runbook_defines_collector_timeout_tolerance"] is False


def test_final_audit_passes_only_clean_complete_window() -> None:
    audit = build_audit(manifest=_manifest(), samples=[_sample(0), _sample(720), _sample(1445)])
    assert audit["status"] == "passed"
    assert audit["passed"] is True


def test_final_audit_fails_observed_operational_regression() -> None:
    samples = [_sample(0), _sample(1445)]
    samples[-1]["api"]["ready"] = False
    audit = build_audit(manifest=_manifest(), samples=samples)
    assert audit["status"] == "failed"
    assert audit["passed"] is False
