from __future__ import annotations

import json
from pathlib import Path

from evaluation.m6_fitness import build_attribution_audit, build_fitness_summary, write_evidence


def test_architecture_fitness_invariants_are_executable() -> None:
    summary = build_fitness_summary()
    assert summary["passed"] is True
    assert all(summary["checks"].values())
    assert summary["violations"] == {
        "ground_truth_import_paths": [],
        "advisory_state_mutations": [],
        "equipment_control_routes": [],
        "ground_truth_exposure_files": [],
        "sqlite_production": [],
    }
    assert len(summary["tool_registry"]) == 5
    assert summary["source_of_truth"].startswith("PostgreSQL")
    assert summary["projection"].startswith("Neo4j")


def test_attribution_audit_preserves_claim_boundaries_and_dependency_metadata() -> None:
    audit = build_attribution_audit()
    assert audit["secom_feature_semantics_invented"] is False
    assert audit["wm811k_to_synthetic_sensor_lineage_claimed"] is False
    assert audit["samsung_or_internal_fab_data_used"] is False
    assert "Interaction grammar only" in audit["palantir_foundry_reference"]
    assert audit["license_audit"]["copied_third_party_source_detected"] is False
    assert audit["license_audit"]["python_direct_dependencies"]
    assert audit["license_audit"]["node_direct_dependencies"]


def test_fitness_evidence_is_generated_not_hand_entered(tmp_path: Path) -> None:
    fitness_path, attribution_path = write_evidence(tmp_path)
    fitness = json.loads(fitness_path.read_text(encoding="utf-8"))
    attribution = json.loads(attribution_path.read_text(encoding="utf-8"))
    assert fitness["schema_version"] == "m6-architecture-fitness-v1"
    assert fitness["passed"] is True
    assert len(attribution["audit_hash"]) == 64
