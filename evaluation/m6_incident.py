from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COMPOSE = ["docker", "compose", "--env-file", "infra/.env", "-f", "infra/docker-compose.yml"]


def _api_port() -> str:
    env_path = Path("infra/.env")
    if not env_path.exists():
        return "8000"
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "FABOPS_API_PORT" and value.strip():
            return value.strip()
    return "8000"


def _ready_url() -> str:
    return f"http://127.0.0.1:{_api_port()}/health/ready"


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def _ready_payload() -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(_ready_url(), timeout=2.0) as response:  # noqa: S310 - fixed localhost health endpoint
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def _wait(predicate: Any, timeout_seconds: float = 45.0) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    deadline = started + timeout_seconds
    last: dict[str, Any] | None = None
    while time.perf_counter() < deadline:
        payload = _ready_payload()
        if payload is not None:
            last = payload
            if predicate(payload):
                return payload, time.perf_counter() - started
        time.sleep(0.5)
    raise RuntimeError(f"readiness predicate not satisfied; last_status={last}")


def run_incident(output_path: Path) -> dict[str, Any]:
    _run(["docker", "info"])
    commands: list[dict[str, Any]] = []
    try:
        started = time.perf_counter()
        up = _run([*COMPOSE, "up", "-d", "--build"])
        commands.append({"command": "docker compose ... up -d --build", "exit_code": up.returncode, "duration_seconds": round(time.perf_counter() - started, 3)})
        healthy_before, _ = _wait(lambda item: bool(item.get("ready")))

        started = time.perf_counter()
        stopped = _run([*COMPOSE, "stop", "neo4j"])
        commands.append({"command": "docker compose ... stop neo4j", "exit_code": stopped.returncode, "duration_seconds": round(time.perf_counter() - started, 3)})
        degraded, detection_seconds = _wait(
            lambda item: not item.get("ready", True) and not item.get("integration", {}).get("neo4j_runtime_verified", True)
        )

        started = time.perf_counter()
        restarted = _run([*COMPOSE, "start", "neo4j"])
        commands.append({"command": "docker compose ... start neo4j", "exit_code": restarted.returncode, "duration_seconds": round(time.perf_counter() - started, 3)})
        recovered, recovery_seconds = _wait(lambda item: bool(item.get("ready")) and item.get("integration", {}).get("neo4j_runtime_verified") is True)

        payload = {
            "schema_version": "m6-incident-projection-outage-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "incident": "Neo4j projection dependency unavailable",
            "scope": "isolated local M6 Compose stack",
            "source_of_truth_affected": False,
            "equipment_control_affected": False,
            "healthy_before": healthy_before["ready"],
            "degraded_detected": degraded["status"] == "degraded",
            "neo4j_verified_during_outage": degraded["integration"]["neo4j_runtime_verified"],
            "outage_detection_seconds": round(detection_seconds, 3),
            "recovered": recovered["ready"],
            "recovery_seconds_after_start": round(recovery_seconds, 3),
            "postgres_remained_authoritative": degraded["source_of_truth"]["configured"] == "postgresql",
            "commands": commands,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload
    finally:
        _run([*COMPOSE, "down"], check=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("evidence/m6/incident-projection-outage.json"))
    args = parser.parse_args()
    result = run_incident(args.output)
    if not (result["degraded_detected"] and result["recovered"] and not result["neo4j_verified_during_outage"]):
        raise SystemExit("incident verification failed")


if __name__ == "__main__":
    main()
