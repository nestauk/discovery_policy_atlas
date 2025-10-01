-- Migration: Add search_query column to analysis_projects table
-- Run this in Supabase SQL editor to store search plan information

-- Add search_query JSONB column to analysis_projects
ALTER TABLE analysis_projects 
ADD COLUMN search_query JSONB;

-- Add comment to document the purpose
COMMENT ON COLUMN analysis_projects.search_query IS 'JSON object containing the complete search plan including original query, boolean query, filters, and search parameters';

-- Example structure of search_query JSON:
-- {
--   "original_query": "What are the biggest interventions for decarbonising home heating?",
--   "boolean_query": "(decarbonis* OR \"carbon reduction\") AND (\"home heating\" OR \"residential heating\") AND (intervention* OR program*)",
--   "sub_questions": ["What are the most effective heating interventions?"],
--   "sources": ["openalex", "overton"],
--   "access_types": ["academic", "policy"],
--   "geography_filter": ["United Kingdom", "Germany"],
--   "time_preset": "LAST_5_YEARS",
--   "time_from": "2019-01-01",
--   "time_to": "2024-01-01",
--   "limit": 200,
--   "mode": "semantic",
--   "scope": ["Individuals", "Organizations"],
--   "custom_focus": ["energy efficiency"],
--   "excludes": ["Industry"],
--   "custom_excludes": ["modeling"],
--   "relevance_enabled": true,
--   "use_abstracts_only": false
-- }