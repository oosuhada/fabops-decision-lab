from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")


def test_canonical_stack_does_not_use_image_declared_anonymous_volumes() -> None:
    assert "fabops_redpanda_init_data:/var/lib/redpanda/data" in COMPOSE
    assert "fabops_neo4j_data:/data" in COMPOSE
    assert "fabops_neo4j_logs:/logs" in COMPOSE


def test_neo4j_browser_temp_files_are_bounded() -> None:
    assert "/tmp:size=256m,mode=1777" in COMPOSE
