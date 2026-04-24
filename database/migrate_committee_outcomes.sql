-- Migration: add committee_outcome_evaluations table (commission's Załącznik 4a evaluations)
CREATE TABLE IF NOT EXISTS committee_outcome_evaluations (
    id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id       UUID    NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    learning_outcome_id INTEGER NOT NULL REFERENCES learning_outcomes(id),
    result              assessment_result NOT NULL,
    notes               TEXT,
    UNIQUE (enrollment_id, learning_outcome_id)
);
