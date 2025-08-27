-- Minimal Analysis Tables for Prototyping
-- Run this in Supabase SQL editor

-- 1. Analysis Projects
CREATE TABLE analysis_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id VARCHAR(24) UNIQUE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    query TEXT NOT NULL,
    total_references INTEGER DEFAULT 0,
    relevant_references INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'created',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Analysis Documents  
CREATE TABLE analysis_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_project_id UUID REFERENCES analysis_projects(id) ON DELETE CASCADE,
    doc_id VARCHAR(255) NOT NULL,
    source VARCHAR(50) NOT NULL,
    title TEXT,
    abstract_or_summary TEXT,
    year INTEGER,
    is_relevant BOOLEAN,
    extraction_status VARCHAR(20),
    extraction_results JSONB,
    user_feedback_ok BOOLEAN,
    user_feedback_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(analysis_project_id, doc_id, source)
);

-- 3. Analysis Extractions
CREATE TABLE analysis_extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_project_id UUID REFERENCES analysis_projects(id) ON DELETE CASCADE,
    analysis_document_id UUID REFERENCES analysis_documents(id) ON DELETE CASCADE,
    extraction_type VARCHAR(20) NOT NULL, -- 'issue', 'intervention', 'result', etc.
    label TEXT,
    description TEXT,
    supporting_quote TEXT,
    raw_data JSONB,
    user_feedback_ok BOOLEAN,
    user_feedback_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Basic indexes
CREATE INDEX idx_analysis_documents_project ON analysis_documents(analysis_project_id);
CREATE INDEX idx_analysis_extractions_document ON analysis_extractions(analysis_document_id);
CREATE INDEX idx_analysis_extractions_type ON analysis_extractions(extraction_type);

-- Allow all access for prototyping
ALTER TABLE analysis_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_extractions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all" ON analysis_projects FOR ALL USING (true);
CREATE POLICY "Allow all" ON analysis_documents FOR ALL USING (true);
CREATE POLICY "Allow all" ON analysis_extractions FOR ALL USING (true);