from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.advisory.provider import ADVISORY_VERSION
from services.detection.service import DetectorConfig
from services.rca.projection import PROJECTION_VERSION
from services.rca.ranking import RCA_VERSION
from services.release.identity import RELEASE_VERSION
from services.workflow.state_machine import POLICY_VERSION
from simulator.fabtwin import GENERATOR_VERSION

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "evidence" / "release" / "release-manifest.json"
README_PATH = ROOT / "README.md"
RELEASE_MARKER_START = "<!-- RELEASE_IDENTITY_START -->"
RELEASE_MARKER_END = "<!-- RELEASE_IDENTITY_END -->"

M6_CANONICAL_EVIDENCE = (
    "evidence/m6/telemetry-summary.json",
    "evidence/m6/reliability-summary.json",
    "evidence/m6/trace-sample.json",
    "evidence/m6/performance-summary.json",
    "evidence/m6/recovery-summary.json",
    "evidence/m6/integration-summary.json",
    "evidence/m6/architecture-fitness-summary.json",
    "evidence/m6/attribution-audit.json",
    "evidence/m6/incident-projection-outage.json",
)

CANONICAL_ARTIFACTS = (
    *M6_CANONICAL_EVIDENCE,
    "evidence/release/evaluation-summary.json",
    "docs/operations/SLO.md",
    "docs/operations/RUNBOOK.md",
    "docs/security/THREAT_MODEL.md",
    "docs/security/SECRET_POLICY.md",
    "docs/postmortems/M6_NEO4J_PROJECTION_OUTAGE.md",
    "evaluation/version_registry.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _frontend_version() -> str:
    return str(json.loads((ROOT / "systems/web/package.json").read_text(encoding="utf-8"))["version"])


def _python_project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _m5_hash() -> str:
    data = json.loads((ROOT / "evidence/release/evaluation-summary.json").read_text(encoding="utf-8"))
    return str(data["canonical_hash"])


def _integration_state() -> dict[str, Any]:
    data = json.loads((ROOT / "evidence/m6/integration-summary.json").read_text(encoding="utf-8"))
    keys = (
        "compose_config_verified",
        "postgres_runtime_verified",
        "redpanda_runtime_verified",
        "neo4j_runtime_verified",
        "container_integration_verified",
    )
    return {key: bool(data.get(key, False)) for key in keys} | {"status": data.get("status", "unverified")}


def _canonical_inputs(source_git_commit: str) -> dict[str, Any]:
    evidence_hashes = {path: _sha256(ROOT / path) for path in M6_CANONICAL_EVIDENCE}
    artifact_hashes = {path: _sha256(ROOT / path) for path in CANONICAL_ARTIFACTS}
    return {
        "release_version": RELEASE_VERSION,
        "source_git_commit": source_git_commit,
        "simulator_version": GENERATOR_VERSION,
        "detector_version": DetectorConfig.load().version,
        "rca_version": RCA_VERSION,
        "projection_version": PROJECTION_VERSION,
        "advisory_version": ADVISORY_VERSION,
        "policy_version": POLICY_VERSION,
        "m5_evaluation_hash": _m5_hash(),
        "m6_evidence_hashes": evidence_hashes,
        "frontend_package_version": _frontend_version(),
        "api_version": RELEASE_VERSION,
        "python_project_version": _python_project_version(),
        "integration_verification_state": _integration_state(),
        "artifact_hashes": artifact_hashes,
    }


def _release_hash(canonical_inputs: dict[str, Any]) -> str:
    canonical = json.dumps(canonical_inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _update_readme(manifest: dict[str, Any]) -> None:
    current = README_PATH.read_text(encoding="utf-8")
    if RELEASE_MARKER_START not in current or RELEASE_MARKER_END not in current:
        raise RuntimeError("README release identity markers are missing")
    before, rest = current.split(RELEASE_MARKER_START, 1)
    _, after = rest.split(RELEASE_MARKER_END, 1)
    replacement = (
        f"{RELEASE_MARKER_START}\n"
        f"> Release `0.6.0` · canonical release hash `{manifest['release_hash']}` · "
        f"source commit `{manifest['source_git_commit'][:12]}`\n"
        f"> Generated from `evidence/release/release-manifest.json`; this block is updated by `python -m evaluation.release_manifest`.\n"
        f"{RELEASE_MARKER_END}"
    )
    README_PATH.write_text(before + replacement + after, encoding="utf-8")


def generate_manifest(path: Path = MANIFEST_PATH, *, update_readme: bool = True) -> dict[str, Any]:
    source_git_commit = _git_head()
    canonical_inputs = _canonical_inputs(source_git_commit)
    manifest = {
        "schema_version": "fabops-release-manifest-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_version": RELEASE_VERSION,
        "release_hash": _release_hash(canonical_inputs),
        "source_git_commit": source_git_commit,
        "source_git_commit_semantics": "Commit containing the release source before generated manifest/README identity metadata; later metadata commits do not change canonical release inputs.",
        "canonical_hash_definition": "SHA-256 of UTF-8 canonical JSON (sorted keys, compact separators) of canonical_inputs only. generated_at and the manifest file bytes are excluded to avoid self-reference.",
        "canonical_inputs": canonical_inputs,
        **{key: value for key, value in canonical_inputs.items() if key not in {"artifact_hashes", "m6_evidence_hashes"}},
        "m6_evidence_hashes": canonical_inputs["m6_evidence_hashes"],
        "artifact_hashes": canonical_inputs["artifact_hashes"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    if update_readme:
        _update_readme(manifest)
    return manifest


def check_manifest(path: Path = MANIFEST_PATH) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return ["release manifest is missing"]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    source_git_commit = str(manifest.get("source_git_commit", ""))
    if len(source_git_commit) != 40:
        errors.append("source_git_commit must be a full 40-character SHA")
        return errors
    expected_inputs = _canonical_inputs(source_git_commit)
    if manifest.get("canonical_inputs") != expected_inputs:
        errors.append("canonical_inputs do not match current release artifacts/version registry")
    expected_hash = _release_hash(expected_inputs)
    if manifest.get("release_hash") != expected_hash:
        errors.append("release_hash does not match canonical_inputs")
    if manifest.get("release_version") != RELEASE_VERSION:
        errors.append("release_version drift")
    if manifest.get("api_version") != RELEASE_VERSION:
        errors.append("API version drift")
    if manifest.get("frontend_package_version") != _frontend_version():
        errors.append("frontend package version drift")
    readme = README_PATH.read_text(encoding="utf-8")
    if expected_hash not in readme or f"Release `{RELEASE_VERSION}`" not in readme:
        errors.append("README does not expose the canonical release version/hash")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or verify the FabOps portfolio release manifest.")
    parser.add_argument("--output", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--no-readme-update", action="store_true")
    args = parser.parse_args()
    if args.check:
        errors = check_manifest(args.output)
        if errors:
            raise SystemExit("release manifest check failed: " + "; ".join(errors))
        return
    generate_manifest(args.output, update_readme=not args.no_readme_update)


if __name__ == "__main__":
    main()
