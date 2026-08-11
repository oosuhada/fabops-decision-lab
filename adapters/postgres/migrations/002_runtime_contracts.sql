BEGIN;

CREATE TABLE IF NOT EXISTS fabops_event_reservations (
    event_id UUID PRIMARY KEY,
    reserved_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fabops_consumer_checkpoint (
    consumer TEXT PRIMARY KEY,
    source_sequence BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fabops_event_log_trace_id ON fabops_event_log(trace_id);
CREATE INDEX IF NOT EXISTS idx_fabops_event_log_lot_id ON fabops_event_log(lot_id);
CREATE INDEX IF NOT EXISTS idx_fabops_cases_lot_id ON fabops_cases(lot_id);
CREATE INDEX IF NOT EXISTS idx_fabops_audit_case_id ON fabops_decision_audit(case_id, audit_sequence);

COMMIT;
