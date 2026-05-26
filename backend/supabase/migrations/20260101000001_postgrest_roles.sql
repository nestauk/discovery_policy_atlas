-- PostgREST roles: authenticator, anon, service_role
-- The authenticator password is injected by the migration Lambda as the
-- session variable app.authenticator_password (see run_migrations.py).

DO $$
BEGIN
  -- anon: unauthenticated access role
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;

  -- service_role: privileged access role (bypasses RLS)
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
  END IF;

  -- authenticator: PostgREST login role, switches to anon/service_role via JWT
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
    EXECUTE format(
      'CREATE ROLE authenticator LOGIN PASSWORD %L',
      current_setting('app.authenticator_password')
    );
  ELSE
    -- On re-run, sync the password to match the secret
    EXECUTE format(
      'ALTER ROLE authenticator WITH PASSWORD %L',
      current_setting('app.authenticator_password')
    );
  END IF;
END
$$;

-- authenticator must be able to switch to these roles
GRANT anon TO authenticator;
GRANT service_role TO authenticator;

-- Schema access
GRANT USAGE ON SCHEMA public TO anon, service_role;

-- Table permissions
GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;

-- Sequence permissions
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO anon;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- Function permissions
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO anon, service_role;

-- Default privileges so future tables/sequences/functions get the same grants
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon, service_role;
