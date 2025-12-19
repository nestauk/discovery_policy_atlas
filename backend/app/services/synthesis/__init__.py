"""Synthesis service package.

Provides orchestration and schemas for synthesising analysis outputs
into executive summaries, key issues, interventions, and detailed
findings.
"""

from app.services.synthesis.schemas import (
    KeyIssue,
    PolicyIntervention,
    SynthesisSummary,
    Finding,
    ThematicGroup,
    EvidenceItem,
    StructuredBriefing,
    CitationInfo,
)
from app.services.synthesis.agent import SynthesisAgent
from app.services.synthesis.findings import get_findings

__all__ = [
    # Schemas
    "KeyIssue",
    "PolicyIntervention",
    "SynthesisSummary",
    "Finding",
    "ThematicGroup",
    "EvidenceItem",
    "StructuredBriefing",
    "CitationInfo",
    # Agent
    "SynthesisAgent",
    # Functions
    "get_findings",
]
