-- Add evidence score and details columns to analysis_documents
-- Deterministic values derived from evidence_category + sample_size.
-- Computed after extraction; NULL for legacy rows (fallback calculation handles them).
ALTER TABLE analysis_documents
  ADD COLUMN IF NOT EXISTS evidence_score SMALLINT DEFAULT NULL;

ALTER TABLE analysis_documents
  ADD COLUMN IF NOT EXISTS evidence_justification TEXT DEFAULT NULL;

ALTER TABLE analysis_documents
  ADD COLUMN IF NOT EXISTS evidence_sample_size INTEGER DEFAULT NULL;
