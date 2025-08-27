-- Enhanced Analysis Documents Schema Migration
-- Run this in Supabase SQL editor to add missing fields

-- Add missing fields to analysis_documents table
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS authors JSONB DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS doi TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS source_id TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS landing_page_url TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS pdf_url TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS is_oa BOOLEAN DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS document_type TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS document_type_reason TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS author_institution_countries JSONB DEFAULT NULL;

-- Relevance fields (some already exist)
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS relevance_confidence REAL DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS relevance_reason TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS top_line TEXT DEFAULT NULL;

-- Acquisition fields
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS acquisition_status TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS acquisition_error TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS full_text_available BOOLEAN DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS file_path TEXT DEFAULT NULL;

-- Extraction fields (extraction_status already exists)
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS extraction_error TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS text_source TEXT DEFAULT NULL;

-- Common fields from Paper interface and old system
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS citation_count INTEGER DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS venue TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS topics JSONB DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS source_country TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS published_on TEXT DEFAULT NULL;
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS overton_url TEXT DEFAULT NULL;

-- Add indexes for performance on commonly queried fields
CREATE INDEX IF NOT EXISTS idx_analysis_documents_source_country ON analysis_documents(source_country);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_source_type ON analysis_documents(source_type);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_is_relevant ON analysis_documents(is_relevant);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_year ON analysis_documents(year);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_acquisition_status ON analysis_documents(acquisition_status);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_extraction_status ON analysis_documents(extraction_status);

-- Add step tracking for stepwise uploads
ALTER TABLE analysis_documents ADD COLUMN IF NOT EXISTS upload_step TEXT DEFAULT 'initial';
-- upload_step values: 'initial', 'screened', 'acquired', 'extracted', 'completed'

CREATE INDEX IF NOT EXISTS idx_analysis_documents_upload_step ON analysis_documents(upload_step);

-- Update the constraint to allow updates to the same document
ALTER TABLE analysis_documents DROP CONSTRAINT IF EXISTS analysis_documents_analysis_project_id_doc_id_source_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_documents_unique 
ON analysis_documents(analysis_project_id, doc_id, source) 
WHERE upload_step != 'deleted';

COMMENT ON COLUMN analysis_documents.upload_step IS 
'Tracks the stage of data upload: initial, screened, acquired, extracted, completed';
COMMENT ON COLUMN analysis_documents.authors IS 
'JSON array of author names';
COMMENT ON COLUMN analysis_documents.author_institution_countries IS 
'JSON array of countries from author institutions';
COMMENT ON COLUMN analysis_documents.topics IS 
'JSON array of topic classifications';