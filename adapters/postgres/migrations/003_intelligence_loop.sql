CREATE TABLE IF NOT EXISTS fabops_model_registry (
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('candidate', 'champion', 'retired')),
    training_rows INTEGER NOT NULL,
    feature_schema JSONB NOT NULL,
    parameters JSONB NOT NULL,
    metrics JSONB NOT NULL,
    trained_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (model_name, model_version)
);

CREATE UNIQUE INDEX IF NOT EXISTS fabops_model_registry_one_champion
ON fabops_model_registry(model_name)
WHERE status = 'champion';

CREATE TABLE IF NOT EXISTS fabops_learning_outcomes (
    lot_id TEXT PRIMARY KEY,
    yield_value DOUBLE PRECISION,
    physical_excursion BOOLEAN NOT NULL,
    equipment_alarm BOOLEAN NOT NULL,
    maintenance_observed BOOLEAN NOT NULL,
    features JSONB NOT NULL,
    outcome_document JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fabops_predictions (
    prediction_id BIGSERIAL PRIMARY KEY,
    lot_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    target TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    prediction_document JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS fabops_predictions_lot_created_idx
ON fabops_predictions(lot_id, created_at DESC);

CREATE TABLE IF NOT EXISTS fabops_prediction_feedback (
    prediction_id BIGINT PRIMARY KEY REFERENCES fabops_predictions(prediction_id) ON DELETE CASCADE,
    target TEXT NOT NULL,
    predicted DOUBLE PRECISION NOT NULL,
    actual DOUBLE PRECISION NOT NULL,
    absolute_error DOUBLE PRECISION NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fabops_intelligence_reports (
    report_id BIGSERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    material_signature TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    mode TEXT NOT NULL,
    provider TEXT NOT NULL,
    report_document JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(case_id, material_signature)
);

CREATE TABLE IF NOT EXISTS fabops_visualization_plans (
    plan_id BIGSERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    material_signature TEXT NOT NULL,
    plan_document JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(case_id, material_signature)
);

