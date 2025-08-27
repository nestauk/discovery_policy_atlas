-- Make query field nullable in analysis_projects table
-- Run this in Supabase SQL editor

ALTER TABLE analysis_projects 
ALTER COLUMN query DROP NOT NULL;