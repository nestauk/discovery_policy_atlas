from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class KeyIssue(BaseModel):
    """Represents a canonicalised issue theme with aggregated evidence.

    Attributes:
        issue_theme: A concise, standardised name for the issue.
        summary_description: An LLM-generated synthesis of the issue.
        frequency: Number of documents that mention this issue.
        source_doc_ids: IDs of source documents mentioning this issue.
    """

    issue_theme: str = Field(
        ..., description="A concise, standardised name for the issue."
    )
    summary_description: str = Field(
        ..., description="An LLM-generated summary of the issue."
    )
    frequency: int = Field(
        ..., description="The number of documents that mention this issue."
    )
    source_doc_ids: List[str] = Field(
        ..., description="A list of document IDs where this issue is discussed."
    )
    justification: str = Field(
        ..., description="An explanation of why this theme was created."
    )


class PolicyIntervention(BaseModel):
    """Represents a canonicalised policy intervention with supporting evidence.

    Attributes:
        intervention_name: Standardised name for the intervention.
        brief_description: One-sentence summary of the intervention.
        impact_summary: Synthesised summary of the reported effects.
        frequency: Number of documents that mention this intervention.
        supporting_doc_ids: IDs of documents supporting this intervention.
    """

    intervention_name: str = Field(
        ..., description="A standardised name for the intervention."
    )
    brief_description: str = Field(
        ..., description="A one-sentence, LLM-generated summary of the intervention."
    )
    impact_summary: str = Field(
        ..., description="A synthesised summary of the reported effects."
    )
    frequency: int = Field(
        ..., description="The number of documents that mention this intervention."
    )
    supporting_doc_ids: List[str] = Field(
        ..., description="List of document IDs that discuss this intervention."
    )
    justification: str = Field(
        ..., description="An explanation of why this theme was created."
    )


class SynthesisSummary(BaseModel):
    """Container for the executive briefing and aggregated tables.

    Attributes:
        executive_briefing: Concise narrative summary for policymakers.
        key_issues: Aggregated issue clusters.
        interventions: Aggregated intervention clusters.
    """

    executive_briefing: str = Field(
        ..., description="A concise, narrative summary for policymakers."
    )
    key_issues: List[KeyIssue]
    interventions: List[PolicyIntervention]


class Finding(BaseModel):
    """Flattened evidence finding derived from document extraction results.

    Attributes:
        SourceTitle: Source document title.
        Source: Source system (e.g., OpenAlex, Overton).
        DocId: Stable document identifier.
        Year: Publication year.
        Url: Canonical URL or PDF URL.
        Intervention: Intervention name.
        StudyDesign: Study type design.
        Outcome: Outcome variable assessed.
        EffectDirection: Reported effect direction.
        EffectSizeType: Effect size metric type.
        EffectSize: Effect size value as text.
        PValue: Reported p-value if available.
        Uncertainty: Uncertainty text if provided.
        Evidence: Supporting quotes or result texts.
    """

    SourceTitle: str
    Source: Optional[str] = None
    DocId: Optional[str] = None
    Year: Optional[int] = None
    Url: Optional[str] = None
    Intervention: Optional[str] = None
    StudyDesign: Optional[str] = None
    Outcome: Optional[str] = None
    EffectDirection: Optional[str] = None
    EffectSizeType: Optional[str] = None
    EffectSize: Optional[str] = None
    PValue: Optional[str] = None
    Uncertainty: Optional[str] = None
    Evidence: List[str] = []
