-- Add impact score and transferability fields

ALTER TABLE analysis_documents
ADD COLUMN IF NOT EXISTS impact_score FLOAT,
ADD COLUMN IF NOT EXISTS impact_score_label TEXT,
ADD COLUMN IF NOT EXISTS impact_score_breakdown JSONB,
ADD COLUMN IF NOT EXISTS transferability_score FLOAT,
ADD COLUMN IF NOT EXISTS transferability_breakdown JSONB,
ADD COLUMN IF NOT EXISTS has_harm_warning BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS harm_warning_reason TEXT;

ALTER TABLE synthesis_themes
ADD COLUMN IF NOT EXISTS impact_score FLOAT,
ADD COLUMN IF NOT EXISTS impact_score_label TEXT,
ADD COLUMN IF NOT EXISTS impact_score_breakdown JSONB;

CREATE INDEX IF NOT EXISTS idx_analysis_documents_impact_score
ON analysis_documents (impact_score DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_synthesis_themes_impact_score
ON synthesis_themes (impact_score DESC NULLS LAST);