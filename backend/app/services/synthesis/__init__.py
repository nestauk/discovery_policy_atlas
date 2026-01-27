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
    # RCS (Contextual Summarisation) schemas
    ScoredContext,
    ThemeEvidence,
    RCSConfig,
)
from app.services.synthesis.agent import SynthesisAgent, run_synthesis
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
    # RCS schemas
    "ScoredContext",
    "ThemeEvidence",
    "RCSConfig",
    # Agent
    "SynthesisAgent",
    "run_synthesis",
    # Functions
    "get_findings",
]
