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
    states = {service: "running|healthy" for service in ("api", "web", "postgres", "redpanda", "neo4j")}
    return {
        "captured_at": (START + timedelta(minutes=minutes)).isoformat(),
        "collector_ok": True,
        "api": {"http_status": 200, "ready": True, "projection_lag_events": 0},
        "web": {"http_status": 200, "alive": True},
        "broker": {"total_lag": 0, "error_class": None},
        "containers": {
            "restart_counts": {"api": 0, "web": 0, "postgres": 0, "redpanda": 0, "neo4j": 0},
            "states": states,
        },
        "release": {"release_version": "0.6.0", "deployed_git_sha": "release-sha", "release_hash": "release-hash"},
    }


def test_final_audit_stays_in_progress_before_full_sample_window() -> None:
    audit = build_audit(manifest=_manifest(), samples=[_sample(0), _sample(1435)])
    assert audit["status"] == "in_progress"
    assert audit["passed"] is False
    assert audit["facts"]["window_complete"] is False


def _collector_timeout(sample: dict) -> dict:
    failed = deepcopy(sample)
    failed["collector_ok"] = False
    failed["broker"] = {"total_lag": None, "error_class": "TimeoutExpired"}
    failed["containers"] = {"restart_counts": {}, "states": {}}
    failed["release"] = {}
    return failed


def _complete_window() -> list[dict]:
    return [_sample(minutes) for minutes in range(0, 1446, 5)]


def _index_for_minute(samples: list[dict], minute: int) -> int:
    target = (START + timedelta(minutes=minute)).isoformat()
    return next(index for index, sample in enumerate(samples) if sample["captured_at"] == target)


def test_final_audit_accepts_isolated_collector_only_timeout_with_explicit_gap_status() -> None:
    samples = _complete_window()
    index = _index_for_minute(samples, 720)
    samples[index] = _collector_timeout(samples[index])

    audit = build_audit(manifest=_manifest(), samples=samples)

    assert audit["status"] == "passed_with_observation_gap"
    assert audit["passed"] is True
    assert audit["facts"]["window_complete"] is True
    assert audit["facts"]["collector_failure_count"] == 1
    assert audit["facts"]["qualified_observation_gap_count"] == 1
    assert audit["facts"]["unqualified_observation_gap_count"] == 0
    assert audit["facts"]["api_non_200_samples"] == 0
    assert audit["facts"]["web_non_200_samples"] == 0
    assert audit["facts"]["release_identity_mismatch_count_when_metadata_present"] == 0
    assert audit["collector_failures"][0]["collector_error_class"] == "TimeoutExpired"
    assert audit["collector_failures"][0]["before"]["collector_ok"] is True
    assert audit["collector_failures"][0]["after"]["collector_ok"] is True
    assert audit["collector_failures"][0]["acceptance"]["qualifies_as_observation_gap"] is True
    assert audit["audit_boundary"]["observation_gap_rule"] == "ADR-006"


def test_final_audit_rejects_consecutive_collector_failures_as_unverified() -> None:
    samples = _complete_window()
    first = _index_for_minute(samples, 720)
    second = _index_for_minute(samples, 725)
    samples[first] = _collector_timeout(samples[first])
    samples[second] = _collector_timeout(samples[second])

    audit = build_audit(manifest=_manifest(), samples=samples)

    assert audit["status"] == "unverified_gap"
    assert audit["passed"] is False
    assert audit["facts"]["consecutive_collector_failure_pairs"] == 1
    assert audit["facts"]["unqualified_observation_gap_count"] == 2


def test_final_audit_rejects_excessive_observation_window() -> None:
    samples = _complete_window()
    failed_index = _index_for_minute(samples, 710)
    samples[failed_index] = _collector_timeout(samples[failed_index])
    samples = [sample for sample in samples if sample["captured_at"] not in {
        (START + timedelta(minutes=715)).isoformat(),
        (START + timedelta(minutes=720)).isoformat(),
    }]

    audit = build_audit(manifest=_manifest(), samples=samples)

    assert audit["status"] == "unverified_gap"
    assert audit["passed"] is False
    assert audit["facts"]["cadence_gap_count"] >= 1


def test_final_audit_accepts_isolated_unknown_restart_metadata_only_when_neighbors_prove_zero() -> None:
    samples = _complete_window()
    index = _index_for_minute(samples, 720)
    samples[index] = _collector_timeout(samples[index])

    audit = build_audit(manifest=_manifest(), samples=samples)

    assert audit["status"] == "passed_with_observation_gap"
    assert audit["collector_failures"][0]["container_metadata_available"] is False
    assert audit["collector_failures"][0]["acceptance"]["neighbor_metadata_complete"] is True
    assert audit["collector_failures"][0]["acceptance"]["neighbor_release_identity_consistent"] is True


def test_final_audit_rejects_unknown_restart_metadata_when_neighbor_is_incomplete() -> None:
    samples = _complete_window()
    failed_index = _index_for_minute(samples, 720)
    neighbor_index = _index_for_minute(samples, 725)
    samples[failed_index] = _collector_timeout(samples[failed_index])
    samples[neighbor_index]["containers"]["restart_counts"].pop("neo4j")

    audit = build_audit(manifest=_manifest(), samples=samples)

    assert audit["status"] == "unverified_gap"
    assert audit["passed"] is False
    assert audit["facts"]["metadata_incomplete_healthy_sample_count"] == 1


def test_final_audit_operational_regression_overrides_collector_gap_tolerance() -> None:
    samples = _complete_window()
    index = _index_for_minute(samples, 720)
    samples[index] = _collector_timeout(samples[index])
    samples[index]["api"]["ready"] = False

    audit = build_audit(manifest=_manifest(), samples=samples)

    assert audit["status"] == "failed"
    assert audit["passed"] is False
    assert audit["facts"]["api_not_ready_samples"] == 1


def test_final_audit_fails_release_identity_mismatch() -> None:
    samples = _complete_window()
    samples[_index_for_minute(samples, 720)]["release"]["release_hash"] = "wrong-release-hash"

    audit = build_audit(manifest=_manifest(), samples=samples)

    assert audit["status"] == "failed"
    assert audit["passed"] is False
    assert audit["facts"]["release_identity_mismatch_count_when_metadata_present"] == 1


def test_final_audit_records_collector_only_timeout_acceptance_details() -> None:
    samples = _complete_window()
    index = _index_for_minute(samples, 720)
    failed = deepcopy(samples[index])
    failed["collector_ok"] = False
    failed["broker"] = {"total_lag": None, "error_class": "TimeoutExpired"}
    failed["containers"] = {"restart_counts": {}, "states": {}}
    failed["release"] = {}
    samples[index] = failed

    audit = build_audit(manifest=_manifest(), samples=samples)

    assert audit["status"] == "passed_with_observation_gap"
    assert audit["passed"] is True
    assert audit["facts"]["window_complete"] is True
    assert audit["facts"]["collector_failure_count"] == 1
    assert audit["facts"]["api_non_200_samples"] == 0
    assert audit["facts"]["web_non_200_samples"] == 0
    assert audit["facts"]["release_identity_mismatch_count_when_metadata_present"] == 0
    assert audit["collector_failures"][0]["collector_error_class"] == "TimeoutExpired"
    assert audit["collector_failures"][0]["before"]["collector_ok"] is True
    assert audit["collector_failures"][0]["after"]["collector_ok"] is True
    assert audit["collector_failures"][0]["observation_window_seconds"] == 600.0
    assert audit["facts"]["max_acceptable_observation_window_seconds"] == 900


def test_final_audit_passes_only_clean_complete_window() -> None:
    audit = build_audit(manifest=_manifest(), samples=_complete_window())
    assert audit["status"] == "passed"
    assert audit["passed"] is True


def test_final_audit_fails_observed_operational_regression() -> None:
    samples = _complete_window()
    samples[-1]["api"]["ready"] = False
    audit = build_audit(manifest=_manifest(), samples=samples)
    assert audit["status"] == "failed"
    assert audit["passed"] is False
