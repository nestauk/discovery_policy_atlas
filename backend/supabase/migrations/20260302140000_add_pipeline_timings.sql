-- Pipeline timings table for recording execution duration per stage per run.
-- One row per stage per pipeline execution.

CREATE TABLE IF NOT EXISTS pipeline_timings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES analysis_projects(id) ON DELETE CASCADE,
    pipeline_type   TEXT NOT NULL CHECK (pipeline_type IN ('analysis', 'synthesis')),
    stage_name      TEXT NOT NULL,
    duration_seconds DOUBLE PRECISION NOT NULL,
    document_count  INTEGER,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_pipeline_timings_project_id
    ON pipeline_timings(project_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_timings_pipeline_type
    ON pipeline_timings(pipeline_type);
CREATE INDEX IF NOT EXISTS idx_pipeline_timings_created_at
    ON pipeline_timings(created_at);

-- RLS: match the existing "Allow all" pattern used by other tables
ALTER TABLE pipeline_timings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all" ON pipeline_timings USING (true);
