from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class GraphNode:
    kind: str
    node_id: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    source_kind: str
    source_id: str
    relation: str
    target_kind: str
    target_id: str


class GraphProjectionPort(Protocol):
    def clear(self) -> None: ...
    def upsert_node(self, kind: str, node_id: str, properties: dict[str, Any]) -> None: ...
    def upsert_edge(self, source_kind: str, source_id: str, relation: str, target_kind: str, target_id: str) -> None: ...
    def get_node(self, kind: str, node_id: str) -> GraphNode | None: ...
    def nodes(self, kind: str | None = None) -> list[GraphNode]: ...
    def edges(self, relation: str | None = None) -> list[GraphEdge]: ...
    def outgoing(self, source_kind: str, source_id: str, relation: str | None = None) -> list[GraphEdge]: ...
    def incoming(self, target_kind: str, target_id: str, relation: str | None = None) -> list[GraphEdge]: ...


class InMemoryGraphProjection:
    def __init__(self) -> None:
        self._nodes: dict[tuple[str, str], GraphNode] = {}
        self._edges: dict[tuple[str, str, str, str, str], GraphEdge] = {}

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()

    def upsert_node(self, kind: str, node_id: str, properties: dict[str, Any]) -> None:
        key = (kind, node_id)
        current = self._nodes.get(key)
        merged = dict(current.properties) if current else {}
        merged.update(deepcopy(properties))
        self._nodes[key] = GraphNode(kind, node_id, merged)

    def upsert_edge(self, source_kind: str, source_id: str, relation: str, target_kind: str, target_id: str) -> None:
        edge = GraphEdge(source_kind, source_id, relation, target_kind, target_id)
        self._edges[(source_kind, source_id, relation, target_kind, target_id)] = edge

    def get_node(self, kind: str, node_id: str) -> GraphNode | None:
        node = self._nodes.get((kind, node_id))
        return deepcopy(node) if node else None

    def nodes(self, kind: str | None = None) -> list[GraphNode]:
        values = [node for node in self._nodes.values() if kind is None or node.kind == kind]
        return deepcopy(sorted(values, key=lambda item: (item.kind, item.node_id)))

    def edges(self, relation: str | None = None) -> list[GraphEdge]:
        values = [edge for edge in self._edges.values() if relation is None or edge.relation == relation]
        return deepcopy(sorted(values, key=lambda item: (item.source_kind, item.source_id, item.relation, item.target_kind, item.target_id)))

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

