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
    def nodes_for_lot(self, kind: str, lot_id: str) -> list[GraphNode]: ...
    def edges(self, relation: str | None = None) -> list[GraphEdge]: ...
    def outgoing(self, source_kind: str, source_id: str, relation: str | None = None) -> list[GraphEdge]: ...
    def incoming(self, target_kind: str, target_id: str, relation: str | None = None) -> list[GraphEdge]: ...


class InMemoryGraphProjection:
    def __init__(self) -> None:
        self._nodes: dict[tuple[str, str], GraphNode] = {}
        self._edges: dict[tuple[str, str, str, str, str], GraphEdge] = {}
        self._nodes_by_kind: dict[str, dict[str, GraphNode]] = {}
        self._nodes_by_lot: dict[tuple[str, str], dict[str, GraphNode]] = {}
        self._outgoing_edges: dict[tuple[str, str], dict[tuple[str, str, str, str, str], GraphEdge]] = {}
        self._incoming_edges: dict[tuple[str, str], dict[tuple[str, str, str, str, str], GraphEdge]] = {}

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._nodes_by_kind.clear()
        self._nodes_by_lot.clear()
        self._outgoing_edges.clear()
        self._incoming_edges.clear()

    def upsert_node(self, kind: str, node_id: str, properties: dict[str, Any]) -> None:
        key = (kind, node_id)
        current = self._nodes.get(key)
        merged = dict(current.properties) if current else {}
        merged.update(deepcopy(properties))
        node = GraphNode(kind, node_id, merged)
        self._nodes[key] = node
        self._nodes_by_kind.setdefault(kind, {})[node_id] = node
        old_lot = str(current.properties.get("lot_id")) if current and current.properties.get("lot_id") is not None else None
        new_lot = str(merged.get("lot_id")) if merged.get("lot_id") is not None else None
        if old_lot and old_lot != new_lot:
            bucket = self._nodes_by_lot.get((kind, old_lot))
            if bucket is not None:
                bucket.pop(node_id, None)
        if new_lot:
            self._nodes_by_lot.setdefault((kind, new_lot), {})[node_id] = node

    def upsert_edge(self, source_kind: str, source_id: str, relation: str, target_kind: str, target_id: str) -> None:
        edge = GraphEdge(source_kind, source_id, relation, target_kind, target_id)
        key = (source_kind, source_id, relation, target_kind, target_id)
        self._edges[key] = edge
        self._outgoing_edges.setdefault((source_kind, source_id), {})[key] = edge
        self._incoming_edges.setdefault((target_kind, target_id), {})[key] = edge

    def get_node(self, kind: str, node_id: str) -> GraphNode | None:
        node = self._nodes.get((kind, node_id))
        return deepcopy(node) if node else None

    def nodes(self, kind: str | None = None) -> list[GraphNode]:
        values = list(self._nodes.values()) if kind is None else list(self._nodes_by_kind.get(kind, {}).values())
        return deepcopy(sorted(values, key=lambda item: (item.kind, item.node_id)))

    def nodes_for_lot(self, kind: str, lot_id: str) -> list[GraphNode]:
        values = list(self._nodes_by_lot.get((kind, lot_id), {}).values())
        return deepcopy(sorted(values, key=lambda item: item.node_id))

    def prune_to_lots(self, keep_lots: set[str]) -> None:
        removable = [
            key
            for key, node in self._nodes.items()
            if node.properties.get("lot_id") is not None and str(node.properties.get("lot_id")) not in keep_lots
        ]
        for kind, node_id in removable:
            node = self._nodes.pop((kind, node_id), None)
            if node is None:
                continue
            self._nodes_by_kind.get(kind, {}).pop(node_id, None)
            lot_id = str(node.properties.get("lot_id"))
            bucket = self._nodes_by_lot.get((kind, lot_id))
            if bucket is not None:
                bucket.pop(node_id, None)
                if not bucket:
                    self._nodes_by_lot.pop((kind, lot_id), None)
            edge_keys = set(self._outgoing_edges.get((kind, node_id), {})) | set(self._incoming_edges.get((kind, node_id), {}))
            for edge_key in edge_keys:
                edge = self._edges.pop(edge_key, None)
                if edge is None:
                    continue
                outgoing = self._outgoing_edges.get((edge.source_kind, edge.source_id))
                incoming = self._incoming_edges.get((edge.target_kind, edge.target_id))
                if outgoing is not None:
                    outgoing.pop(edge_key, None)
                    if not outgoing:
                        self._outgoing_edges.pop((edge.source_kind, edge.source_id), None)
                if incoming is not None:
                    incoming.pop(edge_key, None)
                    if not incoming:
                        self._incoming_edges.pop((edge.target_kind, edge.target_id), None)

    def edges(self, relation: str | None = None) -> list[GraphEdge]:
        values = [edge for edge in self._edges.values() if relation is None or edge.relation == relation]
        return deepcopy(sorted(values, key=lambda item: (item.source_kind, item.source_id, item.relation, item.target_kind, item.target_id)))

    def outgoing(self, source_kind: str, source_id: str, relation: str | None = None) -> list[GraphEdge]:
        values = list(self._outgoing_edges.get((source_kind, source_id), {}).values())
        if relation is not None:
            values = [edge for edge in values if edge.relation == relation]
        return deepcopy(sorted(values, key=lambda item: (item.relation, item.target_kind, item.target_id)))

    def incoming(self, target_kind: str, target_id: str, relation: str | None = None) -> list[GraphEdge]:
        values = list(self._incoming_edges.get((target_kind, target_id), {}).values())
        if relation is not None:
            values = [edge for edge in values if edge.relation == relation]
        return deepcopy(sorted(values, key=lambda item: (item.relation, item.source_kind, item.source_id)))

