-- Seed data for local development.
-- Runs on every `supabase db reset` (configured in config.toml).
--
-- Uses deterministic UUIDs so they're predictable in dev/tests.
-- Uses ON CONFLICT to be safely re-runnable.

-- ============================================================================
-- TEST USERS
-- ============================================================================

INSERT INTO public.users (id, email, name)
VALUES
    ('a0000000-0000-0000-0000-000000000001', 'alice@example.com', 'Alice Developer'),
    ('a0000000-0000-0000-0000-000000000002', 'bob@example.com', 'Bob Researcher'),
    ('a0000000-0000-0000-0000-000000000003', 'charlie@example.com', 'Charlie Admin')
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- TEST IDENTITIES (simulate both Clerk and Cognito logins)
-- ============================================================================

INSERT INTO public.user_identities (user_id, provider, provider_user_id)
VALUES
    ('a0000000-0000-0000-0000-000000000001', 'clerk',   'user_clerk_alice'),
    ('a0000000-0000-0000-0000-000000000001', 'cognito', 'b1111111-1111-1111-1111-111111111111'),
    ('a0000000-0000-0000-0000-000000000002', 'clerk',   'user_clerk_bob'),
    ('a0000000-0000-0000-0000-000000000003', 'clerk',   'user_clerk_charlie'),
    ('a0000000-0000-0000-0000-000000000003', 'cognito', 'c3333333-3333-3333-3333-333333333333')
ON CONFLICT ON CONSTRAINT uq_user_identities_provider DO NOTHING;

-- ============================================================================
-- TEST ORGANIZATIONS
-- ============================================================================

INSERT INTO public.organizations (id, name, slug, external_id)
VALUES
    ('b0000000-0000-0000-0000-000000000001', 'Nesta Dev', 'nesta-dev', 'org_clerk_nesta_dev'),
    ('b0000000-0000-0000-0000-000000000002', 'Demo Org', 'demo', 'org_clerk_demo')
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- TEST MEMBERSHIPS
-- ============================================================================

INSERT INTO public.organization_memberships (user_id, organization_id, role)
VALUES
    ('a0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'member'),
    ('a0000000-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-000000000002', 'member'),
    ('a0000000-0000-0000-0000-000000000003', 'b0000000-0000-0000-0000-000000000001', 'admin')
ON CONFLICT ON CONSTRAINT uq_org_membership DO NOTHING;
