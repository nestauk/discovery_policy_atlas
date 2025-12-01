"""Synthesis service package.

Provides orchestration and schemas for synthesising analysis outputs
into executive summaries, key issues, interventions, and detailed
findings.
"""

from .schemas import (
    KeyIssue,
    PolicyIntervention,
    SynthesisSummary,
    Finding,
    ThematicGroup,
    EvidenceItem,
)

__all__ = [
    # Schemas
    "KeyIssue",
    "PolicyIntervention",
    "SynthesisSummary",
    "Finding",
    "ThematicGroup",
    "EvidenceItem",
]
