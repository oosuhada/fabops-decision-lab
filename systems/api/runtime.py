from __future__ import annotations

from dataclasses import dataclass

from services.advisory.provider import DeterministicAdvisoryProvider
from services.advisory.tools import ToolRegistry
from services.detection.service import DeterministicDetector
from services.ingestion.adapters import InMemoryCaseRepository, InMemoryEventRepository, InMemoryQuarantine
from services.ingestion.service import IngestionService
from services.rca.cqrs import RcaQueryService
from services.rca.graph import InMemoryGraphProjection
from services.rca.projection import RcaProjectionWorker
from services.workflow.state_machine import CaseWorkflowService
from simulator.config import SimulatorConfig, load_config
from simulator.fabtwin import FabTwinSimulator


@dataclass
class LocalRuntime:
    config: SimulatorConfig
    seed: int
    event_repository: InMemoryEventRepository
    case_repository: InMemoryCaseRepository
    quarantine: InMemoryQuarantine
    detector: DeterministicDetector
    ingestion: IngestionService
    graph: InMemoryGraphProjection
    projection: RcaProjectionWorker
    queries: RcaQueryService
    tools: ToolRegistry
    advisory: DeterministicAdvisoryProvider
    workflow: CaseWorkflowService


def build_local_runtime(seed: int = 42, profile: str = "test") -> LocalRuntime:
    config = load_config(profile)
    trace = FabTwinSimulator(config, seed).generate()
    event_repository = InMemoryEventRepository()
    case_repository = InMemoryCaseRepository()
    quarantine = InMemoryQuarantine()
    detector = DeterministicDetector(case_repository)
    ingestion = IngestionService(event_repository, case_repository, quarantine, detector.consume)
    for event in trace.events:
        ingestion.ingest(event)
    graph = InMemoryGraphProjection()
    projection = RcaProjectionWorker(event_repository, graph)
    projection.rebuild()
    queries = RcaQueryService(graph, case_repository, projection)
    tools = ToolRegistry(case_repository, graph, queries)
    advisory = DeterministicAdvisoryProvider(tools)
    workflow = CaseWorkflowService(case_repository)
    return LocalRuntime(
        config,
        seed,
        event_repository,
        case_repository,
        quarantine,
        detector,
        ingestion,
        graph,
        projection,
        queries,
        tools,
        advisory,
        workflow,
    )

