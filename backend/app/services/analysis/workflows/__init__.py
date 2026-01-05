"""
Multi-workflow extraction system for different evidence types.

Provides workflow routing based on evidence_category and confidence,
with specialized extraction workflows for RCT, SR, and Policy documents.
"""

from .factory import WorkflowFactory
from .base import BaseExtractionWorkflow
from .rct import RCTExtractionWorkflow
from .sr import SRExtractionWorkflow

__all__ = [
    "WorkflowFactory",
    "BaseExtractionWorkflow",
    "RCTExtractionWorkflow",
    "SRExtractionWorkflow",
]
