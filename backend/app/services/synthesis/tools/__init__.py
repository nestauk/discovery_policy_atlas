"""
Agentic briefing tools for evidence retrieval and verification.

This module provides tools that the orchestrator LLM can use to query
evidence from pre-computed state and the database.

Tools available:
- get_theme_evidence: Retrieve RCS-scored evidence for a specific theme
- get_document_quality: Get quality scores for a citation
- get_multiple_document_quality: Get quality scores for multiple citations
- search_extractions: Semantic search across document chunks
- verify_claim_support: Verify a claim against evidence
- verify_multiple_claims: Batch verify multiple claims
"""

from app.services.synthesis.tools.base import (
    BaseTool,
    ToolRegistry,
    ToolResult,
    get_tool_registry,
    register_tool,
)
from app.services.synthesis.tools.evidence import (
    get_theme_evidence,
    GetThemeEvidenceTool,
    ThemeEvidenceItem,
)
from app.services.synthesis.tools.quality import (
    get_document_quality,
    get_multiple_document_quality,
    GetDocumentQualityTool,
    GetMultipleDocumentQualityTool,
    DocumentQualityInfo,
)
from app.services.synthesis.tools.search import (
    search_extractions,
    SearchExtractionsTool,
    SearchResultItem,
)
from app.services.synthesis.tools.verification import (
    verify_claim_support,
    verify_multiple_claims,
    VerifyClaimSupportTool,
    VerifyMultipleClaimsTool,
    ClaimVerificationResult,
)
from app.services.synthesis.tools.models import (
    ORCHESTRATOR_MODEL,
    VERIFICATION_MODEL,
    GENERATION_MODEL,
    RCS_MODEL,
    get_model_config,
)
from app.services.synthesis.tools.orchestrator import (
    BriefingOrchestrator,
    OrchestratorContext,
    SectionOutput,
    generate_agentic_section,
    MAX_TOOL_CALLS_PER_SECTION,
)

__all__ = [
    # Base classes
    "BaseTool",
    "ToolRegistry",
    "ToolResult",
    "get_tool_registry",
    "register_tool",
    # Evidence tools
    "get_theme_evidence",
    "GetThemeEvidenceTool",
    "ThemeEvidenceItem",
    # Quality tools
    "get_document_quality",
    "get_multiple_document_quality",
    "GetDocumentQualityTool",
    "GetMultipleDocumentQualityTool",
    "DocumentQualityInfo",
    # Search tools
    "search_extractions",
    "SearchExtractionsTool",
    "SearchResultItem",
    # Verification tools
    "verify_claim_support",
    "verify_multiple_claims",
    "VerifyClaimSupportTool",
    "VerifyMultipleClaimsTool",
    "ClaimVerificationResult",
    # Model configuration
    "ORCHESTRATOR_MODEL",
    "VERIFICATION_MODEL",
    "GENERATION_MODEL",
    "RCS_MODEL",
    "get_model_config",
    # Orchestrator
    "BriefingOrchestrator",
    "OrchestratorContext",
    "SectionOutput",
    "generate_agentic_section",
    "MAX_TOOL_CALLS_PER_SECTION",
]
