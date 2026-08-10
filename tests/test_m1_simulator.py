from __future__ import annotations

import ast
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from simulator.config import load_config
from simulator.fabtwin import FabTwinSimulator, canonical_hash
from simulator.generate import config_from_manifest, write_artifacts


def _trace(seed: int = 42):
    return FabTwinSimulator(load_config("test"), seed).generate()


def test_all_fault_families_exist_deterministically():
    result = _trace()
    assert [fault["family"] for fault in result.ground_truth["faults"]] == ["F1", "F2", "F3", "F4", "F5", "F6"]


def test_same_seed_and_config_produce_same_canonical_hash():
    assert canonical_hash(_trace(42).events) == canonical_hash(_trace(42).events)


def test_different_seed_meaningfully_changes_measurements():
    first = _trace(42).events
    second = _trace(43).events
    first_values = [event["payload"]["value"] for event in first if event["event_type"] == "process.measurement.recorded.v1"]
    second_values = [event["payload"]["value"] for event in second if event["event_type"] == "process.measurement.recorded.v1"]
    assert first_values != second_values
    assert abs(sum(first_values) - sum(second_values)) > 0.01


def test_every_event_validates_against_backward_compatible_envelope():
    schema = json.loads(Path("contracts/events/event-envelope.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    result = _trace()
    assert len(result.events) > 100
    for event in result.events:
        validator.validate(event)


def test_event_ids_remain_unique_even_for_f6_quality_incident():
    ids = [event["event_id"] for event in _trace().events]
    assert len(ids) == len(set(ids))


def test_required_event_types_are_present():
    event_types = {event["event_type"] for event in _trace().events}
    required = {
        "lot.released.v1",
        "process.started.v1",
        "process.measurement.recorded.v1",
        "process.completed.v1",
        "equipment.alarm.raised.v1",
        "maintenance.completed.v1",
        "inspection.completed.v1",
        "action.proposed.v1",
        "action.approved.v1",
        "action.rejected.v1",
        "case.closed.v1",
        "data.quality.incident.v1",
    }
    assert required <= event_types


def test_lot_step_equipment_chamber_inspection_lineage_is_referentially_intact():
    events = _trace().events
    lot_ids = {event["lot_id"] for event in events if event["event_type"] == "lot.released.v1"}
    runs = {
        event["payload"]["process_run_id"]: event
        for event in events
        if event["event_type"] == "process.started.v1"
    }
    completed = {
        event["payload"]["process_run_id"]
        for event in events
        if event["event_type"] == "process.completed.v1"
    }
    measurements = [event for event in events if event["event_type"] == "process.measurement.recorded.v1"]
    inspections = [event for event in events if event["event_type"] == "inspection.completed.v1"]
    assert runs.keys() <= completed
    assert all(event["lot_id"] in lot_ids for event in measurements + inspections)
    assert all(event["payload"]["process_run_id"] in runs for event in measurements)
    assert all(event["equipment_id"] and event["chamber_id"] for event in measurements)
    assert all(event["wafer_id"] and event["payload"]["step_id"] == "INSPECTION" for event in inspections)


def test_fault_effect_is_limited_to_intended_scope():
    result = _trace()
    intended = {
        fault["family"]: (fault["start_lot"], fault["end_lot"])
        for fault in result.ground_truth["faults"]
        if fault["physical_fault"]
    }
    assert intended == {"F1": (2, 3), "F2": (4, 4), "F3": (5, 5), "F4": (6, 6)}
    yields_by_lot: dict[str, list[float]] = {}
    for event in result.events:
        if event["event_type"] == "inspection.completed.v1":
            yields_by_lot.setdefault(event["lot_id"], []).append(event["payload"]["yield"])
    assert all(sum(yields_by_lot[f"LOT-{index:05d}"]) / len(yields_by_lot[f"LOT-{index:05d}"]) < 0.90 for index in range(2, 7))
    assert sum(yields_by_lot["LOT-00007"]) / len(yields_by_lot["LOT-00007"]) > 0.90
    assert sum(yields_by_lot["LOT-00008"]) / len(yields_by_lot["LOT-00008"]) > 0.90


def test_f5_has_sensor_shift_without_real_yield_impact():
    events = _trace().events
    f5_measurements = [event for event in events if event["lot_id"] == "LOT-00007" and event["event_type"] == "process.measurement.recorded.v1"]
    assert max(event["payload"]["value"] for event in f5_measurements if event["payload"]["sensor_name"] == "temperature") > 12.0
    assert all("physical_deviation" not in event["payload"] for event in f5_measurements)
    f5_yields = [event["payload"]["yield"] for event in events if event["lot_id"] == "LOT-00007" and event["event_type"] == "inspection.completed.v1"]
    assert min(f5_yields) > 0.90


def test_f6_is_non_physical_ground_truth_and_only_quality_events():
    result = _trace()
    f6 = next(fault for fault in result.ground_truth["faults"] if fault["family"] == "F6")
    assert f6["physical_fault"] is False
    assert f6["yield_impact"] is False
    f6_events = [event for event in result.events if event["lot_id"] == "LOT-00008"]
    assert any(event["event_type"] == "data.quality.incident.v1" for event in f6_events)
    assert all("physical_deviation" not in event["payload"] for event in f6_events)


def test_operational_import_graph_cannot_reach_ground_truth():
    roots = [Path("services"), Path("systems"), Path("adapters")]
    violations: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(alias.name == "ground_truth" or alias.name.startswith("ground_truth.") for alias in node.names):
                        violations.append(str(path))
                elif isinstance(node, ast.ImportFrom) and node.module and (node.module == "ground_truth" or node.module.startswith("ground_truth.")):
                    violations.append(str(path))
    assert violations == []


def test_operational_dependency_graph_has_no_transitive_ground_truth_import():
    project_modules: dict[str, Path] = {}
    for root in (Path("services"), Path("systems"), Path("adapters"), Path("simulator"), Path("evaluation"), Path("ground_truth")):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            module = ".".join(path.with_suffix("").parts)
            if module.endswith(".__init__"):
                module = module[: -len(".__init__")]
            project_modules[module] = path

    imports: dict[str, set[str]] = {module: set() for module in project_modules}
    for module, path in project_modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports[module].update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports[module].add(node.module)

    operational_roots = [module for module in project_modules if module.startswith(("services", "systems", "adapters"))]
    visited: set[str] = set()
    stack = list(operational_roots)
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for dependency in imports.get(current, set()):
            if dependency == "ground_truth" or dependency.startswith("ground_truth."):
                raise AssertionError(f"operational dependency graph reaches {dependency} from {current}")
            for candidate in project_modules:
                if candidate == dependency or candidate.startswith(dependency + "."):
                    stack.append(candidate)


def test_manifest_is_sufficient_to_regenerate_artifact(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest = write_artifacts(first, 42, load_config("test"))
    seed, config = config_from_manifest(first / "manifest.json")
    replay_manifest = write_artifacts(second, seed, config)
    assert manifest["canonical_event_hash"] == replay_manifest["canonical_event_hash"]
    assert manifest["canonical_ground_truth_hash"] == replay_manifest["canonical_ground_truth_hash"]
    assert (first / "data-card.md").exists()

