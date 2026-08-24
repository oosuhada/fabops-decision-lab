from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adapters.neo4j import Neo4jConfig, Neo4jDriverProjectionAdapter
from adapters.postgres import PostgresConfig, PostgresRepository, ReadOnlyPostgresRepository
from adapters.redpanda.adapter import RedpandaConfig, RedpandaEventBusAdapter
from services.advisory.provider import DeterministicAdvisoryProvider
from services.advisory.tools import ToolRegistry
from services.detection.service import DeterministicDetector
from services.ingestion.adapters import InMemoryCaseRepository, InMemoryEventRepository, InMemoryQuarantine
from services.ingestion.service import IngestionService
from services.observability.telemetry import TelemetryRecorder
from services.rca.cqrs import RcaQueryService
from services.rca.graph import InMemoryGraphProjection
from services.rca.projection import RcaProjectionWorker
from services.workflow.state_machine import AuthorizationError, CaseWorkflowService
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
    telemetry: TelemetryRecorder
    runtime_mode: str = "local"

    def integration_status(self) -> dict[str, Any]:
        evidence_path = Path("evidence/m6/integration-summary.json")
        if not evidence_path.exists():
            return {
                "status": "unverified",
                "compose_config_verified": False,
                "postgres_runtime_verified": False,
                "redpanda_runtime_verified": False,
                "neo4j_runtime_verified": False,
                "container_integration_verified": False,
                "reason": "M6 integration evidence has not been generated yet",
            }
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
        return {
            "status": data.get("status", "unverified"),
            "compose_config_verified": bool(data.get("compose_config_verified", False)),
            "postgres_runtime_verified": bool(data.get("postgres_runtime_verified", False)),
            "redpanda_runtime_verified": bool(data.get("redpanda_runtime_verified", False)),
            "neo4j_runtime_verified": bool(data.get("neo4j_runtime_verified", False)),
            "container_integration_verified": bool(data.get("container_integration_verified", False)),
            "reason": data.get("reason"),
        }

    def health_status(self) -> dict[str, Any]:
        projection = self.projection.status()
        integration = self.integration_status()
        source_ready = len(self.event_repository.all_events()) > 0 and self.event_repository.checkpoint("detection") == len(self.event_repository.all_events())
        advisory_ready = len(self.tools.names) == 5
        local_ready = source_ready and not projection.stale and advisory_ready
        integration_ready = bool(integration["container_integration_verified"])
        ready = local_ready if self.runtime_mode == "local" else local_ready and integration_ready
        return {
            "status": "ready" if ready else "degraded",
            "ready": ready,
            "runtime_mode": self.runtime_mode,
            "data_source": "preview",
            "source_of_truth": {
                "configured": "in-memory-local-adapter" if self.runtime_mode == "local" else "postgresql",
                "production_authority": "postgresql",
                "ready": source_ready,
                "production_verified": bool(integration["postgres_runtime_verified"]),
            },
            "projection": {
                "projection_version": projection.projection_version,
                "source_checkpoint": projection.source_checkpoint,
                "projection_checkpoint": projection.projection_checkpoint,
                "lag_events": projection.lag_events,
                "stale": projection.stale,
            },
            "advisory": {"available": advisory_ready, "external_llm_required": False, "external_llm_state": "disabled-optional"},
            "integration": integration,
            "equipment_control_enabled": False,
        }


@dataclass
class IntegrationRuntime:
    config: SimulatorConfig
    seed: int
    event_repository: PostgresRepository
    case_repository: PostgresRepository
    quarantine: PostgresRepository
    detector: DeterministicDetector
    ingestion: IngestionService
    graph: Neo4jDriverProjectionAdapter
    projection: RcaProjectionWorker
    queries: RcaQueryService
    tools: ToolRegistry
    advisory: DeterministicAdvisoryProvider
    workflow: CaseWorkflowService
    telemetry: TelemetryRecorder
    event_bus: RedpandaEventBusAdapter
    runtime_mode: str = "integration"
    initialization_error: str | None = None

    def integration_status(self) -> dict[str, Any]:
        postgres_ready = self.event_repository.healthcheck()
        redpanda_ready = self.event_bus.healthcheck()
        neo4j_ready = self.graph.healthcheck()
        verified = postgres_ready and redpanda_ready and neo4j_ready and self.initialization_error is None
        return {
            "status": "verified" if verified else "degraded",
            "compose_config_verified": True,
            "postgres_runtime_verified": postgres_ready,
            "redpanda_runtime_verified": redpanda_ready,
            "neo4j_runtime_verified": neo4j_ready,
            "container_integration_verified": verified,
            "reason": self.initialization_error,
        }

    def health_status(self) -> dict[str, Any]:
        integration = self.integration_status()
        try:
            event_count = len(self.event_repository.all_events())
            detection_checkpoint = self.event_repository.checkpoint("detection")
            projection = self.projection.status()
            source_ready = event_count > 0 and detection_checkpoint == event_count
            projection_payload = {
                "projection_version": projection.projection_version,
                "source_checkpoint": projection.source_checkpoint,
                "projection_checkpoint": projection.projection_checkpoint,
                "lag_events": projection.lag_events,
                "stale": projection.stale,
            }
        except Exception as exc:  # noqa: BLE001 - readiness must remain queryable when a dependency is unavailable
            source_ready = False
            projection_payload = {
                "projection_version": "rca-graph-v1.0.0",
                "source_checkpoint": 0,
                "projection_checkpoint": 0,
                "lag_events": 0,
                "stale": True,
                "error_classification": type(exc).__name__,
            }
        advisory_ready = len(self.tools.names) == 5
        ready = source_ready and not projection_payload["stale"] and advisory_ready and bool(integration["container_integration_verified"])
        return {
            "status": "ready" if ready else "degraded",
            "ready": ready,
            "runtime_mode": self.runtime_mode,
            "data_source": "database",
            "source_of_truth": {
                "configured": "postgresql",
                "production_authority": "postgresql",
                "ready": source_ready,
                "production_verified": bool(integration["postgres_runtime_verified"]),
            },
            "projection": projection_payload,
            "advisory": {"available": advisory_ready, "external_llm_required": False, "external_llm_state": "disabled-optional"},
            "integration": integration,
            "equipment_control_enabled": False,
        }


class ReadOnlyWorkflowService:
    """Fail closed for every workflow mutation in database-backed preview mode."""

    @staticmethod
    def _deny() -> None:
        raise AuthorizationError("database-backed preview is read-only")

    def request_evidence(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self._deny()

    def propose_action(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self._deny()

    def approve(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self._deny()

    def reject(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self._deny()

    def close(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self._deny()

    def check_timeouts(self) -> list[str]:
        self._deny()


@dataclass
class DatabaseReadOnlyRuntime:
    config: SimulatorConfig
    seed: int
    event_repository: ReadOnlyPostgresRepository
    case_repository: ReadOnlyPostgresRepository
    quarantine: ReadOnlyPostgresRepository
    detector: DeterministicDetector
    ingestion: IngestionService
    graph: InMemoryGraphProjection
    projection: RcaProjectionWorker
    queries: RcaQueryService
    tools: ToolRegistry
    advisory: DeterministicAdvisoryProvider
    workflow: ReadOnlyWorkflowService
    telemetry: TelemetryRecorder
    runtime_mode: str = "database-readonly"

    def integration_status(self) -> dict[str, Any]:
        postgres_ready = self.event_repository.healthcheck()
        return {
            "status": "verified" if postgres_ready else "degraded",
            "compose_config_verified": True,
            "postgres_runtime_verified": postgres_ready,
            "redpanda_runtime_verified": False,
            "neo4j_runtime_verified": False,
            "container_integration_verified": postgres_ready,
            "required_dependencies": ["postgres"],
            "read_only": True,
            "reason": None if postgres_ready else "configured PostgreSQL source is unavailable",
        }

    def health_status(self) -> dict[str, Any]:
        integration = self.integration_status()
        try:
            counter = getattr(self.event_repository, "event_count", None)
            event_count = int(counter()) if callable(counter) else len(self.event_repository.all_events())
            detection_checkpoint = self.event_repository.checkpoint("detection")
            projection = self.projection.catch_up()
            source_ready = event_count > 0 and detection_checkpoint == event_count
            projection_payload = {
                "projection_version": projection.projection_version,
                "source_checkpoint": projection.source_checkpoint,
                "projection_checkpoint": projection.projection_checkpoint,
                "lag_events": projection.lag_events,
                "stale": projection.stale,
            }
        except Exception as exc:  # noqa: BLE001 - readiness must remain descriptive
            source_ready = False
            projection_payload = {
                "projection_version": "rca-graph-v1.0.0",
                "source_checkpoint": 0,
                "projection_checkpoint": 0,
                "lag_events": 0,
                "stale": True,
                "error_classification": type(exc).__name__,
            }
        advisory_ready = len(self.tools.names) == 5
        ready = source_ready and not projection_payload["stale"] and advisory_ready and bool(integration["postgres_runtime_verified"])
        return {
            "status": "ready" if ready else "degraded",
            "ready": ready,
            "runtime_mode": self.runtime_mode,
            "data_source": "database",
            "source_of_truth": {
                "configured": "postgresql-read-only",
                "production_authority": "postgresql",
                "ready": source_ready,
                "production_verified": bool(integration["postgres_runtime_verified"]),
            },
            "projection": projection_payload,
            "advisory": {"available": advisory_ready, "external_llm_required": False, "external_llm_state": "disabled-optional"},
            "integration": integration,
            "equipment_control_enabled": False,
        }


def build_local_runtime(seed: int = 42, profile: str = "test", telemetry: TelemetryRecorder | None = None) -> LocalRuntime:
    config = load_config(profile)
    trace = FabTwinSimulator(config, seed).generate()
    recorder = telemetry or TelemetryRecorder()
    event_repository = InMemoryEventRepository()
    case_repository = InMemoryCaseRepository()
    quarantine = InMemoryQuarantine()
    detector = DeterministicDetector(case_repository, telemetry=recorder)
    ingestion = IngestionService(event_repository, case_repository, quarantine, detector.consume, telemetry=recorder)
    for event in trace.events:
        ingestion.ingest(event)
    graph = InMemoryGraphProjection()
    projection = RcaProjectionWorker(event_repository, graph, telemetry=recorder)
    projection.rebuild()
    queries = RcaQueryService(graph, case_repository, projection, telemetry=recorder)
    tools = ToolRegistry(case_repository, graph, queries, telemetry=recorder)
    advisory = DeterministicAdvisoryProvider(tools, telemetry=recorder)
    workflow = CaseWorkflowService(case_repository, telemetry=recorder)
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
        recorder,
    )


def build_integration_runtime(seed: int = 42, profile: str = "test", telemetry: TelemetryRecorder | None = None) -> IntegrationRuntime:
    postgres_dsn = os.environ.get("FABOPS_POSTGRES_DSN")
    neo4j_uri = os.environ.get("FABOPS_NEO4J_URI")
    neo4j_user = os.environ.get("FABOPS_NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("FABOPS_NEO4J_PASSWORD")
    redpanda_bootstrap = os.environ.get("FABOPS_REDPANDA_BOOTSTRAP", "redpanda:9092")
    if not postgres_dsn or not neo4j_uri or not neo4j_password:
        missing = [
            name
            for name, value in (
                ("FABOPS_POSTGRES_DSN", postgres_dsn),
                ("FABOPS_NEO4J_URI", neo4j_uri),
                ("FABOPS_NEO4J_PASSWORD", neo4j_password),
            )
            if not value
        ]
        raise RuntimeError(f"integration runtime configuration missing: {', '.join(missing)}")

    config = load_config(profile)
    recorder = telemetry or TelemetryRecorder()
    repository = PostgresRepository(PostgresConfig(postgres_dsn))
    graph = Neo4jDriverProjectionAdapter(Neo4jConfig(neo4j_uri, neo4j_user, neo4j_password))
    event_bus = RedpandaEventBusAdapter(
        config=RedpandaConfig(
            bootstrap_servers=redpanda_bootstrap,
            topic=os.environ.get("FABOPS_REDPANDA_TOPIC", "fabops.events.v1"),
            dlq_topic=os.environ.get("FABOPS_REDPANDA_DLQ_TOPIC", "fabops.events.dlq.v1"),
            group_id=os.environ.get("FABOPS_REDPANDA_GROUP", "fabops-api-v1"),
            idle_timeout_seconds=float(os.environ.get("FABOPS_REDPANDA_IDLE_TIMEOUT", "1.0")),
        )
    )
    detector = DeterministicDetector(repository, telemetry=recorder)
    ingestion = IngestionService(
        repository,
        repository,
        repository,
        detector.consume,
        telemetry=recorder,
        transaction_factory=repository.transaction,
    )
    projection = RcaProjectionWorker(repository, graph, telemetry=recorder)
    queries = RcaQueryService(graph, repository, projection, telemetry=recorder)
    tools = ToolRegistry(repository, graph, queries, telemetry=recorder)
    advisory = DeterministicAdvisoryProvider(tools, telemetry=recorder)
    workflow = CaseWorkflowService(repository, telemetry=recorder)
    runtime = IntegrationRuntime(
        config,
        seed,
        repository,
        repository,
        repository,
        detector,
        ingestion,
        graph,
        projection,
        queries,
        tools,
        advisory,
        workflow,
        recorder,
        event_bus,
    )
    try:
        status = runtime.integration_status()
        if not (status["postgres_runtime_verified"] and status["redpanda_runtime_verified"] and status["neo4j_runtime_verified"]):
            runtime.initialization_error = "one or more configured integration dependencies are unavailable"
            return runtime
        if repository.counts()["events"] == 0:
            trace = FabTwinSimulator(config, seed).generate()
            for event in trace.events:
                event_bus.publish(event_bus.config.topic, event)
        event_bus.subscribe(event_bus.config.topic, ingestion.ingest)
        projection.rebuild()
    except Exception as exc:  # noqa: BLE001 - keep health/readiness available without silently falling back to local state
        runtime.initialization_error = type(exc).__name__
    return runtime


def build_database_readonly_runtime(seed: int = 42, profile: str = "test", telemetry: TelemetryRecorder | None = None) -> DatabaseReadOnlyRuntime:
    postgres_dsn = os.environ.get("FABOPS_POSTGRES_DSN")
    if not postgres_dsn:
        raise RuntimeError("database preview requires FABOPS_POSTGRES_DSN")

    config = load_config(profile)
    recorder = telemetry or TelemetryRecorder()
    repository = ReadOnlyPostgresRepository(PostgresConfig(postgres_dsn))
    if not repository.healthcheck():
        raise RuntimeError("configured PostgreSQL source is unavailable")

    graph = InMemoryGraphProjection()
    projection = RcaProjectionWorker(repository, graph, telemetry=recorder)
    projection.rebuild()
    detector = DeterministicDetector(repository, telemetry=recorder)
    ingestion = IngestionService(repository, repository, repository, detector.consume, telemetry=recorder, transaction_factory=repository.transaction)
    queries = RcaQueryService(graph, repository, projection, telemetry=recorder)
    tools = ToolRegistry(repository, graph, queries, telemetry=recorder)
    advisory = DeterministicAdvisoryProvider(tools, telemetry=recorder)
    return DatabaseReadOnlyRuntime(
        config,
        seed,
        repository,
        repository,
        repository,
        detector,
        ingestion,
        graph,
        projection,
        queries,
        tools,
        advisory,
        ReadOnlyWorkflowService(),
        recorder,
    )


def build_runtime() -> LocalRuntime | IntegrationRuntime | DatabaseReadOnlyRuntime:
    data_source = os.environ.get("FABOPS_DATA_SOURCE", "preview").strip().lower()
    if data_source == "database":
        return build_database_readonly_runtime()
    if data_source not in {"preview", "local"}:
        raise ValueError(f"unsupported FABOPS_DATA_SOURCE: {data_source}")
    mode = os.environ.get("FABOPS_RUNTIME_MODE", "local").strip().lower()
    if mode == "local":
        return build_local_runtime()
    if mode in {"integration", "compose"}:
        return build_integration_runtime()
    raise ValueError(f"unsupported FABOPS_RUNTIME_MODE: {mode}")

