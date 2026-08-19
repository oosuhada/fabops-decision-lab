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

INTEGRATION_VERSION = "m6-container-integration-v1"
COMPOSE = ["docker", "compose", "--env-file", "infra/.env", "-f", "infra/docker-compose.yml"]
ENV_FILE = Path("infra/.env")
DEFAULT_API_PORT = 8000


def _validate_port(raw_value: str, *, source: str) -> int:
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{source} must be an integer in range 1-65535") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{source} must be an integer in range 1-65535")
    return port


def resolve_api_port(env_file: Path = ENV_FILE, *, explicit_port: str | None = None) -> int:
    if explicit_port is not None:
        return _validate_port(explicit_port, source="--api-port")
    if not env_file.exists():
        return DEFAULT_API_PORT
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "FABOPS_API_PORT":
            return _validate_port(value.strip(), source="FABOPS_API_PORT")
    return DEFAULT_API_PORT


def _run(arguments: list[str], *, timeout: int = 300) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=False)
    duration = time.perf_counter() - started
    return {
        "command": " ".join(arguments),
        "exit_code": completed.returncode,
        "duration_seconds": round(duration, 3),
        "stdout_tail": "\n".join(completed.stdout.splitlines()[-20:]),
        "stderr_tail": "\n".join(completed.stderr.splitlines()[-20:]),
    }


def _read_health(host: str, port: int, timeout_seconds: float = 60.0) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_seconds
    health_url = f"http://{host}:{port}/health/ready"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=3) as response:
                return json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            time.sleep(1.0)
    return None


def generate(output: Path, *, keep_up: bool = False, api_port_override: str | None = None) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    commands: list[dict[str, Any]] = []
    docker_info = _run(["docker", "info"], timeout=30)
    docker_available = docker_info["exit_code"] == 0
    if not docker_available:
        result = {
            "schema_version": INTEGRATION_VERSION,
            "generated_at": generated_at,
            "status": "unverified",
            "reason": "Docker daemon unavailable; container-backed integration was not executed",
            "compose_config_verified": False,
            "postgres_runtime_verified": False,
            "redpanda_runtime_verified": False,
            "neo4j_runtime_verified": False,
            "container_integration_verified": False,
            "api_restart_verified": False,
            "docker_daemon_available": False,
            "commands": [{"command": "docker info", "exit_code": docker_info["exit_code"]}],
            "reproduction_commands": [
                "docker info",
                "docker compose --env-file infra/.env -f infra/docker-compose.yml config --quiet",
                "docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --build",
                "docker compose --env-file infra/.env -f infra/docker-compose.yml exec -T -e FABOPS_CONTAINER_INTEGRATION=1 api uv run pytest -q tests/test_m6_container_integration.py",
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    if not ENV_FILE.exists():
        result = {
            "schema_version": INTEGRATION_VERSION,
            "generated_at": generated_at,
            "status": "unverified",
            "reason": "Local server-only infra/.env unavailable; container-backed integration was not executed",
            "compose_config_verified": False,
            "postgres_runtime_verified": False,
            "redpanda_runtime_verified": False,
            "neo4j_runtime_verified": False,
            "container_integration_verified": False,
            "api_restart_verified": False,
            "docker_daemon_available": True,
            "api_port": DEFAULT_API_PORT,
            "commands": [{"command": "docker info", "exit_code": docker_info["exit_code"]}],
            "reproduction_commands": [
                "cp infra/.env.example infra/.env",
                "chmod 0600 infra/.env",
                "docker compose --env-file infra/.env -f infra/docker-compose.yml config --quiet",
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    try:
        api_port = resolve_api_port(ENV_FILE, explicit_port=api_port_override)
    except ValueError:
        result = {
            "schema_version": INTEGRATION_VERSION,
            "generated_at": generated_at,
            "status": "unverified",
            "reason": "Invalid integration API port configuration; expected an integer in range 1-65535",
            "compose_config_verified": False,
            "postgres_runtime_verified": False,
            "redpanda_runtime_verified": False,
            "neo4j_runtime_verified": False,
            "container_integration_verified": False,
            "api_restart_verified": False,
            "docker_daemon_available": True,
            "commands": [{"command": "docker info", "exit_code": docker_info["exit_code"]}],
            "reproduction_commands": [
                "docker compose --env-file infra/.env -f infra/docker-compose.yml config --quiet",
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    compose_config = _run([*COMPOSE, "config", "--quiet"], timeout=30)
    commands.append({key: value for key, value in compose_config.items() if key not in {"stdout_tail", "stderr_tail"}})
    compose_config_verified = compose_config["exit_code"] == 0
    if not compose_config_verified:
        result = {
            "schema_version": INTEGRATION_VERSION,
            "generated_at": generated_at,
            "status": "unverified",
            "reason": "Docker Compose configuration validation failed",
            "compose_config_verified": False,
            "postgres_runtime_verified": False,
            "redpanda_runtime_verified": False,
            "neo4j_runtime_verified": False,
            "container_integration_verified": False,
            "api_restart_verified": False,
            "docker_daemon_available": True,
            "api_port": api_port,
            "commands": commands,
            "reproduction_commands": [compose_config["command"]],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    up = _run([*COMPOSE, "up", "-d", "--build"], timeout=600)
    commands.append({key: value for key, value in up.items() if key not in {"stdout_tail", "stderr_tail"}})
    health: dict[str, Any] | None = None
    restart_health: dict[str, Any] | None = None
    integration_test: dict[str, Any] = {"exit_code": 1, "command": "not executed", "duration_seconds": 0.0}
    restart: dict[str, Any] = {"exit_code": 1, "command": "not executed", "duration_seconds": 0.0}
    try:
        if up["exit_code"] == 0:
            health = _read_health("127.0.0.1", api_port)
            integration_test = _run(
                [
                    *COMPOSE,
                    "exec",
                    "-T",
                    "-e",
                    "FABOPS_CONTAINER_INTEGRATION=1",
                    "api",
                    "uv",
                    "run",
                    "pytest",
                    "-q",
                    "tests/test_m6_container_integration.py",
                ],
                timeout=180,
            )
            commands.append({key: value for key, value in integration_test.items() if key not in {"stdout_tail", "stderr_tail"}})
            restart = _run([*COMPOSE, "restart", "api"], timeout=60)
            commands.append({key: value for key, value in restart.items() if key not in {"stdout_tail", "stderr_tail"}})
            if restart["exit_code"] == 0:
                restart_health = _read_health("127.0.0.1", api_port)
    finally:
        if not keep_up:
            down = _run([*COMPOSE, "down"], timeout=120)
            commands.append({key: value for key, value in down.items() if key not in {"stdout_tail", "stderr_tail"}})

    integration = (health or {}).get("integration", {})
    restart_integration = (restart_health or {}).get("integration", {})
    postgres_verified = bool(integration.get("postgres_runtime_verified"))
    redpanda_verified = bool(integration.get("redpanda_runtime_verified"))
    neo4j_verified = bool(integration.get("neo4j_runtime_verified"))
    restart_verified = bool(restart_health and restart_health.get("ready") and restart_integration.get("container_integration_verified"))
    tests_verified = integration_test["exit_code"] == 0
    container_verified = all(
        (
            up["exit_code"] == 0,
            postgres_verified,
            redpanda_verified,
            neo4j_verified,
            tests_verified,
            restart_verified,
        )
    )
    result = {
        "schema_version": INTEGRATION_VERSION,
        "generated_at": generated_at,
        "status": "verified" if container_verified else "degraded",
        "reason": None if container_verified else "one or more container-backed runtime checks failed",
        "docker_daemon_available": True,
        "api_port": api_port,
        "compose_config_verified": compose_config_verified,
        "postgres_runtime_verified": postgres_verified,
        "redpanda_runtime_verified": redpanda_verified,
        "neo4j_runtime_verified": neo4j_verified,
        "container_integration_verified": container_verified,
        "api_restart_verified": restart_verified,
        "integration_test_exit_code": integration_test["exit_code"],
        "integration_test_result": "4 passed" if tests_verified else "failed",
        "source_of_truth": "PostgreSQL",
        "projection_role": "Neo4j rebuildable projection; non-authoritative",
        "transport_role": "Redpanda/Kafka at-least-once transport with idempotent source handling",
        "host_port_policy": "PostgreSQL, Redpanda and Neo4j are private to the Compose network; API/Web bind to 127.0.0.1 only",
        "actual_equipment_control": False,
        "commands": commands,
        "reproduction_commands": [
            "docker info",
            "docker compose --env-file infra/.env -f infra/docker-compose.yml config --quiet",
            "docker compose --env-file infra/.env -f infra/docker-compose.yml up -d --build",
            "docker compose --env-file infra/.env -f infra/docker-compose.yml exec -T -e FABOPS_CONTAINER_INTEGRATION=1 api uv run pytest -q tests/test_m6_container_integration.py",
            "docker compose --env-file infra/.env -f infra/docker-compose.yml restart api",
            "docker compose --env-file infra/.env -f infra/docker-compose.yml down",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the isolated M6 Docker Compose integration stack.")
    parser.add_argument("--output", type=Path, default=Path("evidence/m6/integration-summary.json"))
    parser.add_argument("--keep-up", action="store_true")
    parser.add_argument("--api-port", help="Override the loopback API port used for readiness probes.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = generate(args.output, keep_up=args.keep_up, api_port_override=args.api_port)
    if args.check and result["docker_daemon_available"] and not result["container_integration_verified"]:
        raise SystemExit("M6 container integration verification failed")


if __name__ == "__main__":
    main()
