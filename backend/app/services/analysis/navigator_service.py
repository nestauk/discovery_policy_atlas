"""
Navigator service for computing issue-intervention relationships.

This module handles the pre-computation of shared document mappings and
evidence strength calculations for the issue-intervention navigator.
"""

from .evidence_strength import (
    build_evidence_info_for_docs,
    calculate_evidence_strength,
)


def compute_shared_docs_mappings(
    issue_themes: list[dict],
    intervention_themes: list[dict],
    theme_to_extractions: dict[str, list],
    doc_mappings: dict[str, list[tuple[str, str]]],
) -> tuple[dict[tuple[str, str], list[str]], dict[str, set[str]]]:
    """Compute which documents are shared between issue-intervention pairs.

    For each (issue_theme, intervention_theme) pair, finds documents that
    contain extractions for BOTH the issue AND the intervention.

    Args:
        issue_themes: List of issue theme dicts with 'id' field
        intervention_themes: List of intervention theme dicts with 'id' field
        theme_to_extractions: Mapping of theme_id -> [extraction_ids]
        doc_mappings: Mapping of doc_id -> [(issue_ext_id, intervention_ext_id)]

    Returns:
        Tuple of:
        - issue_intervention_shared_docs: {(issue_id, intervention_id): [doc_ids]}
        - intervention_shared_docs_union: {intervention_id: set(doc_ids)}
    """
    issue_intervention_shared_docs: dict[tuple[str, str], list[str]] = {}
    intervention_shared_docs_union: dict[str, set[str]] = {}

    for issue_theme in issue_themes:
        issue_theme_id = issue_theme["id"]
        issue_extraction_ids = theme_to_extractions.get(issue_theme_id, [])

        for intervention_theme in intervention_themes:
            intervention_theme_id = intervention_theme["id"]
            intervention_extraction_ids = theme_to_extractions.get(
                intervention_theme_id, []
            )

            # Find documents that have both issue and intervention extractions
            pair_shared_docs = []
            for doc_id, mapping_pairs in doc_mappings.items():
                doc_has_issue = any(
                    issue_ext_id in issue_extraction_ids
                    for issue_ext_id, _ in mapping_pairs
                )
                doc_has_intervention = any(
                    intervention_ext_id in intervention_extraction_ids
                    for _, intervention_ext_id in mapping_pairs
                )

                if doc_has_issue and doc_has_intervention:
                    pair_shared_docs.append(doc_id)
                    # Also add to intervention union
                    if intervention_theme_id not in intervention_shared_docs_union:
                        intervention_shared_docs_union[intervention_theme_id] = set()
                    intervention_shared_docs_union[intervention_theme_id].add(doc_id)

            # Store for reuse in navigator building
            if pair_shared_docs:
                issue_intervention_shared_docs[
                    (issue_theme_id, intervention_theme_id)
                ] = pair_shared_docs

    return issue_intervention_shared_docs, intervention_shared_docs_union


def compute_intervention_docs_with_details(
    intervention_themes: list[dict],
    theme_to_extractions: dict[str, list],
    intervention_shared_docs_union: dict[str, set[str]],
    extractions_by_id: dict[str, dict],
    docs_by_id: dict[str, dict],
) -> dict[str, set[str]]:
    """Find which documents will actually produce visible intervention cards.

    Not every document in the shared_docs pool will render a card in the UI.
    This filters to only documents where the extraction name matches an
    intervention in the document's extraction_results.

    This ensures the evidence_mix display aligns with what users actually see.

    Args:
        intervention_themes: List of intervention theme dicts with 'id' field
        theme_to_extractions: Mapping of theme_id -> [extraction_ids]
        intervention_shared_docs_union: {intervention_id: set(doc_ids)} from step 1
        extractions_by_id: Mapping of extraction_id -> extraction dict
        docs_by_id: Mapping of analysis_document_id -> document dict

    Returns:
        {intervention_theme_id: set(doc_ids)} - only docs that will render cards
    """
    intervention_docs_with_details: dict[str, set[str]] = {}

    for intervention_theme in intervention_themes:
        intervention_theme_id = intervention_theme["id"]
        intervention_extraction_ids = theme_to_extractions.get(
            intervention_theme_id, []
        )
        candidate_doc_ids = intervention_shared_docs_union.get(
            intervention_theme_id, set()
        )

        if not candidate_doc_ids or not intervention_extraction_ids:
            continue

        for ext_id in intervention_extraction_ids:
            extraction = extractions_by_id.get(str(ext_id))
            if not extraction or not extraction.get("analysis_document_id"):
                continue

            doc = docs_by_id.get(str(extraction["analysis_document_id"]))
            if not doc:
                continue

            doc_id = doc.get("doc_id")
            if not doc_id or doc_id not in candidate_doc_ids:
                continue

            extraction_results = doc.get("extraction_results", {}) or {}
            interventions_data = extraction_results.get("interventions", [])
            intervention_name = extraction.get(
                "label", (extraction.get("raw_data") or {}).get("name", "")
            )

            if not intervention_name:
                continue

            # Check if the extraction name matches any intervention in the document
            if any(
                intervention_data.get("name") == intervention_name
                or intervention_data.get("label") == intervention_name
                for intervention_data in interventions_data
            ):
                intervention_docs_with_details.setdefault(
                    intervention_theme_id, set()
                ).add(doc_id)

    return intervention_docs_with_details


def compute_intervention_evidence_cache(
    intervention_themes: list[dict],
    intervention_docs_with_details: dict[str, set[str]],
    intervention_shared_docs_union: dict[str, set[str]],
    docs_by_doc_id: dict[str, dict],
    total_docs: int,
) -> dict[str, dict]:
    """Pre-compute evidence strength for each intervention theme.

    Calculates evidence strength once per intervention theme, using the
    union of all shared docs (across all issues). This is cached and
    reused when building the navigator response.

    Args:
        intervention_themes: List of intervention theme dicts with 'id' field
        intervention_docs_with_details: {intervention_id: set(doc_ids)} from step 2
        intervention_shared_docs_union: {intervention_id: set(doc_ids)} from step 1
        docs_by_doc_id: Mapping of doc_id -> document dict
        total_docs: Total number of documents in the project (for density calc)

    Returns:
        {intervention_theme_id: {stars, base_rating, cap_applied, cap_message, evidence_mix}}
    """
    intervention_evidence_cache: dict[str, dict] = {}

    for intervention_theme in intervention_themes:
        intervention_theme_id = intervention_theme["id"]

        # Prefer aligned docs (those that will render cards), fallback to all shared
        aligned_doc_ids = intervention_docs_with_details.get(
            intervention_theme_id, set()
        )
        intervention_doc_ids = aligned_doc_ids or intervention_shared_docs_union.get(
            intervention_theme_id, set()
        )

        # Build evidence info from documents in the union
        documents_with_evidence = build_evidence_info_for_docs(
            intervention_doc_ids, docs_by_doc_id
        )

        # Calculate and cache evidence strength for this intervention theme
        intervention_evidence_cache[
            intervention_theme_id
        ] = calculate_evidence_strength(
            documents_with_evidence,
            total_docs,
        )

    return intervention_evidence_cache
