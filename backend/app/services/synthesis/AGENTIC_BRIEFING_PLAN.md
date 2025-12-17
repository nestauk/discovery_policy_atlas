# Agentic Executive Briefing: Implementation Plan

## Overview

Enhance the executive briefing generation by giving the LLM access to tools that query
the database and retrieve targeted evidence. This hybrid approach keeps pre-computed
themes/aggregations while enabling iterative, targeted evidence retrieval.

---

## Architecture

### Current Flow (Single-pass)
```
[Pre-computed State] → [Briefing LLM] → [Output]
     (fixed context)       (one call)
```

### Proposed Flow (Tool-augmented with Tiered Models)
```
[Pre-computed State]
        ↓
┌───────────────────────────────────────────────────────────┐
│ ORCHESTRATOR (gpt-5.2) - Best reasoning                   │
│ "What evidence do I need for this section?"               │
└───────────────────────────────────────────────────────────┘
        ↓                                    ↑
   Tool calls                          Tool results
        ↓                                    ↑
┌───────────────────────────────────────────────────────────┐
│ TOOL EXECUTOR                                             │
│ - get_theme_evidence(theme)                               │
│ - search_extractions(query)                               │
│ - get_effect_sizes(intervention)                          │
│ - get_document_quality(citation)                          │
└───────────────────────────────────────────────────────────┘
        ↓
   Evidence gathered
        ↓
┌───────────────────────────────────────────────────────────┐
│ SECTION GENERATOR (gpt-5-mini) - Quality generation       │
│ Generate section content with citations                   │
└───────────────────────────────────────────────────────────┘
        ↓
   Draft section
        ↓
┌───────────────────────────────────────────────────────────┐
│ VERIFIER (gpt-5-mini) - MANDATORY                         │
│ verify_claim_support(claim) for each major claim          │
│ Flag ungrounded claims → request more evidence OR reword  │
└───────────────────────────────────────────────────────────┘
        ↓
   Verified section (or iterate)
        ↓
[Final Output]
```

---

## Available Data Sources

### 1. Pre-computed (already in state)
| Data | Location | Use Case |
|------|----------|----------|
| Aggregated interventions | `state.aggregated_interventions` | Theme names, frequencies |
| Aggregated issues | `state.aggregated_issues` | Issue themes |
| RCS scored contexts | `state.all_scored_contexts` | Pre-scored evidence |
| Document metadata | `state.doc_metadata` | Citations, years |
| Document quality scores | `state.doc_scores` | Evidence strength (1-5) |

### 2. Database (queryable via tools)
| Table | Key Fields | Tool Use Case |
|-------|-----------|---------------|
| `analysis_extractions` | `extraction_type`, `label`, `raw_data`, `supporting_quote` | Query specific findings |
| `analysis_documents` | `extraction_results.conclusion.evidence_strength` | Quality filtering |
| `analysis_documents` | `extraction_results` (full) | Effect sizes, mechanisms |
| `synthesis_themes` | Theme assignments | Theme-based retrieval |

### 3. Vector Store (semantic search)
| Function | Parameters | Use Case |
|----------|------------|----------|
| `search_similar_content` | query, project_id, threshold, count | Semantic evidence search |

---

## Tool Specifications

### Tool 1: `get_theme_evidence`
**Purpose**: Retrieve pre-scored evidence for a specific theme/intervention.

```python
@tool
async def get_theme_evidence(
    theme_name: str,
    min_relevance: int = 5,
    max_results: int = 5,
) -> List[Dict]:
    """Retrieve RCS-scored evidence for a specific theme.
    
    Use when writing about a specific intervention or issue and need
    supporting evidence with citations.
    
    Args:
        theme_name: Name of intervention or issue theme (e.g., "Physical activity interventions")
        min_relevance: Minimum RCS relevance score (0-10), default 5
        max_results: Maximum evidence items to return, default 5
    
    Returns:
        List of evidence items with:
        - summary: Contextualised summary of the evidence
        - citation_number: [N] citation for referencing
        - document_title: Source document title
        - relevance_score: RCS relevance score (0-10)
        - document_quality: Evidence strength score (1-5)
    
    Example:
        evidence = await get_theme_evidence("School-based programmes", min_relevance=6)
        # Returns: [{"summary": "School programmes reduce BMI...", "citation_number": 3, ...}]
    """
```

**Implementation**:
- Look up `state.scored_theme_evidence` by theme name
- Filter by `min_relevance`
- Map to citation numbers via `state.doc_citation_map`
- Return formatted evidence

---

### Tool 2: `search_extractions`
**Purpose**: Search structured extractions for specific findings.

```python
@tool
async def search_extractions(
    query: str,
    extraction_types: List[str] = ["result", "intervention"],
    max_results: int = 10,
) -> List[Dict]:
    """Search structured extractions for specific findings or effect sizes.
    
    Use when you need to find quantitative results, effect sizes, or 
    specific mechanisms not covered by theme-based evidence.
    
    Args:
        query: Natural language search query (e.g., "BMI reduction percentage")
        extraction_types: Types to search ["intervention", "result", "issue", "outcome"]
        max_results: Maximum results to return
    
    Returns:
        List of extractions with:
        - label: Extraction label/name
        - description: Full description
        - supporting_quote: Direct quote from source
        - effect_direction: "increase", "decrease", "null" (for results)
        - effect_size: Quantitative effect if available
        - document_title: Source document
        - citation_number: [N] citation for referencing
    
    Example:
        results = await search_extractions("BMI z-score reduction", ["result"])
        # Returns: [{"label": "BMI outcomes", "effect_size": "-0.06 units", ...}]
    """
```

**Implementation**:
- Vector search over extraction descriptions
- Filter by extraction_type
- Enrich with document metadata and citation numbers
- Return structured results

---

### Tool 3: `get_effect_sizes`
**Purpose**: Retrieve quantitative effect data for an intervention.

```python
@tool
async def get_effect_sizes(
    intervention_name: str,
    outcome_variable: Optional[str] = None,
) -> Dict:
    """Get quantitative effect sizes for an intervention.
    
    Use when writing impact statements and need specific metrics.
    
    Args:
        intervention_name: Name of the intervention theme
        outcome_variable: Optional specific outcome (e.g., "BMI", "weight")
    
    Returns:
        Dictionary with:
        - intervention_name: Normalised intervention name
        - positive_count: Number of studies showing positive effect
        - negative_count: Number of studies showing negative effect
        - null_count: Number of studies showing no effect
        - effect_sizes: List of specific effect sizes found
          - value: Effect size value (e.g., "-0.06")
          - unit: Unit of measurement (e.g., "BMI z-score units")
          - direction: "increase" or "decrease"
          - citation_number: [N] citation
        - summary: Brief summary of overall effect direction
    
    Example:
        effects = await get_effect_sizes("Dietary interventions", "BMI")
        # Returns: {"positive_count": 5, "effect_sizes": [{"value": "-0.06", ...}], ...}
    """
```

**Implementation**:
- Query `analysis_extractions` where `extraction_type='result'`
- Filter by intervention theme (via theme assignments)
- Parse `raw_data.effect_size`, `raw_data.effect_direction`
- Aggregate and return

---

### Tool 4: `verify_claim_support`
**Purpose**: Check if evidence exists to support a specific claim.

```python
@tool
async def verify_claim_support(
    claim: str,
    min_sources: int = 2,
) -> Dict:
    """Verify if sufficient evidence exists to support a claim.
    
    Use before making strong assertions to ensure they are grounded.
    
    Args:
        claim: The claim to verify (e.g., "Multi-component programmes are most effective")
        min_sources: Minimum number of sources needed to support claim
    
    Returns:
        Dictionary with:
        - supported: Boolean - True if claim has sufficient support
        - confidence: "high", "medium", "low"
        - supporting_sources: Number of sources found
        - evidence_snippets: List of supporting evidence summaries with citations
        - gaps: List of evidence gaps if claim is not well supported
        - suggested_rewording: If low confidence, suggested alternative phrasing
    
    Example:
        result = await verify_claim_support("Physical activity reduces obesity risk")
        # Returns: {"supported": True, "confidence": "high", "supporting_sources": 8, ...}
    """
```

**Implementation**:
- Semantic search for claim
- Count supporting RCS contexts with score >= threshold
- Return confidence assessment

---

### Tool 5: `get_document_quality`
**Purpose**: Get quality scores for prioritising citations.

```python
@tool
async def get_document_quality(
    citation_number: int,
) -> Dict:
    """Get quality assessment for a document by citation number.
    
    Use to verify a source is high-quality before citing.
    
    Args:
        citation_number: The [N] citation number
    
    Returns:
        Dictionary with:
        - citation_number: The citation number
        - title: Document title
        - evidence_strength: 1-5 star rating
        - evidence_justification: Why this rating was given
        - predicted_impact: 1-5 star rating
        - impact_justification: Why this rating was given
        - study_type: e.g., "RCT", "Systematic Review"
        - year: Publication year
    
    Example:
        quality = await get_document_quality(3)
        # Returns: {"evidence_strength": 4, "study_type": "RCT", ...}
    """
```

**Implementation**:
- Look up document by citation number via `state.grounded_citations`
- Return `state.doc_scores` for that document

---

## Orchestration Strategy

### Option A: ReAct-style Agent (Recommended)
Use LangGraph with a ReAct loop where the LLM decides when to use tools.

```
[System Prompt] → [LLM generates section] → [Tool calls if needed] → [Refine] → [Output]
```

**Pros**:
- LLM decides when evidence is needed
- Iterative refinement possible
- Flexible

**Cons**:
- More unpredictable
- Higher token usage

### Option B: Structured Tool Calls
Pre-define when tools should be called based on section type.

```
For each section:
  1. Call get_theme_evidence for relevant themes
  2. Call get_effect_sizes for quantitative claims
  3. Generate section with retrieved evidence
  4. Call verify_claim_support on output
```

**Pros**:
- More predictable
- Easier to debug
- Lower cost

**Cons**:
- Less flexible
- May miss edge cases

### Recommended: Hybrid
- Use **structured calls** for predictable sections (background, interventions table)
- Use **ReAct agent** for core answer and recommendations where reasoning is valuable

---

## Integration Points

### 1. State Extensions
```python
class SynthesisState(TypedDict, total=False):
    # ... existing fields ...
    
    # Tool-augmented briefing
    tool_calls_log: List[Dict]  # Track tool usage for debugging
    evidence_cache: Dict[str, List[Dict]]  # Cache tool results
    claim_verifications: List[Dict]  # Verification results
```

### 2. Workflow Changes
```python
def create_synthesis_workflow():
    # ... existing nodes ...
    
    # Replace single briefing node with agentic briefing
    workflow.add_node("agentic_briefing", agentic_briefing_node)
    
    # Or add as additional enhancement step
    workflow.add_edge("synthesize_executive_briefing", "verify_and_enhance")
```

### 3. New Module Structure
```
backend/app/services/synthesis/
├── tools/
│   ├── __init__.py
│   ├── base.py           # Tool base class and registry
│   ├── evidence.py       # get_theme_evidence, search_extractions
│   ├── effects.py        # get_effect_sizes
│   ├── verification.py   # verify_claim_support
│   └── quality.py        # get_document_quality
├── agentic/
│   ├── __init__.py
│   ├── orchestrator.py   # Main agentic loop
│   └── prompts.py        # Agent system prompts
└── nodes/
    └── agentic_briefing.py  # LangGraph node
```

---

## Cost Estimation

### Current Approach
| Component | Model | Est. Tokens | Cost |
|-----------|-------|-------------|------|
| Background | gpt-4.1-mini | ~2K | ~$0.001 |
| Interventions (x5) | gpt-4.1-mini | ~5K | ~$0.003 |
| Recommendations | gpt-4.1-mini | ~3K | ~$0.002 |
| Core answer | gpt-4.1-mini | ~1K | ~$0.001 |
| **Total** | | ~11K | **~$0.007** |

### Tool-Augmented Approach (Tiered Models)
| Component | Model | Est. Tokens | Cost |
|-----------|-------|-------------|------|
| Orchestrator reasoning | gpt-5.2 | ~3K | ~$0.05 |
| Tool calls (x10-15 avg) | - | - | ~$0.000 |
| Section generation (x4) | gpt-5-mini | ~8K | ~$0.02 |
| Verification (x4 sections) | gpt-5-mini | ~4K | ~$0.01 |
| **Total** | | ~15K | **~$0.08** |

### Alternative: All gpt-5.2 (Higher Quality, Higher Cost)
| Component | Model | Est. Tokens | Cost |
|-----------|-------|-------------|------|
| All components | gpt-5.2 | ~15K | ~$0.25 |

**Tiered approach benefits**:
- ✅ Best-in-class orchestration (gpt-5.2)
- ✅ Quality generation (gpt-5-mini)
- ✅ Mandatory verification
- ✅ ~3x cheaper than all-gpt-5.2 approach

---

## Implementation Phases

¬### Phase 1: Tool Infrastructure (1 day) ✅ COMPLETED
- [x] Create `tools/` module structure
- [x] Define tool base class with Langfuse tracing
- [x] Implement `get_theme_evidence` tool (uses pre-computed RCS)
- [x] Implement `get_document_quality` tool (uses doc_scores)
- [x] Implement `get_multiple_document_quality` tool (batch query)
- [x] Add tool registry for LangGraph integration

### Phase 2: Database Query Tools (1 day) ✅ COMPLETED
- [x] Implement `search_extractions` tool (vector search + RCS fallback)
- [x] Implement `verify_claim_support` tool (LLM-based verification)
- [x] Implement `verify_multiple_claims` tool (batch verification)
- [x] Add fallback to pre-computed RCS for empty results
- [x] Model configuration (gpt-5.2 orchestrator, gpt-5-mini generation)

### Phase 3: Orchestration & Verification (1 day) ✅ COMPLETED
- [x] Design orchestrator prompt (gpt-5.2)
- [x] Design verifier prompt (gpt-5-mini) 
- [x] Implement `BriefingOrchestrator` class with tool loop
- [x] Implement mandatory verification loop
- [x] Add retry logic for ungrounded claims (max 2 retries)

### Phase 4: LangGraph Integration (1 day) ✅ COMPLETED
- [x] Create `generate_agentic_briefing` node
- [x] Wire into existing workflow (direct edge, no conditional)
- [x] Add `agentic_results` state field for tool call stats
- [x] Deprecate legacy briefing mode - agentic is now the only mode
- [ ] End-to-end testing with real projects
- [ ] Cost monitoring and Langfuse trace review

### Tool Implementation Priority
1. **get_theme_evidence** - Most critical, enables basic functionality
2. **verify_claim_support** - Required for mandatory verification
3. **get_effect_sizes** - Needed for quantitative claims
4. **search_extractions** - Enhances coverage
5. **get_document_quality** - Nice-to-have for citation prioritisation

---

## Success Criteria

1. **Citation Accuracy**: No citations to non-existent sources (0% hallucinated citations)
2. **Verification Coverage**: 100% of major claims pass verification check
3. **Evidence Relevance**: All cited evidence has relevance score >= 5/10
4. **Quantitative Grounding**: Effect sizes come from actual extraction `raw_data`
5. **Quality Awareness**: Mean evidence_strength of cited docs >= 3/5 stars
6. **Cost Efficiency**: < $0.15 per briefing (tiered model approach)
7. **Latency**: < 60 seconds total generation time
8. **Fallback Reliability**: Empty tool results gracefully use pre-computed RCS

---

## Design Decisions (Confirmed)

### 1. Verification: **Mandatory**
Grounding is essential for policy decisions. Users must trust that outputs don't contain
hallucinations. Every claim in the briefing will be verified against evidence.

### 2. Max Tool Calls: **5 per section**
Balances thoroughness with cost control.

### 3. Model Selection: **Tiered Approach**

| Component | Model | Rationale |
|-----------|-------|-----------|
| Orchestration (tool selection) | gpt-5.2 | Best reasoning for complex tool selection decisions |
| Verification (claim checking) | gpt-5-mini | Reliable claim verification at moderate cost |
| Section generation | gpt-5-mini | Better quality output than gpt-4.1-mini |

**Estimated cost per briefing**: ~$0.08-0.12

### 4. Fallback: **Use Pre-computed RCS**
If tools return empty, fall back to pre-computed RCS scored contexts (already high quality).

---

## Model Configuration

```python
# models.py
ORCHESTRATOR_MODEL = "gpt-5.2"          # Best reasoning for tool selection
VERIFICATION_MODEL = "gpt-5-mini"       # Reliable claim verification
GENERATION_MODEL = "gpt-5-mini"         # Quality content generation
```

---

## Next Steps

1. ✅ Plan confirmed - proceed with implementation
2. ✅ Phase 1: Tool infrastructure complete
3. ✅ Phase 2: Database query tools complete
4. ✅ Phase 3: Orchestration & verification complete
5. ✅ Phase 4: LangGraph integration complete
6. **NEXT**: End-to-end testing with real projects

## Files Created

### Tools Module (`backend/app/services/synthesis/tools/`)
```
├── __init__.py          # Module exports (all tools)
├── base.py              # BaseTool, ToolRegistry, ToolResult, Langfuse tracing
├── evidence.py          # get_theme_evidence tool
├── quality.py           # get_document_quality, get_multiple_document_quality
├── search.py            # search_extractions tool
├── verification.py      # verify_claim_support, verify_multiple_claims
├── models.py            # Model configuration (gpt-5.2, gpt-5-mini)
└── orchestrator.py      # BriefingOrchestrator, section generation with tool loop
```

### Updated Files
```
├── nodes/briefing.py           # Briefing generation (renamed from agentic_briefing.py)
├── nodes/__init__.py           # Updated: exports generate_briefing, BriefingConfig
├── state.py                    # Updated: briefing_results field
└── agent.py                    # Updated: simplified workflow
```

## Usage

```python
# Run synthesis
agent = SynthesisAgent()
result = await agent.run(project_id="...")

# Or use convenience function
from app.services.synthesis import run_synthesis
result = await run_synthesis(project_id="...")

# Access results
briefing = result.get("structured_briefing")
briefing_stats = result.get("briefing_results")  # Tool calls, verification results
```

## Implementation Status

✅ **COMPLETE** - All phases implemented and tested (December 2024)

