"""Shared business logic for project data operations.

This module contains functions used by both authenticated and public API endpoints
to avoid code duplication. All functions here are pure data operations without
authentication concerns.
"""

import logging
from typing import Optional

from app.services.vectorization import vectorization_service
from app.utils.geography import COUNTRY_NAME_TO_CODE, COUNTRY_CODE_TO_NAME

logger = logging.getLogger(__name__)


def get_project_documents_list(project_id: str) -> dict:
    """Get all documents for a project with field mapping.

    Args:
        project_id: The project UUID.

    Returns:
        Dict with 'documents' list and 'total' count.
    """
    docs_result = (
        vectorization_service.supabase.table("analysis_documents")
        .select("*")
        .eq("analysis_project_id", project_id)
        .execute()
    )

    documents = []
    for doc in docs_result.data:
        doc_copy = doc.copy()
        if "citation_count" in doc_copy:
            doc_copy["cited_by_count"] = doc_copy["citation_count"]
        documents.append(doc_copy)

    return {"documents": documents, "total": len(documents)}


def aggregate_charts_data(project_id: str) -> dict:
    """Aggregate chart data (by year, country, author) for a project.

    Args:
        project_id: The project UUID.

    Returns:
        Dict with 'documents_by_year', 'documents_by_country', 'documents_by_author'.
    """
    docs_result = (
        vectorization_service.supabase.table("analysis_documents")
        .select("year, source_country, authors")
        .eq("analysis_project_id", project_id)
        .execute()
    )

    if not docs_result.data:
        return {
            "documents_by_year": [],
            "documents_by_country": [],
            "documents_by_author": [],
        }

    year_counts = {}
    country_counts = {}
    author_counts = {}

    for doc in docs_result.data:
        year = doc.get("year")
        if year and year > 1900 and year <= 2025:
            year_counts[year] = year_counts.get(year, 0) + 1

        doc_countries = []
        country_str = doc.get("source_country")
        if country_str and country_str.strip():
            countries = [c.strip() for c in country_str.split(",") if c.strip()]
            for country in countries:
                normalized_country = country
                country_code = COUNTRY_NAME_TO_CODE.get(country)
                if country_code:
                    normalized_country = COUNTRY_CODE_TO_NAME.get(country_code, country)
                country_counts[normalized_country] = (
                    country_counts.get(normalized_country, 0) + 1
                )
                doc_countries.append(normalized_country)

        authors = doc.get("authors", [])
        if isinstance(authors, list):
            for author in authors:
                if author and author.strip():
                    author = author.strip()
                    institutional_keywords = [
                        "Ministry",
                        "Department",
                        "Agency",
                        "Bureau",
                        "Office",
                        "Government",
                        "National",
                        "Federal",
                        "State",
                        "Regional",
                        "Institute",
                        "Center",
                        "Centre",
                        "Council",
                        "Commission",
                        "Authority",
                        "Administration",
                        "Service",
                    ]
                    is_institutional = any(
                        keyword in author for keyword in institutional_keywords
                    )
                    if is_institutional and doc_countries:
                        primary_country = doc_countries[0]
                        author_with_context = f"{author} ({primary_country})"
                        author_counts[author_with_context] = (
                            author_counts.get(author_with_context, 0) + 1
                        )
                    else:
                        author_counts[author] = author_counts.get(author, 0) + 1

    documents_by_year = [
        {"year": year, "count": count} for year, count in sorted(year_counts.items())
    ]

    documents_by_country = [
        {"country": country, "count": count}
        for country, count in sorted(
            country_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]
    ]

    documents_by_author = [
        {"author": author, "count": count}
        for author, count in sorted(
            author_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]
    ]

    return {
        "documents_by_year": documents_by_year,
        "documents_by_country": documents_by_country,
        "documents_by_author": documents_by_author,
    }


def _get_study_type_rank(study_type: Optional[str]) -> int:
    """Convert study type letter to numeric rank for sorting (lower = better).

    g (RCT) is highest quality, empty/unknown is lowest quality.
    """
    if not study_type:
        return 999

    study_type_clean = study_type.strip().lower()
    ranks = {
        "g": 1,  # Randomised controlled trial
        "h": 2,  # Meta-analysis
        "f": 3,  # Quasi-experimental study
        "e": 4,  # Comparison of outcomes in treated group
        "d": 5,  # Study measures outcome pre and post
        "c": 6,  # Cross-sectional with control variables
        "b": 7,  # Study measures outcome pre and post (simpler)
        "a": 8,  # Purely cross-sectional study
        "i": 9,  # Policy recommendation/theoretical modelling
        "j": 10,  # News article/opinion piece/government announcement
    }
    return ranks.get(study_type_clean, 999)


def aggregate_interventions(project_id: str) -> dict:
    """Aggregate intervention data from project documents.

    Args:
        project_id: The project UUID.

    Returns:
        Dict with 'interventions' list and 'total' count.
    """
    docs_result = (
        vectorization_service.supabase.table("analysis_documents")
        .select("*")
        .eq("analysis_project_id", project_id)
        .not_.is_("extraction_results", "null")
        .execute()
    )

    if not docs_result.data:
        return {"interventions": [], "total": 0}

    aggregated_interventions = {}

    for document in docs_result.data:
        extraction_results = document.get("extraction_results", {})
        interventions = extraction_results.get("interventions", [])
        results = extraction_results.get("results", [])

        results_by_intervention = {}
        for result in results:
            intervention_idx = result.get("intervention_idx")
            if intervention_idx is not None:
                if intervention_idx not in results_by_intervention:
                    results_by_intervention[intervention_idx] = []
                results_by_intervention[intervention_idx].append(result)

        for intervention in interventions:
            intervention_name = intervention.get("name", "Unknown Intervention")
            intervention_idx = intervention.get("idx")
            intervention_key = (
                f"{intervention_name}_{intervention.get('type', '')}_"
                f"{intervention.get('country', '')}"
            )

            if intervention_key not in aggregated_interventions:
                aggregated_interventions[intervention_key] = {
                    "name": intervention_name,
                    "type": intervention.get("type", "Unknown"),
                    "country": intervention.get("country", "Unknown"),
                    "description": intervention.get("description", ""),
                    "study_types": [],
                    "sample_sizes": [],
                    "result_count": 0,
                    "results_summary": [],
                    "highest_study_type": None,
                    "highest_study_type_rank": 999,
                    "documents": [],
                }

            aggregated_interventions[intervention_key]["documents"].append(
                {
                    "doc_id": document.get("doc_id"),
                    "title": document.get("title"),
                    "source": document.get("source"),
                    "landing_page_url": document.get("landing_page_url"),
                }
            )

            study_type = intervention.get("study_type")
            if study_type:
                aggregated_interventions[intervention_key]["study_types"].append(
                    study_type
                )
                study_rank = _get_study_type_rank(study_type)
                if (
                    study_rank
                    < aggregated_interventions[intervention_key][
                        "highest_study_type_rank"
                    ]
                ):
                    aggregated_interventions[intervention_key][
                        "highest_study_type"
                    ] = study_type
                    aggregated_interventions[intervention_key][
                        "highest_study_type_rank"
                    ] = study_rank

            sample_size = intervention.get("sample_size")
            if sample_size:
                try:
                    aggregated_interventions[intervention_key]["sample_sizes"].append(
                        int(sample_size)
                    )
                except (ValueError, TypeError):
                    pass

            intervention_results = results_by_intervention.get(intervention_idx, [])
            aggregated_interventions[intervention_key]["result_count"] += len(
                intervention_results
            )

            for result in intervention_results:
                outcome = result.get("outcome_variable", "Unknown outcome")
                direction = result.get("effect_direction", "unknown")
                if outcome and outcome != "Unknown outcome":
                    result_detail = {
                        "outcome": outcome,
                        "direction": direction,
                        "effect_size": result.get("effect_size"),
                        "effect_size_type": result.get("effect_size_type"),
                        "p_value": result.get("p_value"),
                        "uncertainty": result.get("uncertainty"),
                        "result_text": result.get("result_text"),
                        "supporting_quote": result.get("supporting_quote"),
                        "population_measured": result.get("population_measured"),
                        "subgroup_or_dose": result.get("subgroup_or_dose"),
                    }
                    aggregated_interventions[intervention_key][
                        "results_summary"
                    ].append(result_detail)

    interventions_list = []
    for key, intervention_data in aggregated_interventions.items():
        sample_sizes = intervention_data["sample_sizes"]
        if sample_sizes:
            intervention_data["total_sample_size"] = sum(sample_sizes)
            intervention_data["avg_sample_size"] = sum(sample_sizes) / len(sample_sizes)
        else:
            intervention_data["total_sample_size"] = None
            intervention_data["avg_sample_size"] = None

        unique_results = []
        seen_combinations = set()
        for result in intervention_data["results_summary"]:
            combo = (result["outcome"], result["direction"])
            if combo not in seen_combinations:
                unique_results.append(result)
                seen_combinations.add(combo)
            else:
                existing_idx = next(
                    i
                    for i, r in enumerate(unique_results)
                    if (r["outcome"], r["direction"]) == combo
                )
                existing = unique_results[existing_idx]
                existing_details = sum(
                    1
                    for v in [
                        existing.get("effect_size"),
                        existing.get("p_value"),
                        existing.get("uncertainty"),
                    ]
                    if v
                )
                new_details = sum(
                    1
                    for v in [
                        result.get("effect_size"),
                        result.get("p_value"),
                        result.get("uncertainty"),
                    ]
                    if v
                )
                if new_details > existing_details:
                    unique_results[existing_idx] = result

        intervention_data["results_summary"] = unique_results
        del intervention_data["sample_sizes"]
        del intervention_data["study_types"]
        interventions_list.append(intervention_data)

    interventions_list.sort(
        key=lambda x: (x["highest_study_type_rank"], -x["result_count"])
    )

    return {"interventions": interventions_list, "total": len(interventions_list)}


def _load_navigator_base_data(project_id: str) -> Optional[dict]:
    """Load base data needed for building the issue-intervention navigator.

    Returns None if no completed synthesis run exists.

    Args:
        project_id: The project UUID.

    Returns:
        Dict with themes, assignments, extractions, documents, mappings and scores,
        or None if no data available.
    """
    runs_res = (
        vectorization_service.supabase.table("synthesis_runs")
        .select("*")
        .eq("analysis_project_id", project_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not runs_res.data:
        return None

    run_id = runs_res.data[0]["id"]

    themes_res = (
        vectorization_service.supabase.table("synthesis_themes")
        .select("*")
        .eq("synthesis_run_id", run_id)
        .execute()
    )

    if not themes_res.data:
        return None

    themes = themes_res.data
    issue_themes = [t for t in themes if t["theme_type"] == "issue"]
    intervention_themes = [t for t in themes if t["theme_type"] == "intervention"]

    assignments_res = (
        vectorization_service.supabase.table("theme_assignments")
        .select("*")
        .eq("synthesis_run_id", run_id)
        .execute()
    )

    assignments = assignments_res.data or []

    theme_to_extractions = {}
    for assignment in assignments:
        if not assignment:
            continue
        theme_id = assignment.get("synthesis_theme_id")
        extraction_id = assignment.get("extraction_id")
        if theme_id and extraction_id:
            if theme_id not in theme_to_extractions:
                theme_to_extractions[theme_id] = []
            theme_to_extractions[theme_id].append(extraction_id)

    extractions_res = (
        vectorization_service.supabase.table("analysis_extractions")
        .select("*")
        .eq("analysis_project_id", project_id)
        .execute()
    )

    extractions = extractions_res.data or []
    extractions_by_id = {str(e["id"]): e for e in extractions if e and e.get("id")}

    docs_result = (
        vectorization_service.supabase.table("analysis_documents")
        .select("*")
        .eq("analysis_project_id", project_id)
        .execute()
    )

    documents = docs_result.data or []
    docs_by_id = {str(d["id"]): d for d in documents if d and d.get("id")}

    doc_mappings = {}
    doc_scores = {}

    for document in documents:
        if not document:
            continue
        doc_id = document.get("doc_id")
        analysis_doc_id = document.get("id")
        if not analysis_doc_id:
            continue
        analysis_doc_id = str(analysis_doc_id)
        extraction_results = document.get("extraction_results", {})

        if not extraction_results or not doc_id:
            continue

        conclusion = extraction_results.get("conclusion", {}) or {}
        evidence_strength = conclusion.get("evidence_strength", {}) or {}
        predicted_impact = conclusion.get("predicted_impact", {}) or {}

        doc_scores[doc_id] = {
            "impact_score": predicted_impact.get("stars"),
            "evidence_score": evidence_strength.get("stars"),
            "impact_justification": predicted_impact.get("justification", ""),
            "evidence_justification": evidence_strength.get("justification", ""),
        }

        doc_issue_extractions = []
        doc_intervention_extractions = []

        for extraction in extractions:
            if str(extraction.get("analysis_document_id")) == analysis_doc_id:
                if extraction.get("extraction_type") == "issue":
                    doc_issue_extractions.append(extraction["id"])
                elif extraction.get("extraction_type") == "intervention":
                    doc_intervention_extractions.append(extraction["id"])

        doc_mapping_pairs = []
        for issue_ext_id in doc_issue_extractions:
            for intervention_ext_id in doc_intervention_extractions:
                doc_mapping_pairs.append((issue_ext_id, intervention_ext_id))

        if doc_mapping_pairs:
            doc_mappings[doc_id] = doc_mapping_pairs

    return {
        "run_id": run_id,
        "issue_themes": issue_themes,
        "intervention_themes": intervention_themes,
        "theme_to_extractions": theme_to_extractions,
        "extractions": extractions,
        "extractions_by_id": extractions_by_id,
        "documents": documents,
        "docs_by_id": docs_by_id,
        "doc_mappings": doc_mappings,
        "doc_scores": doc_scores,
    }


def build_issue_intervention_navigator(
    project_id: str, include_detailed_interventions: bool = True
) -> dict:
    """Build the issue-intervention navigator structure.

    Args:
        project_id: The project UUID.
        include_detailed_interventions: If True, includes full intervention details
            with results, scores, and source documents. If False, includes only
            name and description.

    Returns:
        Dict with 'issue_themes' list.
    """
    base_data = _load_navigator_base_data(project_id)
    if not base_data:
        return {"issue_themes": []}

    issue_themes = base_data["issue_themes"]
    intervention_themes = base_data["intervention_themes"]
    theme_to_extractions = base_data["theme_to_extractions"]
    extractions_by_id = base_data["extractions_by_id"]
    docs_by_id = base_data["docs_by_id"]
    doc_mappings = base_data["doc_mappings"]
    doc_scores = base_data["doc_scores"]

    navigator_issue_themes = []

    for issue_theme in issue_themes:
        theme_id = issue_theme["id"]
        theme_name = issue_theme["theme_name"]
        theme_description = issue_theme.get("summary_description", "")
        frequency = issue_theme.get("frequency", 0)

        issue_extraction_ids = theme_to_extractions.get(theme_id, [])
        related_interventions = []

        for intervention_theme in intervention_themes:
            intervention_theme_id = intervention_theme["id"]
            intervention_theme_name = intervention_theme["theme_name"]
            intervention_description = intervention_theme.get("summary_description", "")
            intervention_extraction_ids = theme_to_extractions.get(
                intervention_theme_id, []
            )

            shared_docs = []
            impact_scores = []
            evidence_scores = []

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
                    shared_docs.append(doc_id)
                    scores = doc_scores.get(doc_id, {})
                    if scores.get("impact_score") is not None:
                        impact_scores.append(scores["impact_score"])
                    if scores.get("evidence_score") is not None:
                        evidence_scores.append(scores["evidence_score"])

            if shared_docs:
                avg_impact_score = (
                    sum(impact_scores) / len(impact_scores) if impact_scores else None
                )
                avg_evidence_score = (
                    sum(evidence_scores) / len(evidence_scores)
                    if evidence_scores
                    else None
                )

                intervention_freq = intervention_theme.get("frequency", 0)

                if include_detailed_interventions:
                    detailed_interventions = _build_detailed_interventions(
                        intervention_extraction_ids,
                        extractions_by_id,
                        docs_by_id,
                        doc_scores,
                        shared_docs,
                    )
                else:
                    detailed_interventions = _build_simple_interventions(
                        intervention_extraction_ids,
                        extractions_by_id,
                    )

                related_interventions.append(
                    {
                        "theme_id": str(intervention_theme_id),
                        "theme_name": intervention_theme_name,
                        "description": intervention_description,
                        "impact_summary": intervention_theme.get("impact_summary", ""),
                        "frequency": intervention_freq
                        if not include_detailed_interventions
                        else len(shared_docs),
                        "document_count": len(shared_docs),
                        "avg_impact_score": round(avg_impact_score, 1)
                        if avg_impact_score
                        else None,
                        "avg_evidence_score": round(avg_evidence_score, 1)
                        if avg_evidence_score
                        else None,
                        "detailed_interventions": detailed_interventions,
                    }
                )

        related_interventions.sort(
            key=lambda x: x.get("document_count", x.get("frequency", 0)), reverse=True
        )

        issue_extractions = [
            extractions_by_id.get(str(ext_id))
            for ext_id in issue_extraction_ids
            if extractions_by_id.get(str(ext_id))
        ]

        detailed_issues = []
        for ext in issue_extractions:
            if ext:
                detailed_issues.append(
                    {
                        "name": ext.get("label", "Unknown"),
                        "description": ext.get("description", ""),
                    }
                )

        if include_detailed_interventions:
            if related_interventions:
                navigator_issue_themes.append(
                    {
                        "theme_name": theme_name,
                        "description": theme_description,
                        "frequency": frequency,
                        "related_interventions": related_interventions,
                    }
                )
        else:
            navigator_issue_themes.append(
                {
                    "theme_id": str(theme_id),
                    "theme_name": theme_name,
                    "description": theme_description,
                    "frequency": frequency,
                    "detailed_issues": detailed_issues,
                    "related_interventions": related_interventions,
                }
            )

    navigator_issue_themes.sort(key=lambda x: x["frequency"], reverse=True)

    return {"issue_themes": navigator_issue_themes}


def _build_simple_interventions(
    intervention_extraction_ids: list,
    extractions_by_id: dict,
) -> list:
    """Build simple intervention details (name + description only)."""
    detailed_interventions = []
    for ext_id in intervention_extraction_ids:
        ext = extractions_by_id.get(str(ext_id))
        if ext:
            detailed_interventions.append(
                {
                    "name": ext.get("label", "Unknown"),
                    "description": ext.get("description", ""),
                }
            )
    return detailed_interventions


def _build_detailed_interventions(
    intervention_extraction_ids: list,
    extractions_by_id: dict,
    docs_by_id: dict,
    doc_scores: dict,
    shared_docs: list,
) -> list:
    """Build detailed intervention data with results and scores."""
    detailed_interventions = []

    for ext_id in intervention_extraction_ids:
        extraction = extractions_by_id.get(str(ext_id))
        if not extraction or not extraction.get("analysis_document_id"):
            continue

        doc = docs_by_id.get(str(extraction["analysis_document_id"]))
        if not doc or doc.get("doc_id") not in shared_docs:
            continue

        raw_data = extraction.get("raw_data", {})
        intervention_name = extraction.get("label", raw_data.get("name", ""))

        extraction_results = doc.get("extraction_results", {})
        interventions_data = extraction_results.get("interventions", [])
        results_data = extraction_results.get("results", [])

        intervention_results = []
        for i, intervention_data in enumerate(interventions_data):
            if (
                intervention_data.get("name") == intervention_name
                or intervention_data.get("label") == intervention_name
            ):
                for result in results_data:
                    if result.get("intervention_idx") == i:
                        intervention_results.append(
                            {
                                "outcome_variable": result.get("outcome_variable"),
                                "effect_direction": result.get("effect_direction"),
                                "effect_size": result.get("effect_size"),
                                "p_value": result.get("p_value"),
                                "uncertainty": result.get("uncertainty"),
                                "result_text": result.get("result_text"),
                                "population_measured": result.get(
                                    "population_measured"
                                ),
                                "subgroup_or_dose": result.get("subgroup_or_dose"),
                            }
                        )
                break

        doc_id = doc.get("doc_id")
        scores = doc_scores.get(doc_id, {})

        detailed_interventions.append(
            {
                "name": intervention_name,
                "description": extraction.get(
                    "description", raw_data.get("description", "")
                ),
                "type": raw_data.get("type", "Unknown"),
                "country": raw_data.get("country"),
                "study_type": raw_data.get("study_type"),
                "sample_size": raw_data.get("sample_size"),
                "impact_score": scores.get("impact_score"),
                "evidence_score": scores.get("evidence_score"),
                "impact_justification": scores.get("impact_justification", ""),
                "evidence_justification": scores.get("evidence_justification", ""),
                "results": intervention_results,
                "source_documents": [
                    {
                        "doc_id": doc_id,
                        "title": doc.get("title"),
                        "source": doc.get("source"),
                        "landing_page_url": doc.get("landing_page_url"),
                    }
                ],
            }
        )

    unique_interventions = {}
    for detail in detailed_interventions:
        name = detail.get("name", "")
        if name and name not in unique_interventions:
            unique_interventions[name] = detail

    return list(unique_interventions.values())
