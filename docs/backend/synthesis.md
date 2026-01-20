# Synthesis Module

The synthesis module transforms screened document extractions into a structured executive briefing.
It uses a LangGraph workflow to discover themes, retrieve and score evidence, and generate verified briefing sections.

## Overview

Given an `analysis_project`, the synthesis process produces:

- **Executive briefing (structured)**: A `StructuredBriefing` object used by the frontend and PDF renderer.
- **Theme analysis**: Discovered themes for issues, interventions, and outcomes.
- **Citation database**: Grounded citations with source traceability (hoverable `[N]` citations).
- **Evidence coverage snapshot**: Deterministic stats for the “Evidence Base” card.

## Architecture

### Technology stack

| Component | Technology |
|-----------|------------|
| Workflow orchestration | LangGraph StateGraph |
| LLM models | GPT-5.2 (orchestration), GPT-5-mini (generation + verification), GPT-4.1-mini (RCS) |
| Vector search | Supabase pgvector |
| Observability | Langfuse tracing |

### LLM model configuration

```python
# tools/models.py
ORCHESTRATOR_MODEL = "gpt-5.2"      # Tool selection reasoning
VERIFICATION_MODEL = "gpt-5-mini"   # Claim verification
GENERATION_MODEL = "gpt-5-mini"     # Section content generation
RCS_MODEL = "gpt-4.1-mini"          # Contextual summarisation (cost-optimised)
```

## Workflow phases

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
         ├── retrieve_evidence_for_issues
         └── retrieve_evidence_for_outcomes

Phase 5: CONTEXTUAL SUMMARISATION (RCS)
         ├── apply_rcs_to_theme_evidence
         ├── apply_rcs_to_issue_evidence
         └── apply_rcs_to_outcome_evidence

Phase 6: BRIEFING GENERATION
         └── generate_briefing (tool-augmented with verification)
```

### Phase 1: Data loading

**Nodes**: `load_raw_extractions`, `create_canonical_concepts`

Loads:

- **Extractions**: Intervention/issue/outcome/result extractions.
- **Document metadata**: Includes screening status and precomputed summaries.
  - `analysis_documents.is_relevant` (screening outcome)
  - `analysis_documents.top_line` (one-sentence takeaway used in “Key Sources”)
- **User focus** (when available): `analysis_projects.search_query.population` and `analysis_projects.search_query.outcome` are carried into state and used to tailor prompts and ranking.

### Phase 2: Theme discovery

**Nodes**: `process_issue_themes`, `process_intervention_themes`, `process_outcome_themes`

LLM-driven clustering:

1. Discovers coherent themes from extracted concepts
2. Critiques and refines theme boundaries
3. Maps individual extractions to themes

### Phase 3: Aggregation

**Nodes**: `compute_evidence_coverage`, `build_aggregated_tables`

Deterministic aggregation to support both retrieval and UI:

- Builds aggregated intervention/issue/outcome summaries from theme mappings.
- Computes an `EvidenceCoverageSnapshot`, including **screened vs synthesised counts**:
  - **Screened**: total `analysis_documents` for the project.
  - **Synthesised**: documents with `is_relevant = true` (passed screening).

> Note on field semantics: `evidence_coverage.total_sources` is kept aligned with the overall evidence-base size (screened) for backwards compatibility, while `total_synthesised` is used by the UI/PDF to show “synthesised”.

### Phase 4: RAG retrieval

**Nodes**: `retrieve_evidence_for_themes`, `retrieve_evidence_for_issues`, `retrieve_evidence_for_outcomes`

Retrieves supporting evidence chunks from the vector store:

- **Constrained retrieval**: chunks are retrieved only from documents contributing to each theme.
- **Quality-weighted reranking**: prioritises documents by evidence strength and predicted impact.

### Phase 5: Contextual summarisation (RCS)

**Nodes**: `apply_rcs_to_theme_evidence`, `apply_rcs_to_issue_evidence`, `apply_rcs_to_outcome_evidence`

RCS improves evidence quality by:

1. **Contextual summarisation**: each chunk is summarised in the context of a theme-specific question
2. **Relevance scoring**: each chunk receives a 0–10 relevance score
3. **Quality filtering**: only chunks meeting a relevance threshold are used

**Configuration** (`RCSConfig`):

```python
score_threshold: int = 3             # Minimum score to include
high_quality_threshold: int = 6      # Score for "high quality"
max_contexts_per_theme: int = 10     # Max contexts per theme
max_total_contexts: int = 50         # Max total for briefing
min_high_quality_per_theme: int = 2  # Required for "sufficient"
rcs_concurrency: int = 10            # Parallel RCS calls
```

### Phase 6: Briefing generation

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
│ - get_theme_evidence(theme_name)                        │
│ - get_top_studies(intervention_name)                    │
│ - get_intervention_outcomes(intervention_name)          │
│ - get_intervention_details(intervention_name)           │
│ - get_citation_context(citation_number)                 │
│ - search_extractions(query)                             │
│ - get_document_quality(citation_number)                 │
│ - get_multiple_document_quality(citation_numbers)       │
│ - verify_claim_support(claim, cited_numbers?)           │
│ - verify_multiple_claims(claims=[...])                  │
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

#### Tool-call budgets

- Default per section: `MAX_TOOL_CALLS_PER_SECTION = 10`.
- Interventions table evidence gathering: budget increases up to **25** to support **per-row evidence retrieval**.

#### Briefing sections

| Section | Purpose |
|---------|---------|
| `background` | Policy context and evidence overview |
| `interventions` | Markdown table of key interventions, including “Key Study” examples |
| `core_answer` | Core findings directly addressing the research question |
| `recommendations` | Evidence-based policy recommendations with an explicit implementation option |

## Output schema

### StructuredBriefing

The main output consumed by the frontend:

```python
class StructuredBriefing(BaseModel):
    core_answer: CoreAnswer
    evidence_snapshot: List[EvidenceSnapshotRow]
    evidence_snapshot_summary: str

    background_section: Optional[BackgroundSection]

    # Table rows include a "Key Study" (1–2 top studies ranked by evidence + impact)
    interventions_table: List[InterventionTableRow]

    # Recommendations include an explicit implementation option for rendering
    recommendations: List[RecommendationItem]

    # "Key Sources" items use analysis_documents.top_line (not LLM-generated)
    top_citations: List[TopCitationItem]

    synthesis_sections: List[SynthesisSection]
    follow_up_suggestions: List[str]
```

### Citation selection

Top citations are selected using a multi-signal ranking:

1. **Usage frequency** (0–10 points): how often cited across briefing sections
2. **Document quality** (0–10 points): evidence strength + predicted impact
3. **RCS relevance** (0–10 points): average relevance score across RCS contexts

Each selected “Key Source” displays a short, precomputed summary:

- `TopCitationItem.reason` is populated from `analysis_documents.top_line`.

## Database tables

| Table | Purpose |
|-------|---------|
| `analysis_documents` | Screened documents (includes `is_relevant`, `top_line`, extraction results) |
| `analysis_extractions` | Raw extractions (issues/interventions/outcomes/results) |
| `synthesis_runs` | Run metadata, cached `structured_briefing_data`, cached `evidence_coverage` |
| `synthesis_citations` | Citation details with author/year/title/URL/supporting quote |
| `synthesis_themes` | Discovered themes and their document mappings |

## Configuration

### Evidence gathering + verification

- **Tool-call budgets** are controlled in `backend/app/services/synthesis/tools/orchestrator.py`:
  - `MAX_TOOL_CALLS_PER_SECTION = 10`
  - Interventions table: up to 25 tool calls for per-row evidence

- **RCS thresholds** are controlled via `RCSConfig`.

## Observability

All LLM calls are traced via Langfuse:

- Session ID: derived from project ID
- Tool execution: logged with duration and results
- Verification failures: captured with suggested fixes

---

## Recent changes (January 2026)

- **Evidence Base card**: shows both **screened** and **synthesised** counts.
- **Key Sources**: removed LLM “why selected” generation; now uses `analysis_documents.top_line`.
- **Interventions table**: adds a “Key Study” column and performs per-row evidence gathering via tools.
- **Recommendations**: structured output includes a clearer `implementation_option` field for rendering.
- **Tool budgets**: increased default per-section tool budget and expanded interventions-section budget.

## Module structure

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
│   ├── data_loading.py         # Phase 1: Load extractions + doc metadata
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
    ├── evidence.py             # Evidence tools (theme evidence, intervention outcomes/details/top studies)
    ├── search.py               # search_extractions tool
    ├── quality.py              # get_document_quality + batch quality
    └── verification.py         # verify_claim_support + verify_multiple_claims
```

## See also

- This document is the canonical overview of the current synthesis pipeline.
