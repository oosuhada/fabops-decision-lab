from __future__ import annotations

from evaluation.m6_gate import (
    EXPECTED_FAULT_FAMILIES,
    EXPECTED_M5_HASH,
    _release_critical_placeholders,
    build_gate,
)


def test_placeholder_scan_does_not_match_its_own_search_literals() -> None:
    violations = _release_critical_placeholders()
    assert not any(item.startswith("evaluation/m6_gate.py:") for item in violations)


def test_m6_final_gate_is_derived_from_release_evidence() -> None:
    gate = build_gate()
    assert gate["passed"] is True
    assert gate["m5_evaluation_hash"] == EXPECTED_M5_HASH
    assert set(gate["held_out_fault_families"]) == EXPECTED_FAULT_FAMILIES
    assert gate["known_negative_contradicting_evidence_coverage"] == 0.42857
    assert gate["integration_verification"]["container_integration_verified"] is True
