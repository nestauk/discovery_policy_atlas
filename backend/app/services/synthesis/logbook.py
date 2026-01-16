"""
Supabase-based caching for synthesis agent runs.

Handles reading/writing synthesis results to:
- synthesis_runs: Main run records
- synthesis_themes: Issue and intervention themes
- synthesis_outcome_themes: Outcome theme clusters
- synthesis_citations: Citation references
- theme_assignments: Extraction to theme mappings
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, List, Set

from app.core.config import settings
from app.services.synthesis.schemas import (
    SynthesisSummary,
    KeyIssue,
    PolicyIntervention,
    OutcomeTheme,
    RiskTheme,
    CitationInfo,
    EvidenceCoverageSnapshot,
    StructuredBriefing,
)
from supabase import create_client

logger = logging.getLogger(__name__)


def get_supabase():
    """Get Supabase client."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


async def read_cached_summary(project_id: str) -> Optional[SynthesisSummary]:
    """Read cached synthesis summary for a project."""
    supabase = get_supabase()

    # Get most recent completed run
    runs_res = (
        supabase.table("synthesis_runs")
        .select("*")
        .eq("analysis_project_id", project_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not runs_res.data:
        return None

    run = runs_res.data[0]
    run_id = run["id"]

    # Get themes
    themes_res = (
        supabase.table("synthesis_themes")
        .select("*")
        .eq("synthesis_run_id", run_id)
        .execute()
    )
    outcome_themes_res = (
        supabase.table("synthesis_outcome_themes")
        .select("*")
        .eq("synthesis_run_id", run_id)
        .execute()
    )
    citations_res = (
        supabase.table("synthesis_citations")
        .select("*")
        .eq("synthesis_run_id", run_id)
        .execute()
    )

    themes = themes_res.data or []
    issue_themes = [t for t in themes if t["theme_type"] == "issue"]
    intervention_themes = [t for t in themes if t["theme_type"] == "intervention"]
    risk_theme_rows = [t for t in themes if t["theme_type"] == "risk"]

    # Map doc UUIDs to doc_ids
    docs_res = (
        supabase.table("analysis_documents")
        .select("id, doc_id")
        .eq("analysis_project_id", project_id)
        .execute()
    )
    uuid_to_docid = {
        str(d["id"]): str(d.get("doc_id") or "") for d in (docs_res.data or [])
    }

    # Build issues
    key_issues = []
    for t in issue_themes:
        src_ids = [
            uuid_to_docid.get(str(u), "")
            for u in (t.get("source_document_ids") or [])
            if uuid_to_docid.get(str(u))
        ]
        if t.get("theme_name"):
            key_issues.append(
                KeyIssue(
                    issue_theme=t["theme_name"],
                    summary_description=t.get("summary_description") or "",
                    frequency=t.get("frequency") or 0,
                    source_doc_ids=src_ids,
                )
            )

    # Build interventions
    interventions = []
    for t in intervention_themes:
        supp_ids = [
            uuid_to_docid.get(str(u), "")
            for u in (t.get("source_document_ids") or [])
            if uuid_to_docid.get(str(u))
        ]
        if t.get("theme_name"):
            interventions.append(
                PolicyIntervention(
                    intervention_name=t["theme_name"],
                    brief_description=t.get("summary_description") or "",
                    impact_summary=t.get("impact_summary") or "",
                    frequency=t.get("frequency") or 0,
                    supporting_doc_ids=supp_ids,
                    effect_consensus=t.get("effect_consensus"),
                    positive_count=t.get("positive_count") or 0,
                    negative_count=t.get("negative_count") or 0,
                    null_count=t.get("null_count") or 0,
                    sample_effect_sizes=t.get("sample_effect_sizes") or [],
                    countries=t.get("countries") or [],
                    study_types=t.get("study_types") or {},
                    transferability_rating=t.get("transferability_rating"),
                    transferability_note=t.get("transferability_note"),
                    transferability_breakdown=t.get("transferability_breakdown"),
                    primary_causal_mechanism=t.get("primary_causal_mechanism"),
                    causal_mechanism_detail=t.get("causal_mechanism_detail"),
                )
            )

    # Build risk themes
    risk_themes: List[RiskTheme] = []
    for t in risk_theme_rows:
        if t.get("theme_name"):
            risk_themes.append(
                RiskTheme(
                    theme_name=t["theme_name"],
                    summary_description=t.get("summary_description") or "",
                    frequency=t.get("frequency") or 0,
                    source_doc_ids=t.get("source_doc_ids") or [],
                    has_harm_warning=t.get("has_harm_warning") or False,
                    linked_intervention_theme_id=t.get("linked_intervention_theme_id"),
                )
            )

    # Build outcome themes
    outcome_themes: List[OutcomeTheme] = []
    for ot in outcome_themes_res.data or []:
        if ot.get("outcome_name"):
            outcome_themes.append(
                OutcomeTheme(
                    outcome_name=ot["outcome_name"],
                    outcome_description=ot.get("outcome_description") or "",
                    effect_consensus=ot.get("effect_consensus") or "insufficient",
                    positive_count=ot.get("positive_count") or 0,
                    negative_count=ot.get("negative_count") or 0,
                    null_count=ot.get("null_count") or 0,
                    sample_effect_sizes=ot.get("sample_effect_sizes") or [],
                    frequency=ot.get("frequency") or 0,
                    source_doc_ids=ot.get("source_doc_ids") or [],
                    verdict_label=ot.get("verdict_label"),
                    verdict_description=ot.get("verdict_description"),
                    discord_flag=ot.get("discord_flag") or False,
                    discord_reason=ot.get("discord_reason"),
                    predicted_magnitude=ot.get("predicted_magnitude"),
                    magnitude_confidence=ot.get("magnitude_confidence"),
                    intervention_theme_id=ot.get("intervention_theme_id"),
                )
            )

    # Build citation map
    citation_map: Dict[str, CitationInfo] = {}
    for cit in citations_res.data or []:
        cit_key = cit.get("citation_key", "")
        if cit_key:
            citation_map[cit_key] = CitationInfo(
                citation_key=cit_key,
                citation_number=cit.get("citation_index") or 0,
                doc_id=cit.get("doc_id"),
                analysis_document_id=str(cit.get("analysis_document_id", "")),
                author_short=cit.get("author_short"),
                year=cit.get("year"),
                title=cit.get("title"),
                url=cit.get("url"),
                supporting_quote=cit.get("supporting_quote"),
                chunk_id=cit.get("chunk_id"),
            )

    # Parse evidence coverage
    evidence_coverage: Optional[EvidenceCoverageSnapshot] = None
    ec_data = run.get("evidence_coverage")
    if ec_data and isinstance(ec_data, dict):
        try:
            evidence_coverage = EvidenceCoverageSnapshot.model_validate(ec_data)
        except Exception as e:
            logger.warning(f"Failed to parse evidence_coverage: {e}")

    # Parse structured briefing
    structured_briefing: Optional[StructuredBriefing] = None
    sb_data = run.get("structured_briefing_data")
    if sb_data and isinstance(sb_data, dict):
        try:
            structured_briefing = StructuredBriefing.model_validate(sb_data)
        except Exception as e:
            logger.warning(f"Failed to parse structured_briefing: {e}")

    logger.info(f"Read {len(citation_map)} citations from DB for project {project_id}")
    if citation_map:
        sample_key = next(iter(citation_map.keys()))
        sample_cit = citation_map[sample_key]
        logger.info(
            f"Sample citation - key: {sample_key}, number: {sample_cit.citation_number}, title: {sample_cit.title}, author: {sample_cit.author_short}"
        )

    return SynthesisSummary(
        executive_briefing=run.get("executive_briefing") or "",
        structured_briefing=structured_briefing,
        key_issues=key_issues,
        interventions=interventions,
        outcome_themes=outcome_themes,
        risk_themes=risk_themes,
        evidence_coverage=evidence_coverage,
        citation_map=citation_map,
    )


async def write_run_from_state(project_id: str, final_state: Dict) -> None:
    """Write synthesis agent final state to cache tables."""
    supabase = get_supabase()

    # Prepare evidence coverage
    ec = final_state.get("evidence_coverage")
    ec_data = (
        ec.model_dump()
        if hasattr(ec, "model_dump")
        else (ec if isinstance(ec, dict) else None)
    )

    # Prepare structured briefing
    sb = final_state.get("structured_briefing")
    sb_data = (
        sb.model_dump()
        if hasattr(sb, "model_dump")
        else (sb if isinstance(sb, dict) else None)
    )

    # Create run record
    run_id = str(uuid.uuid4())
    run_data = {
        "id": run_id,
        "analysis_project_id": project_id,
        "status": "completed",
        "version": 4,
        "executive_briefing": final_state.get("executive_briefing", ""),
        "evidence_coverage": ec_data,
        "structured_briefing_data": sb_data,
        "total_outcomes": len(final_state.get("aggregated_outcomes") or []),
        "model_info": {
            "total_issues": len(final_state.get("aggregated_issues") or []),
            "total_interventions": len(
                final_state.get("aggregated_interventions") or []
            ),
            "total_outcomes": len(final_state.get("aggregated_outcomes") or []),
        },
    }
    supabase.table("synthesis_runs").insert(run_data).execute()

    # Write all citations (keyed by citation_number for frontend lookup)
    citation_map = final_state.get("citation_map") or {}
    logger.info(f"Writing {len(citation_map)} citations for run {run_id}")

    if citation_map:
        citations_to_insert = []

        for i, (cit_key, info) in enumerate(citation_map.items(), 1):
            info_dict = info.model_dump() if hasattr(info, "model_dump") else info
            if not isinstance(info_dict, dict):
                continue

            citations_to_insert.append(
                {
                    "id": str(uuid.uuid4()),
                    "synthesis_run_id": run_id,
                    "analysis_document_id": info_dict.get("analysis_document_id"),
                    "citation_key": cit_key,
                    "citation_index": info_dict.get("citation_number") or i,
                    "author_short": info_dict.get("author_short"),
                    "year": info_dict.get("year"),
                    "title": info_dict.get("title"),
                    "url": info_dict.get("url"),
                    "supporting_quote": info_dict.get("supporting_quote"),
                    "chunk_id": info_dict.get("chunk_id"),
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

        logger.info(f"Inserting {len(citations_to_insert)} citations")
        if citations_to_insert:
            try:
                supabase.table("synthesis_citations").insert(
                    citations_to_insert
                ).execute()
            except Exception as e:
                logger.warning(f"Failed to insert citations batch: {e}")

    # Build theme->extraction mappings
    theme_to_ex_ids: Dict[str, List[str]] = {}
    for branch in ["issue", "intervention", "outcome", "risk"]:
        for ft in final_state.get(f"final_{branch}_themes") or []:
            if isinstance(ft, dict):
                name = ft.get("name") or ft.get("theme_name")
                concepts = ft.get("concepts", [])
            else:
                name = getattr(ft, "name", None) or getattr(ft, "theme_name", None)
                concepts = getattr(ft, "concepts", [])
            if name:
                theme_to_ex_ids[name] = _dedupe(
                    [c["id"] if isinstance(c, dict) else c.id for c in (concepts or [])]
                )

    theme_assignments: List[Dict] = []

    # Write issue themes
    for issue in final_state.get("aggregated_issues") or []:
        issue_dict = issue.model_dump() if hasattr(issue, "model_dump") else issue
        theme_id = str(uuid.uuid4())
        supabase.table("synthesis_themes").insert(
            {
                "id": theme_id,
                "synthesis_run_id": run_id,
                "theme_type": "issue",
                "theme_name": issue_dict.get("issue_theme"),
                "summary_description": issue_dict.get("summary_description"),
                "frequency": issue_dict.get("frequency", 0),
                "source_doc_ids": issue_dict.get("source_doc_ids", []),
                "created_at": datetime.utcnow().isoformat(),
            }
        ).execute()

        for ex_id in theme_to_ex_ids.get(issue_dict.get("issue_theme", ""), []):
            theme_assignments.append(
                {
                    "id": str(uuid.uuid4()),
                    "synthesis_run_id": run_id,
                    "synthesis_theme_id": theme_id,
                    "extraction_id": ex_id,
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

    # Write intervention themes
    intervention_id_by_name: Dict[str, str] = {}
    for intv in final_state.get("aggregated_interventions") or []:
        intv_dict = intv.model_dump() if hasattr(intv, "model_dump") else intv
        theme_id = str(uuid.uuid4())
        intervention_name = intv_dict.get("intervention_name")
        supabase.table("synthesis_themes").insert(
            {
                "id": theme_id,
                "synthesis_run_id": run_id,
                "theme_type": "intervention",
                "theme_name": intervention_name,
                "summary_description": intv_dict.get("brief_description"),
                "impact_summary": intv_dict.get("impact_summary"),
                "frequency": intv_dict.get("frequency", 0),
                "source_doc_ids": intv_dict.get("supporting_doc_ids", []),
                "effect_consensus": intv_dict.get("effect_consensus"),
                "positive_count": intv_dict.get("positive_count", 0),
                "negative_count": intv_dict.get("negative_count", 0),
                "null_count": intv_dict.get("null_count", 0),
                "sample_effect_sizes": intv_dict.get("sample_effect_sizes", []),
                "countries": intv_dict.get("countries", []),
                "study_types": intv_dict.get("study_types", {}),
                "transferability_rating": intv_dict.get("transferability_rating"),
                "transferability_note": intv_dict.get("transferability_note"),
                "transferability_breakdown": intv_dict.get("transferability_breakdown"),
                "primary_causal_mechanism": intv_dict.get("primary_causal_mechanism"),
                "causal_mechanism_detail": intv_dict.get("causal_mechanism_detail"),
                "created_at": datetime.utcnow().isoformat(),
            }
        ).execute()

        if intervention_name:
            intervention_id_by_name[intervention_name] = theme_id

        for ex_id in theme_to_ex_ids.get(intervention_name or "", []):
            theme_assignments.append(
                {
                    "id": str(uuid.uuid4()),
                    "synthesis_run_id": run_id,
                    "synthesis_theme_id": theme_id,
                    "extraction_id": ex_id,
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

    # Write outcome themes
    outcome_assignments: List[Dict] = []
    for out in final_state.get("aggregated_outcomes") or []:
        out_dict = out.model_dump() if hasattr(out, "model_dump") else out
        outcome_id = str(uuid.uuid4())
        intervention_link = out_dict.get("intervention_theme_id")
        if intervention_link in intervention_id_by_name:
            intervention_link = intervention_id_by_name[intervention_link]
        supabase.table("synthesis_outcome_themes").insert(
            {
                "id": outcome_id,
                "synthesis_run_id": run_id,
                "outcome_name": out_dict.get("outcome_name"),
                "outcome_description": out_dict.get("outcome_description"),
                "effect_consensus": out_dict.get("effect_consensus"),
                "positive_count": out_dict.get("positive_count", 0),
                "negative_count": out_dict.get("negative_count", 0),
                "null_count": out_dict.get("null_count", 0),
                "sample_effect_sizes": out_dict.get("sample_effect_sizes", []),
                "frequency": out_dict.get("frequency", 0),
                "source_doc_ids": out_dict.get("source_doc_ids", []),
                "verdict_label": out_dict.get("verdict_label"),
                "verdict_description": out_dict.get("verdict_description"),
                "discord_flag": out_dict.get("discord_flag", False),
                "discord_reason": out_dict.get("discord_reason"),
                "predicted_magnitude": out_dict.get("predicted_magnitude"),
                "magnitude_confidence": out_dict.get("magnitude_confidence"),
                "intervention_theme_id": intervention_link,
                "created_at": datetime.utcnow().isoformat(),
            }
        ).execute()

        for ex_id in theme_to_ex_ids.get(out_dict.get("outcome_name", ""), []):
            outcome_assignments.append(
                {
                    "id": str(uuid.uuid4()),
                    "synthesis_run_id": run_id,
                    "synthesis_outcome_theme_id": outcome_id,
                    "extraction_id": ex_id,
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

    # Batch insert assignments
    if theme_assignments:
        unique = _dedupe_assignments(theme_assignments, "synthesis_theme_id")
        supabase.table("theme_assignments").insert(unique).execute()

    if outcome_assignments:
        unique = _dedupe_assignments(outcome_assignments, "synthesis_outcome_theme_id")
        supabase.table("outcome_theme_assignments").insert(unique).execute()

    # Write risk themes
    for risk in final_state.get("final_risk_themes") or []:
        risk_dict = risk.model_dump() if hasattr(risk, "model_dump") else risk
        risk_theme_id = str(uuid.uuid4())
        linked = risk_dict.get("linked_intervention_theme_id")
        if linked in intervention_id_by_name:
            linked = intervention_id_by_name[linked]
        supabase.table("synthesis_themes").insert(
            {
                "id": risk_theme_id,
                "synthesis_run_id": run_id,
                "theme_type": "risk",
                "theme_name": risk_dict.get("theme_name"),
                "summary_description": risk_dict.get("summary_description"),
                "frequency": risk_dict.get("frequency", 0),
                "source_doc_ids": risk_dict.get("source_doc_ids", []),
                "has_harm_warning": risk_dict.get("has_harm_warning", False),
                "linked_intervention_theme_id": linked,
                "created_at": datetime.utcnow().isoformat(),
            }
        ).execute()


def _dedupe(items: List[str]) -> List[str]:
    """Deduplicate list while preserving order."""
    seen: Set[str] = set()
    return [x for x in items if x and x not in seen and not seen.add(x)]


def _dedupe_assignments(assignments: List[Dict], theme_key: str) -> List[Dict]:
    """Deduplicate assignments by (theme_id, extraction_id)."""
    seen: Set[str] = set()
    unique: List[Dict] = []
    for a in assignments:
        k = f"{a[theme_key]}::{a['extraction_id']}"
        if k not in seen:
            seen.add(k)
            unique.append(a)
    return unique


async def get_synthesis_status(project_id: str) -> str:
    """Get current synthesis status for a project."""
    supabase = get_supabase()
    runs_res = (
        supabase.table("synthesis_runs")
        .select("status")
        .eq("analysis_project_id", project_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return runs_res.data[0].get("status", "none") if runs_res.data else "none"


async def invalidate_cache(project_id: str) -> None:
    """Invalidate cached synthesis results for a project."""
    supabase = get_supabase()
    supabase.table("synthesis_runs").update({"status": "invalidated"}).eq(
        "analysis_project_id", project_id
    ).eq("status", "completed").execute()


async def create_synthesis_run_placeholder(project_id: str) -> str:
    """Create a 'running' synthesis run to prevent duplicates.

    Returns:
        run_id: The ID of the created synthesis run.
    """
    supabase = get_supabase()
    run_id = str(uuid.uuid4())
    run_data = {
        "id": run_id,
        "analysis_project_id": project_id,
        "status": "running",
        "version": 4,
        "executive_briefing": "",
        "model_info": {},
        "created_at": datetime.utcnow().isoformat(),
    }
    supabase.table("synthesis_runs").insert(run_data).execute()
    return run_id


async def mark_synthesis_complete(run_id: str) -> None:
    """Mark a synthesis run as completed."""
    supabase = get_supabase()
    supabase.table("synthesis_runs").update({"status": "completed"}).eq(
        "id", run_id
    ).execute()


async def mark_synthesis_failed(run_id: str, error: str) -> None:
    """Mark a synthesis run as failed."""
    supabase = get_supabase()
    supabase.table("synthesis_runs").update(
        {
            "status": "failed",
            "model_info": {"error": error[:500]},
        }
    ).eq("id", run_id).execute()
