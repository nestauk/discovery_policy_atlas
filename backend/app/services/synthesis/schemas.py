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
    chunk_type: str = Field("content", description="abstract | content")
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
    document_type: Optional[str] = Field(None, description="Document/study type")
    evidence_score: Optional[int] = Field(None, description="Evidence strength score")
    impact_score: Optional[float] = Field(None, description="Impact score")
    supporting_quote: Optional[str] = Field(
        None, description="Grounded quote from chunk"
    )
    chunk_id: Optional[str] = Field(None, description="Source chunk ID")
    claim_quotes: List["ClaimQuote"] = Field(
        default_factory=list, description="Per-claim grounded quotes for this citation"
    )


class ClaimQuote(BaseModel):
    """Per-claim grounded quote tied to a citation."""

    claim_text: str = Field(..., description="Claim text this quote supports")
    supporting_quote: str = Field(..., description="Verbatim supporting quote")
    attribution: Literal["direct", "synthesised", "inferred"] = Field(
        ..., description="Attribution relationship between claim and source"
    )
    chunk_id: str = Field("", description="Chunk UUID for the supporting quote")
    section: str = Field("", description="Briefing section where claim appears")


class DocumentContextInfo(BaseModel):
    """Metadata for a source document shown in citation context."""

    analysis_document_id: str = Field(..., description="Internal document UUID")
    title: str = Field(..., description="Document title")
    author_display: Optional[str] = Field(
        None, description="First author as stored in metadata"
    )
    author_short: Optional[str] = Field(None, description="Short author reference")
    year: Optional[int] = Field(None, description="Publication year")
    country: Optional[str] = Field(None, description="Source country")
    url: Optional[str] = Field(None, description="Canonical source URL")
    source_type: Optional[str] = Field(None, description="Normalised source type")
    document_type: Optional[str] = Field(None, description="Document/study type")
    evidence_category: Optional[str] = Field(
        None, description="Evidence category classification"
    )
    evidence_score: Optional[int] = Field(None, description="Evidence strength score")
    impact_score: Optional[float] = Field(None, description="Impact score")


class ChunkContextResponse(BaseModel):
    """Chunk context payload for citation inspection sidebar."""

    chunk_id: str = Field(..., description="Target chunk UUID")
    chunk_content: str = Field(..., description="Target chunk content")
    chunk_index: int = Field(..., description="Target chunk index within document")
    previous_chunk_content: Optional[str] = Field(
        None, description="Immediate previous chunk content"
    )
    next_chunk_content: Optional[str] = Field(
        None, description="Immediate next chunk content"
    )
    document: DocumentContextInfo


# =============================================================================
# CONTEXTUAL SUMMARISATION (RCS) - paper-qa inspired
# =============================================================================


class ScoredContext(BaseModel):
    """A document chunk summarised in context of a specific question/theme.

    Implements paper-qa's Ranking and Contextual Summarisation (RCS) pattern:
    - Each chunk is summarised in context of a question
    - Assigned a relevance score (0-10)
    - Used for quality-based filtering and ranking
    """

    context_id: str = Field(..., description="Unique identifier for this context")
    summary: str = Field(
        ..., description="Contextual summary of the chunk (max ~100 words)"
    )
    relevance_score: int = Field(
        ..., ge=0, le=10, description="Relevance to question (0-10)"
    )
    question: str = Field(..., description="Question/theme used for summarisation")

    # Source traceability
    chunk_id: str = Field(..., description="Reference to source document chunk")
    document_id: str = Field(..., description="Reference to source document UUID")
    document_title: str = Field("", description="Document title for citation")

    # Citation metadata
    citation_key: str = Field(..., description="Short citation key e.g., 'pqa-abc123'")
    full_citation: str = Field("", description="Full citation for bibliography")

    # Theme linkage (for structured output)
    theme_id: Optional[str] = Field(
        None, description="Associated theme ID if applicable"
    )
    theme_name: Optional[str] = Field(
        None, description="Associated theme name if applicable"
    )


class ThemeEvidence(BaseModel):
    """Evidence gathered for a specific theme via RCS.

    Groups scored contexts by theme for structured briefing generation.
    """

    theme_id: str = Field(..., description="Theme identifier")
    theme_name: str = Field(..., description="Theme display name")
    theme_description: str = Field("", description="Theme summary/description")
    theme_question: str = Field(..., description="Question used for RCS scoring")

    # Scored contexts for this theme
    scored_contexts: List["ScoredContext"] = Field(
        default_factory=list, description="Contexts scored for this theme"
    )

    # Quality metrics
    total_chunks_retrieved: int = Field(
        0, description="Total chunks retrieved before scoring"
    )
    total_chunks_scored: int = Field(
        0, description="Total chunks that received RCS scoring"
    )
    high_quality_count: int = Field(0, description="Count of contexts with score >= 6")
    evidence_sufficient: bool = Field(
        False, description="Whether theme has sufficient evidence"
    )


class EvidenceGatheringResult(BaseModel):
    """Output of the theme-driven evidence gathering phase."""

    theme_evidence: List[ThemeEvidence] = Field(
        default_factory=list, description="Evidence grouped by theme"
    )

    # Cross-theme metrics
    total_contexts: int = Field(
        0, description="Total scored contexts across all themes"
    )
    themes_with_sufficient_evidence: int = Field(
        0, description="Count of themes with sufficient evidence"
    )
    themes_with_gaps: List[str] = Field(
        default_factory=list, description="Theme names lacking evidence"
    )
    iterations_run: int = Field(1, description="Number of retrieval iterations")


class RCSConfig(BaseModel):
    """Configuration for Contextual Summarisation (RCS) process."""

    score_threshold: int = Field(
        3, ge=0, le=10, description="Minimum score to include context"
    )
    high_quality_threshold: int = Field(
        6, ge=0, le=10, description="Score threshold for high-quality evidence"
    )
    max_contexts_per_theme: int = Field(
        10, description="Maximum contexts to keep per theme"
    )
    max_total_contexts: int = Field(
        50, description="Maximum total contexts for briefing"
    )
    min_high_quality_per_theme: int = Field(
        2, description="Minimum high-quality contexts for theme sufficiency"
    )
    chunks_to_retrieve: int = Field(
        15, description="Number of chunks to retrieve per theme"
    )
    rcs_concurrency: int = Field(10, description="Max parallel RCS calls")


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
        ..., description="Dominant effect: increase, decrease, no change, mixed"
    )
    positive_count: int = Field(0, description="Count of positive effects")
    negative_count: int = Field(0, description="Count of negative effects")
    null_count: int = Field(0, description="Count of null effects")


class InterventionTableRow(BaseModel):
    """A row in the Key Interventions table."""

    intervention_name: str = Field(..., description="Intervention type/category name")
    citation_numbers: List[int] = Field(
        default_factory=list, description="Citation numbers [N] used"
    )
    context: str = Field(
        "",
        description=(
            "Context and features: delivery method, setting, key components, "
            "notable features (e.g., 'School-based with family involvement')"
        ),
    )
    key_study_description: str = Field(
        "",
        description=(
            "Concrete implementation details from the top-ranked study in this intervention "
            "category (what was done, where, duration/intensity), suitable for the 'Key Study' column."
        ),
    )
    key_study_citation: Optional[int] = Field(
        None,
        description=(
            "Citation number [N] for the key study described in key_study_description, if available."
        ),
    )
    population_applicability: str = Field(
        "",
        description=(
            "How this intervention applies to the target population (as specified by the user at search time). "
            "Used to tailor synthesis; may be left empty if not applicable."
        ),
    )
    outcome_relevance: str = Field(
        "",
        description=(
            "How this intervention maps to the target outcomes (as specified by the user at search time). "
            "Used to tailor synthesis; may be left empty if not applicable."
        ),
    )
    delivery_features: List[str] = Field(
        default_factory=list,
        description="Key delivery attributes (e.g., school-based, family involvement, duration/intensity).",
    )
    subgroup_effects: List[str] = Field(
        default_factory=list,
        description="Notable subgroup findings (e.g., more effective in younger children, girls, high-risk groups).",
    )
    impact_narrative: str = Field(
        "",
        description=(
            "Impact and outcomes: effectiveness on key outcomes, effect sizes, "
            "findings (e.g., 'Modest BMI reduction; more effective in overweight children')"
        ),
    )
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
    implementation_option: str = Field(
        "",
        description=(
            "Optional implementation option / delivery suggestion that extrapolates beyond the evidence base. "
            "Should be explicitly labelled as an option and written conditionally."
        ),
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


class SynthesisSection(BaseModel):
    """Optional synthesis section inserted between interventions and recommendations."""

    title: str = Field(..., description="Section title")
    content_type: Literal["paragraphs", "bullets"] = Field(
        "paragraphs", description="Rendering preference."
    )
    paragraphs: List[str] = Field(default_factory=list, description="Paragraph content")
    bullets: List[str] = Field(default_factory=list, description="Bullet content")
    citation_numbers_used: List[int] = Field(
        default_factory=list, description="Citations referenced in this section"
    )


class SynthesisSectionProposal(BaseModel):
    """Structured proposal for a synthesis section."""

    section_title: str = Field(..., description="Proposed section title")
    rationale: str = Field(..., description="Why this section is needed")
    focus: str = Field(..., description="What the section will cover")


class StructuredBriefing(BaseModel):
    """Complete structured executive briefing for frontend rendering."""

    core_answer: CoreAnswer = Field(..., description="Headline answer")
    evidence_snapshot: List[EvidenceSnapshotRow] = Field(default_factory=list)
    evidence_snapshot_summary: str = Field("")
    background_section: Optional[BackgroundSection] = Field(None)
    interventions_table: List[InterventionTableRow] = Field(default_factory=list)
    synthesis_sections: List["SynthesisSection"] = Field(default_factory=list)
    recommendations: List[RecommendationItem] = Field(default_factory=list)
    top_citations: List[TopCitationItem] = Field(default_factory=list)
    follow_up_suggestions: List[str] = Field(default_factory=list)


# =============================================================================
# EVIDENCE COVERAGE
# =============================================================================


class EvidenceCoverageSnapshot(BaseModel):
    """Deterministically computed evidence coverage statistics."""

    total_screened: int = Field(
        ..., description="Number of documents screened (all retrieved candidates)"
    )
    total_synthesised: int = Field(
        ...,
        description="Number of evidence documents synthesised (excluding 'Other' non-evidence docs)",
    )
    study_types: Dict[str, int] = Field(default_factory=dict)
    source_types: Dict[str, int] = Field(
        default_factory=dict, description="Academic, Government, NGO, etc."
    )
    evidence_categories: Dict[str, int] = Field(
        default_factory=dict,
        description="Evidence type distribution: Systematic Review, RCT, Observational, etc.",
    )
    countries: Dict[str, int] = Field(default_factory=dict)
    years: Dict[int, int] = Field(default_factory=dict)
    overall_strength: str = Field("Unknown", description="High | Moderate | Low")
    gaps: List[str] = Field(default_factory=list)


# =============================================================================
# AGGREGATED THEMES
# =============================================================================


VerdictType = Literal[
    "well_evidenced_positive",
    "well_evidenced_negative",
    "evidenced_positive",
    "evidenced_negative",
    "suggested_positive",
    "suggested_negative",
    "contested",
    "no_effect",
    "insufficient_evidence",
    "probable_contribution",
]


SemanticMagnitudeType = Literal[
    "transformational",
    "substantial",
    "large",
    "moderate",
    "marginal",
    "unknown",
]


CausalityClaimType = Literal["attribution", "contribution", "correlation"]


class TransferabilityBreakdown(BaseModel):
    """Per-dimension transferability scores."""

    inner_setting: str
    population: str
    geography: str
    notes: Dict[str, str] = Field(default_factory=dict)
    data_availability: Dict[str, str] = Field(default_factory=dict)
    context_fit_rating: Optional[str] = None
    implementation_requirements_rating: Optional[str] = None
    implementation_constraints_specified: bool = False
    implementation_evidence: Dict[str, str] = Field(default_factory=dict)
    implementation_constraints: Dict[str, str] = Field(default_factory=dict)
    implementation_exceeds_tolerance: Dict[str, bool] = Field(default_factory=dict)


class MagnitudeDetail(BaseModel):
    """Structured magnitude breakdown for tooltips."""

    direction: Literal["increase", "decrease", "contested"]
    bucket_counts: Dict[str, int] = Field(default_factory=dict)
    source_count: int
    total_sources: int
    measurement_count: int
    dominant_scale: Optional[str] = None
    thresholds: str


class CausalityDetail(BaseModel):
    """Structured causal mechanism counts for tooltips."""

    attribution: int = 0
    contribution: int = 0
    correlation: int = 0


class RiskTheme(BaseModel):
    """LLM-clustered risk theme (stored in synthesis_themes with type='risk')."""

    theme_name: str
    summary_description: str
    frequency: int
    source_doc_ids: List[str] = Field(default_factory=list)
    has_harm_warning: bool = False
    linked_intervention_theme_id: Optional[str] = None
    linked_interventions: List[Dict[str, str]] = Field(default_factory=list)


class OutcomeTheme(BaseModel):
    """Clustered outcome theme with aggregated effect data."""

    outcome_name: str = Field(..., description="Canonical outcome name")
    outcome_description: str = Field("")
    effect_consensus: Literal[
        "increase", "decrease", "mixed", "no change", "insufficient"
    ] = Field("insufficient")
    positive_count: int = Field(0)
    negative_count: int = Field(0)
    null_count: int = Field(0)
    sample_effect_sizes: List[str] = Field(default_factory=list)
    frequency: int = Field(0)
    source_doc_ids: List[str] = Field(default_factory=list)
    verdict_label: Optional[VerdictType] = Field(None)
    verdict_description: Optional[str] = Field(None)
    discord_flag: bool = Field(False)
    discord_reason: Optional[str] = Field(None)
    predicted_magnitude: Optional[SemanticMagnitudeType] = Field(None)
    magnitude_detail: Optional[MagnitudeDetail] = Field(None)
    intervention_theme_id: Optional[str] = Field(None)
    primary_causal_mechanism: Optional[CausalityClaimType] = Field(None)
    causal_mechanism_detail: Optional[CausalityDetail] = Field(None)


class InterventionDetails(BaseModel):
    """Rich intervention detail for table enrichment."""

    intervention_name: str = Field(..., description="Intervention type/category name")
    delivery_features: List[str] = Field(
        default_factory=list,
        description="Delivery method, setting, intensity, components (e.g., school-based, family involvement, duration).",
    )
    target_population: List[str] = Field(
        default_factory=list,
        description="Populations targeted (ages, risk groups, sexes).",
    )
    subgroup_effects: List[str] = Field(
        default_factory=list,
        description="Subgroup differences (e.g., more effective in girls, younger children).",
    )
    effect_sizes: List[str] = Field(
        default_factory=list,
        description="Effect sizes with units (e.g., BMI −0.2 kg/m², prevalence −5%).",
    )
    supporting_citations: List[int] = Field(
        default_factory=list, description="Citation numbers supporting these details."
    )


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
        Literal["increase", "decrease", "mixed", "no change", "insufficient"]
    ] = Field(None)
    positive_count: int = Field(0)
    negative_count: int = Field(0)
    null_count: int = Field(0)
    sample_effect_sizes: List[str] = Field(default_factory=list)
    countries: List[str] = Field(default_factory=list)
    study_types: Dict[str, int] = Field(default_factory=dict)
    related_outcomes: List[str] = Field(default_factory=list)
    transferability_rating: Optional[str] = Field(None)
    transferability_note: Optional[str] = Field(None)
    transferability_breakdown: Optional[TransferabilityBreakdown] = Field(None)
    impact_score: Optional[float] = Field(None)
    impact_score_label: Optional[str] = Field(None)
    impact_score_breakdown: Optional[Dict[str, object]] = Field(None)


class SynthesisSummary(BaseModel):
    """Container for the executive briefing and aggregated tables."""

    executive_briefing: str = Field("", description="Legacy markdown (deprecated)")
    structured_briefing: Optional[StructuredBriefing] = Field(None)
    key_issues: List[KeyIssue] = Field(default_factory=list)
    interventions: List[PolicyIntervention] = Field(default_factory=list)
    outcome_themes: List[OutcomeTheme] = Field(default_factory=list)
    risk_themes: List[RiskTheme] = Field(default_factory=list)
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
