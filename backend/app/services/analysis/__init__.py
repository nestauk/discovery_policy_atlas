"""Deterministic analysis pipeline services.

This package contains the stepwise, auditable services for:
- References ingestion and normalization
- Acquisition (PDF/HTML) [to be implemented]
- Parsing and normalization [to be implemented]
- LLM-driven extraction with strict JSON schemas [to be implemented]
- Post-processing and CSV/JSON exports [to be implemented]
- RAG chunk/embedding exports (CSV placeholders) [to be implemented]
"""

__all__ = [
    "schemas",
    "prompts",
    "extract",
]
