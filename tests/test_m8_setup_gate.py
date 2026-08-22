from __future__ import annotations

from datetime import datetime

from evaluation.m8_setup_gate import build_gate


def test_m8_setup_gate_passes_without_claiming_completed_soak() -> None:
    gate = build_gate()

    assert gate["passed"] is True
    assert gate["status"] == "passed"
    assert gate["m8_overall_status"] == "in_progress"
    assert gate["m8_overall_passed"] is False
    assert all(gate["checks"].values())


def test_m8_next_audit_is_exactly_twenty_four_hours_after_start() -> None:
    gate = build_gate()
    started = datetime.fromisoformat(gate["soak_started_at"])
    next_audit = datetime.fromisoformat(gate["next_audit_at"])

    assert (next_audit - started).total_seconds() == 24 * 60 * 60
