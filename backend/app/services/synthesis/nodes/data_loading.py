"""
Data loading nodes for the synthesis workflow.

Phase 1: Load raw extractions from database and create canonical concepts.
"""

from __future__ import annotations

from typing import Dict, List

from app.services.vectorization import vectorization_service
from app.services.synthesis.state import SynthesisState, Concept
from app.services.synthesis.utils import normalize_study_type
from app.services.analysis.evidence_strength import calculate_document_evidence_score


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

    # Fetch research question
    proj_res = (
        supabase.table("analysis_projects")
        .select("title, query")
        .eq("id", project_id)
        .execute()
    )
    research_question = (
        (proj_res.data[0].get("title") or proj_res.data[0].get("query"))
        if proj_res.data
        else "Not specified"
    )

    # Fetch document metadata including evidence_category and extraction_results
    docs_res = (
        supabase.table("analysis_documents")
        .select(
            "id, doc_id, title, year, authors, landing_page_url, pdf_url, source, document_type, evidence_category, extraction_results"
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
            "year": doc.get("year"),
            "author_short": author_short,
            "url": doc.get("landing_page_url") or doc.get("pdf_url"),
            "source": doc.get("source"),
            "document_type": doc.get("document_type"),
        }

        # Get evidence score (with sample size penalty) and impact score from conclusion
        evidence_result = calculate_document_evidence_score(doc)

        extraction_results = doc.get("extraction_results") or {}
        conclusion = extraction_results.get("conclusion") or {}
        predicted_impact = conclusion.get("predicted_impact") or {}

        doc_scores[doc_uuid] = {
            "evidence_score": evidence_result["score"],  # 0-5 with sample size penalty
            "impact_score": predicted_impact.get("stars"),  # 1-5 or None
            "evidence_category": doc.get("evidence_category"),
            "evidence_justification": evidence_result["justification"],
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
                "study_type": normalize_study_type(str(raw_st)),
                "country": str(raw.get("country") or ""),
                "description": str(
                    row.get("description") or raw.get("description") or ""
                ),
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
                # Support both 'direction' (new schema) and 'effect_direction' (legacy)
                "effect_direction": str(
                    raw.get("direction") or raw.get("effect_direction") or ""
                ),
                "effect_size": str(raw.get("effect_size") or ""),
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
            # Support both 'direction' (new) and 'effect_direction' (legacy)
            effect_dir = ext.get("direction") or ext.get("effect_direction", "")
            desc = f"Outcome: {ext.get('outcome_variable', '')}. Effect: {effect_dir}"
            outcome_concepts.append(Concept(id=ext["id"], canonical_description=desc))

    print(
        f"Created {len(issue_concepts)} issue, {len(intervention_concepts)} intervention, {len(outcome_concepts)} outcome concepts"
    )
    return {
        "issue_concepts": issue_concepts,
        "intervention_concepts": intervention_concepts,
        "outcome_concepts": outcome_concepts,
    }
