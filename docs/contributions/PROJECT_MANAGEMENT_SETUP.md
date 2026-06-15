# Project Management Feature Setup

This document outlines the implementation of the project management feature for the Policy Discovery Atlas.

## Overview

The project management feature allows users to:
- Create and manage research projects
- Organize evidence and documents by project
- View project-specific results and documents
- Use RAG chat functionality filtered by active project
- Track project statistics (evidence count, last search date)

## Architecture Changes

### Database Schema
- **projects table**: Stores project metadata (name, description, evidence count, dates)
- **documents table**: Updated to include project_id reference
- **chunks table**: Updated to include project_id reference

### Backend Changes
1. **New API endpoints** (`/backend/app/api/projects.py`):
   - GET `/projects/` - List all projects
   - POST `/projects/` - Create new project
   - GET `/projects/{id}` - Get specific project
   - PUT `/projects/{id}` - Update project
   - DELETE `/projects/{id}` - Delete project and associated data
   - GET `/projects/{id}/documents` - Get project documents
   - POST `/projects/{id}/update-stats` - Update project statistics

2. **Updated existing endpoints**:
   - `/api/agent/chat` - Now accepts project_id for RAG filtering
   - `/api/agent/search` - Now accepts project_id to save results to specific project

3. **Enhanced services**:
   - RAG chat service now filters by project_id
   - Vectorization service saves documents to specified project
   - Project statistics automatically updated after searches

### Frontend Changes
1. **New components**:
   - Project store (`/frontend/lib/projectStore.ts`) - Zustand store for project state
   - Enhanced project API functions (`/frontend/lib/api.ts`)

2. **Updated pages**:
   - **Projects page** (`/frontend/app/agent/projects/page.tsx`):
     - Full CRUD operations for projects
     - Project selection and active project management
     - Real-time loading from Supabase
   
   - **Results page** (`/frontend/app/agent/results/page.tsx`):
     - Displays project-specific documents
     - Handles cases with no project selected or no documents
     - Shows project context in header

3. **Updated navigation**:
   - Sidebar shows "Results" under "Projects"
   - Removed "Saved Evidence" page (redundant)
   - Active project displayed in sidebar

4. **Enhanced chatbot**:
   - RAG responses filtered by active project
   - Project ID sent with all chat requests

## Setup Instructions

### 1. Database Setup
Run the SQL setup script in your Supabase instance:

```sql
-- Execute the contents of backend/supabase_setup.sql in your Supabase SQL editor
```

This will:
- Create the projects table with proper schema
- Add project_id columns to existing tables if needed
- Create indexes for performance
- Insert sample projects for testing
- Set up automatic timestamp updates

### 2. Backend Setup
No additional setup required - the new endpoints are automatically included via the existing main.py imports.

### 3. Frontend Setup
No additional packages required - uses existing dependencies.

## Usage Flow

### Creating a New Project
1. Navigate to Projects page
2. Click "New Project" 
3. Enter project name and description
4. Project is created and becomes the active project

### Selecting an Active Project
1. Go to Projects page
2. Click on any project card
3. Project becomes active and user is taken to Results page
4. Active project name shows in sidebar

### Performing Project-Specific Searches
1. Ensure a project is selected (visible in sidebar)
2. Use the Search Hub to perform searches
3. Results are automatically saved to the active project
4. View results in the Results page

### Using Project-Filtered RAG Chat
1. With an active project selected
2. Open the chatbot (floating button or Assistant tab)
3. Ask questions about evidence
4. RAG responses will only reference documents from the active project

### Viewing Project Evidence
1. Select a project (becomes active)
2. Go to Results page
3. View all documents and evidence for that project
4. Use different tabs to explore the evidence

## Key Features

### Project Management
- **CRUD Operations**: Full create, read, update, delete for projects
- **Active Project State**: Persistent selection across page navigation
- **Statistics Tracking**: Evidence count and last search date auto-updated

### Evidence Organization
- **Project Isolation**: Each project maintains its own evidence collection
- **Automatic Association**: Search results automatically saved to active project
- **Supabase Integration**: All data persisted in cloud database

### Enhanced User Experience
- **Visual Indicators**: Active project highlighted and shown in sidebar
- **Contextual Navigation**: Results page adapts based on project selection
- **Seamless Integration**: Existing search and chat flows enhanced, not replaced

## Technical Implementation Notes

### State Management
- **Frontend**: Zustand store with persistence for project state
- **Backend**: Project ID passed through all relevant API calls
- **Database**: Foreign key relationships maintain data integrity

### Performance Considerations
- **Indexes**: Database indexes on project_id columns for fast queries
- **Lazy Loading**: Documents loaded only when project is selected
- **Efficient Updates**: Project statistics updated in background

### Error Handling
- **Graceful Degradation**: Falls back to default behavior if no project selected
- **User Feedback**: Clear error messages and loading states
- **Data Validation**: Server-side validation for all project operations

## Future Enhancements

1. **User-Specific Projects**: Add user authentication and project ownership
2. **Project Sharing**: Allow multiple users to collaborate on projects
3. **Advanced Analytics**: Project-level insights and visualizations
4. **Bulk Operations**: Import/export project data
5. **Project Templates**: Pre-configured project types for common research areas

## Testing

### Manual Testing Checklist
- [ ] Create new project
- [ ] Update project details
- [ ] Delete project (confirm data cleanup)
- [ ] Select active project
- [ ] Perform search with active project
- [ ] Verify documents appear in Results page
- [ ] Test RAG chat with project context
- [ ] Test navigation between projects
- [ ] Verify project statistics update

### Database Verification
- [ ] Projects table created with correct schema
- [ ] Documents linked to projects via project_id
- [ ] Indexes created for performance
- [ ] Sample data inserted correctly

This implementation provides a solid foundation for project-based research organization while maintaining backward compatibility with existing functionality.