from __future__ import annotations

import json
from pathlib import Path

from evaluation.release_manifest import RELEASE_VERSION, _release_hash, generate_manifest


def test_release_manifest_is_generated_without_self_referential_hash(tmp_path: Path) -> None:
    output = tmp_path / "release-manifest.json"
    manifest = generate_manifest(output, update_readme=False)
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert manifest == persisted
    assert manifest["release_version"] == RELEASE_VERSION == "0.6.0"
    assert manifest["release_hash"] == _release_hash(manifest["canonical_inputs"])
    assert "generated_at" not in manifest["canonical_inputs"]
    assert "evidence/release/release-manifest.json" not in manifest["artifact_hashes"]
    assert manifest["m5_evaluation_hash"] == "78f7e90d37fa144ea8e29fb5977c21f300f1dc7bd062969b1bb0ec4dbe96a005"
    assert manifest["advisory_version"] == "deterministic-advisory-v1.1.0"
    assert manifest["integration_verification_state"]["container_integration_verified"] is True
