-- Add user_feedback column to analysis_projects table
-- This column will store user feedback as JSON with rating and comments

ALTER TABLE analysis_projects 
ADD COLUMN user_feedback JSONB DEFAULT NULL;

-- Add a comment to document the column structure
COMMENT ON COLUMN analysis_projects.user_feedback IS 'User feedback stored as JSON with structure: {"rating": 1-5, "comment": "text", "updated_at": "timestamp", "user_id": "string"}';

-- Create an index on the user_feedback column for better query performance
CREATE INDEX IF NOT EXISTS idx_analysis_projects_user_feedback 
ON analysis_projects USING GIN (user_feedback);