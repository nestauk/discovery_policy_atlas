# Synthesis Module

The synthesis module transforms document extractions into structured executive briefings. It uses LangGraph to orchestrate a multi-phase workflow that discovers themes, retrieves evidence, scores relevance, and generates verified briefing sections.

## Overview

The synthesis process takes a project's extracted data and generates:
- **Executive Briefing**: A structured document with background, core findings, intervention analysis, and recommendations
- **Theme Analysis**: Discovered themes for issues, interventions, and outcomes
- **Citation Database**: Grounded citations with source traceability

## Architecture

### Technology Stack

| Component | Technology |
|-----------|------------|
| Workflow Orchestration | LangGraph StateGraph |
| LLM Models | GPT-5.2 (orchestration), GPT-5-mini (generation, verification), GPT-4.1-mini (RCS) |
| Vector Search | Supabase pgvector |
| Observability | Langfuse tracing |

### LLM Model Configuration

```python
# tools/models.py
ORCHESTRATOR_MODEL = "gpt-5.2"      # Tool selection reasoning
VERIFICATION_MODEL = "gpt-5-mini"   # Claim verification
GENERATION_MODEL = "gpt-5-mini"     # Section content generation
RCS_MODEL = "gpt-4.1-mini"          # Contextual summarisation (cost-optimised)
```

## Workflow Phases

The synthesis workflow consists of 6 phases:

```
Phase 1: DATA LOADING
         └── load_raw_extractions, create_canonical_concepts

Phase 2: THEME DISCOVERY (parallel)
         ├── process_issue_themes
         ├── process_intervention_themes
         └── process_outcome_themes

Phase 3: AGGREGATION
         ├── compute_evidence_coverage
         └── build_aggregated_tables

Phase 4: RAG RETRIEVAL
         ├── retrieve_evidence_for_themes
         └── retrieve_evidence_for_issues

Phase 5: CONTEXTUAL SUMMARISATION (RCS)
         ├── apply_rcs_to_theme_evidence
         └── apply_rcs_to_issue_evidence

Phase 6: BRIEFING GENERATION
         └── generate_briefing (tool-augmented with verification)
```

### Phase 1: Data Loading

**Nodes**: `load_raw_extractions`, `create_canonical_concepts`

Fetches all extractions for a project and normalises them into canonical concepts. Handles:
- Intervention, issue, outcome, and result extractions
- Document metadata and quality scores
- Citation information

### Phase 2: Theme Discovery

**Nodes**: `process_issue_themes`, `process_intervention_themes`, `process_outcome_themes`

Runs in parallel using LLM-driven clustering:
1. Discovers coherent themes from extracted concepts
2. Critiques and refines theme boundaries
3. Maps individual extractions to themes

### Phase 3: Aggregation

**Nodes**: `compute_evidence_coverage`, `build_aggregated_tables`

Computes evidence coverage statistics and builds aggregated tables for interventions and issues:
- Document counts per theme
- Study types distribution
- Evidence strength summary

### Phase 4: RAG Retrieval

**Nodes**: `retrieve_evidence_for_themes`, `retrieve_evidence_for_issues`

Retrieves supporting evidence chunks from the vector store:
- **Constrained retrieval**: Chunks are retrieved only from documents contributing to each theme
- **Quality-weighted reranking**: Prioritises documents by evidence strength and predicted impact

### Phase 5: Contextual Summarisation (RCS)

**Nodes**: `apply_rcs_to_theme_evidence`, `apply_rcs_to_issue_evidence`

Inspired by the paper-qa library, RCS improves evidence quality by:

1. **Contextual Summarisation**: Each chunk is summarised in the context of a theme-specific question
2. **Relevance Scoring**: Each chunk receives a 0-10 relevance score
3. **Quality Filtering**: Only chunks meeting a relevance threshold are used

**Configuration** (`RCSConfig`):
```python
score_threshold: int = 3           # Minimum score to include
high_quality_threshold: int = 6    # Score for "high quality"
max_contexts_per_theme: int = 10   # Max contexts per theme
max_total_contexts: int = 50       # Max total for briefing
min_high_quality_per_theme: int = 2  # Required for "sufficient"
rcs_concurrency: int = 10          # Parallel RCS calls
```

### Phase 6: Briefing Generation

**Node**: `generate_briefing`

Tool-augmented generation with mandatory verification:

```
┌─────────────────────────────────────────────────────────┐
│ ORCHESTRATOR (gpt-5.2)                                  │
│ "What evidence do I need for this section?"             │
└─────────────────────────────────────────────────────────┘
        ↓                                    ↑
   Tool calls                          Tool results
        ↓                                    ↑
┌─────────────────────────────────────────────────────────┐
│ TOOL EXECUTOR                                           │
│ - get_theme_evidence(theme)                             │
│ - search_extractions(query)                             │
│ - get_document_quality(citation)                        │
│ - verify_claim_support(claim)                           │
└─────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────┐
│ SECTION GENERATOR (gpt-5-mini)                          │
│ Generate section content with inline [N] citations      │
└─────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────┐
│ VERIFIER (gpt-5-mini) - MANDATORY                       │
│ Verify each claim is grounded in cited evidence         │
│ Flag ungrounded claims → retry with corrections         │
└─────────────────────────────────────────────────────────┘
```

#### Briefing Sections

| Section | Purpose |
|---------|---------|
| `background` | Policy context and evidence overview |
| `interventions` | Markdown table of key interventions with citations |
| `core_answer` | Core findings directly addressing the research question |
| `recommendations` | Evidence-based policy recommendations |

#### Available Tools

| Tool | Purpose |
|------|---------|
| `get_theme_evidence` | Retrieve RCS-scored evidence for a theme |
| `search_extractions` | Semantic search across all extractions |
| `get_document_quality` | Get quality scores for citations |
| `verify_claim_support` | Check if a claim is supported by evidence |

## Output Schema

### StructuredBriefing

The main output consumed by the frontend:

```python
class StructuredBriefing(BaseModel):
    core_answer: CoreAnswer                    # Main findings
    background_section: BackgroundSection      # Context paragraphs
    interventions_table: List[InterventionTableRow]  # Top 6 interventions
    recommendations: List[RecommendationItem]  # Policy recommendations
    top_citations: List[TopCitationItem]       # Key sources with reasons
    evidence_snapshot: List[EvidenceSnapshotRow]     # Summary stats
    follow_up_suggestions: List[str]           # Further research
    evidence_snapshot_summary: str             # Brief summary
```

### Citation Selection

Top citations are selected using a multi-signal ranking:

1. **Usage frequency** (0-10 pts): How often cited across sections
2. **Document quality** (0-10 pts): Evidence strength + predicted impact
3. **RCS relevance** (0-10 pts): Average relevance score from contextual summarisation

Each selected citation includes an **LLM-generated reason** explaining its contribution to the briefing.

## Database Tables

| Table | Purpose |
|-------|---------|
| `synthesis_runs` | Run metadata, structured briefing JSON |
| `synthesis_citations` | Citation details with author, year, title, URL |
| `synthesis_themes` | Discovered themes with extraction mappings |

## Usage

```python
from app.services.synthesis import SynthesisAgent, run_synthesis

# Using the convenience function
result = await run_synthesis(project_id="...")
briefing = result.get("structured_briefing")
stats = result.get("briefing_results")

# Or using the agent class
agent = SynthesisAgent()
result = await agent.run(project_id="...", user_id="...")
```

## Configuration

### BriefingConfig

```python
@dataclass
class BriefingConfig:
    max_tool_calls_per_section: int = 5   # Max tools per section
    max_verification_retries: int = 2     # Retry on verification failure
    min_evidence_per_section: int = 3     # Minimum evidence items
```

## Observability

All LLM calls are traced via Langfuse:
- Session ID: Derived from project ID
- Tool execution: Logged with duration and results
- Verification failures: Captured with issue details

---

## Recent Changes (December 2024)

### Agentic Briefing Architecture

Replaced the legacy single-pass briefing with a tool-augmented approach:
- **Tool-based evidence retrieval**: LLM decides what evidence to fetch
- **Mandatory verification**: All claims are verified against cited evidence
- **Tiered models**: GPT-5.2 for orchestration, GPT-5-mini for generation

### Contextual Summarisation (RCS)

Added Phase 5 inspired by paper-qa:
- Each chunk is summarised in context of a theme-specific question
- Relevance scoring (0-10) filters low-quality evidence
- Reduces hallucination by providing pre-filtered evidence

### Citation Improvements

- **Intelligent ranking**: Multi-signal ranking (usage, quality, relevance)
- **LLM-generated reasons**: Each top citation has a contextual explanation
- **Proper formatting**: Fixed `[N]` citation parsing and hyperlinks

### Recommendations Parsing

- Fixed parser to handle markdown bold format (`**1. Title**:`)
- Improved title/description splitting
- Added logging for parse failures

### Frontend Integration

- Core findings section renders citation hyperlinks
- Citation tooltips display source information from `synthesis_citations`
- Intervention table limited to top 6 by evidence strength

---

## Module Structure

```
backend/app/services/synthesis/
├── agent.py                    # LangGraph workflow and SynthesisAgent
├── state.py                    # SynthesisState TypedDict
├── schemas.py                  # Pydantic models (StructuredBriefing, etc.)
├── prompts.py                  # LLM prompt templates
├── logbook.py                  # Database read/write operations
├── findings.py                 # Findings extraction utilities
├── utils.py                    # Shared utilities
│
├── nodes/
│   ├── data_loading.py         # Phase 1: Load extractions
│   ├── theme_discovery.py      # Phase 2: Discover themes
│   ├── aggregation.py          # Phase 3: Evidence aggregation
│   ├── rag_retrieval.py        # Phase 4: RAG evidence retrieval
│   ├── contextual_summarisation.py  # Phase 5: RCS scoring
│   └── briefing.py             # Phase 6: Briefing generation
│
└── tools/
    ├── base.py                 # ToolRegistry and base classes
    ├── models.py               # LLM model configuration
    ├── orchestrator.py         # BriefingOrchestrator
    ├── evidence.py             # get_theme_evidence tool
    ├── search.py               # search_extractions tool
    ├── quality.py              # get_document_quality tool
    └── verification.py         # verify_claim_support tool
```

## See Also

- [RCS_ARCHITECTURE.md](../../backend/app/services/synthesis/RCS_ARCHITECTURE.md) - Detailed RCS documentation
- [AGENTIC_BRIEFING_PLAN.md](../../backend/app/services/synthesis/AGENTIC_BRIEFING_PLAN.md) - Original agentic briefing design

