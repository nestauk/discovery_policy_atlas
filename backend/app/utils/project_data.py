"""Shared utilities for project data processing.

These functions are used by both authenticated (projects.py) and public (public.py) API endpoints.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.services.vectorization import vectorization_service
from app.services.synthesis.schemas import EvidenceCoverageSnapshot
from app.services.synthesis.logbook import read_cached_summary
from app.services.analysis.evidence.category import (
    EVIDENCE_CATEGORIES,
    EVIDENCE_CATEGORY_RANKS,
    NON_EVIDENCE_CATEGORY,
    is_non_evidence_document,
)
from app.services.analysis.evidence.strength import (
    UNKNOWN_RANK,
    parse_sample_size,
    calculate_evidence_strength,
    get_document_max_sample_size,
    get_document_evidence_details,
    build_document_evidence_info,
)
from app.services.analysis.utils.navigator import (
    compute_shared_docs_mappings,
    build_doc_scores_and_mappings,
    build_related_interventions,
    aggregate_all_interventions,
)
from app.utils.geography import COUNTRY_NAME_TO_CODE, COUNTRY_CODE_TO_NAME

logger = logging.getLogger(__name__)


def parse_json_field(value: Optional[object]) -> Optional[Dict]:
    """Parse a JSON field that may be stored as text."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def is_prevalence_only(payload: Optional[Dict]) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("is_prevalence_only") is True:
        return True
    raw = payload.get("raw_data")
    if isinstance(raw, dict) and raw.get("is_prevalence_only") is True:
        return True
    return False


def filter_prevalence_only_results(results: List[Dict]) -> List[Dict]:
    """Filter out prevalence-only outcomes from result lists."""
    return [result for result in results if not is_prevalence_only(result)]


def filter_prevalence_only_extractions(extractions: List[Dict]) -> List[Dict]:
    """Filter out prevalence-only results from extraction rows."""
    filtered = []
    for extraction in extractions:
        if not isinstance(extraction, dict):
            continue
        if extraction.get("extraction_type") != "result":
            filtered.append(extraction)
            continue
        payload = parse_json_field(extraction.get("payload"))
        if not is_prevalence_only(payload):
            filtered.append(extraction)
    return filtered


def transform_document_for_api(doc: Dict) -> Dict:
    """Transform a document from database format to API response format.

    Adds computed fields like evidence_category_rank, evidence_strength,
    is_evidence, is_relevant_evidence, etc.
    """
    doc_copy = doc.copy()

    if "citation_count" in doc_copy:
        doc_copy["cited_by_count"] = doc_copy["citation_count"]

    evidence_category = doc_copy.get("evidence_category")
    doc_copy["evidence_category_rank"] = EVIDENCE_CATEGORY_RANKS.get(
        evidence_category, UNKNOWN_RANK
    )

    evidence_details = get_document_evidence_details(doc)
    doc_copy["evidence_strength"] = evidence_details["score"]
    if evidence_details["justification"]:
        doc_copy["evidence_strength_justification"] = evidence_details["justification"]
    doc_copy["sample_size"] = evidence_details["sample_size"]

    conclusion = (doc.get("extraction_results") or {}).get("conclusion") or {}

    predicted_impact = conclusion.get("predicted_impact") or {}
    doc_copy["predicted_impact"] = predicted_impact.get("stars")
    doc_copy["predicted_impact_justification"] = predicted_impact.get("justification")

    is_evidence = not is_non_evidence_document(doc)
    doc_copy["is_evidence"] = is_evidence
    is_relevant = doc_copy.get("is_relevant", True)
    doc_copy["is_relevant_evidence"] = is_relevant and is_evidence

    return doc_copy


def get_project_documents_data(project_id: str) -> Dict:
    """Get processed documents for a project.

    Returns all documents including non-relevant and non-evidence documents.
    Each document includes:
    - is_relevant: whether it passed relevance screening
    - is_evidence: whether it's an evidence document (not "Other (Non-evidence documents)")
    - is_relevant_evidence: convenience flag combining both checks

    Returns:
        Dict with 'documents' list, 'total' count, and 'relevant_evidence_count'
    """
    docs_result = (
        vectorization_service.supabase.table("analysis_documents")
        .select("*")
        .eq("analysis_project_id", project_id)
        .execute()
    )

    documents = []
    relevant_evidence_count = 0

    for doc in docs_result.data or []:
        doc_copy = transform_document_for_api(doc)
        if doc_copy.get("is_relevant_evidence"):
            relevant_evidence_count += 1
        documents.append(doc_copy)

    return {
        "documents": documents,
        "total": len(documents),
        "relevant_evidence_count": relevant_evidence_count,
    }


def aggregate_charts_data(docs_data: List[Dict]) -> Dict:
    """Aggregate document data for chart visualizations.

    Args:
        docs_data: List of document dicts with year, source_country, authors, evidence_category

    Returns:
        Dict with documents_by_year, documents_by_country, documents_by_author,
        documents_by_institution, documents_by_evidence_category
    """
    if not docs_data:
        return {
            "documents_by_year": [],
            "documents_by_country": [],
            "documents_by_author": [],
            "documents_by_institution": [],
            "documents_by_evidence_category": [],
        }

    year_counts: Dict[int, int] = {}
    country_counts: Dict[str, int] = {}
    author_counts: Dict[str, int] = {}
    institution_counts: Dict[str, int] = {}
    evidence_category_counts: Dict[str, int] = {}

    for doc in docs_data:
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
                    clean_author = author.strip()
                    author_counts[clean_author] = author_counts.get(clean_author, 0) + 1

        institutions = doc.get("author_institutions", [])
        if isinstance(institutions, list):
            for institution in institutions:
                if institution and isinstance(institution, str) and institution.strip():
                    clean_institution = institution.strip()
                    institution_counts[clean_institution] = (
                        institution_counts.get(clean_institution, 0) + 1
                    )

        evidence_category = doc.get("evidence_category")
        if evidence_category and evidence_category.strip():
            evidence_category_counts[evidence_category] = (
                evidence_category_counts.get(evidence_category, 0) + 1
            )

    documents_by_year = [
        {"year": year, "count": count} for year, count in sorted(year_counts.items())
    ]

    documents_by_country = [
        {"country": country, "count": count}
        for country, count in sorted(
            country_counts.items(), key=lambda x: x[1], reverse=True
        )
    ][:10]

    documents_by_author = [
        {"author": author, "count": count}
        for author, count in sorted(
            author_counts.items(), key=lambda x: x[1], reverse=True
        )
    ][:10]

    documents_by_institution = [
        {"institution": institution, "count": count}
        for institution, count in sorted(
            institution_counts.items(), key=lambda x: x[1], reverse=True
        )
    ][:10]

    evidence_category_order = [
        cat for cat in EVIDENCE_CATEGORIES if cat != NON_EVIDENCE_CATEGORY
    ]
    documents_by_evidence_category = [
        {"category": cat, "count": evidence_category_counts[cat]}
        for cat in evidence_category_order
        if cat in evidence_category_counts
    ]

    return {
        "documents_by_year": documents_by_year,
        "documents_by_country": documents_by_country,
        "documents_by_author": documents_by_author,
        "documents_by_institution": documents_by_institution,
        "documents_by_evidence_category": documents_by_evidence_category,
    }


def get_project_charts_data(project_id: str) -> Dict:
    """Get chart aggregation data for a project."""
    docs_result = (
        vectorization_service.supabase.table("analysis_documents")
        .select("year, source_country, authors, author_institutions, evidence_category")
        .eq("analysis_project_id", project_id)
        .execute()
    )

    return aggregate_charts_data(docs_result.data or [])


def get_outcome_contributions_data(project_id: str, outcome_theme_id: str) -> Dict:
    """Get contributing outcome extractions for a synthesis outcome theme.

    Args:
        project_id: Analysis project UUID.
        outcome_theme_id: Synthesis outcome theme UUID.

    Returns:
        Dict with 'documents' list of contribution documents and their results.

    Raises:
        HTTPException: 404 if outcome theme not found.
    """
    runs_res = (
        vectorization_service.supabase.table("synthesis_runs")
        .select("id")
        .eq("analysis_project_id", project_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not runs_res.data:
        return {"documents": []}

    run_id = runs_res.data[0].get("id")
    if not run_id:
        return {"documents": []}

    theme_res = (
        vectorization_service.supabase.table("synthesis_outcome_themes")
        .select("id, intervention_theme_id")
        .eq("id", outcome_theme_id)
        .eq("synthesis_run_id", run_id)
        .limit(1)
        .execute()
    )
    if not theme_res.data:
        raise HTTPException(status_code=404, detail="Outcome theme not found")

    intervention_theme_id = theme_res.data[0].get("intervention_theme_id")
    if not intervention_theme_id:
        return {"documents": []}

    assignments_res = (
        vectorization_service.supabase.table("outcome_theme_assignments")
        .select("extraction_id, calibrated_magnitude")
        .eq("synthesis_run_id", run_id)
        .eq("synthesis_outcome_theme_id", outcome_theme_id)
        .execute()
    )
    extraction_ids = [
        str(row.get("extraction_id"))
        for row in (assignments_res.data or [])
        if row.get("extraction_id")
    ]
    calibrated_by_extraction_id = {
        str(row.get("extraction_id")): row.get("calibrated_magnitude")
        for row in (assignments_res.data or [])
        if row.get("extraction_id")
    }
    if not extraction_ids:
        return {"documents": []}

    extractions_res = (
        vectorization_service.supabase.table("analysis_extractions")
        .select("id, analysis_document_id, label, raw_data")
        .in_("id", extraction_ids)
        .execute()
    )
    extractions = filter_prevalence_only_extractions(extractions_res.data or [])
    if not extractions:
        return {"documents": []}

    doc_ids = list(
        {
            str(ext.get("analysis_document_id"))
            for ext in extractions
            if ext.get("analysis_document_id")
        }
    )
    docs_by_id: Dict[str, Dict] = {}
    if doc_ids:
        docs_res = (
            vectorization_service.supabase.table("analysis_documents")
            .select(
                "id, doc_id, title, source, landing_page_url, doi, year, evidence_category, extraction_results"
            )
            .in_("id", doc_ids)
            .execute()
        )
        docs_by_id = {
            str(doc.get("id")): doc
            for doc in (docs_res.data or [])
            if doc and doc.get("id")
        }

    intervention_assignments_res = (
        vectorization_service.supabase.table("theme_assignments")
        .select("extraction_id")
        .eq("synthesis_run_id", run_id)
        .eq("synthesis_theme_id", intervention_theme_id)
        .execute()
    )
    intervention_extraction_ids = {
        str(row.get("extraction_id"))
        for row in (intervention_assignments_res.data or [])
        if row.get("extraction_id")
    }

    intervention_extractions_res = (
        vectorization_service.supabase.table("analysis_extractions")
        .select("id, analysis_document_id, raw_data")
        .eq("analysis_project_id", project_id)
        .eq("extraction_type", "intervention")
        .in_("analysis_document_id", doc_ids)
        .execute()
    )
    intervention_by_doc_idx: Dict[tuple, str] = {}
    for extraction in intervention_extractions_res.data or []:
        raw = extraction.get("raw_data") or {}
        doc_id = str(extraction.get("analysis_document_id") or "")
        idx = raw.get("idx")
        if doc_id and isinstance(idx, int):
            intervention_by_doc_idx[(doc_id, idx)] = str(extraction.get("id"))

    documents_map: Dict[str, Dict] = {}
    for extraction in extractions:
        analysis_document_id = str(extraction.get("analysis_document_id") or "")
        raw = extraction.get("raw_data") or {}
        doc = docs_by_id.get(analysis_document_id, {})
        intervention_idx = raw.get("intervention_idx")
        if not isinstance(intervention_idx, int):
            continue
        intervention_extraction_id = intervention_by_doc_idx.get(
            (analysis_document_id, intervention_idx)
        )
        if not intervention_extraction_id:
            continue
        if intervention_extraction_id not in intervention_extraction_ids:
            continue

        effect_dir = (raw.get("effect_direction") or "").lower()
        is_beneficial = raw.get("is_beneficial")
        is_contributing = False
        if effect_dir in ("null", "none", "no effect"):
            is_contributing = True
        elif is_beneficial is True or is_beneficial is False:
            is_contributing = True
        elif effect_dir in ("increase", "decrease"):
            is_contributing = True
        if not is_contributing:
            continue

        entry = documents_map.setdefault(
            analysis_document_id,
            {
                "analysis_document_id": analysis_document_id,
                "doc_id": doc.get("doc_id"),
                "title": doc.get("title"),
                "source": doc.get("source"),
                "landing_page_url": doc.get("landing_page_url"),
                "doi": doc.get("doi"),
                "year": doc.get("year"),
                "evidence_category": doc.get("evidence_category"),
                "evidence_score": None,
                "results": [],
            },
        )

        entry["results"].append(
            {
                "extraction_id": extraction.get("id"),
                "outcome_variable": raw.get("outcome_variable")
                or extraction.get("label"),
                "effect_direction": raw.get("effect_direction"),
                "magnitude_estimate": raw.get("magnitude_estimate"),
                "calibrated_magnitude": calibrated_by_extraction_id.get(
                    str(extraction.get("id") or "")
                ),
                "effect_size": raw.get("effect_size"),
                "effect_size_type": raw.get("effect_size_type"),
                "uncertainty": raw.get("uncertainty"),
                "p_value": raw.get("p_value"),
                "population_measured": raw.get("population_measured"),
                "subgroup_or_dose": raw.get("subgroup_or_dose"),
                "causality_claim": raw.get("causality_claim"),
                "is_primary": raw.get("is_primary"),
                "is_beneficial": raw.get("is_beneficial"),
                "result_text": raw.get("result_text"),
                "supporting_quote": raw.get("supporting_quote"),
            }
        )

    for doc_id, entry in documents_map.items():
        doc = docs_by_id.get(doc_id)
        if doc:
            entry["evidence_score"] = get_document_evidence_details(doc)["score"]

    documents = list(documents_map.values())
    documents.sort(key=lambda doc: (doc.get("title") or ""))
    return {"documents": documents}


def build_result_detail(result: Dict) -> Dict:
    """Build a result detail dict from a result extraction."""
    outcome = result.get("outcome_variable", "Unknown outcome")
    direction = result.get("direction") or result.get("effect_direction", "unknown")

    return {
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
        "n_studies": result.get("n_studies"),
        "sample_size": result.get("sample_size"),
        "stratum_type": result.get("stratum_type"),
        "stratum_value": result.get("stratum_value"),
        "heterogeneity_I2": result.get("heterogeneity_I2"),
        "tau2": result.get("tau2"),
        "summary_statistic": result.get("summary_statistic"),
        "estimate_level": result.get("estimate_level"),
    }


def deduplicate_results_summary(results_summary: List[Dict]) -> List[Dict]:
    """Deduplicate results by outcome/direction, keeping the one with most details."""
    unique_results = []
    seen_combinations: set = set()

    for result in results_summary:
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

    return unique_results


def get_project_interventions_data(project_id: str) -> Dict:
    """Get aggregated interventions for a project.

    Returns:
        Dict with 'interventions' list and 'total' count
    """
    docs_result = (
        vectorization_service.supabase.table("analysis_documents")
        .select(
            "doc_id, title, source, landing_page_url, "
            "evidence_category, evidence_confidence, extraction_results"
        )
        .eq("analysis_project_id", project_id)
        .not_.is_("extraction_results", "null")
        .execute()
    )

    if not docs_result.data:
        return {"interventions": [], "total": 0}

    project_total_docs = len(docs_result.data)
    aggregated_interventions: Dict[str, Dict] = {}
    accumulator: Dict[str, Dict] = {}

    for document in docs_result.data:
        extraction_results = document.get("extraction_results", {})
        interventions = extraction_results.get("interventions", [])
        results = filter_prevalence_only_results(extraction_results.get("results", []))

        results_by_intervention: Dict[int, List] = {}
        for result in results:
            intervention_idx = result.get("intervention_idx")
            if intervention_idx is not None:
                if intervention_idx not in results_by_intervention:
                    results_by_intervention[intervention_idx] = []
                results_by_intervention[intervention_idx].append(result)

        for intervention in interventions:
            intervention_name = intervention.get("name", "Unknown Intervention")
            intervention_idx = intervention.get("idx")
            intervention_key = f"{intervention_name}_{intervention.get('type', '')}_{intervention.get('country', '')}"

            if intervention_key not in aggregated_interventions:
                evidence_cat = document.get("evidence_category")
                aggregated_interventions[intervention_key] = {
                    "name": intervention_name,
                    "type": intervention.get("type", "Unknown"),
                    "country": intervention.get("country", "Unknown"),
                    "description": intervention.get("description", ""),
                    "evidence_category": evidence_cat,
                    "evidence_category_rank": EVIDENCE_CATEGORY_RANKS.get(
                        evidence_cat, UNKNOWN_RANK
                    )
                    if evidence_cat
                    else UNKNOWN_RANK,
                    "is_systematic_review": evidence_cat
                    == "Systematic Review and Meta-Analysis",
                    "result_count": 0,
                    "results_summary": [],
                    "documents": [],
                }
                accumulator[intervention_key] = {
                    "sample_sizes": [],
                    "seen_doc_ids": set(),
                    "documents_with_evidence": [],
                }

            aggregated_interventions[intervention_key]["documents"].append(
                {
                    "doc_id": document.get("doc_id"),
                    "title": document.get("title"),
                    "source": document.get("source"),
                    "landing_page_url": document.get("landing_page_url"),
                }
            )

            sample_size_int = parse_sample_size(intervention.get("sample_size"))
            if sample_size_int is not None:
                accumulator[intervention_key]["sample_sizes"].append(sample_size_int)

            doc_id = document.get("doc_id")
            if doc_id not in accumulator[intervention_key]["seen_doc_ids"]:
                accumulator[intervention_key]["seen_doc_ids"].add(doc_id)
                max_sample_size = get_document_max_sample_size(interventions)
                accumulator[intervention_key]["documents_with_evidence"].append(
                    build_document_evidence_info(document, max_sample_size, doc_id)
                )

            intervention_results = results_by_intervention.get(intervention_idx, [])
            aggregated_interventions[intervention_key]["result_count"] += len(
                intervention_results
            )

            for result in intervention_results:
                outcome = result.get("outcome_variable", "Unknown outcome")
                if outcome and outcome != "Unknown outcome":
                    aggregated_interventions[intervention_key][
                        "results_summary"
                    ].append(build_result_detail(result))

    interventions_list = []
    for intervention_key, intervention_data in aggregated_interventions.items():
        acc = accumulator[intervention_key]
        sample_sizes = acc["sample_sizes"]

        if sample_sizes:
            intervention_data["total_sample_size"] = sum(sample_sizes)
            intervention_data["avg_sample_size"] = sum(sample_sizes) / len(sample_sizes)
        else:
            intervention_data["total_sample_size"] = None
            intervention_data["avg_sample_size"] = None

        intervention_data["results_summary"] = deduplicate_results_summary(
            intervention_data["results_summary"]
        )

        evidence_strength = calculate_evidence_strength(
            acc["documents_with_evidence"],
            project_total_docs,
        )
        intervention_data["stars"] = evidence_strength["stars"]
        intervention_data["base_rating"] = evidence_strength["base_rating"]
        intervention_data["cap_applied"] = evidence_strength["cap_applied"]
        intervention_data["cap_message"] = evidence_strength["cap_message"]
        intervention_data["evidence_mix"] = evidence_strength["evidence_mix"]

        interventions_list.append(intervention_data)

    interventions_list.sort(
        key=lambda x: (-x["stars"], x["evidence_category_rank"], -x["result_count"])
    )

    return {"interventions": interventions_list, "total": len(interventions_list)}


def get_navigator_overview_data(project_id: str) -> Dict:
    """Lightweight overview for the interventions navigator.

    Uses a single PostgREST embedded query that joins
    themes → assignments → extractions → documents server-side via foreign keys.
    This avoids multiple large table scans and lets the DB use FK indexes.

    Args:
        project_id: The analysis project ID.

    Returns:
        Dict with 'interventions' overview list and 'issue_themes' name list.
    """
    sb = vectorization_service.supabase

    runs_res = (
        sb.table("synthesis_runs")
        .select("id")
        .eq("analysis_project_id", project_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not runs_res.data:
        return {"interventions": [], "issue_themes": []}

    run_id = runs_res.data[0]["id"]

    # Single embedded query: themes → assignments → extractions → documents
    # PostgREST follows FK relationships server-side, avoiding 4 separate round trips.
    themes_res = (
        sb.table("synthesis_themes")
        .select(
            "id, theme_type, theme_name, summary_description, frequency, "
            "impact_score, impact_score_label, "
            "theme_assignments("
            "  extraction_id, "
            "  analysis_extractions("
            "    analysis_document_id, "
            "    analysis_documents(doc_id, evidence_category, evidence_confidence)"
            "  )"
            ")"
        )
        .eq("synthesis_run_id", run_id)
        .in_("theme_type", ["intervention", "issue"])
        .execute()
    )
    themes = themes_res.data or []

    # Total project docs for density cap calculation
    docs_count_res = (
        sb.table("analysis_documents")
        .select("id", count="exact")
        .eq("analysis_project_id", project_id)
        .limit(0)
        .execute()
    )
    total_docs = (
        docs_count_res.count
        if hasattr(docs_count_res, "count") and docs_count_res.count is not None
        else 0
    )

    overview_interventions = []
    issue_theme_names = []

    for theme in themes:
        theme_type = theme.get("theme_type")

        if theme_type == "issue":
            issue_theme_names.append(
                {
                    "theme_name": theme["theme_name"],
                    "frequency": theme.get("frequency", 0),
                }
            )
            continue

        if theme_type != "intervention":
            continue

        # Walk the embedded assignments → extractions → documents
        doc_evidence: Dict[str, Dict] = {}
        for assignment in theme.get("theme_assignments") or []:
            extraction = assignment.get("analysis_extractions")
            if not extraction:
                continue
            doc = extraction.get("analysis_documents")
            if not doc or not doc.get("doc_id"):
                continue
            did = doc["doc_id"]
            if did not in doc_evidence:
                doc_evidence[did] = {
                    "doc_id": did,
                    "evidence_category": doc.get("evidence_category"),
                    "evidence_confidence": doc.get("evidence_confidence", 1.0),
                }

        if not doc_evidence:
            continue

        strength = calculate_evidence_strength(list(doc_evidence.values()), total_docs)
        overview_interventions.append(
            {
                "theme_name": theme["theme_name"],
                "description": theme.get("summary_description", ""),
                "frequency": len(doc_evidence),
                "avg_impact_score": theme.get("impact_score"),
                "avg_evidence_score": strength["stars"],
                "study_count": len(doc_evidence),
            }
        )

    overview_interventions.sort(key=lambda x: x["frequency"], reverse=True)

    return {
        "interventions": overview_interventions,
        "issue_themes": issue_theme_names,
    }


def get_navigator_data(project_id: str) -> Dict:
    """Get issue-intervention navigator data for a project.

    Returns:
        Dict with 'issue_themes' list and 'all_interventions' list
    """
    runs_res = (
        vectorization_service.supabase.table("synthesis_runs")
        .select("id")
        .eq("analysis_project_id", project_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not runs_res.data:
        return {"issue_themes": []}

    run_id = runs_res.data[0]["id"]

    themes_res = (
        vectorization_service.supabase.table("synthesis_themes")
        .select("*")
        .eq("synthesis_run_id", run_id)
        .execute()
    )

    if not themes_res.data:
        return {"issue_themes": []}

    themes = themes_res.data
    issue_themes = [t for t in themes if t["theme_type"] == "issue"]
    intervention_themes = [t for t in themes if t["theme_type"] == "intervention"]
    risk_theme_rows = [t for t in themes if t["theme_type"] == "risk"]

    intervention_themes_by_id = {
        t.get("id"): t for t in intervention_themes if t.get("id")
    }
    intervention_impact_by_id = {
        t.get("id"): {
            "impact_score": t.get("impact_score"),
            "impact_score_label": t.get("impact_score_label"),
            "impact_score_breakdown": parse_json_field(t.get("impact_score_breakdown")),
        }
        for t in intervention_themes
        if t.get("id")
    }

    outcome_themes_res = (
        vectorization_service.supabase.table("synthesis_outcome_themes")
        .select(
            "id, synthesis_run_id, outcome_name, outcome_description, "
            "effect_consensus, positive_count, negative_count, null_count, "
            "sample_effect_sizes, frequency, source_doc_ids, "
            "verdict_label, verdict_description, discord_flag, discord_reason, "
            "predicted_magnitude, magnitude_detail, "
            "primary_causal_mechanism, causal_mechanism_detail, "
            "intervention_theme_id"
        )
        .eq("synthesis_run_id", run_id)
        .execute()
    )
    outcome_themes = outcome_themes_res.data or []
    for outcome in outcome_themes:
        outcome["magnitude_detail"] = parse_json_field(outcome.get("magnitude_detail"))
        outcome["causal_mechanism_detail"] = parse_json_field(
            outcome.get("causal_mechanism_detail")
        )

    outcomes_by_intervention: Dict[str, List[Dict]] = {}
    for outcome in outcome_themes:
        intervention_id = outcome.get("intervention_theme_id")
        if intervention_id:
            outcomes_by_intervention.setdefault(intervention_id, []).append(outcome)

    risks_by_intervention: Dict[str, List[Dict]] = {}
    risk_theme_ids = [t.get("id") for t in risk_theme_rows if t.get("id")]
    links_by_theme: Dict[str, List[Dict]] = {}

    if risk_theme_ids:
        links_res = (
            vectorization_service.supabase.table("theme_intervention_links")
            .select("theme_id, intervention_theme_id, link_strength")
            .in_("theme_id", risk_theme_ids)
            .execute()
        )
        for link in links_res.data or []:
            links_by_theme.setdefault(link["theme_id"], []).append(
                {
                    "intervention_theme_id": link["intervention_theme_id"],
                    "link_strength": link["link_strength"],
                }
            )

    for risk_theme in risk_theme_rows:
        linked_interventions = links_by_theme.get(risk_theme.get("id"), [])
        if linked_interventions:
            risk_theme["linked_interventions"] = linked_interventions
            for linked in linked_interventions:
                risks_by_intervention.setdefault(
                    linked["intervention_theme_id"], []
                ).append(risk_theme)
            continue
        linked_id = risk_theme.get("linked_intervention_theme_id")
        if linked_id:
            risks_by_intervention.setdefault(linked_id, []).append(risk_theme)

    assignments_res = (
        vectorization_service.supabase.table("theme_assignments")
        .select("synthesis_theme_id, extraction_id")
        .eq("synthesis_run_id", run_id)
        .execute()
    )
    assignments = assignments_res.data or []

    theme_to_extractions: Dict[str, List] = {}
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
        .select(
            "id, analysis_document_id, extraction_type, label, description, supporting_quote, raw_data"
        )
        .eq("analysis_project_id", project_id)
        .execute()
    )
    extractions = extractions_res.data or []
    extractions_by_id = {str(e["id"]): e for e in extractions if e and e.get("id")}

    docs_result = (
        vectorization_service.supabase.table("analysis_documents")
        .select(
            "id, doc_id, title, source, landing_page_url, year, evidence_category, "
            "evidence_category_reasoning, evidence_confidence, extraction_results, "
            "impact_score, impact_score_label, impact_score_breakdown, "
            "transferability_score, transferability_breakdown, "
            "has_harm_warning, harm_warning_reason"
        )
        .eq("analysis_project_id", project_id)
        .execute()
    )
    documents = docs_result.data or []
    docs_by_id = {str(d["id"]): d for d in documents if d and d.get("id")}
    docs_by_doc_id = {d.get("doc_id"): d for d in documents if d and d.get("doc_id")}

    doc_scores, doc_mappings = build_doc_scores_and_mappings(documents, extractions)

    issue_intervention_shared_docs = compute_shared_docs_mappings(
        issue_themes,
        intervention_themes,
        theme_to_extractions,
        doc_mappings,
    )

    navigator_issue_themes = []

    for issue_theme in issue_themes:
        theme_name = issue_theme["theme_name"]
        theme_description = issue_theme.get("summary_description", "")
        frequency = issue_theme.get("frequency", 0)

        related_interventions = build_related_interventions(
            issue_theme,
            intervention_themes,
            theme_to_extractions,
            issue_intervention_shared_docs,
            extractions_by_id,
            docs_by_id,
            docs_by_doc_id,
            doc_scores,
            len(documents),
        )

        for intervention in related_interventions:
            theme_id = intervention.get("theme_id")
            if not theme_id:
                continue

            theme = intervention_themes_by_id.get(theme_id)
            if theme:
                intervention["transferability_rating"] = theme.get(
                    "transferability_rating"
                )
                intervention["transferability_note"] = theme.get("transferability_note")
                intervention["transferability_breakdown"] = theme.get(
                    "transferability_breakdown"
                )

            impact_info = intervention_impact_by_id.get(theme_id)
            if impact_info:
                intervention["impact_score"] = impact_info.get("impact_score")
                intervention["impact_score_label"] = impact_info.get(
                    "impact_score_label"
                )
                intervention["impact_score_breakdown"] = impact_info.get(
                    "impact_score_breakdown"
                )

            intervention["outcome_themes"] = outcomes_by_intervention.get(theme_id, [])
            intervention["risk_themes"] = risks_by_intervention.get(theme_id, [])

        if related_interventions:
            navigator_issue_themes.append(
                {
                    "theme_name": theme_name,
                    "description": theme_description,
                    "frequency": frequency,
                    "related_interventions": related_interventions,
                }
            )

    navigator_issue_themes.sort(key=lambda x: x["frequency"], reverse=True)

    all_interventions = aggregate_all_interventions(
        navigator_issue_themes, docs_by_doc_id, len(documents)
    )

    return {
        "issue_themes": navigator_issue_themes,
        "all_interventions": all_interventions,
    }


async def get_summary_with_counts(project_id: str) -> Tuple[Optional[object], int, int]:
    """Get cached summary and compute document counts.

    Returns:
        Tuple of (cached_summary, total_screened, total_synthesised)
    """
    cached = await read_cached_summary(project_id)

    if not cached:
        return None, 0, 0

    try:
        screened_res = (
            vectorization_service.supabase.table("analysis_documents")
            .select("id", count="exact")
            .eq("analysis_project_id", project_id)
            .execute()
        )
        total_screened = (
            screened_res.count
            if hasattr(screened_res, "count")
            else len(screened_res.data or [])
        )

        synthesised_res = (
            vectorization_service.supabase.table("analysis_documents")
            .select("id", count="exact")
            .eq("analysis_project_id", project_id)
            .eq("is_relevant", True)
            .execute()
        )
        total_synthesised = (
            synthesised_res.count
            if hasattr(synthesised_res, "count")
            else len(synthesised_res.data or [])
        )

        if cached.evidence_coverage:
            cached.evidence_coverage.total_screened = total_screened
            cached.evidence_coverage.total_synthesised = total_synthesised
        else:
            cached.evidence_coverage = EvidenceCoverageSnapshot(
                total_screened=total_screened,
                total_synthesised=total_synthesised,
            )

        return cached, total_screened, total_synthesised
    except Exception as e:
        logger.warning(
            f"Failed to compute screened/synthesised counts for project {project_id}: {e}"
        )
        return cached, 0, 0
