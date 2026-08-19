from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from evaluation import canonical_verify, m6_integration


def test_default_integration_api_port_remains_8000(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FABOPS_WEB_PORT=15190\n", encoding="utf-8")
    assert m6_integration.resolve_api_port(env_file) == 8000


def test_custom_fabops_api_port_is_honored(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FABOPS_API_PORT=18090\n", encoding="utf-8")
    assert m6_integration.resolve_api_port(env_file) == 18090


@pytest.mark.parametrize("raw_value", ["zero", "0", "65536", "-1", "8000.5"])
def test_invalid_integration_port_values_fail_safely(tmp_path: Path, raw_value: str) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"FABOPS_API_PORT={raw_value}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="integer in range 1-65535"):
        m6_integration.resolve_api_port(env_file)


def test_env_secrets_are_not_included_in_integration_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_marker = "test-only-secret-marker-never-emit"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"FABOPS_POSTGRES_PASSWORD={secret_marker}",
                f"FABOPS_NEO4J_PASSWORD={secret_marker}",
                "FABOPS_API_PORT=18090",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "integration.json"
    monkeypatch.setattr(m6_integration, "ENV_FILE", env_file)

    def fake_run(arguments: list[str], *, timeout: int = 300) -> dict[str, Any]:
        is_docker_info = arguments == ["docker", "info"]
        return {
            "command": " ".join(arguments),
            "exit_code": 0 if is_docker_info else 1,
            "duration_seconds": 0.0,
            "stdout_tail": secret_marker,
            "stderr_tail": secret_marker,
        }

    monkeypatch.setattr(m6_integration, "_run", fake_run)
    result = m6_integration.generate(output)
    serialized = output.read_text(encoding="utf-8")

    assert result["status"] == "unverified"
    assert result["api_port"] == 18090
    assert secret_marker not in serialized
    assert "FABOPS_POSTGRES_PASSWORD" not in serialized
    assert "FABOPS_NEO4J_PASSWORD" not in serialized


def test_health_probe_uses_resolved_port(monkeypatch: pytest.MonkeyPatch) -> None:
    requested_urls: list[str] = []

    class DummyResponse(io.BytesIO):
        def __enter__(self) -> DummyResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            self.close()

    def fake_urlopen(url: str, timeout: int) -> DummyResponse:
        requested_urls.append(url)
        assert timeout == 3
        return DummyResponse(b'{"ready": true}')

    monkeypatch.setattr(m6_integration.urllib.request, "urlopen", fake_urlopen)
    health = m6_integration._read_health("127.0.0.1", 18090, timeout_seconds=0.1)

    assert health == {"ready": True}
    assert requested_urls == ["http://127.0.0.1:18090/health/ready"]


def test_canonical_e2e_receives_isolated_api_and_web_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(
        name: str,
        arguments: list[str],
        *,
        cwd: Path = canonical_verify.ROOT,
        extra_paths: list[Path] | None = None,
        env_overrides: dict[str, str] | None = None,
        timeout: int = 900,
    ) -> dict[str, Any]:
        captured.update(
            {
                "name": name,
                "arguments": arguments,
                "cwd": cwd,
                "extra_paths": extra_paths,
                "env_overrides": env_overrides,
                "timeout": timeout,
            }
        )
        return {"name": name, "command": "npm run test:e2e", "exit_code": 0, "duration_seconds": 0.0, "output_tail": ""}

    monkeypatch.setattr(canonical_verify, "_run", fake_run)
    step, ports = canonical_verify._run_frontend_e2e("npm")

    assert step["exit_code"] == 0
    assert ports["api_port"] not in {8000, 5173}
    assert ports["web_port"] not in {8000, 5173, ports["api_port"]}
    assert captured["arguments"] == ["npm", "run", "test:e2e"]
    assert captured["env_overrides"] == {
        "FABOPS_E2E_API_PORT": str(ports["api_port"]),
        "FABOPS_E2E_WEB_PORT": str(ports["web_port"]),
    }


def test_canonical_e2e_isolation_does_not_target_default_port_8000(monkeypatch: pytest.MonkeyPatch) -> None:
    invoked_commands: list[list[str]] = []

    def fake_run(
        name: str,
        arguments: list[str],
        *,
        cwd: Path = canonical_verify.ROOT,
        extra_paths: list[Path] | None = None,
        env_overrides: dict[str, str] | None = None,
        timeout: int = 900,
    ) -> dict[str, Any]:
        invoked_commands.append(arguments)
        assert env_overrides is not None
        assert env_overrides["FABOPS_E2E_API_PORT"] != "8000"
        return {"name": name, "command": "npm run test:e2e", "exit_code": 0, "duration_seconds": 0.0, "output_tail": ""}

    monkeypatch.setattr(canonical_verify, "_run", fake_run)
    canonical_verify._run_frontend_e2e("npm")

    assert invoked_commands == [["npm", "run", "test:e2e"]]


def test_canonical_e2e_retries_if_discovered_port_is_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    selected = iter(
        [
            {"api_port": 18091, "web_port": 15191},
            {"api_port": 18092, "web_port": 15192},
        ]
    )
    captured_ports: list[tuple[str, str]] = []

    monkeypatch.setattr(canonical_verify, "_select_isolated_e2e_ports", lambda: next(selected))

    def fake_run(
        name: str,
        arguments: list[str],
        *,
        cwd: Path = canonical_verify.ROOT,
        extra_paths: list[Path] | None = None,
        env_overrides: dict[str, str] | None = None,
        timeout: int = 900,
    ) -> dict[str, Any]:
        assert env_overrides is not None
        captured_ports.append((env_overrides["FABOPS_E2E_API_PORT"], env_overrides["FABOPS_E2E_WEB_PORT"]))
        if len(captured_ports) == 1:
            return {
                "name": name,
                "command": "npm run test:e2e",
                "exit_code": 1,
                "duration_seconds": 0.0,
                "output_tail": "Error: listen EADDRINUSE: address already in use",
            }
        return {
            "name": name,
            "command": "npm run test:e2e",
            "exit_code": 0,
            "duration_seconds": 0.0,
            "output_tail": "3 passed",
        }

    monkeypatch.setattr(canonical_verify, "_run", fake_run)
    step, ports = canonical_verify._run_frontend_e2e("npm")

    assert step["exit_code"] == 0
    assert ports == {"api_port": 18092, "web_port": 15192}
    assert captured_ports == [("18091", "15191"), ("18092", "15192")]


def test_missing_infra_env_remains_unverified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "integration.json"
    missing_env = tmp_path / "missing.env"
    monkeypatch.setattr(m6_integration, "ENV_FILE", missing_env)

    def fake_run(arguments: list[str], *, timeout: int = 300) -> dict[str, Any]:
        assert arguments == ["docker", "info"]
        return {
            "command": "docker info",
            "exit_code": 0,
            "duration_seconds": 0.0,
            "stdout_tail": "",
            "stderr_tail": "",
        }

    monkeypatch.setattr(m6_integration, "_run", fake_run)
    result = m6_integration.generate(output)

    assert result["status"] == "unverified"
    assert result["container_integration_verified"] is False
    assert "infra/.env unavailable" in result["reason"]


def test_existing_container_integration_semantics_remain_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FABOPS_API_PORT=18090\n", encoding="utf-8")
    output = tmp_path / "integration.json"
    monkeypatch.setattr(m6_integration, "ENV_FILE", env_file)

    def fake_run(arguments: list[str], *, timeout: int = 300) -> dict[str, Any]:
        return {
            "command": " ".join(arguments),
            "exit_code": 0,
            "duration_seconds": 0.0,
            "stdout_tail": "",
            "stderr_tail": "",
        }

    health = {
        "ready": True,
        "integration": {
            "postgres_runtime_verified": True,
            "redpanda_runtime_verified": True,
            "neo4j_runtime_verified": True,
            "container_integration_verified": True,
        },
    }
    monkeypatch.setattr(m6_integration, "_run", fake_run)
    monkeypatch.setattr(m6_integration, "_read_health", lambda host, port, timeout_seconds=60.0: health)

    result = m6_integration.generate(output)

    assert result["status"] == "verified"
    assert result["container_integration_verified"] is True
    assert result["postgres_runtime_verified"] is True
    assert result["redpanda_runtime_verified"] is True
    assert result["neo4j_runtime_verified"] is True
    assert result["api_restart_verified"] is True
    assert result["integration_test_result"] == "4 passed"
    assert result["actual_equipment_control"] is False
    assert json.loads(output.read_text(encoding="utf-8"))["api_port"] == 18090
