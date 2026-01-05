-- Synthesis layer: runs, citations (claim-level), themes, and outcome tables

CREATE TABLE IF NOT EXISTS synthesis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_project_id UUID REFERENCES analysis_projects(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'created',
    version INTEGER DEFAULT 1,
    executive_briefing TEXT,
    model_info JSONB,
    state_after_clustering JSONB,
    state_after_critique JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    evidence_coverage JSONB,
    structured_briefing_data JSONB,
    total_outcomes INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_synthesis_runs_project ON synthesis_runs(analysis_project_id);


CREATE TABLE IF NOT EXISTS synthesis_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    synthesis_run_id UUID REFERENCES synthesis_runs(id) ON DELETE CASCADE,
    analysis_document_id UUID REFERENCES analysis_documents(id) ON DELETE SET NULL,
    citation_key TEXT,
    citation_index INTEGER,
    author_short TEXT,
    year INTEGER,
    title TEXT,
    url TEXT,
    study_type TEXT,
    country TEXT,
    supporting_quote TEXT,
    chunk_id UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    section TEXT,
    claim_text TEXT,
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON COLUMN synthesis_citations.section IS 
    'Briefing section where this citation appears: background, core_answer, interventions, recommendations';
COMMENT ON COLUMN synthesis_citations.claim_text IS 
    'Specific claim/sentence being supported by this citation usage';
COMMENT ON COLUMN synthesis_citations.supporting_quote IS 
    'Exact quote from the source document that supports the claim';
COMMENT ON COLUMN synthesis_citations.chunk_id IS 
    'Reference to the evidence chunk containing the supporting quote';
COMMENT ON COLUMN synthesis_citations.confidence IS 
    'Confidence score (0-1) for quote extraction accuracy';

CREATE INDEX IF NOT EXISTS idx_synthesis_citations_run ON synthesis_citations(synthesis_run_id);
CREATE INDEX IF NOT EXISTS idx_synthesis_citations_doc ON synthesis_citations(analysis_document_id);
CREATE INDEX IF NOT EXISTS idx_synthesis_citations_chunk ON synthesis_citations(chunk_id);
CREATE INDEX IF NOT EXISTS idx_citations_run_section ON synthesis_citations(synthesis_run_id, section);
CREATE INDEX IF NOT EXISTS idx_citations_run_number_section ON synthesis_citations(synthesis_run_id, citation_index, section);


CREATE TABLE IF NOT EXISTS synthesis_themes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    synthesis_run_id UUID REFERENCES synthesis_runs(id) ON DELETE CASCADE,
    theme_type TEXT,
    theme_name TEXT,
    summary_description TEXT,
    impact_summary TEXT,
    frequency INTEGER DEFAULT 0,
    source_doc_ids TEXT[],
    created_at TIMESTAMPTZ DEFAULT now(),
    impact_snapshot TEXT,
    implementation_context TEXT,
    effect_consensus TEXT,
    positive_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,
    null_count INTEGER DEFAULT 0,
    sample_effect_sizes JSONB,
    countries TEXT[],
    study_types JSONB,
    citation_keys TEXT[],
    related_outcome_theme_ids UUID[],
    source_document_ids UUID[]
);

COMMENT ON COLUMN synthesis_themes.impact_snapshot IS 
    'Quantitative impact summary, e.g., "~2% reduction in obesity prevalence over 5 years"';
COMMENT ON COLUMN synthesis_themes.implementation_context IS 
    'Implementation details, e.g., "UK (Proposal). Large OOH businesses (250+ employees)"';
COMMENT ON COLUMN synthesis_themes.effect_consensus IS 
    'Aggregated effect direction: positive, negative, mixed, null, or insufficient';
COMMENT ON COLUMN synthesis_themes.positive_count IS 
    'Number of results showing positive/increase effect direction';
COMMENT ON COLUMN synthesis_themes.sample_effect_sizes IS 
    'Array of representative effect size strings from the evidence';
COMMENT ON COLUMN synthesis_themes.countries IS 
    'List of countries where evidence for this theme originates';
COMMENT ON COLUMN synthesis_themes.study_types IS 
    'Distribution of study types, e.g., {"RCT": 3, "case_study": 5, "systematic_review": 1}';
COMMENT ON COLUMN synthesis_themes.citation_keys IS 
    'Array of citation keys for documents supporting this theme';
COMMENT ON COLUMN synthesis_themes.related_outcome_theme_ids IS 
    'Links intervention themes to their measured outcome themes';
COMMENT ON COLUMN synthesis_themes.source_document_ids IS 
    'UUIDs of analysis_documents supporting this theme';

CREATE INDEX IF NOT EXISTS idx_synthesis_themes_run ON synthesis_themes(synthesis_run_id);
CREATE INDEX IF NOT EXISTS idx_synthesis_themes_effect_consensus 
    ON synthesis_themes(effect_consensus) 
    WHERE effect_consensus IS NOT NULL;

-- Theme assignments (maps extractions to synthesis themes)
CREATE TABLE IF NOT EXISTS theme_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    synthesis_theme_id UUID NOT NULL REFERENCES synthesis_themes(id) ON DELETE CASCADE,
    extraction_id UUID NOT NULL REFERENCES analysis_extractions(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(synthesis_theme_id, extraction_id)
);

CREATE INDEX IF NOT EXISTS idx_theme_assignments_theme ON theme_assignments(synthesis_theme_id);
CREATE INDEX IF NOT EXISTS idx_theme_assignments_extraction ON theme_assignments(extraction_id);


CREATE TABLE IF NOT EXISTS synthesis_outcome_themes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    synthesis_run_id UUID NOT NULL REFERENCES synthesis_runs(id) ON DELETE CASCADE,
    outcome_name TEXT NOT NULL,
    outcome_description TEXT,
    effect_consensus VARCHAR(20),
    positive_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,
    null_count INTEGER DEFAULT 0,
    sample_effect_sizes TEXT[],
    frequency INTEGER DEFAULT 0,
    source_doc_ids TEXT[],
    created_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE synthesis_outcome_themes IS 
    'Clusters semantically similar outcomes (e.g., "obesity reduction", "lower BMI") into canonical themes';
COMMENT ON COLUMN synthesis_outcome_themes.effect_consensus IS 
    'Aggregated effect direction: positive, negative, mixed, null, or insufficient';

CREATE INDEX IF NOT EXISTS idx_outcome_themes_run 
    ON synthesis_outcome_themes(synthesis_run_id);
CREATE INDEX IF NOT EXISTS idx_outcome_themes_consensus 
    ON synthesis_outcome_themes(effect_consensus);


CREATE TABLE IF NOT EXISTS outcome_theme_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    synthesis_run_id UUID NOT NULL REFERENCES synthesis_runs(id) ON DELETE CASCADE,
    synthesis_outcome_theme_id UUID NOT NULL REFERENCES synthesis_outcome_themes(id) ON DELETE CASCADE,
    extraction_id UUID NOT NULL REFERENCES analysis_extractions(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(synthesis_outcome_theme_id, extraction_id)
);

COMMENT ON TABLE outcome_theme_assignments IS 
    'Maps result extractions to their canonical outcome themes';

CREATE INDEX IF NOT EXISTS idx_outcome_assignments_theme 
    ON outcome_theme_assignments(synthesis_outcome_theme_id);
CREATE INDEX IF NOT EXISTS idx_outcome_assignments_extraction 
    ON outcome_theme_assignments(extraction_id);

