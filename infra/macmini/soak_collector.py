from __future__ import annotations

import fcntl
import gzip
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COLLECTOR_VERSION = "m8-soak-v1"
DEFAULT_ROOT = Path.home() / "Services" / "fabops-decision-lab-data" / "burnin"
SAMPLE_FILENAME = "soak.jsonl"
MAX_SAMPLE_BYTES = 5 * 1024 * 1024
RETENTION_HOURS = 72
MAX_ROTATED_FILES = 12
API_URL = "http://127.0.0.1:8210/health/ready"
WEB_URL = "http://127.0.0.1:8220/health/live"
EXPECTED_CONTAINERS = {
    "api": "fabops-decision-lab-macmini-api-1",
    "web": "fabops-decision-lab-macmini-web-1",
    "postgres": "fabops-decision-lab-macmini-postgres-1",
    "redpanda": "fabops-decision-lab-macmini-redpanda-1",
    "neo4j": "fabops-decision-lab-macmini-neo4j-1",
}
DOCKER_PATHS = (
    Path.home() / ".orbstack" / "bin" / "docker",
    Path("/usr/local/bin/docker"),
    Path("/opt/homebrew/bin/docker"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _docker() -> str:
    for candidate in DOCKER_PATHS:
        if candidate.exists():
            return str(candidate)
    discovered = shutil.which("docker")
    if discovered:
        return discovered
    raise FileNotFoundError("docker executable not found")


def _run(command: list[str], timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)


def _http_json(url: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=5.0) as response:
            body = response.read(256 * 1024)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            payload = json.loads(body.decode("utf-8"))
            return {
                "http_status": int(response.status),
                "latency_ms": round(elapsed_ms, 3),
                "payload": payload,
                "error_class": None,
            }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "http_status": None,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "payload": {},
            "error_class": type(exc).__name__,
        }


def _container_stats(docker: str) -> dict[str, dict[str, Any]]:
    names = list(EXPECTED_CONTAINERS.values())
    result = _run(
        [docker, "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}", *names],
        timeout=12.0,
    )
    stats: dict[str, dict[str, Any]] = {}
    if result.returncode != 0:
        return {"_error": {"error_class": "DockerStatsFailed", "returncode": result.returncode}}
    inverse = {container: service for service, container in EXPECTED_CONTAINERS.items()}
    for line in result.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3 or parts[0] not in inverse:
            continue
        service = inverse[parts[0]]
        stats[service] = {"cpu_percent": parts[1], "memory_usage": parts[2]}
    return stats


def _restart_counts(docker: str) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    for service, container in EXPECTED_CONTAINERS.items():
        result = _run([docker, "inspect", "-f", "{{.RestartCount}}", container])
        try:
            counts[service] = int(result.stdout.strip()) if result.returncode == 0 else None
        except ValueError:
            counts[service] = None
    return counts


def _running_states(docker: str) -> dict[str, str]:
    states: dict[str, str] = {}
    for service, container in EXPECTED_CONTAINERS.items():
        result = _run([docker, "inspect", "-f", "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}", container])
        states[service] = result.stdout.strip() if result.returncode == 0 else "missing"
    return states


def _release_labels(docker: str) -> dict[str, str | None]:
    container = EXPECTED_CONTAINERS["api"]
    labels = {
        "release_version": "org.opencontainers.image.version",
        "deployed_git_sha": "org.opencontainers.image.revision",
        "release_hash": "com.oosu.fabops.release-hash",
    }
    values: dict[str, str | None] = {}
    for field, label in labels.items():
        result = _run([docker, "inspect", "-f", f"{{{{index .Config.Labels \"{label}\"}}}}", container])
        value = result.stdout.strip() if result.returncode == 0 else ""
        values[field] = value or None
    return values


def _broker_lag(docker: str) -> dict[str, Any]:
    result = _run(
        [
            docker,
            "exec",
            EXPECTED_CONTAINERS["redpanda"],
            "rpk",
            "group",
            "describe",
            "fabops-macmini-api-v1",
            "--brokers",
            "redpanda:9092",
        ],
        timeout=10.0,
    )
    if result.returncode != 0:
        return {"total_lag": None, "error_class": "BrokerLagQueryFailed"}
    match = re.search(r"TOTAL-LAG\s+(\d+)", result.stdout)
    if match:
        return {"total_lag": int(match.group(1)), "error_class": None}
    topic_match = re.search(r"fabops\.events\.v1\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+)", result.stdout)
    return {
        "total_lag": int(topic_match.group(1)) if topic_match else None,
        "error_class": None if topic_match else "BrokerLagParseFailed",
    }


def _error_count(docker: str, container: str) -> int | None:
    result = _run([docker, "logs", "--since", "6m", container], timeout=8.0)
    if result.returncode != 0:
        return None
    combined = result.stdout + "\n" + result.stderr
    return sum(1 for line in combined.splitlines() if re.search(r"\b(ERROR|Traceback|Exception|CRITICAL)\b", line, re.IGNORECASE))


def _disk() -> dict[str, int]:
    usage = shutil.disk_usage("/")
    return {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}


def _build_sample() -> dict[str, Any]:
    api = _http_json(API_URL)
    web = _http_json(WEB_URL)
    api_payload = api.pop("payload", {})
    web_payload = web.pop("payload", {})
    try:
        docker = _docker()
        stats = _container_stats(docker)
        restart_counts = _restart_counts(docker)
        running_states = _running_states(docker)
        labels = _release_labels(docker)
        broker = _broker_lag(docker)
        error_counts = {
            "api_recent_error_lines": _error_count(docker, EXPECTED_CONTAINERS["api"]),
            "web_recent_error_lines": _error_count(docker, EXPECTED_CONTAINERS["web"]),
        }
        docker_error = None
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        stats = {}
        restart_counts = {}
        running_states = {}
        labels = {}
        broker = {"total_lag": None, "error_class": type(exc).__name__}
        error_counts = {"api_recent_error_lines": None, "web_recent_error_lines": None}
        docker_error = type(exc).__name__

    expected_healthy = all(value == "running|healthy" for value in running_states.values()) if running_states else False
    api_ready = api.get("http_status") == 200 and api_payload.get("ready") is True
    web_ready = web.get("http_status") == 200 and web_payload.get("status") == "alive"
    collector_ok = bool(api_ready and web_ready and expected_healthy and docker_error is None)
    return {
        "schema_version": "m8-soak-sample-v1",
        "collector_version": COLLECTOR_VERSION,
        "captured_at": _now_iso(),
        "collector_ok": collector_ok,
        "api": {
            **api,
            "ready": api_payload.get("ready"),
            "runtime_mode": api_payload.get("runtime_mode"),
            "projection_lag_events": api_payload.get("projection", {}).get("lag_events"),
            "integration_status": api_payload.get("integration", {}).get("status"),
        },
        "web": {**web, "alive": web_payload.get("status") == "alive"},
        "containers": {
            "states": running_states,
            "restart_counts": restart_counts,
            "resource_stats": stats,
        },
        "broker": broker,
        "host": {"load_average": list(os.getloadavg()), "disk": _disk()},
        "error_counters": error_counts,
        "release": labels,
        "privacy": {
            "credentials_collected": False,
            "event_payloads_collected": False,
            "container_logs_collected": False,
            "only_error_line_counts_collected": True,
        },
    }


def _rotate(samples_dir: Path, sample_path: Path) -> None:
    if sample_path.exists() and sample_path.stat().st_size >= MAX_SAMPLE_BYTES:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rotated = samples_dir / f"soak-{timestamp}.jsonl.gz"
        with sample_path.open("rb") as source, gzip.open(rotated, "wb", compresslevel=6) as target:
            shutil.copyfileobj(source, target)
        sample_path.unlink()

    cutoff = time.time() - RETENTION_HOURS * 3600
    rotated_files = sorted(samples_dir.glob("soak-*.jsonl.gz"), key=lambda path: path.stat().st_mtime, reverse=True)
    for index, path in enumerate(rotated_files):
        if index >= MAX_ROTATED_FILES or path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


def main() -> None:
    root = Path(os.environ.get("FABOPS_BURNIN_ROOT", str(DEFAULT_ROOT))).expanduser()
    samples_dir = root / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    lock_path = root / "collector.lock"
    sample_path = samples_dir / SAMPLE_FILENAME

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        _rotate(samples_dir, sample_path)
        sample = _build_sample()
        with sample_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(sample, sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
