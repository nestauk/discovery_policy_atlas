-- Migration to extend run_id field length for datetime-based IDs
-- Run this in Supabase SQL editor

-- Extend run_id field to accommodate datetime format (YYYYMMDD_HHMMSS_UUID8 = 20 chars)
ALTER TABLE analysis_projects 
ALTER COLUMN run_id TYPE VARCHAR(24);

-- Update the constraint to handle the new format
-- The UNIQUE constraint will automatically be preserved during the ALTER