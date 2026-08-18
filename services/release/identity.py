from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

RELEASE_VERSION = "0.6.0"
MANIFEST_PATH = Path("evidence/release/release-manifest.json")


def load_release_identity(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "release_version": RELEASE_VERSION,
            "release_hash": "unreleased",
            "source_git_commit": None,
            "manifest_available": False,
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "release_version": data["release_version"],
        "release_hash": data["release_hash"],
        "source_git_commit": data.get("source_git_commit"),
        "manifest_available": True,
    }


def _deployment_value(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    if "\n" in value or "\r" in value:
        return None
    return value[:160]


def load_deployment_identity(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    base_release = load_release_identity(path)
    deployment_kind = (_deployment_value("FABOPS_DEPLOYMENT_KIND") or "official").lower()
    if deployment_kind not in {"official", "candidate"}:
        deployment_kind = "official"

    channel = _deployment_value("FABOPS_DEPLOYMENT_CHANNEL") or ("official" if deployment_kind == "official" else "unspecified")
    runtime_mode = _deployment_value("FABOPS_RUNTIME_MODE") or "local"

    candidate: dict[str, Any] | None = None
    if deployment_kind == "candidate":
        label = _deployment_value("FABOPS_CANDIDATE_LABEL")
        git_sha = _deployment_value("FABOPS_CANDIDATE_GIT_SHA")
        deployment_hash = _deployment_value("FABOPS_DEPLOYMENT_HASH")
        candidate = {
            "label": label,
            "git_sha": git_sha,
            "deployment_hash": deployment_hash,
            "metadata_available": all((label, git_sha, deployment_hash)),
        }

    return {
        "schema_version": "fabops-deployment-identity-v1",
        "deployment_kind": deployment_kind,
        "channel": channel,
        "candidate": candidate,
        "base_release": {
            "version": base_release["release_version"],
            "release_hash": base_release["release_hash"],
            "source_git_commit": base_release["source_git_commit"],
            "manifest_available": base_release["manifest_available"],
        },
        "runtime": {
            "mode": runtime_mode,
            "equipment_control_enabled": False,
        },
    }
