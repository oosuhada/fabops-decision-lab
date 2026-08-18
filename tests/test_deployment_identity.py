from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.release.identity import load_deployment_identity
from systems.api.app import app


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "release-manifest.json"
    path.write_text(
        json.dumps(
            {
                "release_version": "0.6.0",
                "release_hash": "base-release-hash",
                "source_git_commit": "base-source-sha",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_official_deployment_identity_preserves_base_release(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FABOPS_DEPLOYMENT_KIND", raising=False)
    monkeypatch.delenv("FABOPS_DEPLOYMENT_CHANNEL", raising=False)
    monkeypatch.delenv("FABOPS_CANDIDATE_LABEL", raising=False)
    monkeypatch.delenv("FABOPS_CANDIDATE_GIT_SHA", raising=False)
    monkeypatch.delenv("FABOPS_DEPLOYMENT_HASH", raising=False)

    identity = load_deployment_identity(_manifest(tmp_path))

    assert identity["deployment_kind"] == "official"
    assert identity["channel"] == "official"
    assert identity["candidate"] is None
    assert identity["base_release"]["version"] == "0.6.0"
    assert identity["base_release"]["release_hash"] == "base-release-hash"
    assert identity["runtime"]["equipment_control_enabled"] is False


def test_candidate_deployment_identity_is_separate_from_base_release(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FABOPS_DEPLOYMENT_KIND", "candidate")
    monkeypatch.setenv("FABOPS_DEPLOYMENT_CHANNEL", "public-preview")
    monkeypatch.setenv("FABOPS_CANDIDATE_LABEL", "0.6.0-v0.7-candidate")
    monkeypatch.setenv("FABOPS_CANDIDATE_GIT_SHA", "64f74cd9a387a6f41a5611d84835dc10287c0998")
    monkeypatch.setenv("FABOPS_DEPLOYMENT_HASH", "candidate-64f74cd9a387a6f41a5611d84835dc10287c0998")

    identity = load_deployment_identity(_manifest(tmp_path))

    assert identity["deployment_kind"] == "candidate"
    assert identity["channel"] == "public-preview"
    assert identity["candidate"] == {
        "label": "0.6.0-v0.7-candidate",
        "git_sha": "64f74cd9a387a6f41a5611d84835dc10287c0998",
        "deployment_hash": "candidate-64f74cd9a387a6f41a5611d84835dc10287c0998",
        "metadata_available": True,
    }
    assert identity["base_release"]["version"] == "0.6.0"
    assert identity["base_release"]["release_hash"] == "base-release-hash"
    assert identity["candidate"]["git_sha"] != identity["base_release"]["release_hash"]


def test_candidate_missing_metadata_is_explicit_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FABOPS_DEPLOYMENT_KIND", "candidate")
    monkeypatch.setenv("FABOPS_DEPLOYMENT_CHANNEL", "public-preview")
    monkeypatch.delenv("FABOPS_CANDIDATE_LABEL", raising=False)
    monkeypatch.delenv("FABOPS_CANDIDATE_GIT_SHA", raising=False)
    monkeypatch.delenv("FABOPS_DEPLOYMENT_HASH", raising=False)

    identity = load_deployment_identity(_manifest(tmp_path))

    assert identity["candidate"] == {
        "label": None,
        "git_sha": None,
        "deployment_hash": None,
        "metadata_available": False,
    }
    assert identity["base_release"]["release_hash"] == "base-release-hash"


def test_deployment_identity_does_not_leak_unrelated_secret_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FABOPS_DEPLOYMENT_KIND", "candidate")
    monkeypatch.setenv("FABOPS_CANDIDATE_LABEL", "candidate")
    monkeypatch.setenv("FABOPS_CANDIDATE_GIT_SHA", "abc1234")
    monkeypatch.setenv("FABOPS_DEPLOYMENT_HASH", "candidate-abc1234")
    monkeypatch.setenv("FABOPS_DEMO_SESSION_SECRET", "must-not-appear")
    monkeypatch.setenv("FABOPS_LOCAL_LLM_TOKEN", "must-not-appear-either")

    serialized = json.dumps(load_deployment_identity(_manifest(tmp_path)), sort_keys=True)

    assert "must-not-appear" not in serialized
    assert "must-not-appear-either" not in serialized


def test_deployment_identity_endpoint_is_machine_readable(monkeypatch) -> None:
    monkeypatch.setenv("FABOPS_DEPLOYMENT_KIND", "candidate")
    monkeypatch.setenv("FABOPS_DEPLOYMENT_CHANNEL", "public-preview")
    monkeypatch.setenv("FABOPS_CANDIDATE_LABEL", "test-candidate")
    monkeypatch.setenv("FABOPS_CANDIDATE_GIT_SHA", "abc1234")
    monkeypatch.setenv("FABOPS_DEPLOYMENT_HASH", "candidate-abc1234")

    response = TestClient(app).get("/api/deployment-identity")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "fabops-deployment-identity-v1"
    assert body["deployment_kind"] == "candidate"
    assert body["candidate"]["git_sha"] == "abc1234"
    assert body["base_release"]["version"] == "0.6.0"
