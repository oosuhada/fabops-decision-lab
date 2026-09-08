-- Indexes selected from measured repository query shapes.
-- Keep these narrow: JSONB payload columns stay in the heap to avoid bloating
-- the write path for the authoritative event/case tables.
BEGIN;

CREATE INDEX IF NOT EXISTS fabops_event_log_event_type_sequence_idx
    ON fabops_event_log(event_type, sequence DESC);

CREATE INDEX IF NOT EXISTS fabops_cases_classification_lot_updated_idx
    ON fabops_cases(classification, lot_id DESC, updated_at DESC);

COMMIT;
