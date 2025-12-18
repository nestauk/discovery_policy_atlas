# Synthesis Module

The synthesis module generates executive briefings from extracted policy evidence. It orchestrates a multi-phase workflow using LangGraph, combining LLM-driven theme discovery with RAG-grounded citation building.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SYNTHESIS WORKFLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Phase 1: LOAD                                                              │
│  ┌─────────────────────┐    ┌─────────────────────────┐                    │
│  │ load_raw_extractions│───▶│ create_canonical_concepts│                    │
│  └─────────────────────┘    └───────────┬─────────────┘                    │
│                                         │                                   │
│  Phase 2: THEME DISCOVERY (parallel)    ▼                                   │
│  ┌──────────────────────────────────────┴──────────────────────────────┐   │
│  │    ┌─────────────────┐  ┌─────────────────────┐  ┌────────────────┐ │   │
│  │    │ process_issue   │  │ process_intervention│  │ process_outcome│ │   │
│  │    │ _themes         │  │ _themes             │  │ _themes        │ │   │
│  │    └────────┬────────┘  └─────────┬───────────┘  └───────┬────────┘ │   │
│  └─────────────┼────────────────────┼───────────────────────┼──────────┘   │
│                └────────────────────┼───────────────────────┘              │
│                                     ▼                                       │
│  Phase 3: AGGREGATION                                                       │
│  ┌──────────────────────────┐    ┌─────────────────────────┐               │
│  │ compute_evidence_coverage│───▶│ build_aggregated_tables │               │
│  └──────────────────────────┘    └───────────┬─────────────┘               │
│                                              │                              │
│  Phase 4: RAG RETRIEVAL                      ▼                              │
│  ┌──────────────────────────────┐    ┌─────────────────────────────┐       │
│  │ retrieve_evidence_for_themes │───▶│ retrieve_evidence_for_issues│       │
│  └──────────────────────────────┘    └───────────┬─────────────────┘       │
│                                                  │                          │
│  Phase 5: BRIEFING                               ▼                          │
│  ┌────────────────────────────────┐                                        │
│  │ synthesize_executive_briefing  │───▶ StructuredBriefing                 │
│  └────────────────────────────────┘                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Structure

```
backend/app/services/synthesis/
├── agent.py           # SynthesisAgent facade + workflow definition
├── state.py           # SynthesisState TypedDict + internal models
├── schemas.py         # Pydantic output schemas (StructuredBriefing, etc.)
├── prompts.py         # LLM prompt templates
├── utils.py           # Helper functions and constants
├── findings.py        # get_findings() for drill-down views
├── logbook.py         # Database caching for synthesis runs
└── nodes/
    ├── data_loading.py    # Phase 1: Load extractions
    ├── theme_discovery.py # Phase 2: Theme clustering
    ├── aggregation.py     # Phase 3: Evidence statistics
    ├── rag_retrieval.py   # Phase 4: Vector search
    └── briefing.py        # Phase 5: Briefing generation
```

---

## Phase 1: Data Loading

**Files:** `nodes/data_loading.py`

### `load_raw_extractions`

Fetches all extractions and document metadata from Supabase for the project.

**Inputs:**
- `project_id` from state

**Outputs:**
- `raw_extractions`: List of normalised extraction dicts (issues, interventions, results)
- `doc_metadata`: `{doc_uuid: {title, year, author_short, url, ...}}`
- `doc_scores`: `{doc_uuid: {evidence_score, impact_score}}` — from `extraction_results.conclusion`
- `extraction_to_doc`: `{extraction_id: doc_uuid}` mapping
- `research_question`: From project title/query

### `create_canonical_concepts`

Transforms raw extractions into `Concept` objects for theme clustering.

**Outputs:**
- `issue_concepts`: Concepts from issue extractions
- `intervention_concepts`: Concepts from intervention extractions
- `outcome_concepts`: Concepts from result extractions

---

## Phase 2: Theme Discovery

**Files:** `nodes/theme_discovery.py`

For each branch (issues, interventions, outcomes), performs:

### 1. Discover Themes (`_discover_themes`)

Uses LLM to cluster concepts into coherent themes.

- **Model:** `gpt-5-mini` (THEME_MODEL)
- **Input:** List of concepts + research question
- **Output:** `List[DiscoveredTheme]` with `theme_name` and `theme_description`

### 2. Critique Themes (`_critique_themes`)

Quality assurance pass — LLM reviews themes for clarity and distinctiveness.

### 3. Map Concepts (`_map_concepts_to_themes`)

Classifies each concept to its best-fit theme using parallel LLM calls.

- **Model:** `gpt-5-nano` (MAPPING_MODEL)
- **Concurrency:** 32 parallel requests
- **Output:** `List[FinalTheme]` with assigned concepts and frequency counts

**State Updates:**
```python
{
    "discovered_issue_themes": [...],
    "final_issue_themes": [...],
    "discovered_intervention_themes": [...],
    "final_intervention_themes": [...],
    "discovered_outcome_themes": [...],
    "final_outcome_themes": [...],
}
```

---

## Phase 3: Aggregation

**Files:** `nodes/aggregation.py`

### `compute_evidence_coverage`

Deterministically computes evidence statistics (no LLM).

**Output:** `EvidenceCoverageSnapshot`
```python
{
    "total_sources": 42,
    "study_types": {"RCT": 5, "Quasi-experimental": 12, ...},
    "source_types": {"Academic": 30, "Government": 8, ...},
    "countries": {"USA": 15, "UK": 10, ...},
    "years": {2020: 5, 2021: 8, ...},
    "overall_strength": "Moderate",  # High | Moderate | Low
    "gaps": ["No meta-analyses found"]
}
```

### `build_aggregated_tables`

Builds structured tables from final themes.

**Outputs:**
- `aggregated_issues`: `List[KeyIssue]`
- `aggregated_interventions`: `List[PolicyIntervention]`
- `aggregated_outcomes`: `List[OutcomeTheme]`
- `extraction_quotes`: `{doc_uuid: [quote, ...]}` for RAG fallback
- `outcome_doc_effects`: `{outcome_name: {doc_id: [effects]}}` for effect tracking
- `theme_to_doc_uuids`: `{theme_name: [doc_uuid, ...]}` for constrained RAG

---

## Phase 4: RAG Retrieval

**Files:** `nodes/rag_retrieval.py`

### Constrained Retrieval

Only retrieves chunks from documents that **contributed to the theme** via extractions. This ensures citations are directly relevant.

```
Theme "School-based interventions"
    ↓
Lookup theme_to_doc_uuids → [doc_1, doc_2, doc_3]
    ↓
Vector search → filter to chunks from [doc_1, doc_2, doc_3]
    ↓
Rerank by quality score
```

### Quality-Weighted Reranking

Documents are scored by their evidence strength and predicted impact:

```python
quality_score = 0.6 × evidence_score_norm + 0.4 × impact_score_norm
final_score = 0.7 × similarity + 0.3 × quality_score
```

Where:
- `evidence_score_norm` = `(stars - 1) / 4` (converts 1-5 to 0-1)
- Documents without scores receive `quality_score = 0`

### `retrieve_evidence_for_themes`

Retrieves chunks for intervention themes.

- **Match count:** 30 candidates
- **Final kept:** Top 8 per theme

### `retrieve_evidence_for_issues`

Retrieves chunks for issue themes (used in background section).

- **Match count:** 20 candidates
- **Final kept:** Top 6 per theme

**Outputs:**
- `theme_evidence`: `{theme_name: List[RetrievedChunk]}`
- `issue_evidence`: `{issue_name: List[RetrievedChunk]}`
- `grounded_citations`: `List[CitationInfo]` with supporting quotes
- `chunk_to_citation`: `{chunk_id: citation_number}`

---

## Phase 5: Briefing Generation

**Files:** `nodes/briefing.py`

### `synthesize_executive_briefing`

Orchestrates the generation of all briefing sections:

| Section | Method | LLM? |
|---------|--------|------|
| Evidence Snapshot | `_build_evidence_snapshot` | No |
| Background | `_generate_background` | Yes |
| Interventions Table | `_generate_interventions_table` | Yes (per row) |
| Core Answer | `_generate_core_answer` | Yes |
| Recommendations | `_generate_recommendations` | Yes |
| Top Citations | `_build_top_citations` | No |
| Follow-up Suggestions | Hardcoded rules | No |

**Output:** `StructuredBriefing`

```python
{
    "core_answer": {
        "query": "What works to reduce youth crime?",
        "answer": "Multi-component school programmes show strongest effects...",
        "directive": "Prioritise early intervention in secondary schools"
    },
    "evidence_snapshot": [...],
    "background_section": {...},
    "interventions_table": [...],
    "recommendations": [...],
    "top_citations": [...],
    "follow_up_suggestions": [...]
}
```

---

## Output Schema

### StructuredBriefing

The final output consumed by the frontend:

```python
class StructuredBriefing(BaseModel):
    core_answer: CoreAnswer
    evidence_snapshot: List[EvidenceSnapshotRow]
    evidence_snapshot_summary: str
    background_section: Optional[BackgroundSection]
    interventions_table: List[InterventionTableRow]
    recommendations: List[RecommendationItem]
    top_citations: List[TopCitationItem]
    follow_up_suggestions: List[str]
```

### InterventionTableRow

```python
class InterventionTableRow(BaseModel):
    intervention_name: str
    citation_numbers: List[int]
    context: str  # "Location: UK, USA | Setting: Schools | Study types: RCT (3)"
    impact_narrative: str  # RAG-grounded 1-2 sentence summary
    outcome_effects: List[OutcomeEffect]
```

### CitationInfo

```python
class CitationInfo(BaseModel):
    citation_key: str  # "[1]"
    citation_number: int
    doc_id: Optional[str]
    analysis_document_id: str
    author_short: Optional[str]
    year: Optional[int]
    title: Optional[str]
    url: Optional[str]
    supporting_quote: Optional[str]  # Grounded from RAG chunk
    chunk_id: Optional[str]
```

---

## Usage

```python
from app.services.synthesis.agent import SynthesisAgent

agent = SynthesisAgent()
final_state = await agent.run(project_id="...")

briefing = final_state.get("structured_briefing")
citations = final_state.get("grounded_citations")
```

---

## Database Tables

The synthesis module reads from and writes to:

| Table | Usage |
|-------|-------|
| `analysis_projects` | Read: project title/query |
| `analysis_documents` | Read: document metadata, extraction_results (scores) |
| `analysis_extractions` | Read: issues, interventions, results |
| `chunks` | Read: vector search via pgvector |
| `synthesis_runs` | Write: cached synthesis results |
| `synthesis_themes` | Write: discovered themes |
| `synthesis_citations` | Write: grounded citations |
| `synthesis_outcome_themes` | Write: outcome themes |

---

## Observability

All LLM calls are traced via Langfuse with tags:
- `component:synthesis`
- `component:synthesis.<step>` (e.g., `synthesis.discover_themes`)
- `branch:<issue|intervention|outcome>`
- `model:<model_name>`

