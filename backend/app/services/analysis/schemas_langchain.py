"""
Minimal data models for the langchain/langgraph extraction workflow.
Uses index-based references and lightweight structures.

Supports multiple workflow types (RCT, SR, Policy) with shared base schemas
and workflow-specific nullable fields.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel


class IssueItem(BaseModel):
    """A problem statement or need addressed by the paper.

    For RCT: Problem statements that motivated the research
    For SR: Review questions or evidence gaps
    For Policy: Policy challenges or objectives
    """

    idx: int
    label: str
    explanation: str  # 1-2 sentence LLM interpretation of the issue
    supporting_quote: str


class InterventionItem(BaseModel):
    """An intervention, program, or treatment evaluated or proposed.

    For RCT: Specific interventions/treatments being tested
    For SR: Intervention categories/themes reviewed (e.g., "CBT-based interventions")
    For Policy: Concrete policy measures or recommendations
    """

    idx: int
    name: str
    type: str
    description: str
    country: Optional[str] = None
    population_intervened: Optional[str] = None
    population_demographics: Optional[str] = None
    sample_size: Optional[str] = None  # Total sample size for this intervention
    # NEW: Comparator/control condition (useful for both RCT and SR)
    comparator: Optional[str] = None
    supporting_quote: str


class MappingItem(BaseModel):
    """Links issues to interventions with grounded rationale."""

    issue_idx: int
    intervention_idx: int
    rationale: str
    supporting_quote: str


class ResultItem(BaseModel):
    """Results/outcomes for a specific intervention.

    Unified schema supporting RCT, SR, and Policy workflows with
    workflow-specific nullable fields.
    """

    intervention_idx: int
    outcome_variable: str
    # RENAMED: direction (was effect_direction), added mixed_or_unclear
    direction: Literal["increase", "decrease", "null", "mixed_or_unclear"]
    # NEW: Distinguishes study-level (RCT), pooled (SR), or claim (Policy) estimates
    estimate_level: Optional[Literal["study", "pooled", "claim"]] = None

    # RCT/SR empirical fields (nullable)
    effect_size_type: Optional[str] = None
    effect_size: Optional[str] = None
    uncertainty: Optional[str] = None
    p_value: Optional[str] = None

    # SR-specific fields (nullable, for meta-analytic results)
    heterogeneity_I2: Optional[str] = None  # I² statistic
    tau2: Optional[str] = None  # τ² (between-study variance)
    summary_statistic: Optional[str] = None  # e.g., "pooled OR", "SMD"
    n_studies: Optional[int] = None  # Number of studies pooled (k)
    sample_size: Optional[int] = None  # Total participants across pooled studies (N)

    # Stratum fields (for SR subgroup analyses - each result row = one stratum)
    stratum_type: Optional[
        str
    ] = None  # e.g., "follow-up period", "age subgroup", "setting"
    stratum_value: Optional[str] = None  # e.g., "12 months", "children 5-11 years"
    is_primary_stratum: Optional[bool] = None  # True if this is the main/overall result

    # Policy-specific field (nullable, constrained qualitative scale)
    impact_magnitude: Optional[
        Literal[
            "substantial", "moderate", "modest", "marginal", "negligible", "unclear"
        ]
    ] = None

    # Common fields
    population_measured: Optional[
        str
    ] = None  # Who was measured for this specific result
    subgroup_or_dose: Optional[str] = None
    result_text: str
    supporting_quote: str


# Intermediate extraction models for each stage
class IssuesExtraction(BaseModel):
    """Output from the issues extraction stage."""

    issues: List[IssueItem]
    coverage_note: Optional[str] = None


class InterventionsExtraction(BaseModel):
    """Output from the interventions extraction stage."""

    interventions: List[InterventionItem]
    coverage_note: Optional[str] = None


class MappingsExtraction(BaseModel):
    """Output from the mapping extraction stage."""

    mappings: List[MappingItem]


class ResultsExtraction(BaseModel):
    """Output from the results extraction stage."""

    results: List[ResultItem]


class ImpactRating(BaseModel):
    """Star rating with justification, used for both evidence strength and predicted impact."""

    stars: Optional[int] = None  # 1-5 star rating, null if insufficient evidence
    justification: str  # 2-4 sentences explaining rating and discounting logic
    evidence_gap: Optional[str] = None  # explanation if stars is null


class ConclusionItem(BaseModel):
    """Study conclusions and key takeaways."""

    top_line_summary: str  # One direct sentence summarizing the main conclusion
    detailed_explanation: str  # Paragraph explaining key reasons for the conclusion
    supporting_quote: str
    evidence_strength: Optional[ImpactRating] = None  # Computed evidence strength
    predicted_impact: Optional[ImpactRating] = None  # Predicted scalability and impact


class ConclusionsExtraction(BaseModel):
    """Output from the conclusions extraction stage."""

    conclusion: ConclusionItem


# Final document extraction bundle
class DocumentExtractionBundle(BaseModel):
    """Complete extraction output for one paper.

    Includes workflow routing metadata and workflow-specific fields.
    """

    paper_id: str
    # NEW: Workflow routing metadata
    workflow_used: Optional[str] = None  # "rct", "sr", "policy"
    routing_reason: Optional[
        str
    ] = None  # "evidence_category", "low_confidence_fallback"

    # Core extraction outputs
    issues: List[IssueItem]
    interventions: List[InterventionItem]
    mappings: List[MappingItem]
    results: List[ResultItem]
    conclusion: Optional[ConclusionItem] = None

    # SR document-level fields
    n_studies_included: Optional[int] = None  # Aggregate study count for SR
    sr_completeness_flag: Optional[str] = None  # "complete", "incomplete_heterogeneity"
