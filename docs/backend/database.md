# Database setup

The application uses **Supabase** (managed PostgreSQL) with **pgvector** for vector similarity search. Schema changes are managed through **Supabase CLI migrations**.

## Architecture

```
backend/supabase/
├── config.toml          # Local Supabase configuration
└── migrations/          # SQL migration files (timestamped)
    ├── 20260101000000_baseline.sql
    └── 20260106000001_remove_unused_functions.sql
```

## Core tables

### Analysis layer

| Table | Purpose |
|-------|---------|
| `analysis_projects` | Research projects with metadata, search queries, and user ownership |
| `analysis_documents` | Documents within projects (papers, policy docs) with screening/extraction status |
| `analysis_extractions` | Extracted entities (issues, interventions, results) from documents |

### Synthesis layer

| Table | Purpose |
|-------|---------|
| `synthesis_runs` | Synthesis execution records with briefings and evidence coverage |
| `synthesis_themes` | Clustered themes (issues/interventions) with effect consensus |
| `theme_assignments` | Links extractions to their assigned themes |
| `synthesis_outcome_themes` | Outcome clusters with effect direction aggregates |
| `outcome_theme_assignments` | Links result extractions to outcome themes |
| `synthesis_citations` | Per-claim citations for executive briefings |

### Supporting tables

| Table | Purpose |
|-------|---------|
| `user_feedback` | User ratings and comments on projects |

### Vector store

| Table | Purpose |
|-------|---------|
| `chunks` | Document chunks with 1536-dim embeddings for RAG queries |

The `match_chunks()` function performs vector similarity search with project filtering.

## Local development

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) running
- [Supabase CLI](https://supabase.com/docs/guides/cli) installed (`brew install supabase/tap/supabase`)

### Setup

```bash
cd backend

# Start local Supabase (Postgres, Studio, Auth, Storage)
supabase start

# Access points after startup:
# - Studio UI: http://localhost:54323
# - API: http://localhost:54321
# - DB: postgresql://postgres:postgres@localhost:54322/postgres
```

### Reset database

To apply all migrations from scratch:

```bash
supabase db reset
```

### Stop services

```bash
supabase stop
```

## Environment variables

The application requires these environment variables to connect to Supabase:

```bash
SUPABASE_URL=<your_supabase_url>
SUPABASE_KEY=<your_supabase_anon_key>
```

### Local development

After running `supabase start`, get your local credentials:

```bash
supabase status
```

And set in your `.env`:

```bash
SUPABASE_URL=http://127.0.0.1:54321 # Studio URL from supabase status
SUPABASE_KEY=sb_secret_...  # Secret key from supabase status
```

### Production

Get credentials from the [Supabase Dashboard](https://supabase.com/dashboard):
1. Select your project
2. Go to **Data API** to find SUPABASE_URL
3. Go to **Project Settings** and **API Keys** to find SUPABASE_KEY

## Making schema changes

### 1. Create a migration

```bash
supabase migration new descriptive_name
# Creates: supabase/migrations/YYYYMMDDHHMMSS_descriptive_name.sql
```

### 2. Write your SQL

Edit the generated file with your schema changes. Use idempotent patterns:

```sql
-- Tables
CREATE TABLE IF NOT EXISTS my_table (...);

-- Columns
ALTER TABLE my_table ADD COLUMN IF NOT EXISTS new_col TEXT;

-- Functions
CREATE OR REPLACE FUNCTION my_func() ...;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_name ON my_table(column);
```

### 3. Test locally

```bash
supabase db reset
```

### 4. Push to production

```bash
# Preview changes
supabase db diff --linked

# Apply to production
supabase db push
```

## Linking to production

First-time setup to connect CLI to your cloud project:

```bash
# Authenticate
supabase login

# Link to project (get ref from Supabase dashboard URL)
supabase link --project-ref YOUR_PROJECT_REF
```

## Best practices

1. **Never edit applied migrations** - Create new migrations for changes
2. **Test locally first** - Always run `supabase db reset` before pushing
3. **Use safe DDL** - Prefer `IF EXISTS` / `IF NOT EXISTS` clauses
4. **One concern per migration** - Keep migrations focused and reviewable
5. **Document breaking changes** - Add comments for non-obvious migrations
