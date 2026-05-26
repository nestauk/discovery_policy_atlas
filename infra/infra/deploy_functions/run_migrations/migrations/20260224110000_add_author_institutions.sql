-- Store flattened OpenAlex author institutions for citation/document metadata.
ALTER TABLE IF EXISTS public.analysis_documents
ADD COLUMN IF NOT EXISTS author_institutions jsonb;

COMMENT ON COLUMN public.analysis_documents.author_institutions IS
'JSON array of flattened author institution names extracted from source metadata';
