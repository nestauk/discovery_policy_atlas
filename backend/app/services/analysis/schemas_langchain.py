"""
Minimal data models for the langchain/langgraph extraction workflow.
Uses index-based references and lightweight structures.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel


class IssueItem(BaseModel):
    """A problem statement or need addressed by the paper."""

    idx: int
    label: str
    explanation: str  # 1-2 sentence LLM interpretation of the issue
    supporting_quote: str


class InterventionItem(BaseModel):
    """An intervention, program, or treatment evaluated or proposed."""

    idx: int
    name: str
    type: str
    description: str
    study_type: str  # Maryland Scientific Methods Scale (a-h)
    country: Optional[str] = None
    population_intervened: Optional[str] = None
    population_demographics: Optional[str] = None
    sample_size: Optional[str] = None  # Total sample size for this intervention
    supporting_quote: str


class MappingItem(BaseModel):
    """Links issues to interventions with grounded rationale."""

    issue_idx: int
    intervention_idx: int
    rationale: str
    supporting_quote: str


class ResultItem(BaseModel):
    """Results/outcomes for a specific intervention."""

    intervention_idx: int
    outcome_variable: str
    effect_direction: Literal["increase", "decrease", "null"]
    effect_size_type: Optional[str] = None
    effect_size: Optional[str] = None
    uncertainty: Optional[str] = None
    p_value: Optional[str] = None
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


class ConclusionItem(BaseModel):
    """Study conclusions and key takeaways."""

    top_line_summary: str  # One direct sentence summarizing the main conclusion
    detailed_explanation: str  # Paragraph explaining key reasons for the conclusion
    supporting_quote: str


class ConclusionsExtraction(BaseModel):
    """Output from the conclusions extraction stage."""

    conclusion: ConclusionItem


# Final document extraction bundle
class DocumentExtractionBundle(BaseModel):
    """Complete extraction output for one paper."""

    paper_id: str
    issues: List[IssueItem]
    interventions: List[InterventionItem]
    mappings: List[MappingItem]
    results: List[ResultItem]
    conclusion: Optional[ConclusionItem] = None
