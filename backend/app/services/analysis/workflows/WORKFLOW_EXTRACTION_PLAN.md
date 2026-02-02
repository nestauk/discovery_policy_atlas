# Multi-Workflow Extraction System

## Overview

The extraction system supports multiple evidence types through workflow routing based on `evidence_category`. Phase 1 implements RCT and Systematic Review (SR) workflows. Phase 2 adds PolicyExtractionWorkflow for claim-level extraction from policy documents. Modelling & Simulation workflow is planned for Phase 3.

## Workflow Routing

### Evidence Category → Workflow Mapping

| Evidence Category | Workflow | Notes |
|---|---|---|
| Systematic Review and Meta-Analysis | SR | Specialized for meta-analytic data |
| RCTs and Quasi-Experimental Studies | RCT | Default workflow |
| Observational Research Studies | RCT | Uses RCT workflow |
| Modelling & Simulation | RCT (Phase 3) | Own workflow planned |
| Policy Syntheses & Guidance Documents | Policy | Claim-level extraction |
| Qualitative & Contextual Evidence | Policy | Claim-level extraction |
| Expert Opinion and Commentary | Policy | Claim-level extraction |
| Unknown / Insufficient information | RCT | Fallback |
| Other (Non-evidence) | Filtered | Excluded before extraction |

### Confidence-Based Fallback

- **RCT/SR:** If `evidence_confidence < 0.5` → Route to RCT workflow
- **Policy:** No confidence fallback. Policy categories always use Policy workflow regardless of confidence (policy documents are structurally different enough that RCT extraction would produce poor results)

## Architecture

### Function-Based Routing

```python
from app.services.analysis.workflows import create_workflow

workflow = create_workflow(
    evidence_category="Policy Syntheses & Guidance Documents",
    confidence=0.9,
    model="gpt-4o-mini",
    policy_project_id="project_123",
    policy_user_id="user_456",
)
result = await workflow.run(paper_id, full_text, evidence_category, confidence)
```

**File:** `backend/app/services/analysis/workflows/routing.py`

```python
# Evidence categories that use Policy workflow
POLICY_CATEGORIES = {
    "Policy Syntheses & Guidance Documents",
    "Qualitative & Contextual Evidence",
    "Expert Opinion and Commentary",
}

def create_workflow(
    evidence_category: str,
    confidence: float = 1.0,
    model: str = "gpt-4o-mini",
    policy_project_id: Optional[str] = None,
    policy_user_id: Optional[str] = None,
) -> BaseExtractionWorkflow:
    """Create the appropriate workflow based on evidence category and confidence."""
    normalized = _normalize_category(evidence_category)

    if normalized in FILTERED_CATEGORIES:
        raise ValueError(f"Category '{evidence_category}' should be filtered")

    # Policy workflow - no confidence fallback
    if normalized in POLICY_CATEGORIES:
        return PolicyExtractionWorkflow(...)

    # SR workflow with confidence fallback
    if normalized in SR_CATEGORIES and confidence >= CONFIDENCE_THRESHOLD:
        return SRExtractionWorkflow(...)

    # Default to RCT
    return RCTExtractionWorkflow(...)
```

### Workflow Class Hierarchy

```
BaseExtractionWorkflow (ABC)
├── RCTExtractionWorkflow
├── SRExtractionWorkflow
├── PolicyExtractionWorkflow (Phase 2)
└── ModellingExtractionWorkflow (Phase 3)
```

### Directory Structure

```
backend/app/services/analysis/workflows/
├── __init__.py     # Exports: create_workflow, all workflow classes
├── base.py         # BaseExtractionWorkflow (ABC)
├── routing.py      # create_workflow() function
├── rct.py          # RCTExtractionWorkflow
├── sr.py           # SRExtractionWorkflow
└── policy.py       # PolicyExtractionWorkflow (Phase 2)
```

---

## Phase 2: Policy Workflow

### Design Principles

1. **Claim-style only**: Policy workflow produces claim-level extractions, not empirical results
2. **No mixed modes**: A single document produces EITHER empirical OR claim results, never both
3. **Grounded extraction**: All claims must have supporting quotes
4. **Atomic claims**: Compound claims are split into separate ResultItems

### Schema Changes

#### InterventionItem Extensions

Add two nullable fields for Policy interventions:

```python
class InterventionItem(BaseModel):
    # ... existing fields ...

    # Policy-specific fields (Phase 2)
    responsible_actor: Optional[str] = None  # e.g., "national government", "local authorities"
    implementation_level: Optional[
        Literal["international", "national", "regional", "local", "organizational", "individual"]
    ] = None
```

#### ResultItem Extensions

Add claim-level fields for Policy workflow:

```python
class ResultItem(BaseModel):
    intervention_idx: int
    outcome_variable: str  # For Policy: what the claim is about

    # Direction fields (mutually exclusive usage)
    direction: Literal["increase", "decrease", "null", "mixed_or_unclear"]  # RCT/SR
    impact_direction: Optional[
        Literal["positive", "negative", "mixed", "unclear"]
    ] = None  # Policy

    estimate_level: Optional[Literal["study", "pooled", "claim"]] = None

    # RCT/SR empirical fields
    effect_size_type: Optional[str] = None
    effect_size: Optional[str] = None
    uncertainty: Optional[str] = None
    p_value: Optional[str] = None
    heterogeneity_I2: Optional[str] = None
    tau2: Optional[str] = None
    summary_statistic: Optional[str] = None
    n_studies: Optional[int] = None

    # SR stratum fields
    stratum_type: Optional[str] = None
    stratum_value: Optional[str] = None
    is_primary_stratum: Optional[bool] = None

    # Policy-specific fields (Phase 2)
    claim_text: Optional[str] = None  # One-sentence LLM summary preserving meaning
    claim_type: Optional[
        Literal["recommendation", "assessment", "prediction", "warning"]
    ] = None
    evidence_basis: Optional[
        Literal["empirical", "synthesis", "expert_judgement", "precedent", "unspecified"]
    ] = None
    uncertainty_language: Optional[
        Literal["confident", "mixed", "cautious"]
    ] = None
    population_targeted: Optional[str] = None  # Only if explicitly stated

    # Shared fields
    impact_magnitude: Optional[
        Literal["substantial", "moderate", "modest", "marginal", "negligible", "unclear"]
    ] = None
    population_measured: Optional[str] = None
    subgroup_or_dose: Optional[str] = None
    result_text: str
    supporting_quote: str
```

#### Schema Validation

Add Pydantic validator enforcing mutual exclusivity:

```python
from pydantic import model_validator

class ResultItem(BaseModel):
    # ... fields ...

    @model_validator(mode='after')
    def validate_workflow_fields(self) -> 'ResultItem':
        """Ensure empirical and claim fields are mutually exclusive."""
        empirical_fields = [
            self.effect_size, self.effect_size_type, self.p_value,
            self.uncertainty, self.heterogeneity_I2, self.tau2,
            self.summary_statistic, self.n_studies
        ]
        claim_fields = [
            self.claim_text, self.claim_type, self.evidence_basis,
            self.uncertainty_language
        ]

        has_empirical = any(f is not None for f in empirical_fields)
        has_claim = any(f is not None for f in claim_fields)

        if has_empirical and has_claim:
            raise ValueError(
                "ResultItem cannot have both empirical fields (effect_size, p_value, etc.) "
                "and claim fields (claim_text, claim_type, etc.). Use one mode only."
            )
        return self
```

### Policy Field Semantics

#### claim_text
- One-sentence LLM summary preserving original meaning and modality
- Do not paraphrase into stronger or weaker language
- If multiple distinct claims exist, split into separate ResultItems

#### claim_type
| Value | Description |
|-------|-------------|
| `recommendation` | Proposes an action or policy |
| `assessment` | Evaluates a situation or intervention |
| `prediction` | States an expected future effect |
| `warning` | Highlights risks or potential harms |

Choose exactly one. If a statement contains both assessment AND recommendation, split into two ResultItems.

#### evidence_basis
| Value | Description |
|-------|-------------|
| `empirical` | Cites primary studies or data |
| `synthesis` | Cites reviews or bodies of evidence |
| `expert_judgement` | Based on professional opinion, panels, or author reasoning |
| `precedent` | Justified by past policy or implementation |
| `unspecified` | No explicit justification |

This field classifies the TYPE of evidence, not specific citations. Not ordered by strength.

#### uncertainty_language
| Value | Description | Examples |
|-------|-------------|----------|
| `confident` | Assertive language, no caveats | "will reduce", "evidence clearly shows", "must implement" |
| `mixed` | Both hedging and assertive language | "likely to improve, though...", "evidence suggests but..." |
| `cautious` | Hedging, caveats, conditionality | "may help", "could potentially", "under certain conditions" |

Based on document wording, not personal judgement.

#### impact_direction
| Value | Description |
|-------|-------------|
| `positive` | Beneficial/improving direction |
| `negative` | Harmful/worsening direction |
| `mixed` | Both positive and negative aspects |
| `unclear` | Direction not stated or ambiguous |

Do not infer direction if not explicit in the document.

#### impact_magnitude
Already defined. Populate only when magnitude language is present in the document. LLM may infer from context (e.g., "50% reduction" → "substantial").

#### population_targeted
Extract only if explicitly stated. Examples: "low-income households", "children under 5", "urban local authorities". Do not infer.

#### supporting_quote
Mandatory for all Policy ResultItems. Prefer the sentence that best grounds:
1. The claim itself
2. The evidence basis
3. The uncertainty language

### Policy Workflow Stages

Same 5-stage structure as RCT/SR:

| Stage | Name | Purpose |
|-------|------|---------|
| A | Issues Extraction | Extract 1-3 key problem statements that motivated the policy |
| B | Interventions Extraction | Identify concrete policies, measures, or actions proposed |
| C | Mapping Extraction | Link each issue to relevant interventions with rationale |
| D | Results Extraction | Extract claims per intervention (per-intervention loop) |
| E | Conclusions Extraction | Extract overall document stance and key takeaways |

#### Stage A: Policy Issues

Extract policy problems/challenges the document addresses. Focus on:
- What problem or gap is being addressed?
- What policy failure or need is identified?
- What objective is the document trying to achieve?

#### Stage B: Policy Interventions

Extract concrete policy measures, recommendations, or actions. Key guidance:
- Each target actor's recommendations = separate InterventionItem
- Set `intervention_semantic_type = "policy_measure"`
- Include `responsible_actor` and `implementation_level` when stated
- Group thematically related measures under one intervention

#### Stage D: Policy Results (Claims)

Extract claims per intervention. Key guidance:
- One claim per ResultItem (split compound claims)
- Set `estimate_level = "claim"`
- Use `impact_direction` instead of `direction`
- Do not populate empirical fields (effect_size, p_value, etc.)
- Deduplicate: if same claim appears in summary AND body, extract once (prefer body text)

### Policy Prompts

Located in `prompts.py`:
- `POLICY_ISSUES_PROMPT` - Extract policy problems/challenges
- `POLICY_INTERVENTIONS_PROMPT` - Extract policy measures with actor/level
- `POLICY_RESULTS_PROMPT` - Extract claim-level results

Policy workflow uses shared `MAPPING_PROMPT` and `CONCLUSIONS_PROMPT`.

#### Prompt Design

- Generic "policy document" framing (not subtype-specific)
- Include examples from different document types (guidance, briefs, white papers)
- Explicit examples for uncertainty_language calibration:

```
uncertainty_language calibration:
- "confident": "This policy will reduce emissions by 30%" / "Evidence clearly demonstrates..."
- "cautious": "This approach may help..." / "Under certain conditions, this could..."
- "mixed": "While evidence suggests benefits, implementation challenges remain..."
```

### PolicyExtractionWorkflow Implementation

```python
class PolicyExtractionWorkflow(BaseExtractionWorkflow):
    """Workflow for policy syntheses, qualitative evidence, and expert opinion."""

    workflow_type = "policy"

    async def _extract_issues(self, state: WorkflowState) -> Dict[str, Any]:
        """Extract policy problems/challenges."""
        # Use POLICY_ISSUES_PROMPT
        ...

    async def _extract_interventions(self, state: WorkflowState) -> Dict[str, Any]:
        """Extract policy measures with responsible actors."""
        # Use POLICY_INTERVENTIONS_PROMPT
        # Set intervention_semantic_type = "policy_measure"
        ...

    async def _extract_results(self, state: WorkflowState) -> Dict[str, Any]:
        """Extract claim-level results per intervention."""
        # Use POLICY_RESULTS_PROMPT
        # Set estimate_level = "claim"
        # Populate claim_text, claim_type, evidence_basis, uncertainty_language
        # Use impact_direction instead of direction
        ...
```

---

## Frontend Integration

### Table Display

| Column | Description |
|--------|-------------|
| Intervention | Name/theme |
| Outcome | outcome_variable (for Policy: claim subject) |
| Direction | `direction` (RCT/SR) or `impact_direction` (Policy) |
| Workflow Type | "SR" / "RCT" / "Policy" |
| Evidence Category | From classification |

### Expandable Details (Structured Field Grid)

**RCT:** effect_size, CI, p_value, sample_size

**SR:** pooled effect, I², τ², n_studies, summary_statistic, stratum info

**Policy:** claim_text, claim_type, evidence_basis, uncertainty_language, impact_magnitude, population_targeted, supporting_quote

### Synthesis Pipeline

Unified pipeline with `workflow_used` field gating which fields to consider:
- RCT/SR: Aggregate by effect direction and magnitude
- Policy: Aggregate by claim_type (group recommendations, assessments, etc.)

---

## Phase 1 Status (Implemented)

- [x] `create_workflow()` routing function
- [x] `BaseExtractionWorkflow` abstract base class
- [x] `RCTExtractionWorkflow` implementation
- [x] `SRExtractionWorkflow` implementation
- [x] Extended schemas with SR and workflow fields
- [x] SR-specific prompts
- [x] Retry logic for stage failures
- [x] Integration with `extractor_langchain.py`
- [x] Integration with `test_extraction.py`

## Phase 2 Implementation Checklist

### Schema Changes
- [ ] Add `responsible_actor` field to InterventionItem
- [ ] Add `implementation_level` field to InterventionItem
- [ ] Add `claim_text` field to ResultItem
- [ ] Add `claim_type` field to ResultItem
- [ ] Add `evidence_basis` field to ResultItem
- [ ] Add `uncertainty_language` field to ResultItem
- [ ] Add `population_targeted` field to ResultItem
- [ ] Add `impact_direction` field to ResultItem
- [ ] Add Pydantic validator for empirical/claim mutual exclusivity

### Routing Changes
- [ ] Add `POLICY_CATEGORIES` set to routing.py
- [ ] Update `create_workflow()` to route Policy categories (no confidence fallback)
- [ ] Export `PolicyExtractionWorkflow` from `__init__.py`

### Workflow Implementation
- [ ] Create `policy.py` with `PolicyExtractionWorkflow` class
- [ ] Implement `_extract_issues()` using POLICY_ISSUES_PROMPT
- [ ] Implement `_extract_interventions()` using POLICY_INTERVENTIONS_PROMPT
- [ ] Implement `_extract_results()` using POLICY_RESULTS_PROMPT
- [ ] Reuse `_extract_mappings()` and `_extract_conclusions()` from base

### Prompts
- [ ] Create `POLICY_ISSUES_PROMPT` with policy problem framing
- [ ] Create `POLICY_INTERVENTIONS_PROMPT` with actor/level guidance
- [ ] Create `POLICY_RESULTS_PROMPT` with claim extraction guidance and uncertainty examples

### Testing
- [ ] Test with existing policy document corpus
- [ ] Validate claim extraction quality
- [ ] Verify mutual exclusivity validator works

### Frontend (Optional for Phase 2)
- [ ] Update detail panel to show Policy-specific fields
- [ ] Add claim_type filtering/grouping option

## Phase 3 Scope (Planned)

1. Implement `ModellingExtractionWorkflow` for Modelling & Simulation documents
2. Add modelling-specific fields (model_type, assumptions, scenarios)
3. Route Modelling & Simulation category to dedicated workflow

---

## Files

### Workflow Package

| File | Purpose |
|------|---------|
| `workflows/__init__.py` | Package exports |
| `workflows/base.py` | BaseExtractionWorkflow (ABC) |
| `workflows/routing.py` | `create_workflow()` routing function |
| `workflows/rct.py` | RCTExtractionWorkflow |
| `workflows/sr.py` | SRExtractionWorkflow |
| `workflows/policy.py` | PolicyExtractionWorkflow (Phase 2) |

### Related Files

| File | Purpose |
|------|---------|
| `schemas_langchain.py` | Extended Pydantic models |
| `prompts.py` | All prompts (RCT + SR + Policy) |
| `extractor_langchain.py` | Batch extraction service |
| `api/test_extraction.py` | Test extraction API |
