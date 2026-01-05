"""
LangGraph workflow for document extraction.

This module provides backward compatibility for the original ExtractionWorkflow API.
New code should use the workflows/ package directly via WorkflowFactory.
"""

import logging
from typing import Optional

from .schemas_langchain import DocumentExtractionBundle
from .workflows import WorkflowFactory

logger = logging.getLogger(__name__)


class ExtractionWorkflow:
    """Legacy extraction workflow - delegates to WorkflowFactory.

    Provides backward compatibility for existing code. New code should use
    WorkflowFactory directly for evidence-category-aware routing.
    """

    def __init__(
        self,
        model: str = "gpt-5-mini",
        temperature: float = 0.0,
        *,
        policy_project_id: Optional[str] = None,
        policy_user_id: Optional[str] = None,
    ):
        self.model = model
        self.policy_project_id = policy_project_id
        self.policy_user_id = policy_user_id

    async def run(
        self,
        paper_id: str,
        full_text: str,
        evidence_category: str = "RCTs and Quasi-Experimental Studies",
        evidence_confidence: float = 1.0,
    ) -> DocumentExtractionBundle:
        """Run extraction workflow with evidence category routing."""
        workflow = WorkflowFactory.create(
            evidence_category=evidence_category,
            confidence=evidence_confidence,
            model=self.model,
            policy_project_id=self.policy_project_id,
            policy_user_id=self.policy_user_id,
        )
        return await workflow.run(
            paper_id, full_text, evidence_category, evidence_confidence
        )
