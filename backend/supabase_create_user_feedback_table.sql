-- Create user_feedback table for storing project feedback as structured columns
CREATE TABLE IF NOT EXISTS user_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES analysis_projects(id) ON DELETE CASCADE,
    user_id uuid REFERENCES auth.users(id),
    user_email text,
    user_name text,
    rating integer NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    -- Add any additional metadata columns as needed
    -- e.g., feedback_type, context, etc.
    CONSTRAINT fk_project FOREIGN KEY(project_id) REFERENCES analysis_projects(id)
);

-- Index for faster lookup by project
CREATE INDEX IF NOT EXISTS idx_user_feedback_project_id ON user_feedback(project_id);

-- Index for faster lookup by user
CREATE INDEX IF NOT EXISTS idx_user_feedback_user_id ON user_feedback(user_id);
