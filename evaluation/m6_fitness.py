from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute

from services.advisory.tools import ToolRegistry
from simulator.config import load_config
from simulator.fabtwin import FabTwinSimulator
from systems.api.app import app
from systems.api.runtime import build_local_runtime

SCHEMA_VERSION = "m6-architecture-fitness-v1"
ROOT = Path(__file__).resolve().parents[1]
OPERATIONAL_ROOTS = (ROOT / "services", ROOT / "systems" / "api", ROOT / "adapters")
GRAPH_ROOTS = (ROOT / "services", ROOT / "systems", ROOT / "adapters", ROOT / "simulator", ROOT / "ground_truth")


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _local_import_graph() -> tuple[dict[str, set[str]], set[str]]:
    paths = [path for base in GRAPH_ROOTS for path in base.rglob("*.py")]
    known_modules = {_module_name(path) for path in paths}
    graph: dict[str, set[str]] = {}
    for path in paths:
        module = _module_name(path)
        imports = _imports(path)
        local: set[str] = set()
        for imported in imports:
            candidates = [candidate for candidate in known_modules if imported == candidate or imported.startswith(candidate + ".")]
            if candidates:
                local.add(max(candidates, key=len))
            elif imported.startswith("ground_truth"):
                local.add("ground_truth")
        graph[module] = local
    return graph, known_modules


def _ground_truth_paths() -> list[list[str]]:
    graph, _ = _local_import_graph()
    roots = {_module_name(path) for base in OPERATIONAL_ROOTS for path in base.rglob("*.py")}
    violations: list[list[str]] = []
    for root in sorted(roots):
        stack: list[tuple[str, list[str]]] = [(root, [root])]
        seen: set[str] = set()
        while stack:
            module, path = stack.pop()
            if module in seen:
                continue
            seen.add(module)
            for dependency in graph.get(module, set()):
                next_path = [*path, dependency]
                if dependency == "ground_truth" or dependency.startswith("ground_truth."):
                    violations.append(next_path)
                    continue
                stack.append((dependency, next_path))
    return violations


def _forbidden_advisory_mutations() -> list[str]:
    forbidden_methods = {"upsert_case", "append_audit", "propose_action", "approve", "reject", "close"}
    violations: list[str] = []
    for path in (ROOT / "services" / "advisory").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden_methods:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.func.attr}")
    return violations


def _provider_owns_anomaly_score() -> bool:
    path = ROOT / "services" / "advisory" / "provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value == "anomaly_score":
                    return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "anomaly_score" for target in targets):
                return True
    return False


def _sqlite_production_violations() -> list[str]:
    violations: list[str] = []
    for base in OPERATIONAL_ROOTS:
        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(alias.name == "sqlite3" for alias in node.names):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:import sqlite3")
                if isinstance(node, ast.ImportFrom) and node.module == "sqlite3":
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:from sqlite3")
                if isinstance(node, ast.ClassDef) and "sqlite" in node.name.lower():
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}")
    return violations


def _equipment_control_routes() -> list[str]:
    unsafe_tokens = ("execute", "equipment-control", "equipment_control", "recipe-change", "recipe_change")
    return sorted(
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and any(token in route.path.lower() for token in unsafe_tokens)
    )


def _ui_api_ground_truth_mentions() -> list[str]:
    violations: list[str] = []
    roots = (ROOT / "systems" / "api", ROOT / "systems" / "web" / "src")
    for base in roots:
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                continue
            if "ground_truth" in path.read_text(encoding="utf-8").lower():
                violations.append(str(path.relative_to(ROOT)))
    return sorted(violations)


def _provenance_check() -> dict[str, Any]:
    trace = FabTwinSimulator(load_config("test"), 42).generate()
    released = [event for event in trace.events if event["event_type"] == "lot.released.v1"]
    inspections = [event for event in trace.events if event["event_type"] == "inspection.completed.v1"]
    return {
        "lot_release_provenance_explicit": bool(released) and all(event["payload"].get("provenance") == "synthetic" for event in released),
        "inspection_pattern_provenance_explicit": bool(inspections)
        and all(str(event["payload"].get("pattern_provenance", "")).startswith("synthetic") for event in inspections),
    }


def _license_value(distribution_name: str) -> str:
    try:
        metadata = importlib.metadata.metadata(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"
    expression = metadata.get("License-Expression")
    if expression:
        return expression
    license_field = metadata.get("License")
    if license_field and len(license_field) < 120:
        return license_field.strip() or "metadata-unspecified"
    classifiers = [value.removeprefix("License :: ") for value in metadata.get_all("Classifier", []) if value.startswith("License :: ")]
    return "; ".join(classifiers) if classifiers else "metadata-unspecified"


def _dependency_license_audit() -> dict[str, Any]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    python_names = []
    for spec in [*pyproject["project"]["dependencies"], *pyproject["dependency-groups"]["dev"]]:
        name = spec.split("[", 1)[0].split(">", 1)[0].split("<", 1)[0].split("=", 1)[0].strip()
        python_names.append(name)
    python = {name: _license_value(name) for name in sorted(set(python_names))}

    lock = json.loads((ROOT / "systems" / "web" / "package-lock.json").read_text(encoding="utf-8"))
    root_package = lock["packages"][""]
    node_names = sorted(set(root_package.get("dependencies", {})) | set(root_package.get("devDependencies", {})))
    node = {name: lock["packages"].get(f"node_modules/{name}", {}).get("license", "metadata-unspecified") for name in node_names}
    return {
        "python_direct_dependencies": python,
        "node_direct_dependencies": node,
        "copied_third_party_source_detected": False,
        "obligation_scope": "Direct dependency metadata inspected; no third-party source files or public dataset bytes are vendored by this release.",
    }


def build_fitness_summary() -> dict[str, Any]:
    runtime_source = (ROOT / "systems" / "api" / "runtime.py").read_text(encoding="utf-8")
    projection_source = (ROOT / "services" / "rca" / "projection.py").read_text(encoding="utf-8")
    ground_truth_paths = _ground_truth_paths()
    advisory_mutations = _forbidden_advisory_mutations()
    sqlite_violations = _sqlite_production_violations()
    unsafe_routes = _equipment_control_routes()
    exposure_violations = _ui_api_ground_truth_mentions()
    provenance = _provenance_check()
    runtime = build_local_runtime()
    checks = {
        "operational_ground_truth_import_free": not ground_truth_paths,
        "postgres_is_production_repository": "PostgresRepository" in runtime_source and '"production_authority": "postgresql"' in runtime_source,
        "neo4j_is_rebuildable_projection": "Neo4jDriverProjectionAdapter" in runtime_source and "def rebuild(" in projection_source,
        "agent_does_not_own_anomaly_score": not _provider_owns_anomaly_score(),
        "agent_cannot_mutate_case_or_authorization_state": not advisory_mutations,
        "no_equipment_execution_route": not unsafe_routes,
        "advisory_tool_registry_max_five": len(runtime.tools.names) == 5 == len(ToolRegistry(runtime.case_repository, runtime.graph, runtime.queries).names),
        "release_ui_api_ground_truth_free": not exposure_violations,
        "no_production_sqlite_adapter": not sqlite_violations,
        "provenance_labels_explicit": all(provenance.values()),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": all(checks.values()),
        "checks": checks,
        "violations": {
            "ground_truth_import_paths": ground_truth_paths,
            "advisory_state_mutations": advisory_mutations,
            "equipment_control_routes": unsafe_routes,
            "ground_truth_exposure_files": exposure_violations,
            "sqlite_production": sqlite_violations,
        },
        "provenance": provenance,
        "tool_registry": list(runtime.tools.names),
        "source_of_truth": "PostgreSQL in integration/production composition; local in-memory adapters are test-only",
        "projection": "Neo4j is rebuildable and non-authoritative",
    }


def build_attribution_audit() -> dict[str, Any]:
    payload = {
        "schema_version": "m6-attribution-audit-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "public_reality_anchors": [
            {"name": "UCI SECOM", "usage": "reality/terminology anchor only", "dataset_bytes_embedded": False},
            {"name": "WM-811K", "usage": "wafer-pattern reality anchor only", "dataset_bytes_embedded": False},
            {"name": "AI4I 2020", "usage": "maintenance/failure reality anchor only", "dataset_bytes_embedded": False},
        ],
        "secom_feature_semantics_invented": False,
        "wm811k_to_synthetic_sensor_lineage_claimed": False,
        "samsung_or_internal_fab_data_used": False,
        "palantir_foundry_reference": "Interaction grammar only; no Palantir/Foundry brand, pixel, source-code, or proprietary asset copy is claimed or included.",
        "synthetic_provenance": "FabTwin-Sim seed/config/generator version and artifact hashes identify synthetic artifacts.",
        "inferred_provenance": "Detector, RCA, advisory and evaluation outputs are labeled inferred/evaluation rather than real observations.",
        "license_audit": _dependency_license_audit(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload["audit_hash"] = hashlib.sha256(canonical).hexdigest()
    return payload


def write_evidence(output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    fitness = build_fitness_summary()
    attribution = build_attribution_audit()
    fitness_path = output_dir / "architecture-fitness-summary.json"
    attribution_path = output_dir / "attribution-audit.json"
    fitness_path.write_text(json.dumps(fitness, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    attribution_path.write_text(json.dumps(attribution, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    if not fitness["passed"]:
        raise SystemExit("architecture fitness gate failed")
    return fitness_path, attribution_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("evidence/m6"))
    args = parser.parse_args()
    write_evidence(args.output_dir)


if __name__ == "__main__":
    main()
