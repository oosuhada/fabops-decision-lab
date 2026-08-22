from __future__ import annotations

import json
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
