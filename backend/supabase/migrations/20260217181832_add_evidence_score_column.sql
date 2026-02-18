-- Add evidence_score column to analysis_documents
-- Deterministic score (0-5) derived from evidence_category + sample_size.
-- Computed after extraction; NULL for legacy rows (fallback calculation handles them).
ALTER TABLE analysis_documents
  ADD COLUMN IF NOT EXISTS evidence_score SMALLINT DEFAULT NULL;
