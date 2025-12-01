"""
Pydantic schemas for synthesis agent.

These models define the data structures for:
- RAG retrieval (chunks, citations)
- Structured briefing output (for frontend rendering)
- Evidence coverage statistics
- Aggregated themes (issues, interventions, outcomes)
"""

from __future__ import annotations

from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field


# =============================================================================
# RAG RETRIEVAL
# =============================================================================


class RetrievedChunk(BaseModel):
    """A chunk retrieved via RAG for citation grounding."""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    document_id: str = Field(..., description="analysis_documents.id UUID")
    content: str = Field(..., description="Chunk text content")
    chunk_type: str = Field("content", description="summary | abstract | content")
    similarity: float = Field(0.0, description="Cosine similarity score")
    doc_title: Optional[str] = Field(None, description="Document title")
    author_short: Optional[str] = Field(None, description="Author surname")
    year: Optional[int] = Field(None, description="Publication year")
    url: Optional[str] = Field(None, description="Document URL")


class CitationInfo(BaseModel):
    """Grounded citation reference with supporting quote from RAG retrieval."""

    citation_key: str = Field(..., description="Display key like '[1]'")
    citation_number: int = Field(0, description="Numeric citation identifier")
    doc_id: Optional[str] = Field(None, description="External document identifier")
    analysis_document_id: str = Field(..., description="Internal UUID of the document")
    author_short: Optional[str] = Field(None, description="Short author reference")
    year: Optional[int] = Field(None, description="Publication year")
    title: Optional[str] = Field(None, description="Document title")
    url: Optional[str] = Field(None, description="Canonical URL or PDF URL")
    supporting_quote: Optional[str] = Field(
        None, description="Grounded quote from chunk"
    )
    chunk_id: Optional[str] = Field(None, description="Source chunk ID")


# =============================================================================
# STRUCTURED BRIEFING (JSON for Frontend Rendering)
# =============================================================================


class EvidenceSnapshotRow(BaseModel):
    """A row in the Evidence Coverage Snapshot table."""

    metric: str = Field(..., description="Metric name")
    detail: str = Field(..., description="Detail text")


class OutcomeEffect(BaseModel):
    """Effect on a grouped outcome theme."""

    outcome_theme: str = Field(..., description="Name of the outcome theme")
    direction: str = Field(
        ..., description="Dominant effect: positive, negative, null, mixed"
    )
    positive_count: int = Field(0, description="Count of positive effects")
    negative_count: int = Field(0, description="Count of negative effects")
    null_count: int = Field(0, description="Count of null effects")


class InterventionTableRow(BaseModel):
    """A row in the Key Interventions table."""

    intervention_name: str = Field(..., description="Intervention name")
    citation_numbers: List[int] = Field(
        default_factory=list, description="Citation numbers"
    )
    context: str = Field("", description="Location, setting, population, study design")
    outcome_effects: List[OutcomeEffect] = Field(
        default_factory=list, description="Effects grouped by outcome theme"
    )


class RecommendationItem(BaseModel):
    """A structured recommendation item."""

    number: int = Field(..., description="Recommendation number (1, 2, 3, etc)")
    title: str = Field(
        ...,
        description="Short action title (3-6 words, e.g. 'Fund multicomponent school programmes')",
    )
    description: str = Field(
        ...,
        description="Full recommendation text with evidence and citations in [N] format",
    )
    citation_numbers: List[int] = Field(
        default_factory=list, description="List of citation numbers used in description"
    )


class RecommendationsOutput(BaseModel):
    """Structured output for recommendations generation."""

    recommendations: List[RecommendationItem] = Field(
        ...,
        description="List of 3-4 policy recommendations",
        min_length=1,
        max_length=5,
    )


class TopCitationItem(BaseModel):
    """A top citation for the reading list."""

    citation_number: int = Field(..., description="Citation number")
    title: str = Field(..., description="Document title")
    author_year: str = Field(..., description="Author, Year string")
    reason: str = Field("", description="Recommendation reason")
    url: Optional[str] = Field(None, description="Document URL")


class BackgroundSection(BaseModel):
    """Structured background/context section."""

    title: str = Field("Policy Background & Context", description="Section title")
    paragraphs: List[str] = Field(default_factory=list, description="Paragraph texts")
    citation_numbers_used: List[int] = Field(
        default_factory=list, description="Citations used"
    )


class CoreAnswer(BaseModel):
    """The core answer section at the top of the briefing."""

    query: str = Field(..., description="Original user query")
    answer: str = Field(..., description="Headline answer")
    directive: str = Field("", description="Key recommendation")


class StructuredBriefing(BaseModel):
    """Complete structured executive briefing for frontend rendering."""

    core_answer: CoreAnswer = Field(..., description="Headline answer")
    evidence_snapshot: List[EvidenceSnapshotRow] = Field(default_factory=list)
    evidence_snapshot_summary: str = Field("")
    background_section: Optional[BackgroundSection] = Field(None)
    interventions_table: List[InterventionTableRow] = Field(default_factory=list)
    recommendations: List[RecommendationItem] = Field(default_factory=list)
    top_citations: List[TopCitationItem] = Field(default_factory=list)
    follow_up_suggestions: List[str] = Field(default_factory=list)


# =============================================================================
# EVIDENCE COVERAGE
# =============================================================================


class EvidenceCoverageSnapshot(BaseModel):
    """Deterministically computed evidence coverage statistics."""

    total_sources: int = Field(
        ..., description="Total number of unique source documents"
    )
    study_types: Dict[str, int] = Field(default_factory=dict)
    source_types: Dict[str, int] = Field(
        default_factory=dict, description="Academic, Government, NGO, etc."
    )
    countries: Dict[str, int] = Field(default_factory=dict)
    years: Dict[int, int] = Field(default_factory=dict)
    overall_strength: str = Field("Unknown", description="High | Moderate | Low")
    gaps: List[str] = Field(default_factory=list)


# =============================================================================
# AGGREGATED THEMES
# =============================================================================


class OutcomeTheme(BaseModel):
    """Clustered outcome theme with aggregated effect data."""

    outcome_name: str = Field(..., description="Canonical outcome name")
    outcome_description: str = Field("")
    effect_consensus: Literal[
        "positive", "negative", "mixed", "null", "insufficient"
    ] = Field("insufficient")
    positive_count: int = Field(0)
    negative_count: int = Field(0)
    null_count: int = Field(0)
    sample_effect_sizes: List[str] = Field(default_factory=list)
    frequency: int = Field(0)
    source_doc_ids: List[str] = Field(default_factory=list)


class KeyIssue(BaseModel):
    """A canonicalised issue theme with aggregated evidence."""

    issue_theme: str = Field(..., description="Standardised name for the issue")
    summary_description: str = Field(..., description="LLM-generated summary")
    frequency: int = Field(..., description="Number of documents mentioning this issue")
    source_doc_ids: List[str] = Field(
        ..., description="Document IDs where this issue appears"
    )


class PolicyIntervention(BaseModel):
    """A canonicalised policy intervention with supporting evidence."""

    intervention_name: str = Field(..., description="Standardised name")
    brief_description: str = Field(..., description="One-sentence summary")
    impact_summary: str = Field(..., description="Synthesised summary of effects")
    frequency: int = Field(..., description="Number of documents")
    supporting_doc_ids: List[str] = Field(..., description="Supporting document IDs")
    effect_consensus: Optional[
        Literal["positive", "negative", "mixed", "null", "insufficient"]
    ] = Field(None)
    positive_count: int = Field(0)
    negative_count: int = Field(0)
    null_count: int = Field(0)
    sample_effect_sizes: List[str] = Field(default_factory=list)
    countries: List[str] = Field(default_factory=list)
    study_types: Dict[str, int] = Field(default_factory=dict)
    related_outcomes: List[str] = Field(default_factory=list)


class SynthesisSummary(BaseModel):
    """Container for the executive briefing and aggregated tables."""

    executive_briefing: str = Field("", description="Legacy markdown (deprecated)")
    structured_briefing: Optional[StructuredBriefing] = Field(None)
    key_issues: List[KeyIssue] = Field(default_factory=list)
    interventions: List[PolicyIntervention] = Field(default_factory=list)
    outcome_themes: List[OutcomeTheme] = Field(default_factory=list)
    evidence_coverage: Optional[EvidenceCoverageSnapshot] = Field(None)
    citation_map: Dict[str, CitationInfo] = Field(default_factory=dict)


class Finding(BaseModel):
    """Drill-down finding for intervention/issue detail views."""

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
    Evidence: List[str] = Field(default_factory=list)


# =============================================================================
# EVIDENCE VIEW (Used by frontend Evidence tab)
# =============================================================================


class ThematicGroup(BaseModel):
    """Level-1 thematic grouping for the Evidence view."""

    id: str
    theme_title: str
    theme_summary: str
    item_count: int


class OutcomeItem(BaseModel):
    """A single outcome within an intervention item."""

    outcome: str
    direction_of_effect: str
    effect_size: Optional[str] = None
    significance: Optional[str] = None


class EvidenceItem(BaseModel):
    """Rich evidence item for the Evidence tab cards."""

    id: str
    title: str
    brief_description: Optional[str] = None
    frequency: Optional[int] = None
    outcomes: List[OutcomeItem] = Field(default_factory=list)
    supporting_evidence: List[str] = Field(default_factory=list)
    countries: List[str] = Field(default_factory=list)
    document: Optional[dict] = None
