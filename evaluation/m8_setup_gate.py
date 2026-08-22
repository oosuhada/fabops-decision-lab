from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "evidence/m8/soak-manifest.json"
COLLECTOR_PATH = ROOT / "infra/macmini/soak_collector.py"


def _load(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_gate() -> dict[str, Any]:
    m7 = _load("evidence/m7-gate.json")
    deployment = _load("evidence/m7/deployment-summary.json")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    started = datetime.fromisoformat(manifest["soak_started_at"])
    next_audit = datetime.fromisoformat(manifest["next_audit_at"])
    collector = manifest.get("collector", {})
    storage = manifest.get("storage", {})
    release = manifest.get("release", {})
    samples = manifest.get("initial_samples", {})
    privacy = manifest.get("privacy", {})

    checks = {
        "m7_passed": m7.get("passed") is True and m7.get("status") == "passed",
        "m8_overall_not_prematurely_passed": manifest.get("status") == "in_progress"
        and manifest.get("m8_passed") is False
        and manifest.get("soak_state") == "in_progress",
        "setup_marked_passed": manifest.get("setup_status") == "passed",
        "target_duration_24h": manifest.get("target_duration_hours") == 24,
        "next_audit_exactly_24h_after_start": (next_audit - started).total_seconds() == 86400,
        "timezone_is_asia_seoul": manifest.get("timezone") == "Asia/Seoul" and started.utcoffset().total_seconds() == 9 * 3600,
        "collector_version_pinned": collector.get("version") == "m8-soak-v1",
        "collector_hash_matches_repository": collector.get("sha256") == _sha256(COLLECTOR_PATH),
        "five_minute_launchd_interval": collector.get("collection_interval_seconds") == 300
        and collector.get("start_interval_seconds") == 300,
        "launchd_install_verified": collector.get("launchd_label") == "com.oosu.fabops-burnin"
        and collector.get("launchd_last_exit_code") == 0
        and int(collector.get("launchd_runs_observed", 0)) >= 1
        and collector.get("run_at_load") is True,
        "secure_file_modes": collector.get("launchd_plist_mode") == "0600" and collector.get("collector_file_mode") == "0700",
        "bounded_rotation": storage.get("rotation_max_bytes") == 5 * 1024 * 1024
        and storage.get("retention_hours") == 72
        and storage.get("max_rotated_files") == 12
        and storage.get("compression") == "gzip",
        "unbounded_launchd_logs_disabled": storage.get("launchd_stdout") == "/dev/null"
        and storage.get("launchd_stderr") == "/dev/null",
        "initial_samples_exist": int(samples.get("count", 0)) >= 3,
        "latest_sample_healthy": samples.get("latest_collector_ok") is True,
        "latest_projection_lag_zero": samples.get("latest_projection_lag_events") == 0,
        "latest_broker_lag_zero": samples.get("latest_broker_lag") == 0,
        "initial_restart_counts_zero": all(value == 0 for value in samples.get("latest_restart_counts", {}).values())
        and set(samples.get("latest_restart_counts", {})) == {"api", "web", "postgres", "redpanda", "neo4j"},
        "release_identity_matches_m7": release.get("release_version") == deployment.get("release", {}).get("release_version")
        and release.get("release_hash") == deployment.get("release", {}).get("release_hash")
        and release.get("deployed_git_sha") == deployment.get("release", {}).get("deployed_git_sha")
        and release.get("api_image_id") == deployment.get("release", {}).get("api_image_id")
        and release.get("web_image_id") == deployment.get("release", {}).get("web_image_id"),
        "privacy_boundary_preserved": all(value is False for value in privacy.values()),
        "remote_evidence_location_scoped": storage.get("remote_evidence_location")
        == "~/Services/fabops-decision-lab-data/burnin/samples/soak.jsonl",
    }

    passed = all(checks.values())
    return {
        "milestone": "M8-A",
        "schema_version": "m8-setup-gate-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "passed": passed,
        "m8_overall_status": "in_progress",
        "m8_overall_passed": False,
        "soak_started_at": manifest.get("soak_started_at"),
        "next_audit_at": manifest.get("next_audit_at"),
        "checks": checks,
    }


def write_gate(output: Path) -> dict[str, Any]:
    gate = build_gate()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(gate, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return gate


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the M8-A Mac mini burn-in collector setup gate.")
    parser.add_argument("--output", type=Path, default=Path("evidence/m8/setup-gate.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    gate = write_gate(args.output)
    if args.check and not gate["passed"]:
        failed = [name for name, value in gate["checks"].items() if not value]
        raise SystemExit("M8-A setup gate failed: " + ", ".join(failed))


if __name__ == "__main__":
    main()
