# Multi-Workflow Extraction System Design Document

## Overview

Extend the current single RCT-optimized extraction workflow to support multiple evidence types through workflow routing based on `evidence_category`. Phase 1 implements RCT and Systematic Review (SR) workflows where in phase 1 all other categories (e.g. Modelling & Simulation, Policy Syntheses & Guidance Documents) should revert to RCT workflow, with Policy workflow planned for Phase 2.

## Workflow Routing

### Evidence Category → Workflow Mapping

| Evidence Category | Workflow | Notes |
|---|---|---|
| Systematic Review and Meta-Analysis | SR | New workflow |
| RCTs and Quasi-Experimental Studies | RCT | Existing (refactored) |
| Observational Research Studies | RCT | Uses RCT workflow |
| Modelling & Simulation | Policy (Phase 2) | Policy variant with `model_type` |
| Policy Syntheses & Guidance Documents | Policy (Phase 2) | - |
| Qualitative & Contextual Evidence | Policy (Phase 2) | - |
| Expert Opinion and Commentary | Policy (Phase 2) | - |
| Unknown / Insufficient information | RCT | Fallback |
| Other (Non-evidence) | Filtered | Already excluded before acquisition |

### Confidence-Based Fallback
- If `evidence_confidence < 0.5` → Route to RCT workflow (fallback)
- Rationale: RCT workflow is most general and produces usable output across evidence types

## Architecture

### Factory Pattern Implementation

```
WorkflowFactory.create(evidence_category, confidence) → BaseExtractionWorkflow
```

**File:** `backend/app/services/analysis/workflows/factory.py` (new)

```python
class WorkflowFactory:
    @staticmethod
    def create(
        evidence_category: str,
        confidence: float,
        model: str = "gpt-5-mini",
        **kwargs
    ) -> BaseExtractionWorkflow:
        # Route based on category + confidence
        pass
```

### Workflow Class Hierarchy

```
BaseExtractionWorkflow (ABC)
├── RCTExtractionWorkflow (refactored from current)
├── SRExtractionWorkflow (new)
└── PolicyExtractionWorkflow (Phase 2)
```

### Directory Structure

```
backend/app/services/analysis/workflows/
├── __init__.py          # Exports: WorkflowFactory, BaseExtractionWorkflow, RCT/SR workflows
├── base.py              # BaseExtractionWorkflow (ABC) with shared logic
├── factory.py           # WorkflowFactory (separate, handles routing)
├── rct.py               # RCTExtractionWorkflow
└── sr.py                # SRExtractionWorkflow
```

**Backward Compatibility:**
- `backend/app/services/analysis/workflow_langchain.py` - Keep existing, delegate to factory for backward compat

## Schema Design

### Base + Extension Pattern

#### Base Schemas (shared fields)

**InterventionItem (extended):**
```python
class InterventionItem(BaseModel):
    idx: int
    name: str
    type: str
    description: str
    study_type: str
    country: Optional[str] = None
    population_intervened: Optional[List[str]] = None
    population_demographics: Optional[str] = None
    sample_size: Optional[str] = None
    comparator: Optional[str] = None  # NEW: Add to base
    intervention_semantic_type: Literal["trial_intervention", "intervention_category", "policy_measure"]  # NEW
    supporting_quote: str
```

**ResultItem (extended):**
```python
class ResultItem(BaseModel):
    intervention_idx: int
    outcome_variable: str
    direction: Literal["increase", "decrease", "null", "mixed_or_unclear"]  # RENAMED from effect_direction
    estimate_level: Literal["study", "pooled", "claim"]  # NEW

    # RCT/SR empirical fields (nullable)
    effect_size_type: Optional[str] = None
    effect_size: Optional[str] = None
    uncertainty: Optional[str] = None
    p_value: Optional[str] = None

    # SR-specific fields (nullable, additions)
    heterogeneity_I2: Optional[str] = None
    tau2: Optional[str] = None
    summary_statistic: Optional[str] = None

    # Policy-specific field (nullable, constrained qualitative scale)
    impact_magnitude: Optional[Literal[
        "substantial", "moderate", "modest", "marginal", "negligible", "unclear"
    ]] = None

    # Common fields
    population_measured: Optional[str] = None
    subgroup_or_dose: Optional[str] = None
    result_text: str
    supporting_quote: str
```

#### SR-Specific Extensions

**SRInterventionItem** (extends InterventionItem conceptually):
```python
# Uses base InterventionItem with:
# - intervention_semantic_type = "intervention_category"
# - comparator populated from review's comparison description
```

#### Document-Level SR Fields

**DocumentExtractionBundle (extended):**
```python
class DocumentExtractionBundle(BaseModel):
    paper_id: str
    workflow_used: str  # NEW: "rct", "sr", "policy"
    routing_reason: str  # NEW: "evidence_category", "low_confidence_fallback", etc.

    issues: List[IssueItem]
    interventions: List[InterventionItem]
    mappings: List[MappingItem]
    results: List[ResultItem]
    conclusion: Optional[ConclusionItem] = None

    # SR document-level fields
    n_studies_included: Optional[int] = None  # NEW: Aggregate only
    sr_completeness_flag: Optional[str] = None  # NEW: "complete", "incomplete_heterogeneity", etc.
```

## Prompt Strategy

### Conditional Additions Pattern

Base prompts remain shared, with workflow-specific guidance appended:

```python
def get_issues_prompt(workflow_type: str) -> ChatPromptTemplate:
    base = ISSUES_PROMPT_BASE
    if workflow_type == "sr":
        return base + SR_ISSUES_ADDITIONS
    elif workflow_type == "policy":
        return base + POLICY_ISSUES_ADDITIONS
    return base  # RCT default
```

### SR-Specific Prompt Additions

**Issues (SR):**
```
Additional guidance for Systematic Reviews:
- Interpret "issues" as REVIEW QUESTIONS or EVIDENCE GAPS
- Capture language like "The aim of this review was..." or "We sought to determine..."
- Focus on the questions the review addresses, not primary study problems
```

**Interventions (SR):**
```
Additional guidance for Systematic Reviews:
- Treat each row as an INTERVENTION CATEGORY (grouping of similar interventions)
- Examples: "CBT-based interventions", "Parent training programs"
- Capture meta-analytic grouping terms used in the review
- n_studies is extracted at document level, not per-intervention
- Use intervention_semantic_type = "intervention_category"
```

**Results (SR):**
```
Additional guidance for Systematic Reviews:
- Focus on AGGREGATED REVIEW-LEVEL RESULTS, not per-study data
- Extract pooled effect sizes with confidence intervals
- Capture heterogeneity measures (I², τ²) when reported
- Use estimate_level = "pooled"
- If heterogeneity measures not reported, extraction still proceeds (flagged as incomplete)
```

### Policy Workflow Prompt Additions (Phase 2)

**Results (Policy):**
```
Extract author-claimed impacts, not measured effects.

direction: Claimed direction of impact vs baseline.
Values: increase | decrease | null | mixed_or_unclear
Use only explicit or clearly implied claims. If unclear, return null.

impact_magnitude: Qualitative assessment of impact size.
Values: substantial | moderate | modest | marginal | negligible | unclear
Map author language to the closest value. If absent or unclear, return null.

Do NOT populate effect_size, uncertainty, or p_value for policy documents.
Use estimate_level = "claim"
```

## Workflow Implementation

### WorkflowState (extended)

```python
class WorkflowState(TypedDict):
    paper_id: str
    full_text: str
    evidence_category: str  # NEW
    evidence_confidence: float  # NEW
    workflow_type: str  # NEW: "rct", "sr", "policy"

    issues: List[IssueItem]
    interventions: List[InterventionItem]
    mappings: List[MappingItem]
    results: List[ResultItem]
    conclusion: Optional[ConclusionItem]

    # SR-specific state
    n_studies_included: Optional[int]  # NEW
    sr_completeness_flag: Optional[str]  # NEW

    error: Optional[str]
```

### Run Method Signature Change

```python
async def run(
    self,
    paper_id: str,
    full_text: str,
    evidence_category: str,  # NEW
    evidence_confidence: float = 1.0,  # NEW
) -> DocumentExtractionBundle:
```

### Error Handling: Retry Then Continue

```python
async def _extract_with_retry(self, stage_fn, state, max_retries=1):
    for attempt in range(max_retries + 1):
        try:
            return await stage_fn(state)
        except Exception as e:
            if attempt < max_retries:
                await asyncio.sleep(1)  # backoff
                continue
            logger.warning(f"Stage {stage_fn.__name__} failed after retry: {e}")
            return self._empty_stage_result(stage_fn)
```

### SR Completeness Flag Logic

```python
def _check_sr_completeness(self, results: List[ResultItem]) -> str:
    has_heterogeneity = any(
        r.heterogeneity_I2 is not None or r.tau2 is not None
        for r in results
    )
    if not has_heterogeneity:
        return "incomplete_heterogeneity"
    return "complete"
```

## Validation

- **Same rules across all workflows** - fuzzy quote matching threshold unchanged
- Quote grounding applies equally to RCT effect sizes and Policy narrative claims

## Model Configuration

- **All workflows use `gpt-5-mini`** for this phase
- Configuration via existing `settings` pattern (no per-workflow model config yet)

## Frontend Integration

### Table Display (Common Denominator)

| Column | Description |
|--------|-------------|
| Intervention | Name/theme |
| Outcome | outcome_variable |
| Direction | Unified direction field |
| Workflow Type | "SR" / "RCT" / "Policy" |
| Evidence Flags | "quantitative", "narrative", "incomplete" |

### Expandable Details Panel

**RCT:** effect_size, CI, p_value, sample_size
**SR:** pooled effect, I², τ², n_studies, summary_statistic
**Policy:** impact_magnitude, supporting quotes

## Migration

- **Leave existing data as-is** - new fields only apply to future extractions
- Existing extractions lack `workflow_used`, `estimate_level` fields (remain null/undefined)

## Files to Modify/Create

### New Directory Structure
```
backend/app/services/analysis/workflows/
├── __init__.py          # Exports factory + workflow classes
├── base.py              # BaseExtractionWorkflow (ABC)
├── factory.py           # WorkflowFactory (separate from base)
├── rct.py               # RCTExtractionWorkflow
├── sr.py                # SRExtractionWorkflow
└── prompts/             # Optional: workflow-specific prompt additions
    ├── __init__.py
    ├── rct_prompts.py
    └── sr_prompts.py
```

### New Files
- `backend/app/services/analysis/workflows/__init__.py` - Package exports
- `backend/app/services/analysis/workflows/base.py` - Abstract base class
- `backend/app/services/analysis/workflows/factory.py` - WorkflowFactory (routing logic)
- `backend/app/services/analysis/workflows/rct.py` - RCT workflow (refactored)
- `backend/app/services/analysis/workflows/sr.py` - SR workflow

### Modified Files
- `backend/app/services/analysis/schemas_langchain.py` - Extended schemas
- `backend/app/services/analysis/prompts.py` - Add SR prompt additions (or use prompts/ subdir)
- `backend/app/services/analysis/workflow_langchain.py` - Delegate to factory (backward compat)
- `backend/app/services/analysis/service.py` - Pass evidence_category to workflow
- `frontend/lib/analysisProjectStore.ts` - Add new fields to types
- `frontend/components/documents/PapersTable.tsx` - Update display

### Test Files
- `backend/test/services/analysis/workflows/test_factory.py` - Router tests
- `backend/test/services/analysis/workflows/test_rct.py` - RCT workflow tests
- `backend/test/services/analysis/workflows/test_sr.py` - SR workflow tests

## Phase 1 Scope

1. Implement `WorkflowFactory` with routing logic
2. Refactor existing workflow into `RCTExtractionWorkflow`
3. Implement `SRExtractionWorkflow` with SR-specific prompts
4. Extend schemas with new fields
5. Update `service.py` to pass evidence_category
6. Add retry logic for stage failures
7. Write tests using annotated sample documents

## Phase 2 Scope (Future)

1. Implement `PolicyExtractionWorkflow`
2. Add modelling mode variant (`model_type` field)
3. Add Policy-specific prompt additions
4. Frontend updates for Policy evidence flags

## Open Questions Resolved

| Question | Decision |
|----------|----------|
| Low confidence handling | RCT fallback workflow |
| Schema design | Base + extension pattern |
| Missing SR statistics | Flag as incomplete, continue extraction |
| Intervention semantics | Add `intervention_semantic_type` field |
| Effect vs impact fields | Unified `direction` field, additive specific fields |
| Validation rules | Same across all workflows |
| Partial failure | Retry once, then continue with empty |
| estimate_level for Policy | "claim" |
| Router location | Factory pattern |
| Category source | Pass explicitly to run() |
