"""
Data loading nodes for the synthesis workflow.

Phase 1: Load raw extractions from database and create canonical concepts.
"""

from __future__ import annotations

from typing import Dict, List

from app.services.vectorization import vectorization_service
from app.services.synthesis.state import SynthesisState, Concept
from app.services.synthesis.utils import normalize_study_type
from app.services.analysis.evidence.strength import (
    get_document_evidence_score,
    calculate_document_evidence_score,
)


def clean_null_string(value: object) -> str:
    """Normalise literal null strings to empty text.

    Args:
        value: Raw value from extraction payloads.

    Returns:
        Cleaned string with null-like values removed.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in {"null", "none", "n/a", "na"}:
            return ""
        return stripped
    return str(value)


async def load_raw_extractions(state: SynthesisState) -> SynthesisState:
    """Load extractions and document metadata from database.

    Args:
        state: Current workflow state with project_id.

    Returns:
        State update with raw_extractions, research_question, doc_metadata.
    """
    print("--- Loading Extractions & Documents ---")
    project_id = state.get("project_id", "")
    if not project_id:
        return {
            "raw_extractions": [],
            "research_question": "Not specified",
            "doc_metadata": {},
        }

    supabase = vectorization_service.supabase
    theme_assignment_map = await load_theme_assignments(project_id, supabase)

    # Fetch research question + user search intent (population/outcome)
    proj_res = (
        supabase.table("analysis_projects")
        .select("title, query, search_query")
        .eq("id", project_id)
        .execute()
    )
    research_question = (
        (proj_res.data[0].get("title") or proj_res.data[0].get("query"))
        if proj_res.data
        else "Not specified"
    )

    search_query = (proj_res.data[0].get("search_query") or {}) if proj_res.data else {}
    target_population = search_query.get("population") or []
    target_outcomes = search_query.get("outcome") or []
    target_geography = search_query.get("geography") or ["UK"]
    target_inner_setting = search_query.get("inner_setting") or []
    implementation_constraints = search_query.get("implementation_constraints") or {}
    # Normalise to list[str]
    if isinstance(target_population, str):
        target_population = [target_population]
    if isinstance(target_outcomes, str):
        target_outcomes = [target_outcomes]
    if isinstance(target_geography, str):
        target_geography = [target_geography]
    if isinstance(target_inner_setting, str):
        target_inner_setting = [target_inner_setting]

    # Fetch document metadata including extraction_results for scores
    docs_res = (
        supabase.table("analysis_documents")
        .select(
            "id, doc_id, title, year, authors, landing_page_url, pdf_url, source, document_type, extraction_results, evidence_category, top_line, is_relevant, impact_score, impact_score_label, impact_score_breakdown, transferability_score, transferability_breakdown, has_harm_warning, harm_warning_reason"
        )
        .eq("analysis_project_id", project_id)
        .execute()
    )

    doc_metadata: Dict[str, Dict] = {}
    doc_scores: Dict[str, Dict] = {}
    for doc in docs_res.data or []:
        doc_uuid = str(doc.get("id"))
        authors = doc.get("authors") or []
        author_short = None
        if authors and isinstance(authors, list):
            parts = str(authors[0]).strip().split()
            if parts:
                author_short = parts[-1]
        doc_metadata[doc_uuid] = {
            "doc_id": doc.get("doc_id"),
            "title": doc.get("title") or "",
            "top_line": doc.get("top_line") or "",
            "year": doc.get("year"),
            "author_short": author_short,
            "url": doc.get("landing_page_url") or doc.get("pdf_url"),
            "source": doc.get("source"),
            "document_type": doc.get("document_type"),
            "evidence_category": doc.get("evidence_category"),
            "source_country": clean_null_string(doc.get("source_country")),
            "is_relevant": bool(doc.get("is_relevant"))
            if doc.get("is_relevant") is not None
            else None,
        }

        # Get evidence and impact scores (DB column preferred, fallback to calculation)
        evidence_result = calculate_document_evidence_score(doc)

        doc_scores[doc_uuid] = {
            "evidence_score": get_document_evidence_score(
                doc
            ),  # 0-5 with sample size penalty
            "impact_score": doc.get("impact_score"),
            "impact_score_label": doc.get("impact_score_label"),
            "impact_score_breakdown": doc.get("impact_score_breakdown"),
            "transferability_score": doc.get("transferability_score"),
            "transferability_breakdown": doc.get("transferability_breakdown"),
            "evidence_category": doc.get("evidence_category"),
            "evidence_justification": evidence_result["justification"],
            "impact_justification": "",
            "has_harm_warning": bool(doc.get("has_harm_warning")),
            "harm_warning_reason": doc.get("harm_warning_reason"),
        }

    # Fetch extractions
    res = (
        supabase.table("analysis_extractions")
        .select(
            "id, analysis_document_id, extraction_type, label, description, raw_data"
        )
        .eq("analysis_project_id", project_id)
        .execute()
    )

    # Build extraction_id -> doc_uuid mapping
    extraction_to_doc: Dict[str, str] = {}
    for row in res.data or []:
        ext_id = str(row.get("id") or "")
        doc_uuid = str(row.get("analysis_document_id") or "")
        if ext_id and doc_uuid:
            extraction_to_doc[ext_id] = doc_uuid

    def to_uniform(row: Dict) -> Dict:
        """Convert extraction row to uniform format."""
        et = str(row.get("extraction_type") or "")
        raw = row.get("raw_data") or {}
        doc_uuid = str(row.get("analysis_document_id") or "")
        doc_id = doc_metadata.get(doc_uuid, {}).get("doc_id") if doc_uuid else None
        base = {
            "id": str(row.get("id")),
            "doc_uuid": doc_uuid,
            "doc_id": doc_id,
        }
        if et == "intervention":
            raw_st = clean_null_string(raw.get("study_type") or raw.get("type"))
            return {
                **base,
                "type": "intervention",
                "intervention_name": clean_null_string(
                    row.get("label") or raw.get("name")
                ),
                "intervention_idx": raw.get("idx"),
                "study_type": normalize_study_type(str(raw_st)),
                "country": clean_null_string(raw.get("country")),
                "description": clean_null_string(
                    row.get("description") or raw.get("description")
                ),
                "supporting_quote": clean_null_string(raw.get("supporting_quote")),
                "population_intervened": clean_null_string(
                    raw.get("population_intervened")
                ),
                "population_demographics": clean_null_string(
                    raw.get("population_demographics")
                ),
                "sample_size": clean_null_string(raw.get("sample_size")),
                "inner_setting": clean_null_string(raw.get("inner_setting")),
                "resource_intensity": clean_null_string(raw.get("resource_intensity")),
                "delivery_complexity": clean_null_string(
                    raw.get("delivery_complexity")
                ),
                "cost_level": clean_null_string(raw.get("cost_level")),
                "cost_justification": clean_null_string(raw.get("cost_justification")),
                "staffing_level": clean_null_string(raw.get("staffing_level")),
                "staffing_justification": clean_null_string(
                    raw.get("staffing_justification")
                ),
                "implementation_complexity_level": clean_null_string(
                    raw.get("implementation_complexity_level")
                ),
                "implementation_complexity_justification": clean_null_string(
                    raw.get("implementation_complexity_justification")
                ),
            }
        elif et == "issue":
            return {
                **base,
                "type": "issue",
                "issue_label": clean_null_string(row.get("label") or raw.get("label")),
                "explanation": clean_null_string(
                    raw.get("explanation") or row.get("description")
                ),
            }
        elif et == "result":
            if raw.get("is_prevalence_only") is True:
                return None
            return {
                **base,
                "type": "result",
                "outcome_variable": clean_null_string(
                    raw.get("outcome_variable") or row.get("label")
                ),
                "effect_direction": clean_null_string(raw.get("effect_direction")),
                "effect_size": clean_null_string(raw.get("effect_size")),
                "effect_size_type": clean_null_string(raw.get("effect_size_type")),
                "is_beneficial": raw.get("is_beneficial"),
                "is_prevalence_only": raw.get("is_prevalence_only"),
                "causality_claim": raw.get("causality_claim"),
                "p_value": raw.get("p_value"),
                "uncertainty": raw.get("uncertainty"),
                "intervention_idx": raw.get("intervention_idx"),
                "subgroup_or_dose": clean_null_string(raw.get("subgroup_or_dose")),
                "population_measured": clean_null_string(
                    raw.get("population_measured")
                ),
                "result_text": clean_null_string(raw.get("result_text")),
                "supporting_quote": clean_null_string(raw.get("supporting_quote")),
                "negative_impact_flag": raw.get("negative_impact_flag"),
            }
        elif et == "conclusion":
            return {
                **base,
                "type": "conclusion",
                "risk_assessment": raw.get("risk_assessment") or {},
                "evidence_strength": raw.get("evidence_strength") or {},
                "supporting_quote": clean_null_string(raw.get("supporting_quote")),
            }
        return {**base, "type": et}

    uniform = [item for item in (to_uniform(r) for r in (res.data or [])) if item]

    # Count docs with scores
    scored_docs = sum(1 for s in doc_scores.values() if s.get("evidence_score"))
    print(
        f"Loaded {len(uniform)} extractions, {len(doc_metadata)} documents "
        f"({scored_docs} with quality scores)"
    )
    return {
        "raw_extractions": uniform,
        "research_question": research_question,
        "target_population": target_population,
        "target_outcomes": target_outcomes,
        "target_geography": target_geography,
        "target_inner_setting": target_inner_setting,
        "implementation_constraints": implementation_constraints,
        "doc_metadata": doc_metadata,
        "doc_scores": doc_scores,
        "extraction_to_doc": extraction_to_doc,
        "db_theme_to_extraction_ids": theme_assignment_map,
    }


async def load_theme_assignments(project_id: str, supabase) -> Dict[str, List[str]]:
    """Load theme assignments for the latest completed synthesis run.

    Args:
        project_id: Analysis project ID.
        supabase: Supabase client instance.

    Returns:
        Mapping of intervention theme names to extraction IDs.
    """
    if not project_id:
        return {}
    try:
        runs_res = (
            supabase.table("synthesis_runs")
            .select("id")
            .eq("analysis_project_id", project_id)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not runs_res.data:
            return {}
        run_id = runs_res.data[0].get("id")
        if not run_id:
            return {}

        themes_res = (
            supabase.table("synthesis_themes")
            .select("id, theme_name")
            .eq("synthesis_run_id", run_id)
            .eq("theme_type", "intervention")
            .execute()
        )
        theme_id_to_name = {
            str(row.get("id")): row.get("theme_name") or ""
            for row in (themes_res.data or [])
            if row.get("id") and row.get("theme_name")
        }
        if not theme_id_to_name:
            return {}

        assignments_res = (
            supabase.table("theme_assignments")
            .select("synthesis_theme_id, extraction_id")
            .eq("synthesis_run_id", run_id)
            .execute()
        )
        theme_to_extraction_ids: Dict[str, List[str]] = {}
        for row in assignments_res.data or []:
            theme_id = str(row.get("synthesis_theme_id") or "")
            extraction_id = str(row.get("extraction_id") or "")
            theme_name = theme_id_to_name.get(theme_id, "")
            if theme_name and extraction_id:
                theme_to_extraction_ids.setdefault(theme_name, []).append(extraction_id)

        for theme_name, ex_ids in theme_to_extraction_ids.items():
            theme_to_extraction_ids[theme_name] = list(dict.fromkeys(ex_ids))
        return theme_to_extraction_ids
    except Exception:
        return {}


async def create_canonical_concepts(state: SynthesisState) -> SynthesisState:
    """Create concept sets from raw extractions.

    Args:
        state: Current workflow state with raw_extractions.

    Returns:
        State update with issue_concepts, intervention_concepts, outcome_concepts.
    """
    print("--- Creating Canonical Concepts ---")
    issue_concepts: List[Concept] = []
    intervention_concepts: List[Concept] = []
    outcome_concepts: List[Concept] = []
    risk_concepts: List[Concept] = []

    for ext in state.get("raw_extractions") or []:
        if ext.get("issue_label"):
            desc = f"Issue: {ext['issue_label']}. Explanation: {ext.get('explanation', '')}"
            issue_concepts.append(Concept(id=ext["id"], canonical_description=desc))
        if ext.get("intervention_name"):
            desc = f"Intervention: {ext['intervention_name']}. Description: {ext.get('description', '')}"
            intervention_concepts.append(
                Concept(id=ext["id"], canonical_description=desc)
            )
        if ext.get("type") == "result" or ext.get("outcome_variable"):
            # Support both 'direction' (new) and 'effect_direction' (legacy)
            effect_dir = ext.get("direction") or ext.get("effect_direction", "")
            desc = f"Outcome: {ext.get('outcome_variable', '')}. Effect: {effect_dir}"
            outcome_concepts.append(Concept(id=ext["id"], canonical_description=desc))
        if ext.get("type") == "conclusion":
            risk_assessment = ext.get("risk_assessment") or {}
            risks = risk_assessment.get("risks_identified") or []
            for i, risk in enumerate(risks):
                if risk and isinstance(risk, str):
                    risk_concepts.append(
                        Concept(
                            id=f"{ext.get('id', '')}_risk_{i}",
                            canonical_description=f"Risk: {risk}",
                        )
                    )
        if ext.get("type") == "result" and ext.get("negative_impact_flag") is True:
            outcome = ext.get("outcome_variable", "")
            if outcome:
                risk_concepts.append(
                    Concept(
                        id=ext.get("id", ""),
                        canonical_description=f"Negative outcome risk: {outcome}",
                    )
                )

    print(
        f"Created {len(issue_concepts)} issue, {len(intervention_concepts)} intervention, "
        f"{len(outcome_concepts)} outcome, {len(risk_concepts)} risk concepts"
    )
    return {
        "issue_concepts": issue_concepts,
        "intervention_concepts": intervention_concepts,
        "outcome_concepts": outcome_concepts,
        "risk_concepts": risk_concepts,
    }
