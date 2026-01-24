"""
Evidence strength calculation service.

Calculates evidence strength ratings for interventions based on their
supporting documents' evidence categories, sample sizes, and other factors.

The rating system uses a 0-5 star scale where:
- 5 stars: Multiple systematic reviews/meta-analyses
- 4 stars: Single SR/MA, or multiple RCTs with adequate sample sizes
- 3 stars: Single RCT, or multiple observational studies
- 2 stars: Single observational study, or modelling/policy/qualitative evidence
- 1 star: Expert opinion
- 0 stars: No qualifying evidence

Penalties and caps are applied based on:
- Sample size (N<100 for causal evidence types)
- Single-study limitations
- Evidence density (small evidence base)
"""

import logging
import re
from typing import Optional

from .evidence_category import (
    EVIDENCE_CATEGORY_SCORES,
    EVIDENCE_CATEGORY_RANKS,
    EVIDENCE_CATEGORY_TO_KEY,
    EVIDENCE_CONFIDENCE_THRESHOLD,
    DENSITY_THRESHOLD,
    SMALL_SAMPLE_THRESHOLD,
    CAP_MESSAGES,
    CAUSAL_EVIDENCE_CATEGORIES,
)

logger = logging.getLogger(__name__)


def _parse_sample_size(value: object) -> Optional[int]:
    """Parse sample size from various input formats.

    Args:
        value: Raw sample size value (int, float, str, or other)

    Returns:
        Parsed positive integer, or None if invalid/missing
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        if value <= 0 or value != value:  # NaN check
            return None
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if cleaned.isdigit():
            parsed = int(cleaned)
            return parsed if parsed > 0 else None
        match = re.search(r"\d+", cleaned)
        if match:
            parsed = int(match.group(0))
            return parsed if parsed > 0 else None
    return None


def get_document_sample_size(doc: dict) -> Optional[int]:
    """Extract sample size from a document's extraction results.

    Args:
        doc: Document dict with optional 'extraction_results' field

    Returns:
        Sample size from primary intervention, or None if not available
    """
    extraction_results = doc.get("extraction_results") or {}
    interventions = extraction_results.get("interventions") or []
    if not isinstance(interventions, list) or not interventions:
        return None
    primary = interventions[0]
    if not isinstance(primary, dict):
        return None
    return _parse_sample_size(primary.get("sample_size"))


def get_document_max_sample_size(interventions: list[dict]) -> Optional[int]:
    if not interventions:
        return None
    sample_sizes = []
    for intervention in interventions:
        sample_size = intervention.get("sample_size")
        if sample_size:
            try:
                sample_sizes.append(int(sample_size))
            except (ValueError, TypeError):
                pass
    return max(sample_sizes) if sample_sizes else None


def build_document_evidence_info(
    doc: dict, sample_size: Optional[int], doc_id: Optional[str] = None
) -> dict:
    return {
        "doc_id": doc_id or doc.get("doc_id"),
        "evidence_category": doc.get("evidence_category"),
        "evidence_confidence": doc.get("evidence_confidence"),
        "sample_size": sample_size,
    }


def build_evidence_info_for_docs(
    doc_ids: set[str],
    docs_by_doc_id: dict[str, dict],
) -> list[dict]:
    """Build evidence info list from a set of document IDs.

    Consolidates the pattern of iterating over doc_ids, extracting
    interventions, and building evidence info dicts for use with
    calculate_evidence_strength().

    Args:
        doc_ids: Set of document IDs to process
        docs_by_doc_id: Mapping of doc_id -> document dict

    Returns:
        List of evidence info dicts ready for calculate_evidence_strength()
    """
    result = []
    for doc_id in doc_ids:
        doc = docs_by_doc_id.get(doc_id)
        if not doc:
            continue
        extraction_results = doc.get("extraction_results", {}) or {}
        interventions = extraction_results.get("interventions", [])
        max_sample_size = get_document_max_sample_size(interventions)
        result.append(build_document_evidence_info(doc, max_sample_size, doc_id))
    return result


def deduplicate_interventions(
    detailed_interventions: list[dict],
) -> dict[str, dict]:
    """Deduplicate interventions by name, keeping the highest quality one.

    When multiple interventions share the same name, keeps the one with:
    1. Highest evidence score (primary criterion)
    2. Higher-ranked evidence category (tiebreaker)

    Args:
        detailed_interventions: List of intervention dicts with 'name',
            'evidence_score', and 'evidence_category' fields

    Returns:
        Dict mapping intervention name -> best intervention dict
    """
    unique: dict[str, dict] = {}
    for detail in detailed_interventions:
        name = detail.get("name", "")
        if not name:
            continue
        existing = unique.get(name)
        if not existing:
            unique[name] = detail
            continue
        existing_score = existing.get("evidence_score") or 0
        new_score = detail.get("evidence_score") or 0
        if new_score > existing_score:
            unique[name] = detail
        elif new_score == existing_score:
            existing_rank = EVIDENCE_CATEGORY_RANKS.get(
                existing.get("evidence_category"), 999
            )
            new_rank = EVIDENCE_CATEGORY_RANKS.get(detail.get("evidence_category"), 999)
            if new_rank < existing_rank:
                unique[name] = detail
    return unique


def should_apply_sample_penalty(
    evidence_category: str | None,
    sample_size: Optional[int],
) -> bool:
    """Determine if sample size penalty applies to a document.

    Sample size penalty applies when:
    - Evidence category is causal (RCT or Observational)
    - Sample size is known and less than SMALL_SAMPLE_THRESHOLD (100)

    Args:
        evidence_category: The document's evidence category
        sample_size: The document's sample size (None if unknown)

    Returns:
        True if penalty should be applied
    """
    if evidence_category not in CAUSAL_EVIDENCE_CATEGORIES:
        return False
    if sample_size is None or sample_size == 0:
        return False
    return sample_size < SMALL_SAMPLE_THRESHOLD


def calculate_document_evidence_score(doc: dict) -> dict:
    """Calculate evidence score for a single document with sample size penalty.

    This is the single source of truth for document-level evidence scoring.

    Args:
        doc: Document dict with 'evidence_category' and optionally 'extraction_results'

    Returns:
        Dict with:
        - score: Evidence score (0-5) after any penalties
        - base_score: Original score before penalties
        - penalty_applied: Whether sample size penalty was applied
        - justification: Human-readable explanation
        - sample_size: Extracted sample size (or None)
    """
    evidence_category = doc.get("evidence_category")
    base_score = EVIDENCE_CATEGORY_SCORES.get(evidence_category, 0)
    sample_size = get_document_sample_size(doc)
    penalty_applied = should_apply_sample_penalty(evidence_category, sample_size)

    score = max(0, base_score - 1) if penalty_applied else base_score

    justification = ""
    if evidence_category:
        justification = f"Based on evidence category: {evidence_category}"
        if penalty_applied:
            justification = f"{justification}. Score reduced due to sample size < 100."

    return {
        "score": score,
        "base_score": base_score,
        "penalty_applied": penalty_applied,
        "justification": justification,
        "sample_size": sample_size,
    }


def _check_aggregate_sample_penalty(
    qualifying_docs: list[dict],
    base_rating: int,
) -> tuple[bool, str | None]:
    """Check if aggregate sample size penalty should apply.

    Penalty applies when ALL known sample sizes in causal evidence are small.

    Args:
        qualifying_docs: Documents meeting confidence threshold
        base_rating: The base evidence rating (before penalties)

    Returns:
        Tuple of (should_apply_penalty, cap_type if applied)
    """
    # Only check for causal evidence categories (RCT=4, Observational=3)
    if base_rating not in (3, 4):
        return False, None

    causal_docs = [
        d
        for d in qualifying_docs
        if d.get("evidence_category") in CAUSAL_EVIDENCE_CATEGORIES
    ]

    if not causal_docs:
        return False, None

    # Get known sample sizes from causal documents
    known_samples = [
        d.get("sample_size") for d in causal_docs if d.get("sample_size") is not None
    ]

    if not known_samples:
        # No known sample sizes - don't apply penalty
        return False, None

    # If ANY sample is >= threshold, no penalty
    if any(s >= SMALL_SAMPLE_THRESHOLD for s in known_samples):
        return False, None

    # All known samples are small
    return True, "small_sample"


def calculate_evidence_strength(
    documents_with_evidence: list[dict],
    project_total_docs: int,
) -> dict:
    """Calculate evidence strength rating for an intervention.

    Args:
        documents_with_evidence: List of dicts with 'evidence_category',
            'evidence_confidence', and optionally 'sample_size' and 'doc_id'
        project_total_docs: Total documents in project (for density calculation)

    Returns:
        Dict with:
        - stars: Final rating after all penalties (0-5)
        - base_rating: Rating from evidence categories BEFORE penalties
        - cap_applied: Type of cap/penalty applied (if any)
        - cap_message: Human-readable explanation of cap
        - evidence_mix: Counts by evidence type key
    """
    # Filter to documents meeting confidence threshold
    qualifying_docs = [
        d
        for d in documents_with_evidence
        if (d.get("evidence_confidence") or 0) >= EVIDENCE_CONFIDENCE_THRESHOLD
    ]

    if not qualifying_docs:
        return {
            "stars": 0,
            "base_rating": 0,
            "cap_applied": None,
            "cap_message": "No qualifying evidence",
            "evidence_mix": {},
        }

    # Count by evidence category key
    counts: dict[str, int] = {key: 0 for key in EVIDENCE_CATEGORY_TO_KEY.values()}
    for doc in qualifying_docs:
        cat = doc.get("evidence_category")
        if cat:
            key = EVIDENCE_CATEGORY_TO_KEY.get(cat)
            if key:
                counts[key] += 1

    # Calculate base_rating from raw category scores (BEFORE any penalties)
    base_rating = max(
        (
            EVIDENCE_CATEGORY_SCORES.get(d.get("evidence_category"), 0)
            for d in qualifying_docs
        ),
        default=0,
    )

    # Start with base rating
    final_rating = base_rating
    applied_cap = None

    # Check for aggregate sample size penalty first
    should_penalize, penalty_cap = _check_aggregate_sample_penalty(
        qualifying_docs, base_rating
    )
    if should_penalize:
        final_rating = max(0, final_rating - 1)
        applied_cap = penalty_cap
        logger.info(
            f"Sample size penalty applied: base={base_rating}, "
            f"after_penalty={final_rating}, docs={len(qualifying_docs)}"
        )

    # Calculate other caps (applied after sample size penalty)
    caps = []

    # Single-study caps (based on base_rating, not penalized rating)
    if base_rating == 5 and counts["systematic_review"] == 1:
        caps.append(("single_srma", 4))
    if base_rating == 4 and counts["rct"] == 1:
        caps.append(("single_rct", 3))
    if base_rating == 3 and counts["observational"] == 1:
        caps.append(("single_obs", 2))

    # Density cap
    if project_total_docs > 0 and counts["systematic_review"] == 0:
        density = len(qualifying_docs) / project_total_docs
        if density < DENSITY_THRESHOLD:
            caps.append(("density", 3))

    # Apply strictest cap
    for cap_type, cap_value in caps:
        if cap_value < final_rating:
            final_rating = cap_value
            applied_cap = cap_type

    # Build evidence mix for display (only non-zero counts)
    evidence_mix = {k: v for k, v in counts.items() if v > 0}

    # Log if cap was applied (and not already logged for sample size)
    if applied_cap and applied_cap != "small_sample":
        logger.info(
            f"Evidence cap applied: base={base_rating}, final={final_rating}, "
            f"cap={applied_cap}, docs={len(qualifying_docs)}"
        )

    return {
        "stars": final_rating,
        "base_rating": base_rating,
        "cap_applied": applied_cap,
        "cap_message": CAP_MESSAGES.get(applied_cap) if applied_cap else None,
        "evidence_mix": evidence_mix,
    }
