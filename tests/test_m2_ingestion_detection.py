from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from adapters.redpanda.adapter import RedpandaEventBusAdapter
from evaluation.m2_metrics import detector_metrics
from services.detection.service import DeterministicDetector
from services.ingestion.adapters import DeterministicLocalEventBus, InMemoryCaseRepository, InMemoryEventRepository, InMemoryQuarantine
from services.ingestion.service import IngestionService
from simulator.config import load_config
from simulator.fabtwin import FabTwinSimulator, canonical_hash


def _pipeline(seed: int = 42):
    cases = InMemoryCaseRepository()
    events = InMemoryEventRepository()
    quarantine = InMemoryQuarantine()
    detector = DeterministicDetector(cases)
    ingestion = IngestionService(events, cases, quarantine, detector.consume)
    trace = FabTwinSimulator(load_config("test"), seed).generate()
    return trace, ingestion, events, cases, quarantine, detector


def test_duplicate_event_is_exactly_once_noop():
    trace, ingestion, events, cases, _, _ = _pipeline()
    event = next(item for item in trace.events if item["event_type"] == "inspection.completed.v1" and item["lot_id"] == "LOT-00002")
    first = ingestion.ingest(event)
    second = ingestion.ingest(deepcopy(event))
    assert first == "on_time"
    assert second == "duplicate_noop"
    assert len(events.all_events()) == 1
    assert len(cases.audit_log()) <= 1


def test_invalid_event_goes_to_quarantine_without_side_effect():
    _, ingestion, events, cases, quarantine, _ = _pipeline()
    assert ingestion.ingest({"event_id": "broken"}) == "quarantined"
    assert len(quarantine.all()) == 1
    assert events.all_events() == []
    assert cases.list_cases() == []


def test_late_and_out_of_order_are_persisted_once_with_policy_status():
    trace, ingestion, events, _, _, _ = _pipeline()
    ordered = [event for event in trace.events if event["trace_id"] == trace.events[0]["trace_id"]][:3]
    assert ingestion.ingest(ordered[2]) == "on_time"
    assert ingestion.ingest(ordered[0]) == "out_of_order"
    late = next(event for event in trace.events if event["event_type"] == "data.quality.incident.v1" and event["payload"]["incident_type"] == "late")
    assert ingestion.ingest(late) == "late"
    assert [item.delivery_status for item in events.all_events()] == ["on_time", "out_of_order", "late"]


def test_full_trace_distinguishes_physical_f5_and_f6():
    trace, ingestion, _, cases, _, _ = _pipeline()
    for event in trace.events:
        ingestion.ingest(event)
    by_lot = {case["lot_id"]: case for case in cases.list_cases()}
    for index in range(2, 7):
        assert by_lot[f"LOT-{index:05d}"]["classification"] == "physical_excursion"
    assert by_lot["LOT-00007"]["classification"] == "sensor_bias_suspected"
    assert by_lot["LOT-00008"]["classification"] == "data_quality_incident"
    assert by_lot["LOT-00007"]["mean_yield"] > 0.9
    assert by_lot["LOT-00008"]["mean_yield"] is None or by_lot["LOT-00008"]["mean_yield"] > 0.9


def test_repository_recreation_and_replay_yield_identical_case_result():
    trace, ingestion, _, cases, _, _ = _pipeline()
    for event in trace.events:
        ingestion.ingest(event)
    first_hash = canonical_hash(cases.list_cases())

    second_cases = InMemoryCaseRepository()
    second_events = InMemoryEventRepository()
    second_quarantine = InMemoryQuarantine()
    second_detector = DeterministicDetector(second_cases)
    second_ingestion = IngestionService(second_events, second_cases, second_quarantine, second_detector.consume)
    for event in trace.events:
        second_ingestion.ingest(deepcopy(event))
    assert canonical_hash(second_cases.list_cases()) == first_hash
    assert second_events.checkpoint("detection") == len(trace.events)


def test_detector_metrics_are_ground_truth_evaluation_only():
    trace, ingestion, _, cases, _, _ = _pipeline()
    for event in trace.events:
        ingestion.ingest(event)
    metrics = detector_metrics(cases.list_cases(), trace.ground_truth, load_config("test").simulated_days)
    assert metrics["fault_recall"] == 1.0
    assert metrics["false_alarms_per_simulated_day"] == 0.0
    assert metrics["affected_scope_precision"] == 1.0


def test_local_bus_retry_and_dlq_contract():
    bus = DeterministicLocalEventBus(max_attempts=2)
    attempts = {"count": 0}

    def failing(_: dict):
        attempts["count"] += 1
        raise RuntimeError("boom")

    bus.subscribe("events", failing)
    bus.publish("events", {"event_id": "evt-1"})
    assert attempts["count"] == 2
    assert bus.dlq == [{"topic": "events", "event": {"event_id": "evt-1"}, "attempts": 2, "error": "RuntimeError"}]


def test_redpanda_adapter_contract_uses_event_id_as_key_and_canonical_json():
    sent: list[tuple[str, bytes, bytes]] = []
    adapter = RedpandaEventBusAdapter(lambda topic, key, value: sent.append((topic, key, value)))
    event = {"event_id": "evt-1", "event_type": "lot.released.v1", "payload": {"b": 2, "a": 1}}
    adapter.publish("fabops.events.v1", event)
    assert sent[0][0] == "fabops.events.v1"
    assert sent[0][1] == b"evt-1"
    assert json.loads(sent[0][2]) == event


def test_postgres_migration_contains_source_of_truth_outbox_audit_and_checkpoint():
    sql = Path("adapters/postgres/migrations/001_initial.sql").read_text(encoding="utf-8").lower()
    for table in ("fabops_event_log", "fabops_measurements", "fabops_cases", "fabops_decision_audit", "fabops_outbox", "fabops_quarantine", "fabops_projection_checkpoint"):
        assert table in sql
    assert "jsonb" in sql
    assert "sqlite" in sql  # explicit documentation that sqlite is not production

