-- Add impact score and transferability fields

ALTER TABLE analysis_documents
ADD COLUMN IF NOT EXISTS impact_score INTEGER,
ADD COLUMN IF NOT EXISTS impact_score_label TEXT,
ADD COLUMN IF NOT EXISTS impact_score_breakdown JSONB,
ADD COLUMN IF NOT EXISTS transferability_score FLOAT,
ADD COLUMN IF NOT EXISTS transferability_breakdown JSONB;

ALTER TABLE synthesis_themes
ADD COLUMN IF NOT EXISTS impact_score INTEGER,
ADD COLUMN IF NOT EXISTS impact_score_label TEXT,
ADD COLUMN IF NOT EXISTS impact_score_breakdown JSONB;