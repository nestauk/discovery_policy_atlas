-- Migration: Add user tracking columns to analysis_projects table
-- Run this in Supabase SQL editor to add creator information

-- Add user tracking columns to analysis_projects
ALTER TABLE analysis_projects 
ADD COLUMN created_by_user_id TEXT,
ADD COLUMN created_by_name TEXT;

-- Add indexes for better performance when filtering by user
CREATE INDEX IF NOT EXISTS idx_analysis_projects_user_id ON analysis_projects(created_by_user_id);

-- Add comment to document the purpose
COMMENT ON COLUMN analysis_projects.created_by_user_id IS 'Clerk user ID of the person who created this project';
COMMENT ON COLUMN analysis_projects.created_by_name IS 'Display name of the person who created this project (first name + last name or email fallback)';