-- Additive migration for an existing local PostgreSQL database. Review before applying.
CREATE TABLE IF NOT EXISTS quality_check_runs (
    id VARCHAR(36) PRIMARY KEY,
    check_id VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    duration_seconds DOUBLE PRECISION,
    exit_code INTEGER,
    summary VARCHAR(500) NOT NULL DEFAULT '',
    diagnostics TEXT NOT NULL DEFAULT '',
    cases JSON NOT NULL DEFAULT '[]'::json,
    counts JSON NOT NULL DEFAULT '{}'::json,
    project_version VARCHAR(40),
    environment VARCHAR(30) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_quality_check_runs_check_id ON quality_check_runs (check_id);
CREATE INDEX IF NOT EXISTS ix_quality_check_runs_status ON quality_check_runs (status);
