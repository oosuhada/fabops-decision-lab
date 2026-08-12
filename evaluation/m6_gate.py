from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.release_manifest import check_manifest
from services.advisory.provider import ADVISORY_VERSION
from services.release.identity import RELEASE_VERSION

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_M5_HASH = "78f7e90d37fa144ea8e29fb5977c21f300f1dc7bd062969b1bb0ec4dbe96a005"
EXPECTED_FAULT_FAMILIES = {"F1", "F2", "F3", "F4", "F5", "F6"}

REQUIRED_M6_EVIDENCE = (
    "evidence/m6/telemetry-summary.json",
    "evidence/m6/reliability-summary.json",
    "evidence/m6/trace-sample.json",
    "evidence/m6/performance-summary.json",
    "evidence/m6/recovery-summary.json",
    "evidence/m6/integration-summary.json",
    "evidence/m6/architecture-fitness-summary.json",
    "evidence/m6/attribution-audit.json",
    "evidence/m6/incident-projection-outage.json",
    "evidence/m6/canonical-verification.json",
    "evidence/release/release-manifest.json",
)

REQUIRED_DOCS = (
    "docs/operations/SLO.md",
    "docs/operations/RUNBOOK.md",
    "docs/security/THREAT_MODEL.md",
    "docs/security/SECRET_POLICY.md",
    "docs/postmortems/M6_NEO4J_PROJECTION_OUTAGE.md",
    "docs/portfolio/ARCHITECTURE_CASE_STUDY.md",
    "docs/portfolio/DEMO_5_MIN.md",
    "docs/portfolio/ARCHITECTURE_DEEP_DIVE_30_MIN.md",
)

RELEASE_CRITICAL_SCAN_PATHS = (
    "README.md",
    "services",
    "systems/api",
    "adapters",
    "evaluation",
    "scripts",
    "docs/portfolio",
    "docs/security",
    "docs/operations",
)


def _load(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _status_passed(value: Any) -> bool:
    return str(value).lower() == "passed"


def _release_critical_placeholders() -> list[str]:
    markers = ("TODO", "FIXME", "PENDING_GENERATED_MANIFEST")
    violations: list[str] = []
    scanner_path = Path(__file__).resolve()
    for relative in RELEASE_CRITICAL_SCAN_PATHS:
        path = ROOT / relative
        paths = [path] if path.is_file() else list(path.rglob("*"))
        for candidate in paths:
            if candidate.resolve() == scanner_path:
                continue
            if not candidate.is_file() or candidate.suffix not in {"", ".py", ".md", ".sh", ".json", ".ts", ".tsx"}:
                continue
            text = candidate.read_text(encoding="utf-8", errors="ignore")
            for marker in markers:
                if marker in text:
                    violations.append(f"{candidate.relative_to(ROOT)}:{marker}")
    return sorted(set(violations))


def _held_out_fault_families(evaluation: dict[str, Any]) -> set[str]:
    families: set[str] = set()
    for row in evaluation.get("seed_results", {}).get("held_out", []):
        families.update(str(family) for family in row.get("stratified", {}))
    return families


def build_gate() -> dict[str, Any]:
    baseline = {f"M{index}": _load(f"evidence/m{index}-gate.json") for index in range(6)}
    evaluation = _load("evidence/release/evaluation-summary.json")
    canonical = _load("evidence/m6/canonical-verification.json")
    integration = _load("evidence/m6/integration-summary.json")
    telemetry = _load("evidence/m6/telemetry-summary.json")
    reliability = _load("evidence/m6/reliability-summary.json")
    performance = _load("evidence/m6/performance-summary.json")
    recovery = _load("evidence/m6/recovery-summary.json")
    fitness = _load("evidence/m6/architecture-fitness-summary.json")
    incident = _load("evidence/m6/incident-projection-outage.json")
    manifest = _load("evidence/release/release-manifest.json")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    demo = (ROOT / "docs/portfolio/DEMO_5_MIN.md").read_text(encoding="utf-8")

    missing_evidence = [path for path in REQUIRED_M6_EVIDENCE if not (ROOT / path).exists()]
    missing_docs = [path for path in REQUIRED_DOCS if not (ROOT / path).exists()]
    placeholder_violations = _release_critical_placeholders()
    manifest_errors = check_manifest()
    held_out_families = _held_out_fault_families(evaluation)

    checks = {
        "m0_m5_gate_status_passed": all(_status_passed(item.get("status")) for item in baseline.values()),
        "accepted_m5_hash_preserved": evaluation.get("canonical_hash") == EXPECTED_M5_HASH
        and canonical.get("evaluation_hash") == EXPECTED_M5_HASH
        and canonical.get("evaluation_identity_passed") is True,
        "required_m6_evidence_present": not missing_evidence,
        "required_m6_docs_present": not missing_docs,
        "canonical_verification_passed": canonical.get("passed") is True,
        "clean_setup_passed": canonical.get("clean_setup", {}).get("passed") is True,
        "architecture_fitness_passed": fitness.get("passed") is True,
        "release_manifest_consistent": not manifest_errors,
        "release_version_coherent": manifest.get("release_version") == RELEASE_VERSION == "0.6.0",
        "advisory_version_coherent": manifest.get("advisory_version") == ADVISORY_VERSION == "deterministic-advisory-v1.1.0",
        "container_integration_actually_verified": integration.get("container_integration_verified") is True
        and canonical.get("docker_integration", {}).get("container_integration_verified") is True,
        "postgres_runtime_verified": integration.get("postgres_runtime_verified") is True,
        "redpanda_runtime_verified": integration.get("redpanda_runtime_verified") is True,
        "neo4j_runtime_verified": integration.get("neo4j_runtime_verified") is True,
        "telemetry_required_operations_present": telemetry.get("required_operations_present") is True,
        "telemetry_ground_truth_absent": telemetry.get("ground_truth_present") is False,
        "replay_completeness_one": reliability.get("replay_completeness") == 1.0
        and performance.get("replay_completeness") == 1.0,
        "duplicate_side_effect_rate_zero": reliability.get("duplicate_side_effect_rate") == 0.0
        and performance.get("duplicate_side_effect_rate") == 0.0,
        "local_rpo_zero": recovery.get("rpo_events", {}).get("max") == 0,
        "incident_executed_and_recovered": incident.get("degraded_detected") is True
        and incident.get("recovered") is True
        and incident.get("postgres_remained_authoritative") is True,
        "llm_off_core_supported": canonical.get("policy", {}).get("external_llm_required") is False,
        "equipment_control_disabled": canonical.get("policy", {}).get("equipment_control_enabled") is False
        and integration.get("actual_equipment_control") is False,
        "known_negative_result_preserved": evaluation.get("held_out_metrics", {}).get("rca", {}).get("contradicting_evidence_coverage") == 0.42857,
        "f1_f6_held_out_evaluation_connected": held_out_families == EXPECTED_FAULT_FAMILIES,
        "f1_f6_demo_boundary_visible": "F1–F6" in demo or "F1-F6" in demo,
        "release_claim_boundaries_visible": all(
            phrase in readme.lower()
            for phrase in (
                "not a real semiconductor fab",
                "not samsung data",
                "no synthetic-to-real performance claim",
                "no actual equipment control",
            )
        ),
        "no_release_critical_placeholders": not placeholder_violations,
    }
    return {
        "milestone": "M6",
        "schema_version": "m6-gate-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if all(checks.values()) else "failed",
        "passed": all(checks.values()),
        "release_version": manifest.get("release_version"),
        "release_hash": manifest.get("release_hash"),
        "source_git_commit": manifest.get("source_git_commit"),
        "m5_evaluation_hash": evaluation.get("canonical_hash"),
        "known_negative_contradicting_evidence_coverage": evaluation.get("held_out_metrics", {}).get("rca", {}).get("contradicting_evidence_coverage"),
        "checks": checks,
        "missing_evidence": missing_evidence,
        "missing_docs": missing_docs,
        "manifest_errors": manifest_errors,
        "placeholder_violations": placeholder_violations,
        "held_out_fault_families": sorted(held_out_families),
        "integration_verification": {
            "compose_config_verified": integration.get("compose_config_verified"),
            "postgres_runtime_verified": integration.get("postgres_runtime_verified"),
            "redpanda_runtime_verified": integration.get("redpanda_runtime_verified"),
            "neo4j_runtime_verified": integration.get("neo4j_runtime_verified"),
            "container_integration_verified": integration.get("container_integration_verified"),
        },
    }


def write_gate(output: Path) -> dict[str, Any]:
    gate = build_gate()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(gate, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return gate


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the executable FabOps M6 final gate evidence.")
    parser.add_argument("--output", type=Path, default=Path("evidence/m6-gate.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    gate = write_gate(args.output)
    if args.check and not gate["passed"]:
        failed = [name for name, value in gate["checks"].items() if not value]
        raise SystemExit("M6 final gate failed: " + ", ".join(failed))


if __name__ == "__main__":
    main()
