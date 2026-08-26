BEGIN;

CREATE TABLE IF NOT EXISTS fabops_rca_nodes (
    kind TEXT NOT NULL,
    node_id TEXT NOT NULL,
    lot_id TEXT,
    properties JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, node_id)
);

CREATE INDEX IF NOT EXISTS fabops_rca_nodes_kind_lot_idx
    ON fabops_rca_nodes(kind, lot_id);

CREATE INDEX IF NOT EXISTS fabops_rca_nodes_lot_idx
    ON fabops_rca_nodes(lot_id)
    WHERE lot_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS fabops_rca_edges (
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_kind, source_id, relation, target_kind, target_id)
);

CREATE INDEX IF NOT EXISTS fabops_rca_edges_outgoing_idx
    ON fabops_rca_edges(source_kind, source_id, relation);

CREATE INDEX IF NOT EXISTS fabops_rca_edges_incoming_idx
    ON fabops_rca_edges(target_kind, target_id, relation);

INSERT INTO fabops_projection_checkpoint(projection_name, source_sequence, projection_version)
VALUES ('rca-postgres-graph', 0, 'rca-postgres-graph-v2.0.0')
ON CONFLICT (projection_name) DO NOTHING;

COMMIT;
