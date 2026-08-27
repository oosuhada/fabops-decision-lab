from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "infra/macmini/docker-compose.yml").read_text(encoding="utf-8")


def _service_block(name: str) -> str:
    marker = f"  {name}:\n"
    start = COMPOSE.index(marker) + len(marker)
    next_service = re.search(r"^  [a-z][a-z0-9-]*:\n", COMPOSE[start:], flags=re.MULTILINE)
    networks = re.search(r"^networks:\n", COMPOSE[start:], flags=re.MULTILINE)
    candidates = [match.start() for match in (next_service, networks) if match is not None]
    end = min(candidates) if candidates else len(COMPOSE) - start
    return COMPOSE[start : start + end]


def test_macmini_compose_is_isolated_and_resource_bounded() -> None:
    assert "name: fabops-decision-lab-macmini" in COMPOSE
    assert "name: fabops-decision-lab-macmini_private" in COMPOSE
    for service in ("postgres", "redpanda", "redpanda-init", "neo4j", "init", "api", "web"):
        block = _service_block(service)
        assert "cpus:" in block
        assert "mem_limit:" in block
    for service in ("postgres", "redpanda", "neo4j"):
        assert "ports:" not in _service_block(service)
    assert '127.0.0.1:${FABOPS_API_PORT:-8210}:8000' in _service_block("api")
    assert '127.0.0.1:${FABOPS_WEB_PORT:-8220}:80' in _service_block("web")


def test_macmini_release_and_secret_boundaries_are_explicit() -> None:
    manifest = (ROOT / "evidence/release/release-manifest.json").read_text(encoding="utf-8")
    assert "ab8b20a696b9b1996495f23a3e413cc33a67b6861efa184c64742e0f310c6326" in manifest
    assert "com.oosu.fabops.release-hash" in COMPOSE
    env_example = (ROOT / "infra/macmini/.env.example").read_text(encoding="utf-8")
    assert "replace-with-generated-server-secret" in env_example
    assert "FABOPS_API_PORT=8210" in env_example
    assert "FABOPS_WEB_PORT=8220" in env_example


def test_macmini_operational_scripts_and_same_origin_web_exist() -> None:
    for name in ("deploy.sh", "status.sh", "logs.sh", "backup.sh", "restore-test.sh", "rollback.sh"):
        assert (ROOT / "infra/macmini/scripts" / name).is_file()
    nginx = (ROOT / "infra/macmini/nginx.conf").read_text(encoding="utf-8")
    assert "resolver 127.0.0.11" in nginx
    assert "set $fabops_api_upstream api:8000" in nginx
    assert "proxy_pass http://$fabops_api_upstream" in nginx
    assert "VITE_API_URL: \"\"" in COMPOSE


def test_redpanda_init_executes_both_topic_creation_commands_in_one_shell() -> None:
    block = _service_block("redpanda-init")
    assert "entrypoint:" in block
    assert "- /bin/sh" in block
    assert "- -ec" in block
    assert "rpk topic create fabops.events.v1" in block
    assert "rpk topic create fabops.events.dlq.v1" in block
    assert "command:" not in block
