"""
Multi-workflow extraction system for different evidence types.

Provides workflow routing based on evidence_category and confidence,
with specialized extraction workflows for RCT, SR, and Policy documents.
"""

from .routing import create_workflow
from .base import BaseExtractionWorkflow, StageModelConfig
from .rct import RCTExtractionWorkflow
from .sr import SRExtractionWorkflow

__all__ = [
    "create_workflow",
    "BaseExtractionWorkflow",
    "StageModelConfig",
    "RCTExtractionWorkflow",
    "SRExtractionWorkflow",
]
