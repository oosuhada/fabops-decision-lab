from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from adapters.acl.canonical import CanonicalInputAdapter
from adapters.neo4j.adapter import Neo4jProjectionAdapter
from evaluation.m3_metrics import EXPECTED, rca_metrics
from services.detection.service import DeterministicDetector
from services.ingestion.adapters import InMemoryCaseRepository, InMemoryEventRepository, InMemoryQuarantine
from services.ingestion.service import IngestionService
from services.rca.cqrs import (
    ProjectionStatusQuery,
    RankRootCausesQuery,
    RcaCommandHandler,
    RcaQueryService,
    RebuildProjectionCommand,
    TraceAffectedLotsQuery,
)
from services.rca.graph import InMemoryGraphProjection
from services.rca.projection import PROJECTION_VERSION, RcaProjectionWorker
from simulator.config import load_config
from simulator.fabtwin import FabTwinSimulator, canonical_hash


class _PersistentStatusEvents:
    def __init__(self, count: int) -> None:
        self.count = count

    def event_count(self) -> int:
        return self.count


class _PersistentStatusGraph(InMemoryGraphProjection):
    projection_version = "rca-postgres-graph-v2.0.0"

    def __init__(self, checkpoint: int, updated_at: datetime) -> None:
        super().__init__()
        self._checkpoint = checkpoint
        self._updated_at = updated_at

    def projection_checkpoint(self) -> int:
        return self._checkpoint

    def projection_updated_at(self) -> datetime:
        return self._updated_at


def _built(seed: int = 42):
    trace = FabTwinSimulator(load_config("test"), seed).generate()
    cases = InMemoryCaseRepository()
    events = InMemoryEventRepository()
    quarantine = InMemoryQuarantine()
    detector = DeterministicDetector(cases)
    ingestion = IngestionService(events, cases, quarantine, detector.consume)
    for event in trace.events:
        ingestion.ingest(event)
    graph = InMemoryGraphProjection()
    worker = RcaProjectionWorker(events, graph)
    command = RcaCommandHandler(worker)
    command.handle(RebuildProjectionCommand("test"))
    queries = RcaQueryService(graph, cases, worker)
    return trace, ingestion, events, cases, graph, worker, queries


def test_projection_models_required_traceability_entities():
    _, _, _, _, graph, worker, _ = _built()
    for kind in ("Lot", "Wafer", "ProcessRun", "ProcessStep", "Equipment", "Chamber", "Recipe", "Measurement", "Alarm", "Maintenance", "Inspection"):
        assert graph.nodes(kind), kind
    status = worker.status()
    assert status.projection_version == PROJECTION_VERSION
    assert status.stale is False
    assert status.lag_events == 0


def test_persistent_projection_stale_state_tracks_slo_breach_not_small_live_lag():
    current_graph = _PersistentStatusGraph(90, datetime.now(timezone.utc))
    current = RcaProjectionWorker(_PersistentStatusEvents(100), current_graph).status()
    assert current.lag_events == 10
    assert current.slo_state == "MET"
    assert current.stale is False

    old_graph = _PersistentStatusGraph(90, datetime.now(timezone.utc) - timedelta(seconds=45))
    breached = RcaProjectionWorker(_PersistentStatusEvents(100), old_graph).status()
    assert breached.slo_state == "BREACHED"
    assert breached.stale is True


def test_manual_trace_query_answers_lot_step_equipment_chamber_recipe():
    _, _, _, cases, _, _, queries = _built()
    case = next(case for case in cases.list_cases() if case["lot_id"] == "LOT-00006")
    result = queries.execute(TraceAffectedLotsQuery(case["case_id"]))
    assert result["affected_lots"] == ["LOT-00006"]
    assert [item["step_id"] for item in result["process_path"]] == ["LITHO", "ETCH", "DEPOSITION", "CMP", "INSPECTION"]
    etch = next(item for item in result["process_path"] if item["step_id"] == "ETCH")
    assert etch["equipment_id"] == "ETCH-02"
    assert etch["chamber_id"] == "ETCH-02-B"


def test_rca_top_candidate_matches_all_fault_families_without_ground_truth_access():
    trace, _, _, cases, _, _, queries = _built()
    rankings: dict[str, list[dict]] = {}
    for case in cases.list_cases():
        rankings[case["lot_id"]] = queries.execute(RankRootCausesQuery(case["case_id"]))["candidates"]
    metrics = rca_metrics(rankings, trace.ground_truth)
    assert metrics["top1_accuracy"] == 1.0
    assert metrics["top3_accuracy"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["false_causal_attribution_rate"] == 0.0
    for lot_id, ranking in rankings.items():
        assert ranking[0]["candidate_id"] == EXPECTED[next(f["family"] for f in trace.ground_truth["faults"] if f["start_lot"] <= int(lot_id[-5:]) <= f["end_lot"])]


def test_f5_and_f6_do_not_rank_equipment_hold_as_correct_physical_cause():
    _, _, _, cases, _, _, queries = _built()
    f5 = next(case for case in cases.list_cases() if case["lot_id"] == "LOT-00007")
    f6 = next(case for case in cases.list_cases() if case["lot_id"] == "LOT-00008")
    f5_ranking = queries.execute(RankRootCausesQuery(f5["case_id"]))["candidates"]
    f6_ranking = queries.execute(RankRootCausesQuery(f6["case_id"]))["candidates"]
    assert f5_ranking[0]["candidate_type"] == "sensor_calibration"
    assert f5_ranking[0]["contradicting_evidence"]
    assert f6_ranking[0]["candidate_type"] == "data_quality"
    assert "do not hold equipment" in f6_ranking[0]["recommended_action"]


def test_projection_can_be_deleted_and_fully_rebuilt_from_source_of_truth():
    _, _, _, _, graph, worker, _ = _built()
    before = canonical_hash({"nodes": [node.__dict__ for node in graph.nodes()], "edges": [edge.__dict__ for edge in graph.edges()]})
    graph.clear()
    assert graph.nodes() == []
    worker.rebuild()
    after = canonical_hash({"nodes": [node.__dict__ for node in graph.nodes()], "edges": [edge.__dict__ for edge in graph.edges()]})
    assert after == before


def test_projection_lag_and_stale_status_are_exposed_then_caught_up():
    trace, ingestion, events, _, _, worker, queries = _built()
    extra = deepcopy(trace.events[0])
    extra["event_id"] = "00000000-0000-0000-0000-000000000099"
    extra["trace_id"] = "extra-trace"
    ingestion.ingest(extra)
    stale = queries.execute(ProjectionStatusQuery())["projection"]
    assert stale["stale"] is True
    assert stale["lag_events"] == 1
    fresh = worker.catch_up()
    assert fresh.stale is False
    assert fresh.projection_checkpoint == len(events.all_events())


def test_held_out_seeds_keep_representative_top1_answers():
    for seed in (41, 59):
        trace, _, _, cases, _, _, queries = _built(seed)
        rankings = {
            case["lot_id"]: queries.execute(RankRootCausesQuery(case["case_id"]))["candidates"]
            for case in cases.list_cases()
        }
        assert rca_metrics(rankings, trace.ground_truth)["top1_accuracy"] == 1.0


def test_anti_corruption_layer_preserves_public_feature_anonymity_and_provenance():
    record = CanonicalInputAdapter.public_record("UCI-SECOM", "row-1", {"feature_0": 1.2, "feature_589": None})
    assert record["data_classification"] == "real-public"
    assert set(record["features"]) == {"feature_0", "feature_589"}
    assert "do-not-invent-process-meaning" in record["semantics_policy"]


def test_neo4j_adapter_is_rebuildable_projection_contract_not_source_of_truth():
    calls: list[tuple[str, dict]] = []
    adapter = Neo4jProjectionAdapter(lambda query, params: calls.append((query, params)))
    adapter.upsert_node("Lot", "LOT-1", {"lot_id": "LOT-1"})
    adapter.upsert_node("Wafer", "W-1", {"wafer_id": "W-1"})
    adapter.upsert_edge("Lot", "LOT-1", "CONTAINS", "Wafer", "W-1")
    adapter.clear()
    assert len(calls) == 4
    assert "DETACH DELETE" in calls[-1][0]
    assert all("ground_truth" not in query for query, _ in calls)

