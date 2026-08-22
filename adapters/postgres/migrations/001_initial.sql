-- FabOps future-production source-of-truth schema.
-- PostgreSQL is authoritative; SQLite is intentionally not a production option.
BEGIN;

CREATE TABLE IF NOT EXISTS fabops_event_log (
    sequence BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    trace_id TEXT,
    lot_id TEXT,
    equipment_id TEXT,
    chamber_id TEXT,
    schema_version INTEGER NOT NULL,
    delivery_status TEXT NOT NULL,
    envelope JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fabops_measurements (
    event_id UUID PRIMARY KEY REFERENCES fabops_event_log(event_id),
    lot_id TEXT NOT NULL,
    process_run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    equipment_id TEXT NOT NULL,
    chamber_id TEXT NOT NULL,
    sensor_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fabops_cases (
    case_id TEXT PRIMARY KEY,
    lot_id TEXT NOT NULL,
    classification TEXT NOT NULL,
    state TEXT NOT NULL,
    anomaly_score DOUBLE PRECISION NOT NULL,
    detector_version TEXT NOT NULL,
    case_document JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fabops_decision_audit (
    audit_sequence BIGSERIAL PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES fabops_cases(case_id),
    event_type TEXT NOT NULL,
    actor_id TEXT,
    record JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fabops_outbox (
    outbox_id BIGSERIAL PRIMARY KEY,
    topic TEXT NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fabops_quarantine (
    quarantine_id BIGSERIAL PRIMARY KEY,
    raw_event JSONB NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fabops_projection_checkpoint (
    projection_name TEXT PRIMARY KEY,
    source_sequence BIGINT NOT NULL,
    projection_version TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;

