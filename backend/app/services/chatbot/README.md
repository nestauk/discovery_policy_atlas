# V2 Chatbot Service

This module provides a simple RAG (Retrieval-Augmented Generation) chatbot service for the v2 analysis projects.

## Features

- **Simple RAG Implementation**: Uses the existing chunks table for semantic search
- **Neighboring Chunks**: Fetches adjacent chunks for better context
- **Document References**: Provides clear citations with links to source documents
- **Stateless Design**: No conversation state storage (uses message history for context)
- **Project-Focused**: Works specifically with v2 analysis projects

## Architecture

### Backend Components

1. **`chat_service.py`**: Main RAG chatbot service
   - Searches relevant chunks using vector similarity
   - Fetches neighboring chunks for context
   - Enriches with document metadata
   - Generates responses using OpenAI

2. **`models.py`**: Pydantic models for requests/responses
   - `ChatRequest`: User message + recent conversation history
   - `ChatResponse`: AI response + document references
   - `DocumentReference`: Citation information

3. **API Endpoint**: `/api/analysis-projects/{project_id}/chat`
   - POST endpoint for sending chat messages
   - Integrated into existing projects_v2.py router

### Frontend Components

1. **`V2ChatInterface.tsx`**: Main chat interface component
   - Used in both the assistant tab and floating widget
   - Shows document references with links
   - Handles conversation history

2. **`V2ChatbotWidget.tsx`**: Floating chat widget
   - Appears on results page when project is selected
   - Collapsible interface

3. **`v2ChatStore.ts`**: Zustand store for chat state
   - Simplified store (no persistence)
   - Manages messages, loading state, errors

## Key Design Decisions

### No Conversation State
- **Pros**: Simpler, stateless, no database storage needed
- **Cons**: No conversation memory between requests
- **Solution**: Pass recent message history in each request

### Neighboring Chunks
- Fetches chunks with `chunk_index ± 1` from the same document
- Provides better context for understanding
- Uses the existing chunks table structure

### Document References
- Clear citations with document titles, authors, DOI/URLs
- No relevance scores shown (as requested)
- Direct links to source documents

### Both Widget and Tab
- Assistant tab in results page for focused chat
- Floating widget for quick access
- Same underlying component (V2ChatInterface)

## Usage

The chatbot automatically appears when:
1. A v2 analysis project is selected
2. The project has evidence documents with chunks

Users can:
- Ask questions about evidence in the project
- Get responses with clear document references
- Access via both the assistant tab and floating widget

## API Example

```typescript
// Request
POST /api/analysis-projects/{project_id}/chat
{
  "message": "What interventions were most effective?",
  "recent_messages": [
    {
      "role": "user",
      "content": "Tell me about the evidence",
      "timestamp": "2024-01-15T10:00:00Z"
    }
  ]
}

// Response
{
  "message": "Based on the evidence, several interventions showed effectiveness...",
  "references": [
    {
      "document_id": "doc-123",
      "title": "Policy Intervention Study",
      "authors": ["Smith, J.", "Jones, A."],
      "url": "https://doi.org/10.1234/example",
      "chunk_type": "summary"
    }
  ]
}
```