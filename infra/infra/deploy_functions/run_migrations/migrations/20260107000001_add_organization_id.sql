-- Add organization_id to analysis_projects for multi-tenancy
-- Projects belong to the organization that was active when they were created

ALTER TABLE analysis_projects 
ADD COLUMN IF NOT EXISTS organization_id TEXT;

-- Index for efficient filtering by organization
CREATE INDEX IF NOT EXISTS idx_analysis_projects_organization 
ON analysis_projects(organization_id);

-- Note: Existing projects will have NULL organization_id
-- These should be backfilled manually or via a script once orgs are set up

