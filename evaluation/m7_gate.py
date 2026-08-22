from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_EVIDENCE = (
    "evidence/m6-gate.json",
    "evidence/release/release-manifest.json",
    "evidence/m7/host-inventory.redacted.json",
    "evidence/m7/deployment-summary.json",
    "evidence/m7/container-integration-summary.json",
    "evidence/m7/backup-restore-summary.json",
    "evidence/m7/rollback-summary.json",
    "evidence/m7/existing-services-impact.json",
)

EXPECTED_RELEASE_VERSION = "0.6.0"
EXPECTED_RELEASE_HASH = "ab8b20a696b9b1996495f23a3e413cc33a67b6861efa184c64742e0f310c6326"


def _load(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _passed(document: dict[str, Any]) -> bool:
    return document.get("passed") is True and str(document.get("status", "")).lower() == "passed"


def _all_healthy(health: dict[str, Any]) -> bool:
    required = {"api", "web", "postgres", "redpanda", "neo4j"}
    return required.issubset(health) and all(str(health[name]).lower() == "healthy" for name in required)


def _resource_limits_valid(limits: dict[str, Any]) -> bool:
    required = {"api", "web", "postgres", "redpanda", "neo4j"}
    if not required.issubset(limits):
        return False
    return all(
        int(limits[name].get("nano_cpus", 0)) > 0
        and int(limits[name].get("memory_bytes", 0)) > 0
        and limits[name].get("restart_policy") == "unless-stopped"
        for name in required
    )


def build_gate() -> dict[str, Any]:
    missing = [path for path in REQUIRED_EVIDENCE if not (ROOT / path).exists()]
    if missing:
        return {
            "milestone": "M7",
            "schema_version": "m7-gate-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "passed": False,
            "missing_evidence": missing,
            "checks": {"required_evidence_present": False},
        }

    m6 = _load("evidence/m6-gate.json")
    manifest = _load("evidence/release/release-manifest.json")
    host = _load("evidence/m7/host-inventory.redacted.json")
    deployment = _load("evidence/m7/deployment-summary.json")
    integration = _load("evidence/m7/container-integration-summary.json")
    backup = _load("evidence/m7/backup-restore-summary.json")
    rollback = _load("evidence/m7/rollback-summary.json")
    impact = _load("evidence/m7/existing-services-impact.json")

    release = deployment.get("release", {})
    ports = deployment.get("ports", {})
    runtime = deployment.get("runtime", {})
    public_ingress = deployment.get("public_ingress", {})
    boundaries = deployment.get("boundaries", {})
    verified_behaviors = integration.get("verified_behaviors", {})
    restart = integration.get("api_restart_survival", {})
    browser = integration.get("browser_contract", {})
    restore = backup.get("restore_test", {})
    rollback_drill = rollback.get("drill", {})
    redeploy = rollback.get("clean_redeploy_after_drill", {})
    impact_checks = impact.get("checks", {})

    ingress_status = str(public_ingress.get("status", "")).lower()
    public_ingress_boundary_valid = ingress_status == "verified" or (
        ingress_status == "unverified"
        and public_ingress.get("hostname_configured") is False
        and public_ingress.get("ontology_oosu_dev_modified") is False
        and bool(public_ingress.get("reason"))
    )

    checks = {
        "required_evidence_present": True,
        "m6_remains_passed": _passed(m6),
        "host_preflight_passed": host.get("access", {}).get("ssh_verified") is True
        and host.get("port_preflight", {}).get("selected_ports_verified_free") is True,
        "deployment_evidence_passed": _passed(deployment),
        "container_integration_evidence_passed": _passed(integration),
        "backup_restore_evidence_passed": _passed(backup),
        "rollback_evidence_passed": _passed(rollback),
        "existing_services_impact_passed": _passed(impact),
        "release_identity_matches_manifest": release.get("release_version") == manifest.get("release_version") == EXPECTED_RELEASE_VERSION
        and release.get("release_hash") == manifest.get("release_hash") == EXPECTED_RELEASE_HASH,
        "all_long_running_containers_healthy": _all_healthy(deployment.get("container_health", {})),
        "api_web_localhost_only": ports.get("api") == "127.0.0.1:8210" and ports.get("web") == "127.0.0.1:8220",
        "datastores_private_only": ports.get("postgres_host_published") is False
        and ports.get("redpanda_host_published") is False
        and ports.get("neo4j_host_published") is False,
        "resource_ceilings_present": _resource_limits_valid(deployment.get("resource_limits", {})),
        "postgres_authoritative_verified": runtime.get("postgres_runtime_verified") is True,
        "redpanda_verified": runtime.get("redpanda_runtime_verified") is True,
        "neo4j_verified": runtime.get("neo4j_runtime_verified") is True,
        "projection_lag_zero": runtime.get("projection_lag_events") == 0,
        "idempotency_and_dlq_verified": verified_behaviors.get("idempotent_duplicate_ingest") is True
        and verified_behaviors.get("redpanda_reconsume_duplicate_handling") is True
        and verified_behaviors.get("redpanda_dlq") is True,
        "main_and_dlq_topics_present": verified_behaviors.get("main_topic_present") is True
        and verified_behaviors.get("dlq_topic_present") is True
        and verified_behaviors.get("consumer_lag") == 0,
        "api_restart_survives": restart.get("verified") is True and restart.get("counts_before") == restart.get("counts_after"),
        "browser_contract_passed": browser.get("passed") == 1 and browser.get("failed") == 0,
        "isolated_restore_verified": restore.get("restored_events") == 373
        and restore.get("restored_cases") == 7
        and restore.get("restored_schema_migrations") == 2
        and restore.get("temporary_database_removed_after_validation") is True
        and restore.get("unrelated_database_modified") is False,
        "rollback_drill_verified": all(
            rollback_drill.get(key) is True
            for key in (
                "fabops_containers_removed",
                "fabops_network_removed",
                "active_postgres_directory_cleared",
                "active_redpanda_directory_cleared",
                "active_neo4j_directory_cleared",
                "previous_fabops_state_quarantined",
            )
        )
        and rollback_drill.get("unrelated_services_affected") is False,
        "clean_redeploy_verified": redeploy.get("passed") is True
        and redeploy.get("all_long_running_containers_healthy") is True
        and redeploy.get("projection_lag_events") == 0,
        "unrelated_services_unchanged": all(
            impact_checks.get(key) is True
            for key in (
                "all_preexisting_container_names_still_present",
                "ontology_dashboard_healthy",
                "dev_flow_dashboard_still_loaded",
                "cloudflared_still_loaded",
            )
        )
        and impact_checks.get("ontology_oosu_dev_modified") is False
        and impact_checks.get("unrelated_database_contents_modified") is False,
        "public_ingress_boundary_explicit": public_ingress_boundary_valid,
        "equipment_control_disabled": runtime.get("equipment_control_enabled") is False,
        "external_llm_not_required": runtime.get("external_llm_required") is False,
        "claim_boundaries_preserved": boundaries.get("synthetic_demo_data") is True
        and boundaries.get("real_fab_performance_claim") is False
        and boundaries.get("samsung_internal_claim") is False,
        "no_secrets_in_evidence": boundaries.get("secrets_in_evidence") is False
        and host.get("boundaries", {}).get("secrets_captured") is False,
    }

    passed = all(checks.values())
    return {
        "milestone": "M7",
        "schema_version": "m7-gate-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "passed": passed,
        "release_version": release.get("release_version"),
        "release_hash": release.get("release_hash"),
        "deployed_git_sha": release.get("deployed_git_sha"),
        "public_ingress_status": ingress_status,
        "checks": checks,
        "missing_evidence": [],
    }


def write_gate(output: Path) -> dict[str, Any]:
    gate = build_gate()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(gate, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return gate


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the executable FabOps M7 Mac mini deployment gate.")
    parser.add_argument("--output", type=Path, default=Path("evidence/m7-gate.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    gate = write_gate(args.output)
    if args.check and not gate["passed"]:
        failed = [name for name, value in gate["checks"].items() if not value]
        raise SystemExit("M7 gate failed: " + ", ".join(failed))


if __name__ == "__main__":
    main()
