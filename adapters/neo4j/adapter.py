from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from neo4j import GraphDatabase

from services.rca.graph import GraphEdge, GraphNode
from services.reliability import Bulkhead, CircuitBreaker


class Neo4jProjectionAdapter:
    """Thin Cypher adapter; Neo4j is never authoritative state."""

    def __init__(self, run_cypher: Callable[[str, dict[str, Any]], Any]) -> None:
        self.run_cypher = run_cypher

    def clear(self) -> None:
        self.run_cypher("MATCH (n:FabOpsProjection) DETACH DELETE n", {})

    def upsert_node(self, kind: str, node_id: str, properties: dict[str, Any]) -> None:
        query = "MERGE (n:FabOpsProjection {projection_key: $projection_key}) SET n.kind = $kind, n += $properties"
        self.run_cypher(query, {"projection_key": f"{kind}:{node_id}", "kind": kind, "properties": properties})

    def upsert_edge(self, source_kind: str, source_id: str, relation: str, target_kind: str, target_id: str) -> None:
        # Relationship type is stored as a property rather than interpolated into
        # Cypher, which avoids unsafe dynamic query construction.
        query = (
            "MATCH (a:FabOpsProjection {projection_key: $source_key}), "
            "(b:FabOpsProjection {projection_key: $target_key}) "
            "MERGE (a)-[r:FABOPS_RELATION {relation: $relation}]->(b)"
        )
        self.run_cypher(query, {"source_key": f"{source_kind}:{source_id}", "target_key": f"{target_kind}:{target_id}", "relation": relation})


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str
    database: str = "neo4j"


class Neo4jDriverProjectionAdapter(Neo4jProjectionAdapter):
    """Neo4j-backed rebuildable projection. PostgreSQL remains the authoritative state."""

    def __init__(self, config: Neo4jConfig) -> None:
        self.config = config
        self.driver = GraphDatabase.driver(config.uri, auth=(config.username, config.password))
        self.breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=5.0)
        self.bulkhead = Bulkhead(max_concurrency=8, acquire_timeout_seconds=1.0)
        super().__init__(self._run)

    def _run(self, query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        def execute() -> list[dict[str, Any]]:
            with self.driver.session(database=self.config.database) as session:
                result = session.run(query, parameters)
                return [record.data() for record in result]

        return self.bulkhead.call(lambda: self.breaker.call(execute))

    def healthcheck(self) -> bool:
        try:
            rows = self._run("RETURN 1 AS ok", {})
            return bool(rows and rows[0]["ok"] == 1)
        except Exception:  # noqa: BLE001 - dependency health is exposed as a boolean readiness signal
            return False

    def close(self) -> None:
        self.driver.close()

    def get_node(self, kind: str, node_id: str) -> GraphNode | None:
        rows = self._run(
            "MATCH (n:FabOpsProjection {projection_key: $projection_key}) RETURN n.kind AS kind, properties(n) AS properties",
            {"projection_key": f"{kind}:{node_id}"},
        )
        if not rows:
            return None
        properties = dict(rows[0]["properties"])
        properties.pop("projection_key", None)
        properties.pop("kind", None)
        return GraphNode(str(rows[0]["kind"]), node_id, properties)

    def nodes(self, kind: str | None = None) -> list[GraphNode]:
        rows = self._run(
            "MATCH (n:FabOpsProjection) WHERE $kind IS NULL OR n.kind = $kind RETURN n.projection_key AS projection_key, n.kind AS kind, properties(n) AS properties ORDER BY n.kind, n.projection_key",
            {"kind": kind},
        )
        nodes: list[GraphNode] = []
        for row in rows:
            projection_key = str(row["projection_key"])
            _prefix, node_id = projection_key.split(":", 1)
            properties = dict(row["properties"])
            properties.pop("projection_key", None)
            properties.pop("kind", None)
            nodes.append(GraphNode(str(row["kind"]), node_id, properties))
        return nodes

    def edges(self, relation: str | None = None) -> list[GraphEdge]:
        rows = self._run(
            """
            MATCH (a:FabOpsProjection)-[r:FABOPS_RELATION]->(b:FabOpsProjection)
            WHERE $relation IS NULL OR r.relation = $relation
            RETURN a.projection_key AS source_key, r.relation AS relation, b.projection_key AS target_key
            ORDER BY source_key, relation, target_key
            """,
            {"relation": relation},
        )
        result: list[GraphEdge] = []
        for row in rows:
            source_kind, source_id = str(row["source_key"]).split(":", 1)
            target_kind, target_id = str(row["target_key"]).split(":", 1)
            result.append(GraphEdge(source_kind, source_id, str(row["relation"]), target_kind, target_id))
        return result

    def outgoing(self, source_kind: str, source_id: str, relation: str | None = None) -> list[GraphEdge]:
        return [
            edge
            for edge in self.edges(relation)
            if edge.source_kind == source_kind and edge.source_id == source_id
        ]

    def incoming(self, target_kind: str, target_id: str, relation: str | None = None) -> list[GraphEdge]:
        return [
            edge
            for edge in self.edges(relation)
            if edge.target_kind == target_kind and edge.target_id == target_id
        ]

