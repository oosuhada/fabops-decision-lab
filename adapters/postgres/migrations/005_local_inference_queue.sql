CREATE TABLE IF NOT EXISTS fabops_inference_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id TEXT NOT NULL,
    assessment_run_id UUID NOT NULL DEFAULT gen_random_uuid(),
    intent TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    priority INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'QUEUED',
        'WAITING_FOR_LOCAL',
        'RUNNING',
        'COMPLETED',
        'RETRY',
        'EXPIRED',
        'FALLBACK',
        'FAILED',
        'CANCELLED'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    not_before TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    busy_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    input_context_fingerprint TEXT NOT NULL,
    material_signature TEXT NOT NULL,
    provider_preference TEXT NOT NULL DEFAULT 'local-qwen',
    allow_vertex_fallback BOOLEAN NOT NULL DEFAULT false,
    fallback_after_seconds INTEGER,
    dedupe_key TEXT NOT NULL,
    request_document JSONB NOT NULL,
    result_document JSONB,
    error_class TEXT,
    error_detail_bounded TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS fabops_inference_jobs_active_dedupe_idx
ON fabops_inference_jobs(dedupe_key)
WHERE status IN ('QUEUED', 'WAITING_FOR_LOCAL', 'RUNNING', 'RETRY');

CREATE INDEX IF NOT EXISTS fabops_inference_jobs_ready_idx
ON fabops_inference_jobs(status, priority DESC, not_before, created_at)
WHERE status IN ('QUEUED', 'WAITING_FOR_LOCAL', 'RETRY');

CREATE INDEX IF NOT EXISTS fabops_inference_jobs_case_created_idx
ON fabops_inference_jobs(case_id, created_at DESC);

CREATE TABLE IF NOT EXISTS fabops_inference_runtime_state (
    provider TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    model TEXT,
    model_loaded BOOLEAN,
    active_jobs INTEGER NOT NULL DEFAULT 0,
    provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_success_at TIMESTAMPTZ,
    last_error_class TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
