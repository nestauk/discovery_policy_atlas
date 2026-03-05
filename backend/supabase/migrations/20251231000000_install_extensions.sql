-- Install required PostgreSQL extensions before the baseline schema.
-- pgvector: available on Aurora PostgreSQL 14.5+ and RDS PostgreSQL 11+.
CREATE EXTENSION IF NOT EXISTS "vector" WITH SCHEMA "public";
