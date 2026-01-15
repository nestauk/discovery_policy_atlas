"""
Workflow factory for routing documents to appropriate extraction workflows.

Routes based on evidence_category and confidence score, with fallback to RCT
workflow for low confidence or Phase 2 categories.
"""

import logging
import re
from typing import Optional

from .base import BaseExtractionWorkflow

logger = logging.getLogger(__name__)


def normalize_category(category: str) -> str:
    """Strip leading number prefix (e.g., '1. ' from '1. Systematic Review')."""
    return re.sub(r"^\d+\.\s*", "", category)


# Evidence categories that use SR workflow
SR_CATEGORIES = {
    "Systematic Review and Meta-Analysis",
}

# Evidence categories that use RCT workflow (including fallbacks for Phase 2)
RCT_CATEGORIES = {
    "RCTs and Quasi-Experimental Studies",
    "Observational Research Studies",
    # Phase 2 categories - use RCT as fallback until Policy workflow is implemented
    "Modelling & Simulation",
    "Policy Syntheses & Guidance Documents",
    "Qualitative & Contextual Evidence",
    "Expert Opinion and Commentary",
    "Unknown / Insufficient information",
}

# Categories that should be filtered out (not processed)
FILTERED_CATEGORIES = {
    "Other (Non-evidence documents)",
}

# Confidence threshold for fallback routing
CONFIDENCE_THRESHOLD = 0.5


class WorkflowFactory:
    """Factory for creating appropriate extraction workflows based on evidence type.

    Routes documents to specialized workflows:
    - SR workflow for systematic reviews and meta-analyses
    - RCT workflow for individual studies and as fallback for other types

    Fallback behavior:
    - Low confidence (< 0.5) routes to RCT workflow
    - Phase 2 categories (Policy, Modelling, etc.) route to RCT workflow until implemented
    """

    @staticmethod
    def create(
        evidence_category: str,
        confidence: float = 1.0,
        model: str = "gpt-5-mini",
        policy_project_id: Optional[str] = None,
        policy_user_id: Optional[str] = None,
    ) -> BaseExtractionWorkflow:
        """Create the appropriate workflow based on evidence category and confidence.

        Args:
            evidence_category: The document's evidence category classification
            confidence: Confidence score of the classification (0.0-1.0)
            model: LLM model to use for extraction
            policy_project_id: Project ID for Langfuse tracking
            policy_user_id: User ID for Langfuse tracking

        Returns:
            Appropriate workflow instance (RCTExtractionWorkflow or SRExtractionWorkflow)

        Raises:
            ValueError: If category is in FILTERED_CATEGORIES
        """
        # Import here to avoid circular imports
        from .rct import RCTExtractionWorkflow
        from .sr import SRExtractionWorkflow

        # Normalize category (strip number prefix like "1. ")
        normalized_category = normalize_category(evidence_category)

        # Check for filtered categories
        if normalized_category in FILTERED_CATEGORIES:
            raise ValueError(
                f"Category '{evidence_category}' should be filtered before extraction"
            )

        # Determine workflow type based on category and confidence
        workflow_type = WorkflowFactory._resolve_workflow_type(
            normalized_category, confidence
        )

        # Create and return appropriate workflow
        kwargs = {
            "model": model,
            "policy_project_id": policy_project_id,
            "policy_user_id": policy_user_id,
        }

        if workflow_type == "sr":
            logger.info(
                f"Creating SR workflow for category '{evidence_category}' "
                f"(confidence: {confidence:.2f})"
            )
            return SRExtractionWorkflow(**kwargs)
        else:
            logger.info(
                f"Creating RCT workflow for category '{evidence_category}' "
                f"(confidence: {confidence:.2f})"
            )
            return RCTExtractionWorkflow(**kwargs)

    @staticmethod
    def _resolve_workflow_type(evidence_category: str, confidence: float) -> str:
        """Resolve which workflow type to use.

        Args:
            evidence_category: The document's evidence category
            confidence: Classification confidence score

        Returns:
            Workflow type: "rct" or "sr"
        """
        # Low confidence falls back to RCT
        if confidence < CONFIDENCE_THRESHOLD:
            logger.info(
                f"Low confidence ({confidence:.2f}) for '{evidence_category}', "
                "using RCT fallback"
            )
            return "rct"

        # Route based on category
        if evidence_category in SR_CATEGORIES:
            return "sr"

        # Everything else uses RCT (including Phase 2 categories as fallback)
        return "rct"
