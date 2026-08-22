import json

from jsonschema import validate

from simulator.generate import build, canonical_hash


def test_seed_is_deterministic():
    assert canonical_hash(build(42)[0]) == canonical_hash(build(42)[0])

def test_event_schema():
    schema=json.load(open("contracts/events/event-envelope.schema.json"))
    validate(build(42)[0][0], schema)

def test_ground_truth_separate():
    events, truth = build(42)
    assert "fault_family" in truth
    assert "fault_family" not in events[0]["payload"]

def test_event_ids_are_unique():
    events, _ = build(42)
    ids = [event["event_id"] for event in events]
    assert len(ids) == len(set(ids))

def test_different_seed_changes_artifact():
    assert canonical_hash(build(42)[0]) != canonical_hash(build(43)[0])

def test_truth_has_provenance_fields():
    _, truth = build(42)
    assert all(key in truth for key in ["seed", "config_version", "generator_version", "schema_version"])

