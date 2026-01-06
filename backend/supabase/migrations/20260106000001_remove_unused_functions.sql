-- Remove unused database functions that were created ad-hoc via dashboard
-- These functions are not used by the application code

-- get_network_data_for_project: Never called from Python code
DROP FUNCTION IF EXISTS public.get_network_data_for_project(uuid);

-- get_project_thematic_groups: Superseded by get_project_thematic_groups_by_type
DROP FUNCTION IF EXISTS public.get_project_thematic_groups(uuid);

-- get_theme_items: Superseded by get_theme_items_rich
DROP FUNCTION IF EXISTS public.get_theme_items(uuid, text);

-- update_updated_at_column: Orphaned trigger function (no trigger references it)
DROP FUNCTION IF EXISTS public.update_updated_at_column();

