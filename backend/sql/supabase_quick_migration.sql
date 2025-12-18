-- Quick migration to enable stepwise uploads
-- Run this in Supabase SQL editor first to enable basic functionality

-- Add only essential fields for stepwise uploads
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS upload_step TEXT DEFAULT 'initial';
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS source_id TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS top_line TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS relevance_confidence REAL DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS relevance_reason TEXT DEFAULT NULL;

-- Add basic indexes
CREATE INDEX IF NOT EXISTS idx_analysis_documents_upload_step ON analysis_documents(upload_step);

-- Update the constraint to allow updates (drop the old one if it exists)
DO $$
BEGIN
    -- Drop existing unique constraint if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'analysis_documents' 
        AND constraint_name = 'analysis_documents_analysis_project_id_doc_id_source_key'
    ) THEN
        ALTER TABLE analysis_documents DROP CONSTRAINT analysis_documents_analysis_project_id_doc_id_source_key;
    END IF;
END $$;

-- Create a new unique index that allows updates
CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_documents_unique 
ON analysis_documents(analysis_project_id, doc_id, source);

COMMENT ON COLUMN analysis_documents.upload_step IS 
'Tracks the stage of data upload: initial, screened, acquired, extracted, completed';