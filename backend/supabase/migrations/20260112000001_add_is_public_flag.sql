-- Add is_public flag to analysis_projects for publicly shareable projects
ALTER TABLE analysis_projects 
ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT FALSE;

-- Index for efficient filtering of public projects
CREATE INDEX idx_analysis_projects_is_public ON analysis_projects(is_public) WHERE is_public = TRUE;

-- Comment for documentation
COMMENT ON COLUMN analysis_projects.is_public IS 'When true, project results are viewable without authentication via public URL';

