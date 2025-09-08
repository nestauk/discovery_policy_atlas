-- Updated match_chunks function to work with analysis_documents table only
-- Simple version for analysis projects

-- Drop existing function first
DROP FUNCTION IF EXISTS match_chunks(vector, double precision, integer, text);

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
  FROM chunks c
  JOIN analysis_documents ad ON c.document_id = ad.id
  WHERE 
    (project_filter IS NULL OR c.project_id = project_filter)
    AND 1 - (c.embedding <=> query_embedding) > match_threshold
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;