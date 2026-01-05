-- Drop the foreign key constraint that links chunks to documents table
-- This allows chunks to reference analysis_documents.id directly

-- Drop the foreign key constraint
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_document_id_fkey;

-- Add a comment to clarify the new relationship
COMMENT ON COLUMN chunks.document_id IS 'References analysis_documents.id (UUID) for analysis projects, or documents.id for legacy projects';

-- Optional: Add an index on document_id for performance (if not already exists)
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);

-- Note: Project deletion in projects.py handles cleanup by:
-- 1. Finding all analysis_documents.id for the project
-- 2. Deleting chunks WHERE document_id IN (analysis_doc_ids)  
-- 3. Deleting analysis_project (CASCADE handles analysis_documents and analysis_extractions)