"""
Findings retrieval for drill-down views.

Provides get_findings() for fetching detailed findings filtered by
intervention name or issue theme.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from app.services.vectorization import vectorization_service
from app.services.synthesis.schemas import Finding

logger = logging.getLogger(__name__)


async def _async_supabase_query(query_func):
    """Execute a Supabase query asynchronously in thread pool.

    This prevents blocking the event loop during database operations.

    Args:
        query_func: Lambda or callable that executes the Supabase query.

    Returns:
        Query result.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, query_func)


async def get_findings(
    project_id: str,
    *,
    intervention_name: Optional[str] = None,
    issue_theme: Optional[str] = None,
) -> List[Finding]:
    """Flatten detailed findings for an intervention or issue.

    Uses theme_assignments from the latest synthesis run to determine
    which extractions belong to the selected theme.

    Args:
        project_id: Analysis project identifier.
        intervention_name: Optional filter by intervention name.
        issue_theme: Optional filter by issue label/theme.

    Returns:
        List of findings sorted by year (desc) then title.
    """
    supabase = vectorization_service.supabase

    # Load documents for the project
    docs_res = await _async_supabase_query(
        lambda: supabase.table("analysis_documents")
        .select("*")
        .eq("analysis_project_id", project_id)
        .execute()
    )
    documents = docs_res.data or []
    if not documents:
        return []

    filt_intr = (intervention_name or "").strip()
    filt_issue = (issue_theme or "").strip()
    if not filt_intr and not filt_issue:
        return []

    # Use theme_assignments to determine exactly which extractions belong
    # to the selected theme in the latest completed synthesis run.
    assigned_extraction_ids: set[str] = set()
    assigned_doc_uuids: set[str] = set()
    per_doc_assigned_intervention_names: dict[str, set[str]] = {}
    per_doc_assigned_issue_labels: dict[str, set[str]] = {}

    try:
        # Latest completed run
        runs_res = await _async_supabase_query(
            lambda: supabase.table("synthesis_runs")
            .select("id")
            .eq("analysis_project_id", project_id)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if runs_res.data:
            run_id = runs_res.data[0]["id"]
            # Find matching theme record
            if filt_intr:
                themes_res = await _async_supabase_query(
                    lambda: supabase.table("synthesis_themes")
                    .select("id")
                    .eq("synthesis_run_id", run_id)
                    .eq("theme_type", "intervention")
                    .eq("theme_name", filt_intr)
                    .limit(1)
                    .execute()
                )
            else:
                themes_res = await _async_supabase_query(
                    lambda: supabase.table("synthesis_themes")
                    .select("id")
                    .eq("synthesis_run_id", run_id)
                    .eq("theme_type", "issue")
                    .eq("theme_name", filt_issue)
                    .limit(1)
                    .execute()
                )
            if themes_res.data:
                theme_id = themes_res.data[0]["id"]
                # Assignments for theme
                assign_res = await _async_supabase_query(
                    lambda: supabase.table("theme_assignments")
                    .select("extraction_id")
                    .eq("synthesis_theme_id", theme_id)
                    .execute()
                )
                ex_ids = [str(a["extraction_id"]) for a in (assign_res.data or [])]
                if ex_ids:
                    assigned_extraction_ids = set(ex_ids)
                    # Fetch extraction records to map to documents and names/labels
                    exts_res = await _async_supabase_query(
                        lambda: supabase.table("analysis_extractions")
                        .select(
                            "id, analysis_document_id, extraction_type, label, raw_data"
                        )
                        .in_("id", list(assigned_extraction_ids))
                        .execute()
                    )
                    for row in exts_res.data or []:
                        doc_uuid = str(row.get("analysis_document_id") or "")
                        assigned_doc_uuids.add(doc_uuid)
                        etype = str(row.get("extraction_type") or "")
                        raw = row.get("raw_data") or {}
                        if etype == "intervention":
                            name = str(row.get("label") or raw.get("name") or "")
                            if name:
                                per_doc_assigned_intervention_names.setdefault(
                                    doc_uuid, set()
                                ).add(name)
                        elif etype == "issue":
                            label = str(row.get("label") or raw.get("label") or "")
                            if label:
                                per_doc_assigned_issue_labels.setdefault(
                                    doc_uuid, set()
                                ).add(label)
    except Exception as e:
        logger.warning("[findings] Failed to use theme_assignments: %s", e)

    findings: List[Finding] = []
    for doc in documents:
        extraction_results = doc.get("extraction_results") or {}
        if not extraction_results:
            continue

        doc_uuid = str(doc.get("id") or "")
        # If we have precise assignments, restrict to assigned docs
        if assigned_doc_uuids and doc_uuid not in assigned_doc_uuids:
            continue

        interventions = extraction_results.get("interventions", []) or []
        issues = extraction_results.get("issues", []) or []
        results = extraction_results.get("results", []) or []

        # Build lookup maps for exact matching
        name_to_idx: dict[str, int] = {}
        for i in interventions:
            try:
                idx_v = int(i.get("idx"))
            except Exception:
                continue
            nm = str(i.get("name") or "")
            if nm:
                name_to_idx[nm] = idx_v

        label_to_idx: dict[str, int] = {}
        for iss in issues:
            try:
                idx_v = int(iss.get("idx"))
            except Exception:
                continue
            lb = str(iss.get("label") or "")
            if lb:
                label_to_idx[lb] = idx_v

        include_intervention_idxs: set[int] = set()

        if filt_intr:
            # Prefer assigned intervention names for this document if available
            assigned_names = per_doc_assigned_intervention_names.get(doc_uuid)
            if assigned_names:
                for nm in assigned_names:
                    if nm in name_to_idx:
                        include_intervention_idxs.add(name_to_idx[nm])
            else:
                # Fallback: exact name match in this document
                if filt_intr in name_to_idx:
                    include_intervention_idxs.add(name_to_idx[filt_intr])

        if filt_issue:
            # ISSUE DRILL-DOWN: show only narrative evidence for the specific issue.
            assigned_labels = per_doc_assigned_issue_labels.get(doc_uuid)
            matching_issue_labels: set[str] = set()
            if assigned_labels:
                matching_issue_labels.update(assigned_labels)
            else:
                if filt_issue:
                    matching_issue_labels.add(filt_issue)

            # Emit one finding per matching issue occurrence in this document
            for iss in issues:
                lb = str(iss.get("label") or "")
                if not lb or lb not in matching_issue_labels:
                    continue
                evidence_items: List[str] = []
                issue_quote = iss.get("supporting_quote")
                if issue_quote:
                    evidence_items.append(str(issue_quote))
                explanation = iss.get("explanation")
                if explanation and str(explanation) not in evidence_items:
                    evidence_items.append(str(explanation))

                finding = Finding(
                    SourceTitle=str(doc.get("title") or "Unknown Source"),
                    Source=str(doc.get("source") or "") or None,
                    DocId=str(doc.get("doc_id") or doc.get("id") or "") or None,
                    Year=doc.get("year"),
                    Url=(
                        doc.get("landing_page_url")
                        or doc.get("pdf_url")
                        or doc.get("url")
                    )
                    or None,
                    Intervention=None,  # Intentionally omitted for issues
                    StudyDesign=None,
                    Outcome=None,
                    EffectDirection=None,
                    EffectSizeType=None,
                    EffectSize=None,
                    PValue=None,
                    Uncertainty=None,
                    Evidence=[e for e in evidence_items if e],
                )
                findings.append(finding)

            # For issues we purposely skip intervention-result based evidence
            continue

        if not include_intervention_idxs:
            continue

        intr_by_idx = {}
        for i in interventions:
            try:
                intr_by_idx[int(i.get("idx"))] = i
            except Exception:
                continue

        for res in results:
            try:
                intr_idx = int(res.get("intervention_idx"))
            except Exception:
                continue
            if intr_idx not in include_intervention_idxs:
                continue

            intr = intr_by_idx.get(intr_idx) or {}

            evidence_items: List[str] = []
            intr_quote = intr.get("supporting_quote")
            if intr_quote:
                evidence_items.append(str(intr_quote))
            res_quote = res.get("supporting_quote")
            if res_quote:
                evidence_items.append(str(res_quote))
            res_text = res.get("result_text")
            if res_text and str(res_text) not in evidence_items:
                evidence_items.append(str(res_text))

            finding = Finding(
                SourceTitle=str(doc.get("title") or "Unknown Source"),
                Source=str(doc.get("source") or "") or None,
                DocId=str(doc.get("doc_id") or doc.get("id") or "") or None,
                Year=doc.get("year"),
                Url=(
                    doc.get("landing_page_url") or doc.get("pdf_url") or doc.get("url")
                )
                or None,
                Intervention=str(intr.get("name") or "") or None,
                StudyDesign=str(intr.get("study_type") or "") or None,
                Outcome=str(res.get("outcome_variable") or "") or None,
                EffectDirection=str(res.get("effect_direction") or "") or None,
                EffectSizeType=str(res.get("effect_size_type") or "") or None,
                EffectSize=str(res.get("effect_size") or "") or None,
                PValue=str(res.get("p_value") or "") or None,
                Uncertainty=str(res.get("uncertainty") or "") or None,
                Evidence=[e for e in evidence_items if e],
            )
            findings.append(finding)

    findings.sort(key=lambda f: (f.Year or 0, f.SourceTitle or ""), reverse=True)
    return findings
