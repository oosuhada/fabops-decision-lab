from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from services.rca.graph import GraphEdge, GraphNode

PERSISTENT_PROJECTION_NAME = "rca-postgres-graph"
PERSISTENT_PROJECTION_VERSION = "rca-postgres-graph-v2.0.0"


class PostgresGraphProjection:
    """Shared bounded RCA graph read model backed by candidate PostgreSQL.

    API processes open this adapter read-only while the dedicated projection
    worker owns writes. The graph contains only rebuildable projection state;
    authoritative events and cases remain in their existing source tables.
    """

    def __init__(self, dsn: str, *, writable: bool = False) -> None:
        self.dsn = dsn
        self.writable = writable
        self.projection_version = PERSISTENT_PROJECTION_VERSION
        self._writer_connection: psycopg.Connection[Any] | None = None

    def _connection(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def _require_writable(self) -> None:
        if not self.writable:
            raise PermissionError("persistent RCA graph adapter is read-only in this process")

    def _writer(self) -> psycopg.Connection[Any]:
        self._require_writable()
        if self._writer_connection is None or self._writer_connection.closed:
            self._writer_connection = psycopg.connect(self.dsn, row_factory=dict_row, autocommit=True)
        return self._writer_connection

    def close(self) -> None:
        if self._writer_connection is not None and not self._writer_connection.closed:
            self._writer_connection.close()
        self._writer_connection = None

    def clear(self) -> None:
        connection = self._writer()
        connection.execute("TRUNCATE fabops_rca_edges, fabops_rca_nodes")
        connection.execute(
            """
            INSERT INTO fabops_projection_checkpoint(projection_name, source_sequence, projection_version)
            VALUES (%s, 0, %s)
            ON CONFLICT (projection_name) DO UPDATE
            SET source_sequence = 0, projection_version = EXCLUDED.projection_version, updated_at = now()
            """,
            (PERSISTENT_PROJECTION_NAME, PERSISTENT_PROJECTION_VERSION),
        )

    def upsert_node(self, kind: str, node_id: str, properties: dict[str, Any]) -> None:
        lot_id = str(properties["lot_id"]) if properties.get("lot_id") is not None else None
        self._writer().execute(
            """
            INSERT INTO fabops_rca_nodes(kind, node_id, lot_id, properties)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (kind, node_id) DO UPDATE
            SET lot_id = COALESCE(EXCLUDED.lot_id, fabops_rca_nodes.lot_id),
                properties = fabops_rca_nodes.properties || EXCLUDED.properties,
                updated_at = now()
            """,
            (kind, node_id, lot_id, Jsonb(properties)),
        )

    def upsert_edge(self, source_kind: str, source_id: str, relation: str, target_kind: str, target_id: str) -> None:
        self._writer().execute(
            """
            INSERT INTO fabops_rca_edges(source_kind, source_id, relation, target_kind, target_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_kind, source_id, relation, target_kind, target_id) DO UPDATE
            SET updated_at = now()
            """,
            (source_kind, source_id, relation, target_kind, target_id),
        )

    @staticmethod
    def _node(row: dict[str, Any]) -> GraphNode:
        return GraphNode(str(row["kind"]), str(row["node_id"]), deepcopy(row["properties"]))

    @staticmethod
    def _edge(row: dict[str, Any]) -> GraphEdge:
        return GraphEdge(
            str(row["source_kind"]),
            str(row["source_id"]),
            str(row["relation"]),
            str(row["target_kind"]),
            str(row["target_id"]),
        )

    def get_node(self, kind: str, node_id: str) -> GraphNode | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT kind, node_id, properties FROM fabops_rca_nodes WHERE kind = %s AND node_id = %s",
                (kind, node_id),
            ).fetchone()
        return self._node(row) if row else None

    def nodes(self, kind: str | None = None) -> list[GraphNode]:
        with self._connection() as connection:
            if kind is None:
                rows = connection.execute(
                    "SELECT kind, node_id, properties FROM fabops_rca_nodes ORDER BY kind, node_id"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT kind, node_id, properties FROM fabops_rca_nodes WHERE kind = %s ORDER BY node_id",
                    (kind,),
                ).fetchall()
        return [self._node(row) for row in rows]

    def nodes_for_lot(self, kind: str, lot_id: str) -> list[GraphNode]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT kind, node_id, properties
                FROM fabops_rca_nodes
                WHERE kind = %s AND lot_id = %s
                ORDER BY node_id
                """,
                (kind, lot_id),
            ).fetchall()
        return [self._node(row) for row in rows]

    def edges(self, relation: str | None = None) -> list[GraphEdge]:
        with self._connection() as connection:
            if relation is None:
                rows = connection.execute(
                    """
                    SELECT source_kind, source_id, relation, target_kind, target_id
                    FROM fabops_rca_edges
                    ORDER BY source_kind, source_id, relation, target_kind, target_id
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT source_kind, source_id, relation, target_kind, target_id
                    FROM fabops_rca_edges
                    WHERE relation = %s
                    ORDER BY source_kind, source_id, target_kind, target_id
                    """,
                    (relation,),
                ).fetchall()
        return [self._edge(row) for row in rows]

    def outgoing(self, source_kind: str, source_id: str, relation: str | None = None) -> list[GraphEdge]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT source_kind, source_id, relation, target_kind, target_id
                FROM fabops_rca_edges
                WHERE source_kind = %s AND source_id = %s AND (%s IS NULL OR relation = %s)
                ORDER BY relation, target_kind, target_id
                """,
                (source_kind, source_id, relation, relation),
            ).fetchall()
        return [self._edge(row) for row in rows]

    def incoming(self, target_kind: str, target_id: str, relation: str | None = None) -> list[GraphEdge]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT source_kind, source_id, relation, target_kind, target_id
                FROM fabops_rca_edges
                WHERE target_kind = %s AND target_id = %s AND (%s IS NULL OR relation = %s)
                ORDER BY relation, source_kind, source_id
                """,
                (target_kind, target_id, relation, relation),
            ).fetchall()
        return [self._edge(row) for row in rows]

    def prune_to_lots(self, keep_lots: set[str]) -> None:
        if not keep_lots:
            return
        lot_ids = sorted(keep_lots)
        connection = self._writer()
        connection.execute(
            """
            DELETE FROM fabops_rca_edges edge
            WHERE EXISTS (
                SELECT 1 FROM fabops_rca_nodes node
                WHERE node.lot_id IS NOT NULL AND NOT (node.lot_id = ANY(%s))
                  AND ((node.kind = edge.source_kind AND node.node_id = edge.source_id)
                    OR (node.kind = edge.target_kind AND node.node_id = edge.target_id))
            )
            """,
            (lot_ids,),
        )
        connection.execute(
            "DELETE FROM fabops_rca_nodes WHERE lot_id IS NOT NULL AND NOT (lot_id = ANY(%s))",
            (lot_ids,),
        )

    def projection_checkpoint(self) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT source_sequence FROM fabops_projection_checkpoint WHERE projection_name = %s",
                (PERSISTENT_PROJECTION_NAME,),
            ).fetchone()
        return int(row["source_sequence"]) if row else 0

    def projection_updated_at(self) -> datetime | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT updated_at FROM fabops_projection_checkpoint WHERE projection_name = %s",
                (PERSISTENT_PROJECTION_NAME,),
            ).fetchone()
        return row["updated_at"] if row else None

    def set_projection_checkpoint(self, sequence: int) -> None:
        self._writer().execute(
            """
            INSERT INTO fabops_projection_checkpoint(projection_name, source_sequence, projection_version)
            VALUES (%s, %s, %s)
            ON CONFLICT (projection_name) DO UPDATE
            SET source_sequence = EXCLUDED.source_sequence,
                projection_version = EXCLUDED.projection_version,
                updated_at = now()
            """,
            (PERSISTENT_PROJECTION_NAME, int(sequence), PERSISTENT_PROJECTION_VERSION),
        )
