"""
Workflow factory for routing documents to appropriate extraction workflows.

Routes based on evidence_category and confidence score, with fallback to RCT
workflow for low confidence or unsupported categories.
"""

import logging
import re
from typing import Optional

from .base import BaseExtractionWorkflow

logger = logging.getLogger(__name__)

# Evidence categories that use SR workflow
SR_CATEGORIES = {"Systematic Review and Meta-Analysis"}

# Categories that should be filtered out (not processed)
FILTERED_CATEGORIES = {"Other (Non-evidence documents)"}

# Confidence threshold for fallback routing
CONFIDENCE_THRESHOLD = 0.5


def _normalize_category(category: str) -> str:
    """Strip leading number prefix (e.g., '1. ' from '1. Systematic Review')."""
    return re.sub(r"^\d+\.\s*", "", category)


def create_workflow(
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

    normalized_category = _normalize_category(evidence_category)

    if normalized_category in FILTERED_CATEGORIES:
        raise ValueError(
            f"Category '{evidence_category}' should be filtered before extraction"
        )

    kwargs = {
        "model": model,
        "policy_project_id": policy_project_id,
        "policy_user_id": policy_user_id,
    }

    # Use SR workflow for systematic reviews with sufficient confidence
    use_sr = normalized_category in SR_CATEGORIES and confidence >= CONFIDENCE_THRESHOLD

    if use_sr:
        logger.info(
            f"Creating SR workflow for '{evidence_category}' (confidence: {confidence:.2f})"
        )
        return SRExtractionWorkflow(**kwargs)

    # Default to RCT workflow (handles all other categories and low confidence)
    if confidence < CONFIDENCE_THRESHOLD:
        logger.info(
            f"Low confidence ({confidence:.2f}) for '{evidence_category}', using RCT fallback"
        )
    else:
        logger.info(
            f"Creating RCT workflow for '{evidence_category}' (confidence: {confidence:.2f})"
        )
    return RCTExtractionWorkflow(**kwargs)


# Backward compatibility - keep class API for existing code
class WorkflowFactory:
    """Factory for creating extraction workflows. Delegates to create_workflow()."""

    create = staticmethod(create_workflow)
