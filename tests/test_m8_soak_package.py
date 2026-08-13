from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR_PATH = ROOT / "infra/macmini/soak_collector.py"
INSTALLER_PATH = ROOT / "infra/macmini/scripts/install-soak.sh"


def test_soak_collector_is_dependency_free_and_bounded() -> None:
    source = COLLECTOR_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )

    assert "requests" not in imported_roots
    assert "psutil" not in imported_roots
    assert "MAX_SAMPLE_BYTES = 5 * 1024 * 1024" in source
    assert "RETENTION_HOURS = 72" in source
    assert "MAX_ROTATED_FILES = 12" in source
    assert '"event_payloads_collected": False' in source
    assert '"credentials_collected": False' in source


def test_installer_uses_launchd_every_five_minutes_and_stable_data_root() -> None:
    source = INSTALLER_PATH.read_text(encoding="utf-8")

    assert "com.oosu.fabops-burnin" in source
    assert "<integer>300</integer>" in source
    assert "fabops-decision-lab-data/burnin" in source
    assert "launchctl bootstrap" in source
    assert "launchctl kickstart" in source
    assert "chmod 0600" in source
    assert 'SAMPLE_FILENAME="soak.jsonl"' in source
