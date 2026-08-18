from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

EXPECTED_RESTART_SERVICES = ("api", "web", "postgres", "redpanda", "neo4j")


def _read_samples(paths: Iterable[Path]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        if path.suffix == ".gz":
            stream = opener(path, "rt", encoding="utf-8")
        else:
            stream = opener(path, "r", encoding="utf-8")
        with stream as source:
            for line in source:
                if line.strip():
                    samples.append(json.loads(line))
    return sorted(samples, key=lambda sample: sample["captured_at"])


def _sha256(paths: Iterable[Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in paths:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        hashes[path.name] = digest.hexdigest()
    return hashes


def _timestamp(sample: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(sample["captured_at"])


def _neighbor_summary(sample: dict[str, Any] | None) -> dict[str, Any] | None:
    if sample is None:
        return None
    return {
        "captured_at": sample.get("captured_at"),
        "collector_ok": sample.get("collector_ok"),
        "api_http_status": sample.get("api", {}).get("http_status"),
        "api_ready": sample.get("api", {}).get("ready"),
        "web_http_status": sample.get("web", {}).get("http_status"),
        "web_alive": sample.get("web", {}).get("alive"),
        "projection_lag_events": sample.get("api", {}).get("projection_lag_events"),
        "broker_lag": sample.get("broker", {}).get("total_lag"),
        "restart_counts": sample.get("containers", {}).get("restart_counts", {}),
    }


def build_audit(
    *,
    manifest: dict[str, Any],
    samples: list[dict[str, Any]],
    sample_hashes: dict[str, str] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    start = datetime.fromisoformat(manifest["soak_started_at_utc"])
    target_hours = float(manifest["target_duration_hours"])
    expected_release = manifest.get("release", {})
    window = [sample for sample in samples if _timestamp(sample) >= start]

    last_at = _timestamp(window[-1]) if window else None
    elapsed_hours = ((last_at - start).total_seconds() / 3600.0) if last_at else 0.0

    collector_failures = [sample for sample in window if sample.get("collector_ok") is not True]
    failure_records: list[dict[str, Any]] = []
    for failed in collector_failures:
        index = window.index(failed)
        failure_records.append(
            {
                "captured_at": failed.get("captured_at"),
                "collector_error_class": failed.get("broker", {}).get("error_class"),
                "api_http_status": failed.get("api", {}).get("http_status"),
                "api_ready": failed.get("api", {}).get("ready"),
                "web_http_status": failed.get("web", {}).get("http_status"),
                "web_alive": failed.get("web", {}).get("alive"),
                "container_metadata_available": bool(failed.get("containers", {}).get("states")),
                "before": _neighbor_summary(window[index - 1] if index > 0 else None),
                "after": _neighbor_summary(window[index + 1] if index + 1 < len(window) else None),
            }
        )

    projection_lags = [
        sample.get("api", {}).get("projection_lag_events")
        for sample in window
        if sample.get("api", {}).get("projection_lag_events") is not None
    ]
    broker_lags = [
        sample.get("broker", {}).get("total_lag")
        for sample in window
        if sample.get("broker", {}).get("total_lag") is not None
    ]

    restart_observed: dict[str, list[int]] = {service: [] for service in EXPECTED_RESTART_SERVICES}
    restart_missing_samples: dict[str, int] = {service: 0 for service in EXPECTED_RESTART_SERVICES}
    for sample in window:
        counts = sample.get("containers", {}).get("restart_counts", {})
        for service in EXPECTED_RESTART_SERVICES:
            value = counts.get(service)
            if isinstance(value, int):
                restart_observed[service].append(value)
            else:
                restart_missing_samples[service] += 1

    release_samples = [
        sample
        for sample in window
        if sample.get("release", {}).get("release_version") is not None
    ]
    release_mismatches = [
        sample.get("captured_at")
        for sample in release_samples
        if sample.get("release", {}).get("release_version") != expected_release.get("release_version")
        or sample.get("release", {}).get("deployed_git_sha") != expected_release.get("deployed_git_sha")
        or sample.get("release", {}).get("release_hash") != expected_release.get("release_hash")
    ]

    gaps_seconds = [
        (_timestamp(right) - _timestamp(left)).total_seconds()
        for left, right in zip(window, window[1:], strict=False)
    ]

    facts = {
        "sample_count": len(window),
        "first_sample_at": window[0].get("captured_at") if window else None,
        "last_sample_at": window[-1].get("captured_at") if window else None,
        "elapsed_from_declared_start_hours": round(elapsed_hours, 9),
        "target_duration_hours": target_hours,
        "window_complete": elapsed_hours >= target_hours,
        "collector_failure_count": len(collector_failures),
        "api_non_200_samples": sum(sample.get("api", {}).get("http_status") != 200 for sample in window),
        "api_not_ready_samples": sum(sample.get("api", {}).get("ready") is not True for sample in window),
        "web_non_200_samples": sum(sample.get("web", {}).get("http_status") != 200 for sample in window),
        "web_not_alive_samples": sum(sample.get("web", {}).get("alive") is not True for sample in window),
        "max_projection_lag_events": max(projection_lags) if projection_lags else None,
        "max_broker_lag": max(broker_lags) if broker_lags else None,
        "restart_count_max": {
            service: max(values) if values else None for service, values in restart_observed.items()
        },
        "restart_metadata_missing_samples": restart_missing_samples,
        "release_metadata_sample_count": len(release_samples),
        "release_identity_mismatch_count_when_metadata_present": len(release_mismatches),
        "release_identity_mismatch_samples": release_mismatches,
        "max_sample_gap_seconds": round(max(gaps_seconds), 3) if gaps_seconds else None,
    }

    operational_regression = any(
        (
            facts["api_non_200_samples"],
            facts["api_not_ready_samples"],
            facts["web_non_200_samples"],
            facts["web_not_alive_samples"],
            facts["release_identity_mismatch_count_when_metadata_present"],
        )
    ) or (facts["max_projection_lag_events"] not in (None, 0)) or (facts["max_broker_lag"] not in (None, 0)) or any(
        value not in (None, 0) for value in facts["restart_count_max"].values()
    )

    if not facts["window_complete"]:
        status = "in_progress"
        reason = "The collected evidence window has not reached the documented 24-hour duration."
    elif operational_regression:
        status = "failed"
        reason = "The completed evidence window contains an observed operational regression in a documented M8 field."
    elif collector_failures:
        status = "unverified_gap"
        reason = (
            "The 24-hour operational window is healthy, but one or more collector samples are incomplete and the pre-existing "
            "M8 runbook defines no tolerance or pass/fail rule for collector-only metadata timeouts. The audit therefore does not infer PASS."
        )
    else:
        status = "passed"
        reason = "The documented 24-hour window completed with all collected M8 operational fields healthy and no incomplete collector samples."

    return {
        "milestone": "M8-B",
        "schema_version": "m8-final-audit-v1",
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
        "status": status,
        "passed": status == "passed",
        "source_manifest": "evidence/m8/soak-manifest.json",
        "sample_sha256": sample_hashes or {},
        "facts": facts,
        "collector_failures": failure_records,
        "audit_boundary": {
            "pre_existing_runbook_defines_collector_timeout_tolerance": False,
            "collector_failure_not_silently_removed": True,
            "missing_container_metadata_not_treated_as_release_mismatch": True,
            "no_equipment_control_or_runtime_mutation_performed": True,
        },
        "reason": reason,
    }


def write_audit(manifest_path: Path, sample_paths: list[Path], output: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = _read_samples(sample_paths)
    audit = build_audit(manifest=manifest, samples=samples, sample_hashes=_sha256(sample_paths))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the completed FabOps M8 Mac mini soak evidence without mutating the runtime.")
    parser.add_argument("--manifest", type=Path, default=Path("evidence/m8/soak-manifest.json"))
    parser.add_argument("--samples", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-pass", action="store_true", help="Exit non-zero unless the final audit is a truthful PASS.")
    args = parser.parse_args()
    audit = write_audit(args.manifest, args.samples, args.output)
    print(json.dumps({"status": audit["status"], "passed": audit["passed"], "output": str(args.output)}, sort_keys=True))
    if args.check_pass and not audit["passed"]:
        raise SystemExit(f"M8 final audit status is {audit['status']}: {audit['reason']}")


if __name__ == "__main__":
    main()
