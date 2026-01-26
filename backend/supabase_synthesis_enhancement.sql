-- ============================================================================
-- Policy Atlas: Synthesis Enhancement Migration
-- ============================================================================
-- This migration enhances the synthesis system to support:
-- 1. Outcome clustering (grouping semantically similar outcomes)
-- 2. Citation key infrastructure (stable document references)
-- 3. Enhanced intervention themes with effect data
-- 4. Evidence coverage snapshots
--
-- Run this in Supabase SQL editor after the base analysis tables exist.
-- ============================================================================

-- ============================================================================
-- PART 1: OUTCOME CLUSTERING TABLES
-- ============================================================================
-- Clusters semantically similar outcomes across documents
-- e.g., "obesity reduction", "lower BMI", "weight loss" → "Obesity Reduction"

CREATE TABLE IF NOT EXISTS synthesis_outcome_themes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    synthesis_run_id UUID NOT NULL,
    outcome_name TEXT NOT NULL,                    -- Canonical name: "Obesity Reduction"
    outcome_description TEXT,                      -- Brief explanation of what this outcome measures
    effect_consensus VARCHAR(20),                  -- 'positive', 'negative', 'mixed', 'null', 'insufficient'
    positive_count INTEGER DEFAULT 0,              -- Count of positive effect directions
    negative_count INTEGER DEFAULT 0,              -- Count of negative effect directions  
    null_count INTEGER DEFAULT 0,                  -- Count of null effect directions
    sample_effect_sizes TEXT[],                    -- Array of sample effect size strings
    frequency INTEGER DEFAULT 0,                   -- Number of documents mentioning this outcome
    source_doc_ids TEXT[],                         -- Document IDs where this outcome appears
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Foreign key to synthesis_runs (if table exists)
    CONSTRAINT fk_outcome_themes_run 
        FOREIGN KEY (synthesis_run_id) 
        REFERENCES synthesis_runs(id) 
        ON DELETE CASCADE
);

COMMENT ON TABLE synthesis_outcome_themes IS 
    'Clusters semantically similar outcomes (e.g., "obesity reduction", "lower BMI") into canonical themes';

COMMENT ON COLUMN synthesis_outcome_themes.effect_consensus IS 
    'Aggregated effect direction: positive if mostly increases, negative if mostly decreases, mixed if balanced';

-- Links result extractions to outcome themes
CREATE TABLE IF NOT EXISTS outcome_theme_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    synthesis_run_id UUID NOT NULL,
    synthesis_outcome_theme_id UUID NOT NULL,
    extraction_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT fk_outcome_assignment_run 
        FOREIGN KEY (synthesis_run_id) 
        REFERENCES synthesis_runs(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_outcome_assignment_theme 
        FOREIGN KEY (synthesis_outcome_theme_id) 
        REFERENCES synthesis_outcome_themes(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_outcome_assignment_extraction 
        FOREIGN KEY (extraction_id) 
        REFERENCES analysis_extractions(id) 
        ON DELETE CASCADE,
        
    -- Prevent duplicate assignments
    UNIQUE(synthesis_outcome_theme_id, extraction_id)
);

COMMENT ON TABLE outcome_theme_assignments IS 
    'Maps result extractions to their canonical outcome themes';

-- Indexes for outcome clustering
CREATE INDEX IF NOT EXISTS idx_outcome_themes_run 
    ON synthesis_outcome_themes(synthesis_run_id);
CREATE INDEX IF NOT EXISTS idx_outcome_themes_consensus 
    ON synthesis_outcome_themes(effect_consensus);
CREATE INDEX IF NOT EXISTS idx_outcome_assignments_theme 
    ON outcome_theme_assignments(synthesis_outcome_theme_id);
CREATE INDEX IF NOT EXISTS idx_outcome_assignments_extraction 
    ON outcome_theme_assignments(extraction_id);


-- ============================================================================
-- PART 2: CITATION INFRASTRUCTURE
-- ============================================================================
-- Provides stable citation keys for documents throughout synthesis
-- e.g., "[Smith, 2023]" or "[Source 1]"

CREATE TABLE IF NOT EXISTS synthesis_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    synthesis_run_id UUID NOT NULL,
    analysis_document_id UUID NOT NULL,
    citation_key TEXT NOT NULL,                    -- e.g., "[1]", "[2]" (numbered for RAG)
    citation_index INTEGER,                        -- Numeric index for ordering (1, 2, 3...)
    author_short TEXT,                             -- e.g., "Smith et al."
    year INTEGER,
    title TEXT,
    url TEXT,
    study_type TEXT,                               -- From extraction: "RCT", "systematic_review", etc.
    country TEXT,                                  -- Primary country from extraction
    supporting_quote TEXT,                         -- RAG: Grounded quote from retrieved chunk
    chunk_id TEXT,                                 -- RAG: Source chunk ID for traceability
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT fk_citations_run 
        FOREIGN KEY (synthesis_run_id) 
        REFERENCES synthesis_runs(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_citations_document 
        FOREIGN KEY (analysis_document_id) 
        REFERENCES analysis_documents(id) 
        ON DELETE CASCADE,
        
    -- Each document gets one citation key per run
    UNIQUE(synthesis_run_id, analysis_document_id)
);

-- Add new RAG columns if table already exists
ALTER TABLE synthesis_citations 
    ADD COLUMN IF NOT EXISTS supporting_quote TEXT;
ALTER TABLE synthesis_citations 
    ADD COLUMN IF NOT EXISTS chunk_id TEXT;

COMMENT ON TABLE synthesis_citations IS 
    'Stable citation keys for documents, enabling per-claim citations in briefings';

COMMENT ON COLUMN synthesis_citations.citation_key IS 
    'Display key like "[Smith, 2023]" or "[Source 1]" used in executive briefing';

-- Indexes for citation lookup
CREATE INDEX IF NOT EXISTS idx_citations_run 
    ON synthesis_citations(synthesis_run_id);
CREATE INDEX IF NOT EXISTS idx_citations_document 
    ON synthesis_citations(analysis_document_id);
CREATE INDEX IF NOT EXISTS idx_citations_key 
    ON synthesis_citations(citation_key);


-- ============================================================================
-- PART 3: ENHANCE SYNTHESIS_THEMES TABLE
-- ============================================================================
-- Add new columns for intervention evidence data

-- Impact snapshot: quantitative summary like "~2% reduction in obesity"
ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS impact_snapshot TEXT;

COMMENT ON COLUMN synthesis_themes.impact_snapshot IS 
    'Quantitative impact summary, e.g., "~2% reduction in obesity prevalence over 5 years"';

-- Implementation context: where/how the intervention was applied
ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS implementation_context TEXT;

COMMENT ON COLUMN synthesis_themes.implementation_context IS 
    'Implementation details, e.g., "UK (Proposal). Large OOH businesses (250+ employees)"';

-- Effect consensus: overall direction of evidence
ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS effect_consensus VARCHAR(20);

COMMENT ON COLUMN synthesis_themes.effect_consensus IS 
    'Aggregated effect direction: positive, negative, mixed, null, or insufficient';

-- Effect direction counts
ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS positive_count INTEGER DEFAULT 0;

ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS negative_count INTEGER DEFAULT 0;

ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS null_count INTEGER DEFAULT 0;

COMMENT ON COLUMN synthesis_themes.positive_count IS 
    'Number of results showing positive/increase effect direction';

-- Sample effect sizes for display
ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS sample_effect_sizes TEXT[];

COMMENT ON COLUMN synthesis_themes.sample_effect_sizes IS 
    'Array of representative effect size strings from the evidence';

-- Countries covered by this theme
ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS countries TEXT[];

COMMENT ON COLUMN synthesis_themes.countries IS 
    'List of countries where evidence for this theme originates';

-- Study type distribution
ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS study_types JSONB;

COMMENT ON COLUMN synthesis_themes.study_types IS 
    'Distribution of study types, e.g., {"RCT": 3, "case_study": 5, "systematic_review": 1}';

-- Citation keys for this theme
ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS citation_keys TEXT[];

COMMENT ON COLUMN synthesis_themes.citation_keys IS 
    'Array of citation keys for documents supporting this theme, e.g., ["[Source 1]", "[Smith, 2023]"]';

-- Related outcome theme IDs (for intervention → outcome linking)
ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS related_outcome_theme_ids UUID[];

COMMENT ON COLUMN synthesis_themes.related_outcome_theme_ids IS 
    'Links intervention themes to their measured outcome themes';

-- Source document UUIDs (more reliable than doc_id strings)
ALTER TABLE synthesis_themes 
    ADD COLUMN IF NOT EXISTS source_document_ids UUID[];

COMMENT ON COLUMN synthesis_themes.source_document_ids IS 
    'UUIDs of analysis_documents supporting this theme (more reliable than string doc_ids)';

-- Index for effect consensus queries
CREATE INDEX IF NOT EXISTS idx_themes_effect_consensus 
    ON synthesis_themes(effect_consensus) 
    WHERE effect_consensus IS NOT NULL;


-- ============================================================================
-- PART 4: ENHANCE SYNTHESIS_RUNS TABLE
-- ============================================================================
-- Add columns for evidence coverage and structured briefing data

-- Evidence coverage snapshot (deterministically computed)
ALTER TABLE synthesis_runs 
    ADD COLUMN IF NOT EXISTS evidence_coverage JSONB;

COMMENT ON COLUMN synthesis_runs.evidence_coverage IS 
    'Deterministically computed evidence coverage statistics: study_types, countries, years, gaps';

/*
Expected structure:
{
    "total_sources": 23,
    "study_types": {"systematic_review": 3, "rct": 5, "case_study": 15},
    "countries": {"UK": 15, "US": 5, "EU": 3},
    "years": {"2020": 5, "2021": 8, "2022": 10},
    "overall_strength": "Moderate",
    "gaps": ["No RCTs specific to OOH sector", "Limited LMIC data"]
}
*/

-- Structured briefing data (payload passed to final LLM)
ALTER TABLE synthesis_runs 
    ADD COLUMN IF NOT EXISTS structured_briefing_data JSONB;

COMMENT ON COLUMN synthesis_runs.structured_briefing_data IS 
    'Complete structured payload used to generate the executive briefing (for debugging/audit)';

-- Outcome theme count
ALTER TABLE synthesis_runs 
    ADD COLUMN IF NOT EXISTS total_outcomes INTEGER DEFAULT 0;

COMMENT ON COLUMN synthesis_runs.total_outcomes IS 
    'Number of outcome themes discovered in this run';


-- ============================================================================
-- PART 5: HELPER FUNCTIONS
-- ============================================================================

-- Function to get citation key for a document in a synthesis run
CREATE OR REPLACE FUNCTION get_citation_key(
    p_synthesis_run_id UUID,
    p_analysis_document_id UUID
) RETURNS TEXT AS $$
DECLARE
    v_citation_key TEXT;
BEGIN
    SELECT citation_key INTO v_citation_key
    FROM synthesis_citations
    WHERE synthesis_run_id = p_synthesis_run_id
      AND analysis_document_id = p_analysis_document_id;
    
    RETURN COALESCE(v_citation_key, '[Unknown Source]');
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_citation_key IS 
    'Returns the citation key for a document in a specific synthesis run';


-- Function to get outcome themes for a synthesis run
CREATE OR REPLACE FUNCTION get_project_outcome_themes(
    p_project_id UUID
) RETURNS TABLE (
    id UUID,
    outcome_name TEXT,
    outcome_description TEXT,
    effect_consensus VARCHAR(20),
    positive_count INTEGER,
    negative_count INTEGER,
    null_count INTEGER,
    frequency INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ot.id,
        ot.outcome_name,
        ot.outcome_description,
        ot.effect_consensus,
        ot.positive_count,
        ot.negative_count,
        ot.null_count,
        ot.frequency
    FROM synthesis_outcome_themes ot
    JOIN synthesis_runs sr ON sr.id = ot.synthesis_run_id
    WHERE sr.analysis_project_id = p_project_id
      AND sr.status = 'completed'
    ORDER BY sr.created_at DESC, ot.frequency DESC;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_project_outcome_themes IS 
    'Returns outcome themes for a project from the latest completed synthesis run';


-- Function to get evidence coverage for a project
CREATE OR REPLACE FUNCTION get_project_evidence_coverage(
    p_project_id UUID
) RETURNS JSONB AS $$
DECLARE
    v_coverage JSONB;
BEGIN
    SELECT evidence_coverage INTO v_coverage
    FROM synthesis_runs
    WHERE analysis_project_id = p_project_id
      AND status = 'completed'
    ORDER BY created_at DESC
    LIMIT 1;
    
    RETURN COALESCE(v_coverage, '{}'::JSONB);
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_project_evidence_coverage IS 
    'Returns the evidence coverage snapshot for a project from the latest completed synthesis run';


-- ============================================================================
-- PART 6: ROW LEVEL SECURITY (Optional - match existing patterns)
-- ============================================================================

-- Enable RLS on new tables (following existing patterns)
ALTER TABLE synthesis_outcome_themes ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcome_theme_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE synthesis_citations ENABLE ROW LEVEL SECURITY;

-- Permissive policies for prototyping (adjust based on auth requirements)
DO $$
BEGIN
    -- synthesis_outcome_themes policies
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'synthesis_outcome_themes' 
          AND policyname = 'Allow all operations on synthesis_outcome_themes'
    ) THEN
        CREATE POLICY "Allow all operations on synthesis_outcome_themes" 
            ON synthesis_outcome_themes FOR ALL USING (true);
    END IF;
    
    -- outcome_theme_assignments policies
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'outcome_theme_assignments' 
          AND policyname = 'Allow all operations on outcome_theme_assignments'
    ) THEN
        CREATE POLICY "Allow all operations on outcome_theme_assignments" 
            ON outcome_theme_assignments FOR ALL USING (true);
    END IF;
    
    -- synthesis_citations policies
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'synthesis_citations' 
          AND policyname = 'Allow all operations on synthesis_citations'
    ) THEN
        CREATE POLICY "Allow all operations on synthesis_citations" 
            ON synthesis_citations FOR ALL USING (true);
    END IF;
END $$;


-- ============================================================================
-- PART 7: VERIFICATION QUERIES
-- ============================================================================
-- Run these after migration to verify the changes

/*
-- Check new tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN ('synthesis_outcome_themes', 'outcome_theme_assignments', 'synthesis_citations');

-- Check new columns on synthesis_themes
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'synthesis_themes' 
  AND column_name IN (
    'impact_snapshot', 
    'implementation_context', 
    'effect_consensus',
    'positive_count',
    'negative_count',
    'null_count',
    'sample_effect_sizes',
    'countries',
    'study_types',
    'citation_keys',
    'related_outcome_theme_ids',
    'source_document_ids'
  );

-- Check new columns on synthesis_runs
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'synthesis_runs' 
  AND column_name IN ('evidence_coverage', 'structured_briefing_data', 'total_outcomes');

-- Check functions exist
SELECT proname 
FROM pg_proc 
WHERE proname IN ('get_citation_key', 'get_project_outcome_themes', 'get_project_evidence_coverage');
*/


-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- Next steps:
-- 1. Update backend/app/services/synthesis/agent.py with new workflow nodes
-- 2. Update backend/app/services/synthesis/logbook.py to write new tables
-- 3. Update backend/app/services/synthesis/schemas.py with new models
-- 4. Add API endpoints for outcome themes if needed for frontend
-- ============================================================================

