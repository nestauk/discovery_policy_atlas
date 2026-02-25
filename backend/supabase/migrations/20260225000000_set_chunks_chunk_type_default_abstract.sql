-- Set chunks.chunk_type default to abstract for defensive fallback inserts.
ALTER TABLE public.chunks
ALTER COLUMN chunk_type SET DEFAULT 'abstract'::text;
