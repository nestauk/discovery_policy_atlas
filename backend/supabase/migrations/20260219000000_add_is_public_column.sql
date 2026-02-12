-- Add is_public column to analysis_projects for public URL sharing
-- Projects with is_public=true can be accessed without authentication

ALTER TABLE analysis_projects 
ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE;

-- Index for efficient filtering of public projects
CREATE INDEX IF NOT EXISTS idx_analysis_projects_is_public 
ON analysis_projects(is_public) WHERE is_public = TRUE;
