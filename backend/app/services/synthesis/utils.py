"""
Utility functions and constants for the synthesis workflow.

Contains normalisation helpers, string escaping, document info extraction,
and Langfuse configuration utilities.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Any, TYPE_CHECKING

from app.utils.llm.llm_utils import build_langfuse_metadata

if TYPE_CHECKING:
    from app.services.synthesis.state import SynthesisState


# Model selection constants
THEME_MODEL = "gpt-5-mini"
MAPPING_MODEL = "gpt-5-nano"
BRIEFING_MODEL = "gpt-5"

# Study type code mapping (Maryland Scientific Methods Scale - matches extraction prompts)
STUDY_TYPE_LABELS: Dict[str, str] = {
    "a": "Cross-Sectional",
    "b": "Pre-Post Study",
    "c": "Cross-Sectional with Controls",
    "d": "Pre-Post with Controls",
    "e": "Comparison Study",
    "f": "Quasi-Experimental",
    "g": "RCT",
    "h": "Meta-Analysis",
    "i": "Policy/Theoretical",
    "j": "Non-Scientific",
}


def normalize_study_type(study_type: str) -> str:
    """Normalise study type codes to full readable names.

    Args:
        study_type: Raw study type string (code or full name).

    Returns:
        Normalised study type name in title case.
    """
    if not study_type:
        return ""
    st = study_type.strip().lower()
    if st in STUDY_TYPE_LABELS:
        return STUDY_TYPE_LABELS[st]
    for full_name in STUDY_TYPE_LABELS.values():
        if full_name.lower() == st:
            return full_name
    return study_type.strip().title()


def normalize_source_type(source: str, document_type: str) -> str:
    """Normalise document source to readable category.

    Args:
        source: Source identifier (e.g., 'openalex', 'overton').
        document_type: Document type from metadata.

    Returns:
        Normalised source category.
    """
    src = (source or "").strip().lower()
    doc_type = (document_type or "").strip().lower()

    # OpenAlex is always academic
    if src == "openalex":
        return "Academic"

    # Overton document types
    if doc_type in ("journal article", "unknown", ""):
        return "Academic"
    if doc_type in ("government document", "government"):
        return "Government"
    if doc_type in ("ngo document", "ngo", "think tank"):
        return "NGO/Think Tank"
    if doc_type in ("policy document", "policy brief", "policy"):
        return "Policy"
    if doc_type in ("igo",):
        return "IGO"
    if doc_type in ("news", "news article", "media"):
        return "Media"

    # Return title-cased document_type if no match
    return document_type.title() if document_type else "Other"


def escape_braces(text: str) -> str:
    """Escape braces for ChatPromptTemplate.

    Args:
        text: Text that may contain braces.

    Returns:
        Text with braces doubled for safe template interpolation.
    """
    return (text or "").replace("{", "{{").replace("}", "}}")


def extract_doc_info_from_chunk(
    chunk: Dict, doc_metadata: Dict[str, Dict]
) -> Dict[str, Any]:
    """Extract document info from a RAG chunk, with fallbacks for missing metadata.

    Args:
        chunk: RAG chunk dictionary with document_id and optional document_title.
        doc_metadata: Mapping of doc_uuid to document metadata.

    Returns:
        Dictionary with doc_uuid, doc_id, title, author_short, year, url.
    """
    doc_uuid = str(chunk.get("document_id", ""))
    doc_info = doc_metadata.get(doc_uuid, {})

    # Get title: prefer doc_metadata, fallback to chunk's document_title
    chunk_doc_title = str(chunk.get("document_title", "")) or "Untitled"
    title = doc_info.get("title") or chunk_doc_title

    # Get author: prefer doc_metadata, fallback to extracting from title
    author_short = doc_info.get("author_short")
    if not author_short and title and title != "Untitled":
        parts = title.split()
        if parts:
            author_short = parts[0].rstrip(",.")

    # Get year: prefer doc_metadata, fallback to extracting from title
    year = doc_info.get("year")
    if not year and title:
        year_match = re.search(r"\((\d{4})\)", title)
        if year_match:
            year = int(year_match.group(1))

    return {
        "doc_uuid": doc_uuid,
        "doc_id": doc_info.get("doc_id"),
        "title": title,
        "author_short": author_short or "Unknown",
        "year": year,
        "url": doc_info.get("url"),
    }


def build_langfuse_config(
    state: "SynthesisState",
    tags: List[str],
    extra: Optional[Dict] = None,
) -> Dict:
    """Build Langfuse configuration for LLM calls.

    Args:
        state: Current synthesis workflow state.
        tags: List of tags for the trace.
        extra: Optional extra metadata.

    Returns:
        Configuration dict with callbacks, tags, and metadata.
    """
    handler = state.get("langfuse_handler")
    return {
        "callbacks": [handler] if handler else [],
        "tags": tags,
        "metadata": build_langfuse_metadata(
            tags=tags,
            session_id=state.get("langfuse_session_id"),
            user_id=state.get("policy_user_id"),
            project_id=state.get("project_id"),
            extra=extra,
        ),
    }
