-- Additive migration for an existing local SQLite database. Back up the file first.
CREATE TABLE IF NOT EXISTS quality_check_runs (
    id VARCHAR(36) PRIMARY KEY,
    check_id VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    finished_at DATETIME,
    duration_seconds FLOAT,
    exit_code INTEGER,
    summary VARCHAR(500) NOT NULL DEFAULT '',
    diagnostics TEXT NOT NULL DEFAULT '',
    cases JSON NOT NULL DEFAULT '[]',
    counts JSON NOT NULL DEFAULT '{}',
    project_version VARCHAR(40),
    environment VARCHAR(30) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_quality_check_runs_check_id ON quality_check_runs (check_id);
CREATE INDEX IF NOT EXISTS ix_quality_check_runs_status ON quality_check_runs (status);
