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
)
from app.services.synthesis.nodes.aggregation import (
    compute_evidence_coverage,
    build_aggregated_tables,
)
from app.services.synthesis.nodes.rag_retrieval import (
    retrieve_evidence_for_themes,
    retrieve_evidence_for_issues,
)
from app.services.synthesis.nodes.briefing import (
    synthesize_executive_briefing,
)

__all__ = [
    # Data loading
    "load_raw_extractions",
    "create_canonical_concepts",
    # Theme discovery
    "process_issue_themes",
    "process_intervention_themes",
    "process_outcome_themes",
    # Aggregation
    "compute_evidence_coverage",
    "build_aggregated_tables",
    # RAG retrieval
    "retrieve_evidence_for_themes",
    "retrieve_evidence_for_issues",
    # Briefing generation
    "synthesize_executive_briefing",
]
