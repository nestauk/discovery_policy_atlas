-- Change user_id column in user_feedback to text to support Clerk string IDs
ALTER TABLE user_feedback
    ALTER COLUMN user_id TYPE text USING user_id::text;

-- Remove old foreign key constraint if it exists (optional, since auth.users may not be a uuid table)
ALTER TABLE user_feedback DROP CONSTRAINT IF EXISTS user_feedback_user_id_fkey;

-- Optionally, add a comment for clarity
COMMENT ON COLUMN user_feedback.user_id IS 'Clerk user ID (text, not uuid)';
