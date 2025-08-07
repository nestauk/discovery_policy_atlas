# Agent interface

The agent interface provides an AI-powered research query refinement workflow.

## Flow Overview

**Query Input** (`/agent`)

   - User enters free text research question

**AI Refinement** (`/agent/chatbot`)

   - AI chatbot helps to refine the research question
   - User can select original query or any refinement

**Results** (`/agent/results`)

   - Displays search results with tabs for summary, evidence, policy, etc.
   - Real-time search integration with Overton semantic search and AI screening
   - Evidence automatically vectorized and stored for RAG chat functionality

## Chatbot architecture

The Policy Research Assistant chatbot is implemented using a clean, component-based architecture that eliminates code duplication while providing consistent functionality across multiple interfaces.

## Overview

The chatbot system consists of three main interfaces:

1. **Full-screen Chat Page** - Dedicated chatbot experience with auto-start functionality
2. **Floating Widget** - Minimizable chat widget that appears on results pages
3. **Assistant Tab** - Embedded chat interface within the results page tabs

All three interfaces share the same core chat logic through a centralized `ChatInterface` component.

## Architecture Overview

```
🏗️ REFACTORED CHATBOT ARCHITECTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                    ┌─────────────────────────────────────┐
                    │     🧠 ChatInterface (Core)        │
                    │        390 lines | Single Source   │
                    │  ┌─────────────────────────────────┐ │
                    │  │ ✅ Auto-start Conversations    │ │
                    │  │ 🔗 LangChain Integration       │ │
                    │  │ 💾 State Management            │ │
                    │  │ 📝 Markdown Rendering          │ │
                    │  │ ❌ Error Handling              │ │
                    │  │ 🔍 Search Button Integration   │ │
                    │  └─────────────────────────────────┘ │
                    └─────────────────────────────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              │                         │                         │
              ▼                         ▼                         ▼
    ┌─────────────────┐       ┌──────────────────┐       ┌─────────────────┐
    │ 📱 Chat Page    │       │ 💬 Float Widget  │       │ 📋 Assistant    │
    │                 │       │                  │       │     Tab         │
    │ 93 lines        │       │ 129 lines        │       │                 │
    │ (-79% reduction)│       │ (-64% reduction) │       │ 5 lines         │
    │                 │       │                  │       │                 │
    │ • 🎨 Background │       │ • ✨ Animations  │       │ • 📊 Embedded   │
    │ • 🧭 Navigation │       │ • ⬇️ Min/Max     │       │ • 📋 Context   │
    │ • ▶️ Search Btn │       │ • 📜 Auto-scroll │       │   Aware        │
    └─────────────────┘       └──────────────────┘       └─────────────────┘

                    ┌─────────────────────────────────────┐
                    │      ⚙️ Backend Integration         │
                    │                                     │
                    │  FastAPI + LangChain Manager        │
                    │  ├─ 🎯 State Detection (refine/chat)│
                    │  ├─ 🔄 Dynamic Query Building       │
                    │  ├─ ✅ Search Readiness Tracking    │
                    │  └─ 💬 Conversation Memory          │
                    └─────────────────────────────────────┘
```

## Component Breakdown

### ChatInterface (Core Component)
**Lines of Code:** 390 lines

The central component that handles all chat functionality:

- **Auto-start Logic** - Automatically initiates conversations with user queries
- **API Integration** - Communicates with backend chat endpoints
- **State Management** - Manages conversation state using Zustand store
- **Markdown Support** - Renders formatted chat messages
- **Error Handling** - Provides user-friendly error messages
- **Search Integration** - Shows "Start Search" button when ready

**Key Props:**
```typescript
interface ChatInterfaceProps {
  autoStartQuery?: string      // Auto-start with this query
  showStartSearchButton?: boolean  // Show search button
  onStartSearch?: () => void   // Search button handler
  enableAutoScroll?: boolean   // Control scrolling behavior
  placeholder?: string         // Input placeholder text
  autoFocus?: boolean         // Focus input on mount
}
```

### Chat Page
**Lines of Code:** 93 lines (79% reduction from 450 lines)

Provides full-screen chat experience:

- **Auto-start Integration** - Uses query parameter to start conversations
- **Page Layout** - Header with navigation and research question badge
- **Background Styling** - Sets global page background color
- **Search Navigation** - Routes to results page when search is ready

### Chat Widget
**Lines of Code:** 129 lines (64% reduction from 354 lines)

Floating chat interface:

- **Animated UI** - Smooth expand/collapse animations using Framer Motion
- **Minimizable** - Can be minimized to a floating button
- **Auto-scroll** - Scrolls to bottom when opened
- **Status Indicators** - Shows evidence search readiness

### Assistant Tab
**Lines of Code:** 5 lines

Simple tab integration:

- **Embedded Experience** - Chat interface within results tabs
- **Context Aware** - Placeholder text references evidence
- **Auto-focus** - Focuses input when tab is selected

## Code Reduction Summary

| Component | Before | After | Reduction |
|-----------|---------|-------|-----------|
| Chat Page | 450 lines | 93 lines | **-357 lines (-79%)** |
| Chat Widget | 354 lines | 129 lines | **-225 lines (-64%)** |
| ChatInterface | 272 lines | 390 lines | **+118 lines (enhanced)** |
| **Total** | **1,076 lines** | **612 lines** | **-464 lines (-43%)** |

## Benefits

### Maintainability
- **Single Source of Truth** - All chat logic exists in one component
- **Consistent Behavior** - All interfaces work identically
- **Easy Updates** - Fix bugs once, all interfaces benefit

### Performance
- **Smaller Bundle** - Less duplicate code shipped to users
- **Better Tree Shaking** - Unused code can be eliminated more effectively

### Developer Experience
- **Cleaner Code** - Less duplication makes codebase easier to understand
- **Unified Testing** - Test core functionality in one place
- **Flexible Integration** - Easy to add new chat interfaces

## Backend Integration

The chatbot integrates with a LangChain-based conversation manager that:

1. **Detects Conversation State** - Determines if user is in "refine" or "chat" mode
2. **Builds Search Queries** - Dynamically constructs search queries from conversation
3. **Tracks Progress** - Monitors outcomes and scope definition
4. **Manages Context** - Maintains conversation history and state

This architecture provides a robust, maintainable foundation for the Policy Research Assistant's conversational capabilities.

## 🤖 RAG-Enhanced Evidence Chat

### Overview

The chatbot now features **Retrieval-Augmented Generation (RAG)** capabilities that allow users to ask questions about collected research evidence and receive properly cited responses with links to original sources.

### State-Based Chat Modes

The chatbot operates in two distinct modes:

#### **1. Refine Mode** (Default)
- **Purpose**: Help users develop and refine their research questions
- **Features**: 
  - Query clarification and scoping
  - Outcome and demographic definition
  - Search readiness assessment
- **Backend**: Uses LangChain conversation manager for query refinement

#### **2. Evidence Chat Mode** (Post-Search)
- **Purpose**: Answer questions about collected evidence
- **Features**:
  - RAG over vectorized document summaries
  - Proper academic citations with clickable links
  - Evidence-grounded responses only
- **Backend**: Uses pgvector similarity search + OpenAI for synthesis

### Automatic State Transition

```
User refines question → Search triggered → Evidence collected → Auto-switch to Evidence Mode
```

The chatbot automatically transitions from "refine" to "chat" mode when:
1. Search results are found and processed
2. Documents are vectorized in Supabase
3. Evidence is available for RAG queries

### RAG Technical Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    🔍 RAG EVIDENCE PIPELINE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 🔎 SEARCH         │  2. 🤖 AI SCREENING  │  3. 📚 VECTORIZATION │
│     ┌─────────────┐   │     ┌─────────────┐  │     ┌─────────────┐ │
│     │ Overton API │   │     │ OpenAI GPT-4│  │     │ OpenAI      │ │
│     │ Top 20 docs │   │     │ Relevance   │  │     │ Embeddings  │ │
│     │ Semantic    │   │     │ Assessment  │  │     │ text-ada-002│ │
│     │ Search      │   │     │ Confidence  │  │     │ 1536 dims   │ │
│     └─────────────┘   │     └─────────────┘  │     └─────────────┘ │
│                       │                      │                     │
│  4. 💾 STORAGE        │  5. 🔍 SIMILARITY    │  6. 💬 GENERATION   │
│     ┌─────────────┐   │     ┌─────────────┐  │     ┌─────────────┐ │
│     │ Supabase    │   │     │ pgvector    │  │     │ OpenAI GPT-4│ │
│     │ documents   │   │     │ Cosine      │  │     │ Cited       │ │
│     │ chunks      │   │     │ Similarity  │  │     │ Responses   │ │
│     │ pgvector    │   │     │ Top 5 match │  │     │ + Links     │ │
│     └─────────────┘   │     └─────────────┘  │     └─────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Evidence Chat Features

#### **Cited Responses**
- AI responses include numbered document references: `[Document 1]`, `[Document 2]`
- Automatic "References" section with full citations
- Clickable links to original sources (DOI or Overton URLs)

#### **Academic Citation Format**
```markdown
## 📚 References

**Document 1:** Youth Vaping Policy Effectiveness (2023) [United States]
*Authors: Johnson, A., Smith, B., Chen, C.*
🔗 [View Paper (DOI)](https://doi.org/10.1234/example)

**Document 2:** Regulatory Approaches to E-cigarettes (2023) [United Kingdom] 
*Authors: Williams, D., Thompson, E.*
🔗 [View Document (Overton)](https://overton.io/document/12345)
```

#### **Visual State Indicators**
- **Green "Evidence Mode" banner** when RAG is active
- **Table/Card view toggle** for evidence browsing
- **Search completion badges** showing results status

### Database Schema

The RAG system uses two main tables in Supabase:

#### **documents**
```sql
- id (UUID, primary key)
- project_id (text) 
- external_id (text, from Overton/OpenAlex)
- title, authors, abstract, content
- doi, overton_url (for linking)
- confidence, relevance_reason (from AI screening)
- metadata (JSONB for extensibility)
```

#### **chunks** 
```sql
- id (UUID, primary key)
- document_id (UUID, foreign key)
- content (text, document summary)
- embedding (vector(1536), OpenAI embeddings)
- chunk_type ('summary' for now, extensible)
- project_id (text, for scoping)
```

### User Experience Flow

1. **Research Development**: User refines question with AI guidance
2. **Evidence Collection**: Search triggers, results processed and vectorized
3. **Evidence Chat**: Green banner appears, user asks questions about findings
4. **Cited Answers**: AI responds with document references and clickable links
5. **Source Verification**: User clicks through to original policy documents

This RAG implementation transforms the chatbot from a query refinement tool into a comprehensive research assistant that can engage in evidence-based policy discussions.