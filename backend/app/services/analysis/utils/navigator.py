"""Utilities for computing issue-intervention document relationships."""

import logging

from app.services.analysis.evidence.strength import (
    calculate_document_evidence_score,
    calculate_evidence_strength,
    get_document_sample_size,
    build_evidence_info_for_docs,
    build_evidence_info_from_detailed_interventions,
    compute_display_evidence_mix_from_detailed,
    deduplicate_interventions,
    parse_sample_size,
)

logger = logging.getLogger(__name__)


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

            if pair_shared_docs:
                issue_intervention_shared_docs[
                    (issue_theme_id, intervention_theme_id)
                ] = pair_shared_docs

    return issue_intervention_shared_docs


def _build_result_detail(result: dict) -> dict:
    """Build standardized result detail dict from an extraction result.

    This handles both legacy field names (effect_direction) and new names (direction).

    Args:
        result: Raw result dict from extraction_results

    Returns:
        Standardized result detail dict
    """
    return {
        "outcome_variable": result.get("outcome_variable"),
        "effect_direction": result.get("direction") or result.get("effect_direction"),
        "effect_size": result.get("effect_size"),
        "effect_size_type": result.get("effect_size_type"),
        "p_value": result.get("p_value"),
        "uncertainty": result.get("uncertainty"),
        "result_text": result.get("result_text"),
        "supporting_quote": result.get("supporting_quote"),
        "population_measured": result.get("population_measured"),
        "subgroup_or_dose": result.get("subgroup_or_dose"),
        "n_studies": result.get("n_studies"),
        "sample_size": result.get("sample_size"),
        "stratum_type": result.get("stratum_type"),
        "stratum_value": result.get("stratum_value"),
        "heterogeneity_I2": result.get("heterogeneity_I2"),
        "tau2": result.get("tau2"),
        "summary_statistic": result.get("summary_statistic"),
        "estimate_level": result.get("estimate_level"),
    }


def build_doc_scores_and_mappings(
    documents: list[dict],
    extractions: list[dict],
) -> tuple[dict[str, dict], dict[str, list[tuple[str, str]]]]:
    """Build document scores and issue-intervention mappings.

    Args:
        documents: List of analysis_documents records
        extractions: List of analysis_extractions records

    Returns:
        Tuple of (doc_scores, doc_mappings) where:
        - doc_scores: {doc_id: {impact_score, evidence_score, sample_size, justifications}}
        - doc_mappings: {doc_id: [(issue_ext_id, intervention_ext_id), ...]}
    """
    doc_scores: dict[str, dict] = {}
    doc_mappings: dict[str, list[tuple[str, str]]] = {}

    for document in documents:
        if not document:
            continue

        doc_id = document.get("doc_id")
        analysis_doc_id = document.get("id")
        if not analysis_doc_id or not doc_id:
            continue

        analysis_doc_id = str(analysis_doc_id)
        extraction_results = document.get("extraction_results", {})

        if not extraction_results:
            continue

        # Get conclusion scores
        conclusion = extraction_results.get("conclusion", {}) or {}
        stored_evidence = conclusion.get("evidence_strength", {}) or {}

        # Prefer stored evidence strength, fallback to recompute
        if stored_evidence:
            evidence_score = stored_evidence.get("stars")
            evidence_justification = stored_evidence.get("justification", "")
            evidence_sample_size = get_document_sample_size(document)
        else:
            evidence_result = calculate_document_evidence_score(document)
            evidence_score = evidence_result["score"]
            evidence_justification = evidence_result.get("justification", "")
            evidence_sample_size = evidence_result.get("sample_size")

        doc_scores[doc_id] = {
            "impact_score": document.get("impact_score"),
            "impact_score_label": document.get("impact_score_label"),
            "impact_score_breakdown": document.get("impact_score_breakdown"),
            "transferability_score": document.get("transferability_score"),
            "transferability_breakdown": document.get("transferability_breakdown"),
            "has_harm_warning": bool(document.get("has_harm_warning")),
            "harm_warning_reason": document.get("harm_warning_reason"),
            "evidence_score": evidence_score,
            "sample_size": evidence_sample_size,
            "impact_justification": document.get("impact_score_label", "") or "",
            "evidence_justification": evidence_justification,
        }

        # Find extraction IDs for issues and interventions in this document
        doc_issue_extractions = []
        doc_intervention_extractions = []

        for extraction in extractions:
            if str(extraction.get("analysis_document_id")) == analysis_doc_id:
                if extraction.get("extraction_type") == "issue":
                    doc_issue_extractions.append(extraction["id"])
                elif extraction.get("extraction_type") == "intervention":
                    doc_intervention_extractions.append(extraction["id"])

        # Create all possible combinations of issue-intervention pairs
        doc_mapping_pairs = []
        for issue_ext_id in doc_issue_extractions:
            for intervention_ext_id in doc_intervention_extractions:
                doc_mapping_pairs.append((issue_ext_id, intervention_ext_id))

        if doc_mapping_pairs:
            doc_mappings[doc_id] = doc_mapping_pairs

    return doc_scores, doc_mappings


def _build_detailed_intervention(
    extraction: dict,
    doc: dict,
    doc_scores: dict[str, dict],
    interventions_data: list[dict],
    results_data: list[dict],
) -> dict:
    """Build a detailed intervention entry for the navigator.

    Args:
        extraction: The intervention extraction record
        doc: The source document
        doc_scores: Pre-computed document scores {doc_id: {...}}
        interventions_data: List of interventions from extraction_results
        results_data: List of results from extraction_results

    Returns:
        Detailed intervention dict with name, description, results, source_documents, etc.
    """
    raw_data = extraction.get("raw_data", {})
    intervention_name = extraction.get("label", raw_data.get("name", ""))
    doc_id = doc.get("doc_id")
    evidence_cat = doc.get("evidence_category")
    evidence_cat_reasoning = doc.get("evidence_category_reasoning")
    scores = doc_scores.get(doc_id, {})
    # Get supporting quote from extraction or raw_data
    supporting_quote = extraction.get("supporting_quote") or raw_data.get(
        "supporting_quote"
    )

    # Find matching intervention and its results by name/label
    intervention_results = []
    for i, intervention_data in enumerate(interventions_data):
        if (
            intervention_data.get("name") == intervention_name
            or intervention_data.get("label") == intervention_name
        ):
            # Find results for this intervention by idx
            for result in results_data:
                if result.get("intervention_idx") == i:
                    intervention_results.append(_build_result_detail(result))
            break

    return {
        "name": intervention_name,
        "description": extraction.get("description", raw_data.get("description", "")),
        "type": raw_data.get("type", "Unknown"),
        "country": raw_data.get("country"),
        "evidence_category": evidence_cat,
        "evidence_category_reasoning": evidence_cat_reasoning,
        "is_systematic_review": evidence_cat == "Systematic Review and Meta-Analysis",
        "sample_size": parse_sample_size(raw_data.get("sample_size")),
        "impact_score": scores.get("impact_score"),
        "impact_score_label": scores.get("impact_score_label"),
        "impact_score_breakdown": scores.get("impact_score_breakdown"),
        "transferability_score": scores.get("transferability_score"),
        "transferability_breakdown": scores.get("transferability_breakdown"),
        "evidence_score": scores.get("evidence_score"),
        "impact_justification": scores.get("impact_justification", ""),
        "evidence_justification": scores.get("evidence_justification", ""),
        "has_harm_warning": scores.get("has_harm_warning", False),
        "harm_warning_reason": scores.get("harm_warning_reason"),
        "supporting_quote": supporting_quote,
        "results": intervention_results,
        "source_documents": [
            {
                "doc_id": doc_id,
                "title": doc.get("title"),
                "source": doc.get("source"),
                "landing_page_url": doc.get("landing_page_url"),
                "evidence_category": evidence_cat,
                "evidence_confidence": doc.get("evidence_confidence"),
                "sample_size": scores.get("sample_size"),
            }
        ],
    }


def build_related_interventions(
    issue_theme: dict,
    intervention_themes: list[dict],
    theme_to_extractions: dict[str, list],
    issue_intervention_shared_docs: dict[tuple[str, str], list[str]],
    extractions_by_id: dict[str, dict],
    docs_by_id: dict[str, dict],
    docs_by_doc_id: dict[str, dict],
    doc_scores: dict[str, dict],
    total_docs: int,
) -> list[dict]:
    """Build related interventions for a single issue theme.

    Args:
        issue_theme: The issue theme dict
        intervention_themes: All intervention themes
        theme_to_extractions: Mapping of theme_id -> [extraction_ids]
        issue_intervention_shared_docs: Pre-computed shared docs mapping
        extractions_by_id: Extractions indexed by id
        docs_by_id: Documents indexed by analysis_document_id
        docs_by_doc_id: Documents indexed by doc_id
        doc_scores: Pre-computed document scores
        total_docs: Total number of documents (for evidence strength calculation)

    Returns:
        List of related intervention dicts, sorted by frequency
    """
    issue_theme_id = issue_theme["id"]
    related_interventions = []

    for intervention_theme in intervention_themes:
        intervention_theme_id = intervention_theme["id"]
        intervention_theme_name = intervention_theme["theme_name"]
        intervention_description = intervention_theme.get("summary_description", "")

        # Get extractions assigned to this intervention theme
        intervention_extraction_ids = theme_to_extractions.get(
            intervention_theme_id, []
        )

        # Get pre-computed shared docs for this pair
        pair_key = (issue_theme_id, intervention_theme_id)
        shared_docs_for_pair = issue_intervention_shared_docs.get(pair_key, [])

        # Only include if there are actual connections
        if not shared_docs_for_pair:
            continue

        # Collect scores for this pair's shared docs
        impact_scores = []
        for doc_id in shared_docs_for_pair:
            scores = doc_scores.get(doc_id, {})
            if scores.get("impact_score") is not None:
                impact_scores.append(scores["impact_score"])

        avg_impact_score = (
            sum(impact_scores) / len(impact_scores) if impact_scores else None
        )

        # Build detailed interventions from extractions
        detailed_interventions = []
        for ext_id in intervention_extraction_ids:
            extraction = extractions_by_id.get(str(ext_id))
            if not extraction or not extraction.get("analysis_document_id"):
                continue

            doc = docs_by_id.get(str(extraction["analysis_document_id"]))
            if not doc or doc.get("doc_id") not in shared_docs_for_pair:
                continue

            extraction_results = doc.get("extraction_results", {})
            detailed_interventions.append(
                _build_detailed_intervention(
                    extraction,
                    doc,
                    doc_scores,
                    extraction_results.get("interventions", []),
                    extraction_results.get("results", []),
                )
            )

        # Deduplicate by name, keeping highest evidence score
        unique_interventions = deduplicate_interventions(detailed_interventions)

        # Calculate issue-specific evidence strength from docs that contributed cards
        used_doc_ids = {
            detail.get("source_documents", [{}])[0].get("doc_id")
            for detail in unique_interventions.values()
            if detail.get("source_documents")
        }
        used_doc_ids.discard(None)

        issue_documents_with_evidence = build_evidence_info_for_docs(
            used_doc_ids, docs_by_doc_id
        )
        issue_evidence_strength = calculate_evidence_strength(
            issue_documents_with_evidence, total_docs
        )

        display_evidence_mix = compute_display_evidence_mix_from_detailed(
            list(unique_interventions.values())
        )

        related_interventions.append(
            {
                "theme_id": intervention_theme_id,
                "theme_name": intervention_theme_name,
                "description": intervention_description,
                "impact_summary": intervention_theme.get("impact_summary", ""),
                "frequency": len(shared_docs_for_pair),
                "avg_impact_score": round(avg_impact_score, 1)
                if avg_impact_score
                else None,
                "issue_display_evidence_mix": display_evidence_mix,
                "issue_stars": issue_evidence_strength["stars"],
                "issue_base_rating": issue_evidence_strength["base_rating"],
                "issue_cap_applied": issue_evidence_strength["cap_applied"],
                "issue_cap_message": issue_evidence_strength["cap_message"],
                "detailed_interventions": list(unique_interventions.values()),
            }
        )

    # Sort by frequency
    related_interventions.sort(key=lambda x: x["frequency"], reverse=True)
    return related_interventions


def aggregate_all_interventions(
    navigator_issue_themes: list[dict],
    docs_by_doc_id: dict[str, dict],
    total_docs: int,
) -> list[dict]:
    """Aggregate interventions across all issues for the all_interventions view.

    Args:
        navigator_issue_themes: Built navigator issue themes with related_interventions
        docs_by_doc_id: Documents indexed by doc_id
        total_docs: Total number of documents

    Returns:
        List of aggregated intervention dicts, sorted by frequency
    """
    all_interventions_map: dict[str, dict] = {}

    for issue_theme in navigator_issue_themes:
        for intervention in issue_theme["related_interventions"]:
            theme_name = intervention["theme_name"]

            if theme_name not in all_interventions_map:
                all_interventions_map[theme_name] = {
                    "theme_name": theme_name,
                    "theme_id": intervention.get("theme_id"),
                    "description": intervention.get("description", ""),
                    "impact_summary": intervention.get("impact_summary", ""),
                    "impact_score": intervention.get("impact_score"),
                    "impact_score_label": intervention.get("impact_score_label"),
                    "impact_score_breakdown": intervention.get(
                        "impact_score_breakdown"
                    ),
                    "transferability_rating": intervention.get(
                        "transferability_rating"
                    ),
                    "transferability_note": intervention.get("transferability_note"),
                    "transferability_breakdown": intervention.get(
                        "transferability_breakdown"
                    ),
                    "outcome_themes": intervention.get("outcome_themes", []),
                    "risk_themes": intervention.get("risk_themes", []),
                    "frequency": 0,
                    "detailed_interventions_by_doc": {},
                    "impact_scores": [],
                }

            entry = all_interventions_map[theme_name]
            entry["frequency"] += intervention.get("frequency", 0)

            if (
                entry.get("impact_score") is None
                and intervention.get("impact_score") is not None
            ):
                entry["impact_score"] = intervention.get("impact_score")
                entry["impact_score_label"] = intervention.get("impact_score_label")
                entry["impact_score_breakdown"] = intervention.get(
                    "impact_score_breakdown"
                )

            if intervention.get("avg_impact_score") is not None:
                entry["impact_scores"].append(intervention["avg_impact_score"])

            if not entry["impact_summary"] and intervention.get("impact_summary"):
                entry["impact_summary"] = intervention["impact_summary"]
            if not entry.get("theme_id") and intervention.get("theme_id"):
                entry["theme_id"] = intervention.get("theme_id")
            if not entry.get("transferability_rating") and intervention.get(
                "transferability_rating"
            ):
                entry["transferability_rating"] = intervention.get(
                    "transferability_rating"
                )
                entry["transferability_note"] = intervention.get("transferability_note")
                entry["transferability_breakdown"] = intervention.get(
                    "transferability_breakdown"
                )
            if not entry.get("outcome_themes") and intervention.get("outcome_themes"):
                entry["outcome_themes"] = intervention.get("outcome_themes", [])
            if not entry.get("risk_themes") and intervention.get("risk_themes"):
                entry["risk_themes"] = intervention.get("risk_themes", [])

            # Deduplicate detailed_interventions by doc_id
            for detail in intervention.get("detailed_interventions", []):
                source_docs = detail.get("source_documents") or []
                doc_id = source_docs[0].get("doc_id") if source_docs else None
                if doc_id and doc_id not in entry["detailed_interventions_by_doc"]:
                    entry["detailed_interventions_by_doc"][doc_id] = detail

    # Build final list with evidence strength
    all_interventions = []

    for theme_name, entry in all_interventions_map.items():
        detailed = list(entry["detailed_interventions_by_doc"].values())

        if not detailed:
            continue

        # Calculate evidence strength from combined cards
        docs_with_evidence = build_evidence_info_from_detailed_interventions(detailed)
        strength = calculate_evidence_strength(docs_with_evidence, total_docs)

        display_mix = compute_display_evidence_mix_from_detailed(detailed)

        impact_scores = entry["impact_scores"]
        avg_impact = sum(impact_scores) / len(impact_scores) if impact_scores else None
        synthesis_impact = entry.get("impact_score")
        shown_impact = synthesis_impact if synthesis_impact is not None else avg_impact

        all_interventions.append(
            {
                "theme_name": theme_name,
                "theme_id": entry.get("theme_id"),
                "description": entry["description"],
                "impact_summary": entry["impact_summary"],
                "impact_score": synthesis_impact,
                "impact_score_label": entry.get("impact_score_label"),
                "impact_score_breakdown": entry.get("impact_score_breakdown"),
                "frequency": entry["frequency"],
                "transferability_rating": entry.get("transferability_rating"),
                "transferability_note": entry.get("transferability_note"),
                "transferability_breakdown": entry.get("transferability_breakdown"),
                "outcome_themes": entry.get("outcome_themes", []),
                "risk_themes": entry.get("risk_themes", []),
                "avg_impact_score": round(shown_impact, 1)
                if shown_impact is not None
                else None,
                "stars": strength["stars"],
                "base_rating": strength["base_rating"],
                "cap_applied": strength["cap_applied"],
                "cap_message": strength["cap_message"],
                "display_evidence_mix": display_mix,
                "detailed_interventions": detailed,
            }
        )

    # Sort by frequency
    all_interventions.sort(key=lambda x: x["frequency"], reverse=True)
    return all_interventions
