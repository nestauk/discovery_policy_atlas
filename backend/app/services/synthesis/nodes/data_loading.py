"""
Data loading nodes for the synthesis workflow.

Phase 1: Load raw extractions from database and create canonical concepts.
"""

from __future__ import annotations

from typing import Dict, List

from app.services.vectorization import vectorization_service
from app.services.synthesis.state import SynthesisState, Concept
from app.services.synthesis.utils import normalize_study_type


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
    # Normalise to list[str]
    if isinstance(target_population, str):
        target_population = [target_population]
    if isinstance(target_outcomes, str):
        target_outcomes = [target_outcomes]

    # Fetch document metadata including extraction_results for scores
    docs_res = (
        supabase.table("analysis_documents")
        .select(
            "id, doc_id, title, year, authors, landing_page_url, pdf_url, source, document_type, extraction_results, evidence_category, top_line"
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
        }

        # Extract evidence strength and impact scores from conclusion
        extraction_results = doc.get("extraction_results") or {}
        conclusion = extraction_results.get("conclusion") or {}
        evidence_strength = conclusion.get("evidence_strength") or {}
        predicted_impact = conclusion.get("predicted_impact") or {}

        doc_scores[doc_uuid] = {
            "evidence_score": evidence_strength.get("stars"),  # 1-5 or None
            "impact_score": predicted_impact.get("stars"),  # 1-5 or None
            "evidence_justification": evidence_strength.get("justification", ""),
            "impact_justification": predicted_impact.get("justification", ""),
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
        base = {
            "id": str(row.get("id")),
            "doc_uuid": str(row.get("analysis_document_id") or ""),
        }
        if et == "intervention":
            raw_st = raw.get("study_type") or raw.get("type") or ""
            return {
                **base,
                "type": "intervention",
                "intervention_name": str(row.get("label") or raw.get("name") or ""),
                "intervention_idx": raw.get("idx"),
                "study_type": normalize_study_type(str(raw_st)),
                "country": str(raw.get("country") or ""),
                "description": str(
                    row.get("description") or raw.get("description") or ""
                ),
                "supporting_quote": str(raw.get("supporting_quote") or ""),
                "population_intervened": str(raw.get("population_intervened") or ""),
                "population_demographics": str(
                    raw.get("population_demographics") or ""
                ),
                "sample_size": str(raw.get("sample_size") or ""),
            }
        elif et == "issue":
            return {
                **base,
                "type": "issue",
                "issue_label": str(row.get("label") or raw.get("label") or ""),
                "explanation": str(
                    raw.get("explanation") or row.get("description") or ""
                ),
            }
        elif et == "result":
            return {
                **base,
                "type": "result",
                "outcome_variable": str(
                    raw.get("outcome_variable") or row.get("label") or ""
                ),
                "effect_direction": str(raw.get("effect_direction") or ""),
                "effect_size": str(raw.get("effect_size") or ""),
                "effect_size_type": str(raw.get("effect_size_type") or ""),
                "p_value": raw.get("p_value"),
                "uncertainty": raw.get("uncertainty"),
                "intervention_idx": raw.get("intervention_idx"),
                "subgroup_or_dose": str(raw.get("subgroup_or_dose") or ""),
                "population_measured": str(raw.get("population_measured") or ""),
                "result_text": str(raw.get("result_text") or ""),
                "supporting_quote": str(raw.get("supporting_quote") or ""),
            }
        return {**base, "type": et}

    uniform = [to_uniform(r) for r in (res.data or [])]

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
        "doc_metadata": doc_metadata,
        "doc_scores": doc_scores,
        "extraction_to_doc": extraction_to_doc,
    }


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
            desc = f"Outcome: {ext.get('outcome_variable', '')}. Effect: {ext.get('effect_direction', '')}"
            outcome_concepts.append(Concept(id=ext["id"], canonical_description=desc))

    print(
        f"Created {len(issue_concepts)} issue, {len(intervention_concepts)} intervention, {len(outcome_concepts)} outcome concepts"
    )
    return {
        "issue_concepts": issue_concepts,
        "intervention_concepts": intervention_concepts,
        "outcome_concepts": outcome_concepts,
    }
