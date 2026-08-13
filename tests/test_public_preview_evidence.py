from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HASH = "ab8b20a696b9b1996495f23a3e413cc33a67b6861efa184c64742e0f310c6326"
EXPECTED_SHA = "2a3df187294706afb397f0cf8072c0f3ddcc2f23"


def test_public_preview_is_read_only_and_release_bound() -> None:
    summary = json.loads((ROOT / "evidence/m7/public-preview-summary.json").read_text(encoding="utf-8"))
    config = (ROOT / "infra/macmini/public-preview-nginx.conf").read_text(encoding="utf-8")

    assert summary["status"] == "passed"
    assert summary["access_mode"] == "public-read-only"
    assert summary["release_version"] == "0.6.0"
    assert summary["release_hash"] == EXPECTED_HASH
    assert summary["deployed_git_sha"] == EXPECTED_SHA
    assert summary["public_mutation_enabled"] is False
    assert summary["postgres_public"] is False
    assert summary["redpanda_public"] is False
    assert summary["neo4j_public"] is False
    assert summary["ontology_oosu_dev_modified"] is False
    assert summary["m8_soak_interrupted"] is False
    assert summary["m8_application_containers_restarted"] is False
    assert summary["m8_release_changed"] is False

    assert "^\\(GET\\|HEAD\\)$" not in config  # nginx uses regex syntax, not basic-regex escaping.
    assert "^(GET|HEAD)$" in config
    assert "return 405" in config
    assert "proxy_pass http://host.docker.internal:8220" in config
    assert "listen 8080" in config


def test_ui_review_manifest_matches_checked_in_screenshots() -> None:
    manifest = json.loads(
        (ROOT / "evidence/ui-review/0.6.0/ui-review-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["release_version"] == "0.6.0"
    assert manifest["release_hash"] == EXPECTED_HASH
    assert manifest["deployed_git_sha"] == EXPECTED_SHA
    assert manifest["preview_access_mode"] == "public-read-only"
    assert len(manifest["screenshots"]) == 8

    for item in manifest["screenshots"]:
        screenshot = ROOT / item["path"]
        assert screenshot.is_file()
        assert hashlib.sha256(screenshot.read_bytes()).hexdigest() == item["sha256"]


def test_public_demo_document_does_not_call_role_headers_authentication() -> None:
    text = (ROOT / "docs/operations/PUBLIC_DEMO.md").read_text(encoding="utf-8")
    assert "are **not authentication**" in text
    assert "POST /api/cases/{case_id}/actions/approve" in text
    assert "There is no real equipment-control capability" in text
