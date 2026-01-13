"""
State definitions for the synthesis workflow.

Contains the SynthesisState TypedDict that flows through the LangGraph workflow,
plus internal models used during theme discovery and mapping.
"""

from __future__ import annotations

from typing import List, Dict, TypedDict, Optional, Any, Literal

from pydantic import BaseModel, Field

from app.services.synthesis.schemas import (
    KeyIssue,
    PolicyIntervention,
    CitationInfo,
    EvidenceCoverageSnapshot,
    OutcomeTheme,
    RetrievedChunk,
    StructuredBriefing,
    ScoredContext,
    ThemeEvidence,
    RCSConfig,
)


ThemeBranch = Literal["issue", "intervention", "outcome"]


class Concept(BaseModel):
    """A single enriched concept extracted from raw data."""

    id: str
    canonical_description: str


class DiscoveredTheme(BaseModel):
    """Theme discovered by LLM during theme discovery phase."""

    theme_name: str
    theme_description: str


class FinalTheme(BaseModel):
    """Final theme with mapped concepts after classification."""

    name: str
    description: str
    concepts: List[Concept] = Field(default_factory=list)
    frequency: int = 0


class ThemesOut(BaseModel):
    """Structured output for discovered themes from LLM."""

    themes: List[DiscoveredTheme]


class SynthesisState(TypedDict, total=False):
    """State passed through the synthesis workflow.

    This TypedDict defines all fields that can be present in the workflow state.
    Each node function receives the current state and returns a partial update.
    """

    # Core identifiers
    project_id: str
    research_question: str

    # User intent (captured at search time; used to tailor synthesis)
    target_population: List[str]  # e.g., ["Children"]
    target_outcomes: List[str]  # e.g., ["body weight/size reduction"]

    # Raw data
    raw_extractions: List[Dict]
    doc_metadata: Dict[str, Dict[str, Any]]
    doc_scores: Dict[str, Dict[str, Any]]  # doc_uuid -> {evidence_score, impact_score}
    extraction_to_doc: Dict[str, str]  # extraction_id -> doc_uuid

    # Concepts by branch (created from raw extractions)
    issue_concepts: List[Concept]
    intervention_concepts: List[Concept]
    outcome_concepts: List[Concept]

    # Discovered themes by branch (from LLM)
    discovered_issue_themes: List[DiscoveredTheme]
    discovered_intervention_themes: List[DiscoveredTheme]
    discovered_outcome_themes: List[DiscoveredTheme]

    # Final themes with mapped concepts
    final_issue_themes: List[FinalTheme]
    final_intervention_themes: List[FinalTheme]
    final_outcome_themes: List[FinalTheme]

    # Evidence coverage statistics
    evidence_coverage: EvidenceCoverageSnapshot

    # Aggregated outputs (from themes)
    aggregated_issues: List[KeyIssue]
    aggregated_interventions: List[PolicyIntervention]
    aggregated_outcomes: List[OutcomeTheme]
    extraction_quotes: Dict[str, List[str]]  # doc_uuid -> list of extraction quotes
    outcome_doc_effects: Dict[
        str, Dict[str, List[str]]
    ]  # outcome_name -> {doc_id -> [effects]}

    # Theme to document mappings (for constrained RAG)
    theme_to_doc_uuids: Dict[str, List[str]]  # theme_name -> [doc_uuid, ...]

    # RAG retrieval results (legacy - kept for backward compatibility)
    theme_evidence: Dict[str, List[RetrievedChunk]]
    issue_evidence: Dict[str, List[RetrievedChunk]]
    grounded_citations: List[CitationInfo]
    chunk_to_citation: Dict[str, int]
    doc_citation_map: Dict[str, int]  # doc_uuid -> citation number

    # RCS (Contextual Summarisation) results - enhanced evidence gathering
    rcs_config: RCSConfig
    scored_theme_evidence: List[ThemeEvidence]  # Theme-grouped scored contexts
    scored_issue_evidence: List[ThemeEvidence]  # Issue-grouped scored contexts
    all_scored_contexts: List[ScoredContext]  # All contexts across themes
    themes_with_gaps: List[str]  # Themes lacking sufficient evidence
    rcs_iterations_run: int  # Number of evidence gathering iterations

    # Final outputs
    executive_briefing: str
    structured_briefing: Optional[StructuredBriefing]
    citation_map: Dict[str, CitationInfo]

    # Briefing results (tool-augmented generation)
    briefing_results: Optional[Dict[str, Any]]  # Tool calls, verification results

    # Langfuse tracing
    langfuse_handler: Any
    langfuse_session_id: str
    policy_user_id: Optional[str]
