# Contextual Summarisation (RCS) Enhancement

## Overview

This document describes the paper-qa-inspired Contextual Summarisation (RCS)
enhancement added to the Policy Atlas synthesis module.

## Key Concepts

### Ranking and Contextual Summarisation (RCS)

RCS is a technique from the paper-qa library that improves evidence quality by:

1. **Contextual Summarisation**: Each retrieved chunk is summarised in the context
   of the specific question/theme being addressed, rather than using raw chunk text.

2. **Relevance Scoring**: Each chunk receives a relevance score (0-10) indicating
   how useful it is for answering the question.

3. **Quality Filtering**: Only chunks meeting a relevance threshold are used,
   ensuring the briefing is grounded in genuinely relevant evidence.

## Architecture

### New Workflow Phase

The synthesis workflow now has 6 phases (previously 5):

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

Phase 5: CONTEXTUAL SUMMARISATION (RCS) ← NEW
         ├── apply_rcs_to_theme_evidence
         └── apply_rcs_to_issue_evidence

Phase 6: BRIEFING GENERATION
         └── generate_briefing (tool-augmented with verification)
```

### New Data Structures

#### ScoredContext

```python
class ScoredContext(BaseModel):
    context_id: str          # Unique identifier
    summary: str             # Contextual summary (~100 words)
    relevance_score: int     # 0-10 relevance rating
    question: str            # Question used for scoring
    
    # Source traceability
    chunk_id: str
    document_id: str
    document_title: str
    chunk_text: str          # Original text (truncated)
    
    # Citation
    citation_key: str        # e.g., "pqa-abc123"
    full_citation: str       # Full bibliographic citation
    
    # Theme linkage
    theme_id: Optional[str]
    theme_name: Optional[str]
```

#### ThemeEvidence

```python
class ThemeEvidence(BaseModel):
    theme_id: str
    theme_name: str
    theme_description: str
    theme_question: str
    
    scored_contexts: List[ScoredContext]
    
    # Quality metrics
    total_chunks_retrieved: int
    total_chunks_scored: int
    high_quality_count: int      # score >= 6
    evidence_sufficient: bool    # Has enough high-quality evidence
```

#### RCSConfig

```python
class RCSConfig(BaseModel):
    score_threshold: int = 3           # Minimum score to include
    high_quality_threshold: int = 6    # Score for "high quality"
    max_contexts_per_theme: int = 10   # Max contexts per theme
    max_total_contexts: int = 50       # Max total for briefing
    min_high_quality_per_theme: int = 2  # Required for "sufficient"
    chunks_to_retrieve: int = 15       # RAG retrieval count
    rcs_concurrency: int = 10          # Parallel RCS calls
```

## State Changes

New fields added to `SynthesisState`:

```python
# RCS results
rcs_config: RCSConfig
scored_theme_evidence: List[ThemeEvidence]  # Intervention themes
scored_issue_evidence: List[ThemeEvidence]  # Issue themes
all_scored_contexts: List[ScoredContext]    # All contexts
themes_with_gaps: List[str]                 # Themes lacking evidence
rcs_iterations_run: int                     # Iteration count
```

## Briefing Generation Changes

The briefing generation now:

1. **Detects RCS availability**: Checks if `scored_theme_evidence` is populated
2. **Uses RCS paths when available**: Calls `_generate_background_rcs` and
   `_generate_interventions_table_rcs` instead of legacy functions
3. **Falls back gracefully**: Uses legacy RAG evidence if RCS is not available
4. **Uses contextual summaries**: The RCS summaries are already question-specific,
   providing more targeted evidence for LLM prompts

## Benefits

1. **Higher Quality Evidence**: Only relevance-scored evidence is used
2. **Better Grounding**: Contextual summaries are already tailored to the theme
3. **Reduced Hallucination**: LLM sees pre-filtered, relevant evidence
4. **Transparency**: Each context has an explicit relevance score
5. **Gap Detection**: Identifies themes lacking sufficient evidence

## Cost Implications

The RCS phase adds LLM calls for each retrieved chunk:
- Model: `gpt-4.1-mini` (cost-optimised)
- ~15 chunks per theme × number of themes
- Typical: 50-150 additional RCS calls per synthesis run

## Future Enhancements

Potential additions (currently cancelled but documented):

1. **Query Expansion**: Generate sub-questions for targeted retrieval
2. **Iterative Refinement**: Re-retrieve for themes with evidence gaps
3. **Quality-Based Routing**: Different briefing strategies based on evidence quality

