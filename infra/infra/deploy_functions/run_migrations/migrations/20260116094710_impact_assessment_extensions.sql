-- Tier 2 impact synthesis schema updates

-- Extend synthesis_themes for transferability and risk theme support
ALTER TABLE synthesis_themes
  ADD COLUMN IF NOT EXISTS transferability_rating varchar,
  ADD COLUMN IF NOT EXISTS transferability_note text,
  ADD COLUMN IF NOT EXISTS transferability_breakdown jsonb,
  ADD COLUMN IF NOT EXISTS has_harm_warning boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS linked_intervention_theme_id uuid REFERENCES synthesis_themes(id);

-- Update theme_type check constraint to include 'risk'
ALTER TABLE synthesis_themes
  DROP CONSTRAINT IF EXISTS synthesis_themes_theme_type_check;
ALTER TABLE synthesis_themes
  ADD CONSTRAINT synthesis_themes_theme_type_check
  CHECK (theme_type = ANY (ARRAY['issue', 'intervention', 'result', 'risk']));

-- Extend synthesis_outcome_themes for verdict data
ALTER TABLE synthesis_outcome_themes
  ADD COLUMN IF NOT EXISTS verdict_label varchar,
  ADD COLUMN IF NOT EXISTS verdict_description text,
  ADD COLUMN IF NOT EXISTS discord_flag boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS discord_reason text,
  ADD COLUMN IF NOT EXISTS predicted_magnitude varchar,
  ADD COLUMN IF NOT EXISTS magnitude_detail jsonb,
  ADD COLUMN IF NOT EXISTS primary_causal_mechanism varchar,
  ADD COLUMN IF NOT EXISTS causal_mechanism_detail jsonb,
  ADD COLUMN IF NOT EXISTS intervention_theme_id uuid REFERENCES synthesis_themes(id);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_outcome_themes_intervention
  ON synthesis_outcome_themes(intervention_theme_id);
CREATE INDEX IF NOT EXISTS idx_themes_linked_intervention
  ON synthesis_themes(linked_intervention_theme_id)
  WHERE theme_type = 'risk';

-- Document the semantic change to counts
COMMENT ON COLUMN synthesis_outcome_themes.positive_count IS
  'Weighted score: sum of evidence_quality_score for positive direction results';
COMMENT ON COLUMN synthesis_outcome_themes.negative_count IS
  'Weighted score: sum of evidence_quality_score for negative direction results';
COMMENT ON COLUMN synthesis_outcome_themes.null_count IS
  'Weighted score: sum of evidence_quality_score for null/no-effect results';

-- Junction table for many-to-many theme-to-intervention links (risks and issues)
CREATE TABLE IF NOT EXISTS theme_intervention_links (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  theme_id UUID NOT NULL REFERENCES synthesis_themes(id) ON DELETE CASCADE,
  intervention_theme_id UUID NOT NULL REFERENCES synthesis_themes(id) ON DELETE CASCADE,
  link_strength VARCHAR(20) DEFAULT 'primary' CHECK (link_strength IN ('primary', 'secondary')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(theme_id, intervention_theme_id)
);

CREATE INDEX IF NOT EXISTS idx_theme_links_theme ON theme_intervention_links(theme_id);
CREATE INDEX IF NOT EXISTS idx_theme_links_intervention ON theme_intervention_links(intervention_theme_id);

COMMENT ON TABLE theme_intervention_links IS
  'Many-to-many links between risk/issue themes and intervention themes';
COMMENT ON COLUMN theme_intervention_links.link_strength IS
  'primary = strongest document overlap, secondary = additional relevant intervention';

