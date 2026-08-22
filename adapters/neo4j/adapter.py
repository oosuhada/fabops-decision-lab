from __future__ import annotations

from typing import Any, Callable


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

