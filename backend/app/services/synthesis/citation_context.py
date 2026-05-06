"""Shared helpers for citation chunk context retrieval."""

from typing import Optional

from fastapi import HTTPException

from app.services.analysis.evidence.strength import get_or_calculate_document_evidence
from app.services.synthesis.schemas import ChunkContextResponse, DocumentContextInfo
from app.services.synthesis.utils import (
    extract_author_display,
    extract_author_list,
    extract_author_short,
    infer_source_value,
    normalize_source_type,
)
from app.services.vectorization import vectorization_service


def get_chunk_context_response(project_id: str, chunk_id: str) -> ChunkContextResponse:
    """Build chunk context payload for a project and chunk."""
    target_res = (
        vectorization_service.supabase.table("chunks")
        .select("id, content, chunk_index, document_id, project_id")
        .eq("id", chunk_id)
        .eq("project_id", project_id)
        .limit(1)
        .execute()
    )
    if not target_res.data:
        raise HTTPException(status_code=404, detail="Chunk not found for this project")

    target_chunk = target_res.data[0]
    target_index = int(target_chunk.get("chunk_index") or 0)
    document_id = str(target_chunk.get("document_id") or "")
    if not document_id:
        raise HTTPException(status_code=404, detail="Chunk has no source document")

    adjacent_indices = [target_index - 1, target_index + 1]
    adjacent_res = (
        vectorization_service.supabase.table("chunks")
        .select("content, chunk_index")
        .eq("document_id", document_id)
        .eq("project_id", project_id)
        .in_("chunk_index", adjacent_indices)
        .order("chunk_index")
        .execute()
    )

    previous_chunk_content: Optional[str] = None
    next_chunk_content: Optional[str] = None
    for row in adjacent_res.data or []:
        idx = int(row.get("chunk_index") or 0)
        content = str(row.get("content") or "")
        if idx == target_index - 1:
            previous_chunk_content = content
        elif idx == target_index + 1:
            next_chunk_content = content

    doc_res = (
        vectorization_service.supabase.table("analysis_documents")
        .select(
            "id, doc_id, title, authors, author_institutions, year, venue, source_country, source, document_type, evidence_category, evidence_category_reasoning, extraction_results, impact_score, impact_score_label, impact_score_breakdown, transferability_score, transferability_breakdown, pdf_url, landing_page_url, overton_url"
        )
        .eq("id", document_id)
        .eq("analysis_project_id", project_id)
        .limit(1)
        .execute()
    )
    if not doc_res.data:
        raise HTTPException(
            status_code=404, detail="Source document not found for this chunk"
        )

    doc = doc_res.data[0]
    evidence_info = get_or_calculate_document_evidence(doc)
    stars = evidence_info.get("stars")
    evidence_score = int(stars) if isinstance(stars, (int, float)) else None
    source_value = infer_source_value(doc.get("source"), doc.get("doc_id"))

    document = DocumentContextInfo(
        analysis_document_id=str(doc.get("id") or document_id),
        title=str(doc.get("title") or "Unknown source"),
        author_display=extract_author_display(doc.get("authors")),
        authors=extract_author_list(doc.get("authors")),
        author_institutions=extract_author_list(doc.get("author_institutions")),
        author_short=extract_author_short(doc.get("authors")),
        year=doc.get("year"),
        venue=doc.get("venue"),
        country=doc.get("source_country"),
        url=doc.get("pdf_url") or doc.get("landing_page_url") or doc.get("overton_url"),
        source_type=normalize_source_type(
            source_value, str(doc.get("document_type") or "")
        ),
        document_type=doc.get("document_type"),
        evidence_category=doc.get("evidence_category"),
        evidence_category_reasoning=doc.get("evidence_category_reasoning"),
        evidence_score=evidence_score,
        evidence_strength_justification=evidence_info.get("justification"),
        impact_score=doc.get("impact_score"),
        impact_score_label=doc.get("impact_score_label"),
        impact_score_breakdown=doc.get("impact_score_breakdown"),
        transferability_score=doc.get("transferability_score"),
        transferability_breakdown=doc.get("transferability_breakdown"),
    )

    return ChunkContextResponse(
        chunk_id=str(target_chunk.get("id") or chunk_id),
        chunk_content=str(target_chunk.get("content") or ""),
        chunk_index=target_index,
        previous_chunk_content=previous_chunk_content,
        next_chunk_content=next_chunk_content,
        document=document,
    )
