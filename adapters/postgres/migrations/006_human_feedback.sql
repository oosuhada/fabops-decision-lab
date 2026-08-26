CREATE TABLE IF NOT EXISTS fabops_human_feedback (
    feedback_id BIGSERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    prediction_id BIGINT,
    feedback_type TEXT NOT NULL CHECK (
        feedback_type IN (
            'useful',
            'not_useful',
            'false_positive',
            'true_positive',
            'wrong_priority',
            'wrong_mechanism',
            'investigation_confirmed',
            'investigation_contradicted'
        )
    ),
    prediction_target TEXT,
    actor TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    note TEXT,
    feedback_document JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS fabops_human_feedback_case_created_idx
ON fabops_human_feedback(case_id, created_at DESC, feedback_id DESC);

CREATE INDEX IF NOT EXISTS fabops_human_feedback_type_created_idx
ON fabops_human_feedback(feedback_type, created_at DESC);

CREATE INDEX IF NOT EXISTS fabops_human_feedback_prediction_idx
ON fabops_human_feedback(prediction_id)
WHERE prediction_id IS NOT NULL;
