"""
Navigator service for computing issue-intervention relationships.

This module handles the pre-computation of shared document mappings for
the issue-intervention navigator.
"""


def compute_shared_docs_mappings(
    issue_themes: list[dict],
    intervention_themes: list[dict],
    theme_to_extractions: dict[str, list],
    doc_mappings: dict[str, list[tuple[str, str]]],
) -> dict[tuple[str, str], list[str]]:
    """Compute which documents are shared between issue-intervention pairs.

    For each (issue_theme, intervention_theme) pair, finds documents that
    contain extractions for BOTH the issue AND the intervention.

    Args:
        issue_themes: List of issue theme dicts with 'id' field
        intervention_themes: List of intervention theme dicts with 'id' field
        theme_to_extractions: Mapping of theme_id -> [extraction_ids]
        doc_mappings: Mapping of doc_id -> [(issue_ext_id, intervention_ext_id)]

    Returns:
        issue_intervention_shared_docs: {(issue_id, intervention_id): [doc_ids]}
    """
    issue_intervention_shared_docs: dict[tuple[str, str], list[str]] = {}

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

            # Store for reuse in navigator building
            if pair_shared_docs:
                issue_intervention_shared_docs[
                    (issue_theme_id, intervention_theme_id)
                ] = pair_shared_docs

    return issue_intervention_shared_docs
