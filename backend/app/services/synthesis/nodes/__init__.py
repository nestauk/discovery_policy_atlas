"""
Synthesis workflow node functions.

Each module contains node functions for a specific phase of the synthesis workflow.
All nodes receive SynthesisState and return partial state updates.
"""

from app.services.synthesis.nodes.data_loading import (
    load_raw_extractions,
    create_canonical_concepts,
)
from app.services.synthesis.nodes.theme_discovery import (
    process_issue_themes,
    process_intervention_themes,
    process_outcome_themes,
    process_risk_themes,
)
from app.services.synthesis.nodes.aggregation import (
    compute_evidence_coverage,
    build_aggregated_tables,
)
from app.services.synthesis.nodes.impact_synthesis import compute_impact_syntheses
from app.services.synthesis.nodes.rag_retrieval import (
    retrieve_evidence_for_themes,
    retrieve_evidence_for_issues,
    retrieve_evidence_for_outcomes,
)
from app.services.synthesis.nodes.contextual_summarisation import (
    apply_rcs_to_theme_evidence,
    apply_rcs_to_issue_evidence,
    apply_rcs_to_outcome_evidence,
    contextual_summarise_batch,
    generate_theme_question,
)
from app.services.synthesis.nodes.briefing import (
    generate_briefing,
    BriefingConfig,
)

__all__ = [
    # Data loading
    "load_raw_extractions",
    "create_canonical_concepts",
    # Theme discovery
    "process_issue_themes",
    "process_intervention_themes",
    "process_outcome_themes",
    "process_risk_themes",
    # Aggregation
    "compute_evidence_coverage",
    "build_aggregated_tables",
    "compute_impact_syntheses",
    # RAG retrieval
    "retrieve_evidence_for_themes",
    "retrieve_evidence_for_issues",
    "retrieve_evidence_for_outcomes",
    # Contextual Summarisation (RCS)
    "apply_rcs_to_theme_evidence",
    "apply_rcs_to_issue_evidence",
    "apply_rcs_to_outcome_evidence",
    "contextual_summarise_batch",
    "generate_theme_question",
    # Briefing generation (tool-augmented with mandatory verification)
    "generate_briefing",
    "BriefingConfig",
]
