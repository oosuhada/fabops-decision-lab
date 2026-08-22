from __future__ import annotations

from evaluation.m7_gate import EXPECTED_RELEASE_HASH, build_gate


def test_m7_gate_consumes_real_mac_mini_evidence_and_passes() -> None:
    gate = build_gate()

    assert gate["passed"] is True
    assert gate["status"] == "passed"
    assert gate["release_hash"] == EXPECTED_RELEASE_HASH
    assert gate["public_ingress_status"] == "unverified"
    assert all(gate["checks"].values())


def test_m7_gate_keeps_public_ingress_as_explicit_non_blocking_boundary() -> None:
    gate = build_gate()

    assert gate["checks"]["public_ingress_boundary_explicit"] is True
    assert gate["public_ingress_status"] == "unverified"
