ALTER TABLE analysis_projects
  ADD COLUMN IF NOT EXISTS parent_project_id UUID DEFAULT NULL
  REFERENCES analysis_projects(id) ON DELETE SET NULL;
