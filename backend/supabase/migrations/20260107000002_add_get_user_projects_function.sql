-- Function to get projects filtered by organization access rules
-- This centralizes the authorization logic in the database

CREATE OR REPLACE FUNCTION get_user_projects(
    p_user_id TEXT,
    p_organization_id TEXT DEFAULT NULL,
    p_organization_slug TEXT DEFAULT NULL,
    p_demo_org_id TEXT DEFAULT NULL,
    p_admin_org_slug TEXT DEFAULT 'nesta-dev'
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
            -- Projects from user's organization
            organization_id = p_organization_id
            -- Demo org projects (if demo org is configured)
            OR (p_demo_org_id IS NOT NULL AND organization_id = p_demo_org_id)
            -- User's own projects (regardless of org assignment - handles backfill edge case)
            OR created_by_user_id = p_user_id
        ORDER BY created_at DESC;
        RETURN;
    END IF;

    -- User without an organization
    RETURN QUERY
    SELECT * FROM analysis_projects
    WHERE 
        -- User's own projects (any org or no org)
        created_by_user_id = p_user_id
        -- Demo org projects (if demo org is configured)
        OR (p_demo_org_id IS NOT NULL AND organization_id = p_demo_org_id)
    ORDER BY created_at DESC;
END;
$$;

COMMENT ON FUNCTION get_user_projects IS 'Returns projects filtered by organization access rules. Admin org sees all, regular users see their org + demo + their own projects (regardless of org assignment).';

