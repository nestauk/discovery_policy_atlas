-- Create projects table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    evidence_count INTEGER DEFAULT 0,
    last_search_date TIMESTAMP WITH TIME ZONE,
    last_search_query TEXT,
    key_insights JSONB DEFAULT NULL,
    policy_recommendations JSONB DEFAULT NULL,
    executive_brief JSONB DEFAULT NULL,
    analytics JSONB DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Create index for better performance
CREATE INDEX IF NOT EXISTS idx_projects_created_at ON projects(created_at);
CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at);

-- Create a policy to allow all operations for now (adjust based on your auth requirements)
CREATE POLICY "Allow all operations on projects" ON projects 
FOR ALL USING (true);

-- Update the documents table to have proper project_id reference (if not already exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'documents' AND column_name = 'project_id'
    ) THEN
        ALTER TABLE documents ADD COLUMN project_id VARCHAR(255) DEFAULT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
    END IF;
END $$;

-- Create index on project_id in documents table for better performance
CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);

-- Update chunks table if needed
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'chunks' AND column_name = 'project_id'
    ) THEN
        ALTER TABLE chunks ADD COLUMN project_id VARCHAR(255) DEFAULT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
    END IF;
END $$;

-- Create index on project_id in chunks table
CREATE INDEX IF NOT EXISTS idx_chunks_project_id ON chunks(project_id);

-- Add key_insights column to existing projects table (if not already exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'projects' AND column_name = 'key_insights'
    ) THEN
        ALTER TABLE projects ADD COLUMN key_insights JSONB DEFAULT NULL;
    END IF;
END $$;

-- Add policy_recommendations column to existing projects table (if not already exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'projects' AND column_name = 'policy_recommendations'
    ) THEN
        ALTER TABLE projects ADD COLUMN policy_recommendations JSONB DEFAULT NULL;
    END IF;
END $$;

-- Add executive_brief column to existing projects table (if not already exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'projects' AND column_name = 'executive_brief'
    ) THEN
        ALTER TABLE projects ADD COLUMN executive_brief JSONB DEFAULT NULL;
    END IF;
END $$;

-- Add analytics column to existing projects table (if not already exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'projects' AND column_name = 'analytics'
    ) THEN
        ALTER TABLE projects ADD COLUMN analytics JSONB DEFAULT NULL;
    END IF;
END $$;

-- Add last_search_query column to existing projects table (if not already exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'projects' AND column_name = 'last_search_query'
    ) THEN
        ALTER TABLE projects ADD COLUMN last_search_query TEXT;
    END IF;
END $$;

-- Insert some default projects for testing
INSERT INTO projects (id, name, description, evidence_count) 
VALUES 
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Test Project', 'Default project for testing purposes', 0),
    (gen_random_uuid(), 'Youth Vaping Policy', 'Research on the health impacts of vaping among young people and policy recommendations', 0),
    (gen_random_uuid(), 'Climate Policy Analysis', 'Evidence synthesis for climate change mitigation policies and their effectiveness', 0),
    (gen_random_uuid(), 'Education Technology', 'Research on the impact of digital tools in educational settings', 0)
ON CONFLICT (id) DO NOTHING;

-- Create trigger to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_projects_updated_at 
    BEFORE UPDATE ON projects 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();