-- App-owned identity and organisation tables.
--
-- Decouples user identity from any single auth provider (Clerk, Cognito, etc.)
-- by introducing an internal UUID-based user record with a many-to-many link
-- to provider identities.
--
-- All SQL is idempotent (IF NOT EXISTS / CREATE OR REPLACE) because the
-- migration Lambda re-runs every file on each deploy.

-- ============================================================================
-- USERS (canonical app-owned identity)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT,
    name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
    ON public.users (email)
    WHERE email IS NOT NULL;

COMMENT ON TABLE public.users IS
    'App-owned user identity, independent of any auth provider.';

-- ============================================================================
-- USER_IDENTITIES (links provider-specific IDs to internal users)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.user_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_identities_provider UNIQUE (provider, provider_user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_identities_user_id
    ON public.user_identities (user_id);

COMMENT ON TABLE public.user_identities IS
    'Maps external provider IDs (clerk user_xxx, cognito sub UUID) to an internal users.id.';
COMMENT ON COLUMN public.user_identities.provider IS
    'Auth provider name: clerk | cognito';
COMMENT ON COLUMN public.user_identities.provider_user_id IS
    'The subject identifier from the provider (Clerk user_xxx or Cognito sub UUID).';

-- ============================================================================
-- ORGANIZATIONS (app-owned, replaces Clerk native orgs)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT,
    external_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_slug
    ON public.organizations (slug)
    WHERE slug IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_external_id
    ON public.organizations (external_id)
    WHERE external_id IS NOT NULL;

COMMENT ON TABLE public.organizations IS
    'App-owned organisations (previously managed by Clerk).';
COMMENT ON COLUMN public.organizations.external_id IS
    'Original Clerk org_xxx ID, used during backfill to link existing data.';

-- ============================================================================
-- ORGANIZATION_MEMBERSHIPS
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.organization_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_org_membership UNIQUE (user_id, organization_id)
);

CREATE INDEX IF NOT EXISTS idx_org_memberships_user_id
    ON public.organization_memberships (user_id);

CREATE INDEX IF NOT EXISTS idx_org_memberships_org_id
    ON public.organization_memberships (organization_id);

COMMENT ON TABLE public.organization_memberships IS
    'Links users to organisations with a role.';

-- ============================================================================
-- ADD owner_user_id FK TO analysis_projects
-- ============================================================================
-- Coexists with the legacy created_by_user_id TEXT column during transition.
-- The backfill script populates owner_user_id from created_by_user_id via
-- the user_identities lookup. Once cutover is complete, created_by_user_id
-- can be dropped in a follow-up migration.

ALTER TABLE public.analysis_projects
    ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_analysis_projects_owner_user_id
    ON public.analysis_projects (owner_user_id);

-- ============================================================================
-- UPDATE get_user_projects() TO CHECK BOTH COLUMNS
-- ============================================================================
-- The new signature adds p_internal_user_id. CREATE OR REPLACE with a
-- different parameter list would create an *overload* alongside the old
-- 5-param function, making RPC calls ambiguous — drop the old one first.

DROP FUNCTION IF EXISTS get_user_projects(TEXT, TEXT, TEXT, TEXT, TEXT);

CREATE OR REPLACE FUNCTION get_user_projects(
    p_user_id TEXT,
    p_organization_id TEXT DEFAULT NULL,
    p_organization_slug TEXT DEFAULT NULL,
    p_demo_org_id TEXT DEFAULT NULL,
    p_admin_org_slug TEXT DEFAULT 'nesta-dev',
    p_internal_user_id UUID DEFAULT NULL
)
RETURNS SETOF analysis_projects
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    -- Admin org sees everything
    IF p_organization_slug = p_admin_org_slug THEN
        RETURN QUERY
        SELECT * FROM analysis_projects
        ORDER BY created_at DESC;
        RETURN;
    END IF;

    -- User with an organization
    IF p_organization_id IS NOT NULL THEN
        RETURN QUERY
        SELECT * FROM analysis_projects
        WHERE
            organization_id = p_organization_id
            OR (p_demo_org_id IS NOT NULL AND organization_id = p_demo_org_id)
            OR created_by_user_id = p_user_id
            OR (p_internal_user_id IS NOT NULL AND owner_user_id = p_internal_user_id)
        ORDER BY created_at DESC;
        RETURN;
    END IF;

    -- User without an organization
    RETURN QUERY
    SELECT * FROM analysis_projects
    WHERE
        created_by_user_id = p_user_id
        OR (p_internal_user_id IS NOT NULL AND owner_user_id = p_internal_user_id)
        OR (p_demo_org_id IS NOT NULL AND organization_id = p_demo_org_id)
    ORDER BY created_at DESC;
END;
$$;

COMMENT ON FUNCTION get_user_projects IS
    'Returns projects filtered by organisation access rules. Checks both legacy created_by_user_id and new owner_user_id during transition.';
