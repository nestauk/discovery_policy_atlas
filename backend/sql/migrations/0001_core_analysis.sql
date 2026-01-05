-- Core analysis schema

CREATE TABLE IF NOT EXISTS analysis_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id VARCHAR(24) UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    query TEXT,
    total_references INTEGER DEFAULT 0,
    relevant_references INTEGER DEFAULT 0,
    status TEXT DEFAULT 'created',
    created_at TIMESTAMPTZ DEFAULT now(),
    created_by_user_id TEXT,
    created_by_name TEXT,
    user_feedback JSONB,
    search_query JSONB
);

COMMENT ON COLUMN analysis_projects.search_query IS 'JSON object containing the complete search plan including original query, boolean query, filters, and search parameters';
COMMENT ON COLUMN analysis_projects.created_by_user_id IS 'Clerk user ID of the person who created this project';
COMMENT ON COLUMN analysis_projects.created_by_name IS 'Display name of the person who created this project (first name + last name or email fallback)';
COMMENT ON COLUMN analysis_projects.user_feedback IS 'User feedback stored as JSON with structure: {"rating": 1-5, "comment": "text", "updated_at": "timestamp", "user_id": "string"}';

CREATE INDEX IF NOT EXISTS idx_analysis_projects_created_at ON analysis_projects(created_at);
CREATE INDEX IF NOT EXISTS idx_analysis_projects_user_id ON analysis_projects(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_analysis_projects_user_feedback ON analysis_projects USING GIN (user_feedback);


CREATE TABLE IF NOT EXISTS analysis_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_project_id UUID REFERENCES analysis_projects(id) ON DELETE CASCADE,
    doc_id TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT,
    abstract_or_summary TEXT,
    year INTEGER,
    is_relevant BOOLEAN,
    extraction_status TEXT,
    extraction_results JSONB,
    user_feedback_ok BOOLEAN,
    user_feedback_text TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    authors JSONB,
    doi TEXT,
    source_id TEXT,
    landing_page_url TEXT,
    pdf_url TEXT,
    is_oa BOOLEAN,
    document_type TEXT,
    document_type_reason TEXT,
    author_institution_countries JSONB,
    relevance_confidence REAL,
    relevance_reason TEXT,
    top_line TEXT,
    acquisition_status TEXT,
    acquisition_error TEXT,
    full_text_available BOOLEAN,
    file_path TEXT,
    extraction_error TEXT,
    text_source TEXT,
    citation_count INTEGER,
    venue TEXT,
    topics JSONB,
    source_country TEXT,
    source_type TEXT,
    published_on TEXT,
    overton_url TEXT,
    upload_step TEXT DEFAULT 'initial',
    evidence_category TEXT,
    evidence_confidence REAL,
    evidence_category_reasoning TEXT
);

COMMENT ON COLUMN analysis_documents.upload_step IS 'Tracks the stage of data upload: initial, screened, acquired, extracted, completed';
COMMENT ON COLUMN analysis_documents.authors IS 'JSON array of author names';
COMMENT ON COLUMN analysis_documents.author_institution_countries IS 'JSON array of countries from author institutions';
COMMENT ON COLUMN analysis_documents.topics IS 'JSON array of topic classifications';

CREATE INDEX IF NOT EXISTS idx_analysis_documents_project ON analysis_documents(analysis_project_id);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_is_relevant ON analysis_documents(is_relevant);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_year ON analysis_documents(year);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_upload_step ON analysis_documents(upload_step);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_source_country ON analysis_documents(source_country);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_source_type ON analysis_documents(source_type);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_acquisition_status ON analysis_documents(acquisition_status);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_extraction_status ON analysis_documents(extraction_status);
CREATE INDEX IF NOT EXISTS idx_analysis_documents_evidence_category ON analysis_documents(evidence_category);

-- Filtered unique index to allow soft-deleted rows (upload_step = 'deleted')
CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_documents_unique
ON analysis_documents(analysis_project_id, doc_id, source)
WHERE upload_step != 'deleted';


CREATE TABLE IF NOT EXISTS analysis_extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_project_id UUID REFERENCES analysis_projects(id) ON DELETE CASCADE,
    analysis_document_id UUID REFERENCES analysis_documents(id) ON DELETE CASCADE,
    extraction_type TEXT NOT NULL,
    label TEXT,
    description TEXT,
    supporting_quote TEXT,
    raw_data JSONB,
    user_feedback_ok BOOLEAN,
    user_feedback_text TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analysis_extractions_project ON analysis_extractions(analysis_project_id);
CREATE INDEX IF NOT EXISTS idx_analysis_extractions_document ON analysis_extractions(analysis_document_id);
CREATE INDEX IF NOT EXISTS idx_analysis_extractions_type ON analysis_extractions(extraction_type);


-- Structured user feedback table
CREATE TABLE IF NOT EXISTS user_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES analysis_projects(id) ON DELETE CASCADE,
    user_id text,
    user_email text,
    user_name text,
    rating integer NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON COLUMN user_feedback.user_id IS 'Clerk user ID (text, not uuid)';

CREATE INDEX IF NOT EXISTS idx_user_feedback_project_id ON user_feedback(project_id);
CREATE INDEX IF NOT EXISTS idx_user_feedback_user_id ON user_feedback(user_id);