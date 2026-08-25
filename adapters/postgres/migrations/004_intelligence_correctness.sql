ALTER TABLE fabops_model_registry
DROP CONSTRAINT IF EXISTS fabops_model_registry_status_check;

ALTER TABLE fabops_model_registry
ADD CONSTRAINT fabops_model_registry_status_check
CHECK (status IN ('candidate', 'champion', 'retired', 'rejected'));

ALTER TABLE fabops_model_registry
ADD COLUMN IF NOT EXISTS feature_set_version TEXT,
ADD COLUMN IF NOT EXISTS prediction_cutoff TEXT,
ADD COLUMN IF NOT EXISTS training_window JSONB,
ADD COLUMN IF NOT EXISTS calibration_window JSONB,
ADD COLUMN IF NOT EXISTS test_window JSONB,
ADD COLUMN IF NOT EXISTS target_definition TEXT,
ADD COLUMN IF NOT EXISTS dataset_fingerprint TEXT,
ADD COLUMN IF NOT EXISTS code_git_sha TEXT,
ADD COLUMN IF NOT EXISTS simulator_regime TEXT,
ADD COLUMN IF NOT EXISTS promotion_reason TEXT;

ALTER TABLE fabops_intelligence_reports
DROP CONSTRAINT IF EXISTS fabops_intelligence_reports_case_id_material_signature_key;

ALTER TABLE fabops_intelligence_reports
ADD COLUMN IF NOT EXISTS assessment_run_id UUID DEFAULT gen_random_uuid(),
ADD COLUMN IF NOT EXISTS previous_report_id BIGINT REFERENCES fabops_intelligence_reports(report_id),
ADD COLUMN IF NOT EXISTS reused_report_id BIGINT REFERENCES fabops_intelligence_reports(report_id),
ADD COLUMN IF NOT EXISTS review_skipped_reason TEXT,
ADD COLUMN IF NOT EXISTS unchanged_since TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS input_context_fingerprint TEXT,
ADD COLUMN IF NOT EXISTS provider_model TEXT,
ADD COLUMN IF NOT EXISTS latency_ms DOUBLE PRECISION;

CREATE UNIQUE INDEX IF NOT EXISTS fabops_intelligence_reports_assessment_run_id_idx
ON fabops_intelligence_reports(assessment_run_id)
WHERE assessment_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS fabops_intelligence_reports_case_created_idx
ON fabops_intelligence_reports(case_id, created_at DESC, report_id DESC);

CREATE INDEX IF NOT EXISTS fabops_intelligence_reports_signature_created_idx
ON fabops_intelligence_reports(case_id, material_signature, created_at DESC);
