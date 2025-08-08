# Project Management Workflow

The project management system allows researchers to organize evidence collection across multiple searches and maintain persistent research contexts for AI-powered analysis.

## Flow Overview

**Project Selection** (`/agent/projects`)

   - Users can create new research projects or select existing ones
   - Each project serves as a container for related evidence and search results
   - Active project is displayed in the sidebar and persists across sessions

**Evidence Collection** (`/agent` → `/agent/results`)

   - All searches automatically associate results with the active project
   - Multiple searches can contribute evidence to the same project
   - Results page dynamically loads evidence from the active project
   - Real-time updates when new searches complete

**AI-Powered Analysis** (chatbot integration)

   - RAG chatbot restricts search context to active project evidence
   - Conversations are project-aware and context-specific
   - Historical evidence informs AI responses and recommendations

## Architecture Overview

### Frontend Components

#### Project Store (`frontend/lib/projectStore.ts`)
```typescript
interface Project {
  id: string;
  name: string;
  description?: string;
  evidence_count: number;
  last_search_date?: string;
  created_at: string;
  updated_at: string;
}
```

- **Zustand state management** for projects and active project selection
- **Local storage persistence** for active project across browser sessions
- **Type-safe interfaces** for project data

#### API Client (`frontend/lib/api.ts`)
- **Authentication wrapper** around fetch() with Clerk JWT tokens
- **Centralized error handling** for 401 authentication failures
- **Environment-agnostic** base URL configuration
- **Type-safe methods** for all project CRUD operations

#### Results Page (`frontend/app/agent/results/page.tsx`)
- **Dynamic content loading** based on active project
- **Auto-refresh mechanism** when searches complete
- **Graceful fallbacks** for no project/no evidence states
- **Real-time document reloading** with 1-second delay for backend synchronization

### Backend Architecture

#### Project API (`backend/app/api/projects.py`)
```python
# CRUD operations
POST   /projects/                    # Create new project
GET    /projects/                    # List all projects
GET    /projects/{id}                # Get single project
PUT    /projects/{id}                # Update project
DELETE /projects/{id}                # Delete project + evidence

# Evidence management
GET    /projects/{id}/documents      # Get project documents
POST   /projects/{id}/update-stats   # Update project statistics
```

#### Search Integration (`backend/app/api/agent.py`)
- **Automatic project association** for all search results
- **Real-time statistics updates** (evidence_count, last_search_date)
- **Project-aware RAG context** for chatbot responses

#### Vectorization Service (`backend/app/services/vectorization.py`)
- **Supabase integration** for document and chunk storage
- **Project-scoped vector search** for RAG functionality
- **Automatic cleanup** when projects are deleted

## Supabase Database Schema

### Core Tables

#### `projects` Table
```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    evidence_count INTEGER DEFAULT 0,
    last_search_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

#### `documents` Table
```sql
-- Existing table with added project association
ALTER TABLE documents ADD COLUMN project_id UUID REFERENCES projects(id);
CREATE INDEX idx_documents_project_id ON documents(project_id);
```

#### `chunks` Table
```sql
-- Existing table with added project association  
ALTER TABLE chunks ADD COLUMN project_id UUID REFERENCES chunks(id);
CREATE INDEX idx_chunks_project_id ON chunks(project_id);
```

### Database Features

#### **pgvector Extension**
- **Vector similarity search** for RAG functionality
- **Project-scoped embeddings** for contextual AI responses
- **Efficient indexing** for large document collections

#### **Row Level Security (RLS)**
```sql
-- Currently permissive for MVP (all users see all projects)
CREATE POLICY "Allow all operations" ON projects FOR ALL USING (true);
```

#### **Automatic Triggers**
```sql
-- Auto-update timestamps
CREATE TRIGGER update_projects_updated_at 
    BEFORE UPDATE ON projects 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
```

## Data Flow

### Search → Storage Flow
1. **User performs search** from Search Hub (`/agent`)
2. **Results retrieved** from Overton API and processed
3. **Documents vectorized** and stored in Supabase with `project_id`
4. **Project statistics updated** (evidence_count, last_search_date)
5. **Results page auto-refreshes** to show new evidence

### RAG Chat Flow
1. **User sends message** with active project context
2. **Vector search scoped** to project documents in Supabase
3. **Relevant chunks retrieved** using pgvector similarity
4. **AI response generated** with project-specific context
5. **Conversation maintains** project awareness throughout

### Project Management Flow
1. **User selects/creates project** in Projects page
2. **Active project stored** in Zustand + localStorage
3. **Sidebar updates** to show active project name
4. **All subsequent operations** use active project context
5. **Evidence accumulates** across multiple search sessions

## Key Features

### **Multi-Search Evidence Collection**
- Projects can accumulate evidence from multiple searches
- Each search adds to the project's document pool
- No evidence is lost when switching between projects

### **Persistent Context**
- Active project persists across browser sessions
- Chatbot maintains project-specific conversation history
- Search results are permanently associated with projects

### **Real-Time Updates**
- Results page automatically refreshes when searches complete
- Project statistics update immediately after evidence storage
- UI reflects current state without manual refresh

### **Graceful Error Handling**
- Authentication failures provide clear user guidance
- Network errors show helpful retry messages
- Missing projects/evidence display appropriate placeholders

### **Performance Optimizations**
- Zustand state management for efficient re-renders
- Local storage for instant active project loading
- Delayed document reloading to ensure backend consistency

## Future Enhancements

### **User Personalization**
- Row Level Security implementation for user-specific projects
- User ID association for project ownership
- Shared project collaboration features

### **Advanced Analytics**
- Project-level evidence quality metrics
- Search effectiveness tracking
- Evidence gap analysis

### **Enhanced Search Context**
- Cross-project evidence discovery
- Project similarity recommendations
- Automated evidence categorization