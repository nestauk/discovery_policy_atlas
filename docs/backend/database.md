# Database Setup - Supabase with pgvector

This document contains the SQL schema and functions required to set up the RAG (Retrieval-Augmented Generation) system using Supabase with pgvector for vector similarity search.

## Overview

The RAG system uses three main tables:
- **`searches`**: Logs user search queries and activity
- **`documents`**: Stores policy documents with metadata
- **`chunks`**: Stores text chunks with vector embeddings for similarity search

## Prerequisites

1. Enable the `pgvector` extension in your Supabase project
2. Run the SQL commands below in the Supabase SQL editor

## 1. Enable pgvector Extension

```sql
-- Enable the pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;
```

## 2. Searches Table

The `searches` table logs user search queries for analytics and history tracking.

```sql
-- Create searches table for query logging
CREATE TABLE searches (
    search_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    search_query TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX idx_searches_project_id ON searches(project_id);
CREATE INDEX idx_searches_user_id ON searches(user_id);
CREATE INDEX idx_searches_created_at ON searches(created_at);
```

## 3. Documents Table

The `documents` table stores the policy documents collected from search results.

```sql
-- Create documents table
CREATE TABLE documents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    project_id TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    authors TEXT[],
    abstract TEXT,
    content TEXT,
    doi TEXT,
    overton_url TEXT,
    source_country TEXT,
    source_type TEXT,
    published_date TIMESTAMP,
    confidence DECIMAL,
    relevance_reason TEXT,
    is_relevant BOOLEAN DEFAULT true,
    top_line TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX idx_documents_project_id ON documents(project_id);
CREATE INDEX idx_documents_external_id ON documents(external_id);
CREATE INDEX idx_documents_created_at ON documents(created_at);
```

## 4. Chunks Table

The `chunks` table stores document chunks with vector embeddings for semantic search.

```sql
-- Create chunks table with vector embeddings
CREATE TABLE chunks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL,
    content TEXT NOT NULL,
    chunk_type TEXT NOT NULL DEFAULT 'summary',
    chunk_index INTEGER DEFAULT 0,
    embedding VECTOR(1536), -- OpenAI ada-002 embedding dimension
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for vector similarity search
CREATE INDEX idx_chunks_project_id ON chunks(project_id);
CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

## 5. Vector Similarity Search Function

This PostgreSQL function performs efficient vector similarity search with project filtering.

```sql
-- Create function for vector similarity search
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.8,
    match_count INT DEFAULT 5,
    project_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    chunk_type TEXT,
    similarity FLOAT,
    document_title TEXT,
    project_id TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.document_id,
        c.content,
        c.chunk_type,
        1 - (c.embedding <=> query_embedding) AS similarity,
        d.title AS document_title,
        c.project_id
    FROM chunks c
    LEFT JOIN documents d ON c.document_id = d.id
    WHERE 
        (project_filter IS NULL OR c.project_id = project_filter)
        AND (1 - (c.embedding <=> query_embedding)) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

## 6. Row Level Security (Optional)

If you want to enable Row Level Security (RLS) for multi-tenant applications:

```sql
-- Enable RLS on both tables
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;

-- Create policies (example for project-based access)
-- Note: Adjust these policies based on your authentication setup

-- Documents policy
CREATE POLICY "Users can access documents in their projects" ON documents
    FOR ALL USING (
        project_id IN (
            SELECT project_id FROM user_projects 
            WHERE user_id = auth.uid()
        )
    );

-- Chunks policy  
CREATE POLICY "Users can access chunks in their projects" ON chunks
    FOR ALL USING (
        project_id IN (
            SELECT project_id FROM user_projects 
            WHERE user_id = auth.uid()
        )
    );
```

## 7. Environment Variables

Ensure these environment variables are set in your backend:

```bash
# Supabase Configuration
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key

# OpenAI for embeddings
OPENAI_API_KEY=your_openai_api_key
```

## Usage in Application

The Python application uses these tables through the `VectorizationService`:

### Storing Documents
```python
# Store search results with vectorization
await vectorization_service.store_search_results(papers, project_id)
```

### Logging Search Queries
```python
# Log user search activity
search_id = await logging_service.log_search(
    project_id="test_project",
    search_query="refined user query",
    user_id="clerk_user_id"
)
```

### Searching Similar Content
```python
# Find relevant documents for user query
relevant_docs = await vectorization_service.search_similar_content(
    query="user question",
    project_id="test_project",
    match_threshold=0.7,
    match_count=5
)
```

### Getting Search History
```python
# Retrieve recent searches for a project
history = await logging_service.get_search_history(
    project_id="test_project",
    limit=10
)
```

## Performance Considerations

1. **Vector Index**: The `ivfflat` index on embeddings provides approximate nearest neighbor search
2. **Lists Parameter**: Set to 100 for small datasets, increase for larger ones
3. **Embedding Dimensions**: Fixed at 1536 for OpenAI's `text-embedding-ada-002` model
4. **Similarity Threshold**: Adjust `match_threshold` based on your quality requirements

## Data Flow

1. **Search** → Overton API returns policy documents
2. **Screening** → AI filters for relevance 
3. **Vectorization** → Generate embeddings for document summaries
4. **Storage** → Store in `documents` and `chunks` tables
5. **RAG Query** → Use `match_chunks()` function for similarity search
6. **Response** → Generate cited answers with document links

This setup provides a robust foundation for semantic search over policy documents with proper citation and source linking capabilities.