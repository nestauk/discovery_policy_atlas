# PR Notes: Migrate Backend from Supabase SDK to Direct PostgreSQL (psycopg2)

## Summary

Replaced the Supabase Python SDK with direct PostgreSQL access via psycopg2 across the entire backend. This removes the dependency on the Supabase REST/PostgREST layer and connects directly to the database, which is required for the IaC deployment where the database is an RDS Aurora cluster (not a Supabase-managed instance).

## Motivation

- IaC deployment uses AWS RDS Aurora (PostgreSQL), not Supabase
- Supabase SDK communicates over HTTP to the PostgREST API — not available on RDS
- Direct psycopg2 connection is simpler, faster, and avoids the overhead of HTTP round-trips

## New Files

### `backend/app/core/database.py`
psycopg2 connection pool and query helper module. Key exports:
- `db.fetch(sql, params)` → `List[Dict]`
- `db.fetchone(sql, params)` → `Optional[Dict]`
- `db.fetchcount(sql, params)` → `int`
- `db.execute(sql, params)` → `None` (DML without return)
- `db.insert(table, data)` → `Dict` (RETURNING *)
- `db.insert_many(table, rows)` → `None`
- `db.upsert(table, data, conflict_cols)` → `Optional[Dict]`
- `db.upsert_many(table, rows, conflict_cols)` → `None`
- `db.fmt_vector(embedding)` → `str` (pgvector literal)

Uses `ThreadedConnectionPool` (1–20 connections), `RealDictCursor` for dict rows, and `register_default_json/jsonb` for automatic JSONB ↔ Python dict conversion.

### `backend/app/core/db_tables.py`
(Supporting type stubs / table constants if present.)

## Changed Files

### `backend/app/core/config.py`
- Removed: `SUPABASE_URL`, `SUPABASE_KEY`
- Added: `DATABASE_URL: Optional[str]`

### `backend/pyproject.toml`
- Removed: `supabase` dependency
- Added: `psycopg2-binary>=2.9.0`

### `backend/app/services/vectorization.py`
- Removed: `self._supabase` / `supabase` property (Supabase client for vector search)
- Replaced: `vectorization_service.supabase.table("chunks")...` → `db.fetch(...)` using `<-> embedding` operator for similarity search

### `backend/app/services/synthesis/logbook.py`
- Full rewrite: replaced all Supabase table/RPC calls with `db.*` helpers
- Synthesis run status tracking now via direct SQL

### `backend/app/services/synthesis/agent.py`
- Replaced: `vectorization_service.supabase...` → `db.execute()` / `db.fetchone()`

### `backend/app/services/synthesis/nodes/data_loading.py`
- Full rewrite: replaced all Supabase calls with `db.fetch()` / `db.fetchone()`
- `load_theme_assignments(project_id, supabase)` → `load_theme_assignments(project_id)` (supabase param removed)

### `backend/app/services/synthesis/nodes/aggregation.py`
- Replaced 2 Supabase calls: `analysis_documents` and `analysis_extractions` queries
- `.in_("id", chunk)` → `WHERE id = ANY(%s)` with Python list

### `backend/app/services/synthesis/findings.py`
- Full rewrite: removed `_async_supabase_query` helper
- All Supabase chain calls replaced with `db.fetch()` / `db.fetchone()`

### `backend/app/services/chatbot/chat_service.py`
- Replaced 2 Supabase calls: chunks neighbour query and document details lookup
- `vectorization_service.supabase.table("chunks")` → `db.fetch(...)`
- `vectorization_service.supabase.table("analysis_documents")` → `db.fetch(...)`

### `backend/app/utils/project_data.py`
- Full rewrite: all ~15 Supabase calls replaced
- **Critical translation**: `get_navigator_overview_data` — PostgREST nested join across 4 tables (dot-notation embedded query) → single SQL `LEFT JOIN` query + Python aggregation
- Count queries: `.select("id", count="exact").limit(0)` → `db.fetchcount("SELECT COUNT(*) FROM ...")`

### `backend/app/api/public.py`
- Replaced: `vectorization_service.supabase.table("analysis_projects")` → `db.fetchone(...)`

### `backend/app/api/projects.py`
Replaced all Supabase calls (~37 total). Key translations:
- `supabase.rpc("get_user_projects", {...})` → `db.fetch("SELECT * FROM get_user_projects(%s, ...)")`
- `supabase.rpc("get_project_thematic_groups_by_type", {...})` → `db.fetch("SELECT * FROM get_project_thematic_groups_by_type(%s::uuid, %s)")`
- `supabase.rpc("get_theme_items_rich", {...})` → `db.fetch("SELECT * FROM get_theme_items_rich(%s::uuid, %s)")`
- Dynamic UPDATE with RETURNING for `update_analysis_project`
- Batch delete+insert pattern for `delete_analysis_project`
- All status update calls → `db.execute("UPDATE ...")`
- CSV export helpers: all `.table(...)` chains → `db.fetch(...)`
- Feedback endpoints: project check + feedback insert → `db.fetchone()` + `db.insert()`

### `backend/app/services/analysis/storage.py`
- Removed: `from supabase import create_client`, `self._supabase`, `supabase` property, `_async_supabase_query` helper, `_db_semaphore`
- Added: `import app.core.database as db`, `_adapt_params()` helper for JSONB serialisation in dynamic UPDATE statements
- Replaced all ~14 Supabase call sites:
  - `_get_project_search_query`: `db.fetchone(...)`
  - `check_existing_extractions`: `db.fetch(...)` with `= ANY(%s)`
  - `store_single_extraction`: dynamic UPDATE + RETURNING, `db.execute()` DELETE, `db.insert_many()`
  - `store_document_chunks`: `db.fetchone()`, `db.execute()` DELETE, `db.insert_many()` with `db.fmt_vector(embedding)` for pgvector column
  - `update_documents_with_extractions`: `db.fetch(...)`
  - `_create_analysis_project`: `db.insert(...)`
  - `_update_analysis_project`: UPDATE with RETURNING
  - `_upload_extractions`: `db.fetch(...)` + `db.insert_many()`
  - `_mark_analysis_completed` / `_mark_project_failed`: `db.execute(...)` / UPDATE with RETURNING
  - `_upsert_documents`: `db.insert_many()` with individual `db.upsert()` fallback
  - `_update_documents_by_doc_id`: dynamic SET clause UPDATE with RETURNING

## SQL Translation Patterns

| Supabase pattern | SQL equivalent |
|---|---|
| `.select(cols).eq(col, v)` | `SELECT cols FROM t WHERE col = %s` |
| `.in_("col", list)` | `WHERE col = ANY(%s)` (pass Python list) |
| `.select("id", count="exact").limit(0)` | `SELECT COUNT(*) FROM t WHERE ...` |
| `supabase.rpc("func", {"p": v})` | `SELECT * FROM func(%s)` (positional) |
| `.insert(data)` | `INSERT INTO t (...) VALUES (...) RETURNING *` |
| `.update(data).eq(...)` | `UPDATE t SET ... WHERE ... RETURNING *` |
| `.delete().eq(...)` | `DELETE FROM t WHERE ...` |
| `.order("col", desc=True).limit(1)` | `ORDER BY col DESC LIMIT 1` |

## Pre-deployment Requirements

- `DATABASE_URL` environment variable must be set (PostgreSQL DSN)
- Format: `postgresql://user:password@host:5432/dbname`
- The `chunks` table must have a `vector` column for pgvector — embeddings are inserted as `[x,y,z,...]` string literals via `db.fmt_vector()`
