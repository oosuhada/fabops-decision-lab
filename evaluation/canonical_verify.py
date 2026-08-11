from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def expected_m5_evaluation_hash() -> str:
    manifest_path = ROOT / "evidence/release/release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return str(manifest["m5_evaluation_hash"])


def _sanitize(text: str, extra_paths: list[Path] | None = None) -> str:
    sanitized = text
    replacements = [(str(ROOT), "<repo>"), (str(Path.home()), "<home>")]
    for path in extra_paths or []:
        replacements.append((str(path), "<temp>"))
    for needle, replacement in replacements:
        if needle:
            sanitized = sanitized.replace(needle, replacement)
    return sanitized


def _run(
    name: str,
    arguments: list[str],
    *,
    cwd: Path = ROOT,
    extra_paths: list[Path] | None = None,
    timeout: int = 900,
) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        arguments,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=os.environ.copy(),
    )
    duration = time.perf_counter() - started
    output = "\n".join([completed.stdout, completed.stderr]).strip()
    tail = "\n".join(output.splitlines()[-24:])
    command = shlex.join([Path(arguments[0]).name, *arguments[1:]])
    return {
        "name": name,
        "command": _sanitize(command, extra_paths),
        "cwd": "." if cwd == ROOT else str(cwd.relative_to(ROOT)) if cwd.is_relative_to(ROOT) else "<temp>",
        "exit_code": completed.returncode,
        "duration_seconds": round(duration, 3),
        "output_tail": _sanitize(tail, extra_paths),
    }


def _clean_setup(uv: str, npm: str, temp_root: Path) -> dict[str, Any]:
    archive = temp_root / "source.tar"
    snapshot = temp_root / "snapshot"
    snapshot.mkdir()
    archive_result = _run(
        "clean-archive",
        ["git", "archive", "--format=tar", "HEAD", "-o", str(archive)],
        extra_paths=[temp_root],
    )
    steps = [archive_result]
    if archive_result["exit_code"] != 0:
        return {"passed": False, "steps": steps}
    with tarfile.open(archive) as tar:
        tar.extractall(snapshot, filter="data")

    steps.extend(
        [
            _run("clean-python-sync", [uv, "sync", "--locked", "--dev"], cwd=snapshot, extra_paths=[temp_root]),
            _run(
                "clean-foundation-test",
                [uv, "run", "pytest", "-q", "tests/test_foundation.py"],
                cwd=snapshot,
                extra_paths=[temp_root],
            ),
            _run(
                "clean-release-consistency",
                [uv, "run", "python", "-m", "evaluation.release_manifest", "--check"],
                cwd=snapshot,
                extra_paths=[temp_root],
            ),
            _run("clean-frontend-install", [npm, "ci"], cwd=snapshot / "systems/web", extra_paths=[temp_root]),
            _run("clean-frontend-build", [npm, "run", "build"], cwd=snapshot / "systems/web", extra_paths=[temp_root]),
        ]
    )
    return {"passed": all(step["exit_code"] == 0 for step in steps), "steps": steps}


def verify(output: Path) -> dict[str, Any]:
    uv = shutil.which("uv") or "uv"
    npm = shutil.which("npm") or "npm"
    docker = shutil.which("docker") or "docker"
    generated_at = datetime.now(timezone.utc).isoformat()
    git_sha_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    git_sha = git_sha_result.stdout.strip() if git_sha_result.returncode == 0 else None

    with tempfile.TemporaryDirectory(prefix="fabops-canonical-verify-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        temp_release = temp_dir / "release-eval"
        temp_fitness = temp_dir / "fitness"
        temp_integration = temp_dir / "integration-summary.json"
        steps = [
            _run("python-sync", [uv, "sync", "--locked", "--dev"]),
            _run(
                "ruff",
                [uv, "run", "ruff", "check", "services", "systems/api", "adapters", "simulator", "evaluation", "tests"],
            ),
            _run("python-regression", [uv, "run", "pytest", "-q"], timeout=600),
            _run(
                "held-out-release-evaluation",
                [uv, "run", "python", "-m", "evaluation.release_eval", "--output", str(temp_release), "--check"],
                extra_paths=[temp_dir],
                timeout=600,
            ),
            _run("frontend-install", [npm, "ci"], cwd=ROOT / "systems/web"),
            _run("frontend-component-tests", [npm, "run", "test"], cwd=ROOT / "systems/web"),
            _run("frontend-build", [npm, "run", "build"], cwd=ROOT / "systems/web"),
            _run("frontend-audit", [npm, "audit", "--audit-level=high"], cwd=ROOT / "systems/web"),
            _run("frontend-e2e", [npm, "run", "test:e2e"], cwd=ROOT / "systems/web", timeout=300),
            _run(
                "architecture-fitness",
                [uv, "run", "python", "-m", "evaluation.m6_fitness", "--output-dir", str(temp_fitness)],
                extra_paths=[temp_dir],
            ),
            _run("release-manifest-consistency", [uv, "run", "python", "-m", "evaluation.release_manifest", "--check"]),
        ]

        docker_info = _run("docker-info", [docker, "info"], timeout=30)
        docker_available = docker_info["exit_code"] == 0
        env_available = (ROOT / "infra/.env").exists()
        docker_status: dict[str, Any]
        if docker_available and env_available:
            integration_step = _run(
                "container-integration",
                [uv, "run", "python", "-m", "evaluation.m6_integration", "--output", str(temp_integration), "--check"],
                extra_paths=[temp_dir],
                timeout=900,
            )
            steps.append(integration_step)
            integration_payload = json.loads(temp_integration.read_text(encoding="utf-8")) if temp_integration.exists() else {}
            docker_status = {
                "status": "verified" if integration_step["exit_code"] == 0 and integration_payload.get("container_integration_verified") else "failed",
                "docker_daemon_available": True,
                "server_env_available": True,
                "container_integration_verified": bool(integration_payload.get("container_integration_verified", False)),
                "postgres_runtime_verified": bool(integration_payload.get("postgres_runtime_verified", False)),
                "redpanda_runtime_verified": bool(integration_payload.get("redpanda_runtime_verified", False)),
                "neo4j_runtime_verified": bool(integration_payload.get("neo4j_runtime_verified", False)),
            }
        else:
            docker_status = {
                "status": "unverified",
                "docker_daemon_available": docker_available,
                "server_env_available": env_available,
                "container_integration_verified": False,
                "reason": "Docker daemon or local server-only infra/.env unavailable; checked-in integration evidence remains separate and no pass is fabricated.",
            }

        eval_summary_path = temp_release / "evaluation-summary.json"
        evaluation_hash = None
        if eval_summary_path.exists():
            evaluation_hash = json.loads(eval_summary_path.read_text(encoding="utf-8")).get("canonical_hash")
        expected_evaluation_hash = expected_m5_evaluation_hash()
        evaluation_identity_passed = evaluation_hash == expected_evaluation_hash

        clean_setup = _clean_setup(uv, npm, temp_dir)
        core_passed = all(step["exit_code"] == 0 for step in steps)
        docker_gate_passed = docker_status["status"] in {"verified", "unverified"}
        passed = core_passed and docker_gate_passed and clean_setup["passed"] and evaluation_identity_passed

        result = {
            "schema_version": "m6-canonical-verification-v1",
            "generated_at": generated_at,
            "passed": passed,
            "git_sha": git_sha,
            "python_version": platform.python_version(),
            "machine_architecture": platform.machine(),
            "platform_system": platform.system(),
            "evaluation_hash": evaluation_hash,
            "expected_evaluation_hash": expected_evaluation_hash,
            "evaluation_identity_passed": evaluation_identity_passed,
            "steps": steps,
            "docker_integration": docker_status,
            "clean_setup": clean_setup,
            "policy": {
                "docker_unavailable_is_not_container_pass": True,
                "external_llm_required": False,
                "equipment_control_enabled": False,
            },
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the canonical FabOps M6 verification gate.")
    parser.add_argument("--output", type=Path, default=Path("evidence/m6/canonical-verification.json"))
    args = parser.parse_args()
    result = verify(args.output)
    if not result["passed"]:
        failed = [step["name"] for step in result["steps"] if step["exit_code"] != 0]
        if not result["clean_setup"]["passed"]:
            failed.append("clean-setup")
        if result["docker_integration"]["status"] == "failed":
            failed.append("container-integration")
        if not result["evaluation_identity_passed"]:
            failed.append("accepted-m5-evaluation-identity")
        raise SystemExit("canonical verification failed: " + ", ".join(failed))


if __name__ == "__main__":
    main()
