-- Vector store for RAG and match function (aligns to existing 'chunks' table)

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES analysis_documents(id) ON DELETE CASCADE,
    project_id UUID REFERENCES analysis_projects(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    chunk_type TEXT DEFAULT 'summary',
    chunk_index INTEGER DEFAULT 0,
    embedding VECTOR(1536),
    token_count INTEGER,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
    ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

DROP FUNCTION IF EXISTS match_chunks(vector, float, int, text);

CREATE OR REPLACE FUNCTION match_chunks(
  query_embedding vector(1536),
  match_threshold float,
  match_count int,
  project_filter text DEFAULT NULL
)
RETURNS TABLE(
  id uuid,
  document_id uuid,
  content text,
  similarity float,
  chunk_type text,
  document_title text,
  document_authors jsonb,
  top_line text
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    c.id,
    c.document_id,
    c.content,
    1 - (c.embedding <=> query_embedding) AS similarity,
    c.chunk_type,
    ad.title AS document_title,
    ad.authors AS document_authors,
    ad.top_line AS top_line
  FROM document_chunks c
  JOIN analysis_documents ad ON c.document_id = ad.id
  WHERE 
    (project_filter IS NULL OR c.project_id = project_filter::uuid)
    AND 1 - (c.embedding <=> query_embedding) > match_threshold
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

