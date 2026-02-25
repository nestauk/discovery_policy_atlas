-- db/roles.sql
-- Idempotent role and schema setup for Supabase running against AWS RDS.
-- Run once as the RDS master user (postgres) before starting Supabase services.
--
-- RDS limitations vs the upstream supabase/postgres image:
--   * pgsodium is NOT available → Supabase Vault is disabled.
--   * pg_net is NOT available   → Database Webhooks are disabled.
--   * REPLICATION privilege is granted via the RDS-specific rds_replication role.
--   * SUPERUSER is not available; rds_superuser is the equivalent.
--
-- The RDS parameter group must have rds.logical_replication = 1 for Realtime.

-- ── Extensions ───────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"  WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "pgcrypto"   WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "pgjwt"      WITH SCHEMA extensions;
-- pgvector for embeddings (available on RDS)
CREATE EXTENSION IF NOT EXISTS "vector"     WITH SCHEMA extensions;

-- ── Schemas ──────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS storage;
CREATE SCHEMA IF NOT EXISTS realtime;
CREATE SCHEMA IF NOT EXISTS _realtime;
CREATE SCHEMA IF NOT EXISTS graphql_public;

-- ── Roles (all idempotent via DO block) ──────────────────────────────────────
DO $$
BEGIN
  -- Application roles (no login — PostgREST switches into these per-request)
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
  END IF;

  -- Admin role (no login; used for ownership / grants)
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_admin') THEN
    CREATE ROLE supabase_admin NOINHERIT NOLOGIN;
  END IF;

  -- Service-specific login roles — passwords are set below to POSTGRES_PASSWORD.
  -- Each Supabase service connects to the DB using its own role so that
  -- schema ownership and privilege boundaries are maintained.
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_auth_admin') THEN
    CREATE ROLE supabase_auth_admin NOINHERIT LOGIN NOREPLICATION;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_storage_admin') THEN
    CREATE ROLE supabase_storage_admin NOINHERIT LOGIN NOREPLICATION;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_replication_admin') THEN
    -- NOREPLICATION here because on RDS we grant rds_replication instead.
    CREATE ROLE supabase_replication_admin NOINHERIT LOGIN NOREPLICATION;
  END IF;

  -- PostgREST's connection role — switches to anon/authenticated/service_role
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
    CREATE ROLE authenticator NOINHERIT LOGIN NOREPLICATION;
  END IF;
END $$;

-- ── Passwords (set to the RDS master password for self-hosted simplicity) ────
-- init.sh substitutes :POSTGRES_PASSWORD using psql's -v flag.
ALTER ROLE supabase_auth_admin      WITH PASSWORD :'POSTGRES_PASSWORD';
ALTER ROLE supabase_storage_admin   WITH PASSWORD :'POSTGRES_PASSWORD';
ALTER ROLE supabase_replication_admin WITH PASSWORD :'POSTGRES_PASSWORD';
ALTER ROLE authenticator            WITH PASSWORD :'POSTGRES_PASSWORD';

-- ── Logical replication for Realtime (RDS-specific) ──────────────────────────
-- Requires rds.logical_replication = 1 in the RDS parameter group.
GRANT rds_replication TO supabase_replication_admin;

-- ── Role hierarchy ───────────────────────────────────────────────────────────
-- postgres (master user) needs to be able to grant these roles
GRANT anon             TO postgres;
GRANT authenticated    TO postgres;
GRANT service_role     TO postgres;
GRANT supabase_admin   TO postgres;

-- authenticator can switch into all application roles
GRANT anon             TO authenticator;
GRANT authenticated    TO authenticator;
GRANT service_role     TO authenticator;
GRANT supabase_admin   TO authenticator;

-- ── Schema ownership ─────────────────────────────────────────────────────────
ALTER SCHEMA auth      OWNER TO supabase_auth_admin;
ALTER SCHEMA storage   OWNER TO supabase_storage_admin;
ALTER SCHEMA _realtime OWNER TO supabase_replication_admin;
ALTER SCHEMA realtime  OWNER TO supabase_replication_admin;

-- ── Schema usage grants ──────────────────────────────────────────────────────
GRANT USAGE ON SCHEMA public          TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA extensions      TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA graphql_public  TO anon, authenticated, service_role;

-- ── Default privileges ───────────────────────────────────────────────────────
-- Future tables created in public are accessible to the application roles.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;
