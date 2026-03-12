"""
Database caching for synthesis agent runs.

Handles reading/writing synthesis results to:
- synthesis_runs: Main run records
- synthesis_themes: Issue and intervention themes
- synthesis_outcome_themes: Outcome theme clusters
- synthesis_citations: Citation references
- theme_assignments: Extraction to theme mappings
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, List, Set

import app.core.database as db
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
from app.services.synthesis.nodes.impact_synthesis import (
    parse_effect_size_value,
    detect_scale_type,
    _normalise_unit_key,
)

logger = logging.getLogger(__name__)


def _parse_json_field(value: Optional[object]) -> Optional[Dict]:
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


async def read_cached_summary(project_id: str) -> Optional[SynthesisSummary]:
    """Read cached synthesis summary for a project."""
    run = db.fetchone(
        """
        SELECT * FROM synthesis_runs
        WHERE analysis_project_id = %s AND status = 'completed'
        ORDER BY created_at DESC LIMIT 1
        """,
        [project_id],
    )
    if not run:
        return None

    run_id = str(run["id"])

    themes = db.fetch(
        "SELECT * FROM synthesis_themes WHERE synthesis_run_id = %s", [run_id]
    )
    outcome_themes = db.fetch(
        "SELECT * FROM synthesis_outcome_themes WHERE synthesis_run_id = %s", [run_id]
    )
    citations = db.fetch(
        "SELECT * FROM synthesis_citations WHERE synthesis_run_id = %s", [run_id]
    )

    issue_themes = [t for t in themes if t["theme_type"] == "issue"]
    intervention_themes = [t for t in themes if t["theme_type"] == "intervention"]
    risk_theme_rows = [t for t in themes if t["theme_type"] == "risk"]

    # Map doc UUIDs to doc_ids
    docs = db.fetch(
        "SELECT id, doc_id FROM analysis_documents WHERE analysis_project_id = %s",
        [project_id],
    )
    uuid_to_docid = {str(d["id"]): str(d.get("doc_id") or "") for d in docs}

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
                    impact_score=t.get("impact_score"),
                    impact_score_label=t.get("impact_score_label"),
                    impact_score_breakdown=_parse_json_field(
                        t.get("impact_score_breakdown")
                    ),
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
    outcome_theme_objects: List[OutcomeTheme] = []
    for ot in outcome_themes:
        if ot.get("outcome_name"):
            outcome_theme_objects.append(
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
                    magnitude_detail=_parse_json_field(ot.get("magnitude_detail")),
                    intervention_theme_id=ot.get("intervention_theme_id"),
                    primary_causal_mechanism=ot.get("primary_causal_mechanism"),
                    causal_mechanism_detail=_parse_json_field(
                        ot.get("causal_mechanism_detail")
                    ),
                )
            )

    # Build citation map
    citation_map: Dict[str, CitationInfo] = {}
    for cit in citations:
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

    return SynthesisSummary(
        executive_briefing=run.get("executive_briefing") or "",
        structured_briefing=structured_briefing,
        key_issues=key_issues,
        interventions=interventions,
        outcome_themes=outcome_theme_objects,
        risk_themes=risk_themes,
        evidence_coverage=evidence_coverage,
        citation_map=citation_map,
    )


async def write_run_from_state(project_id: str, final_state: Dict) -> None:
    """Write synthesis agent final state to cache tables."""
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
    db.insert("synthesis_runs", run_data)

    # Write citations
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
        if citations_to_insert:
            try:
                db.insert_many("synthesis_citations", citations_to_insert)
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

    raw_extractions = final_state.get("raw_extractions") or []
    outcome_name_by_extraction_id = (
        final_state.get("outcome_name_by_extraction_id") or {}
    )
    thresholds_by_outcome_name = (
        final_state.get("magnitude_thresholds_by_outcome_name") or {}
    )
    calibrated_magnitude_by_extraction_id: Dict[str, str] = {}
    for ext in raw_extractions:
        if ext.get("type") != "result":
            continue
        ext_id = str(ext.get("id") or "")
        if not ext_id:
            continue
        outcome_name = outcome_name_by_extraction_id.get(ext_id)
        if not outcome_name:
            continue
        thresholds_by_unit = thresholds_by_outcome_name.get(outcome_name) or {}
        effect_size = ext.get("effect_size")
        numeric_val = parse_effect_size_value(effect_size) if effect_size else None
        if numeric_val is None:
            continue
        unit_key = _normalise_unit_key(ext.get("effect_size_type"))
        if not unit_key:
            unit_key = detect_scale_type("", str(effect_size or ""))
        thresholds = thresholds_by_unit.get(unit_key)
        if not thresholds:
            continue
        value = abs(numeric_val)
        if value >= thresholds.get("substantial", float("inf")):
            calibrated_magnitude_by_extraction_id[ext_id] = "substantial"
        elif value >= thresholds.get("large", float("inf")):
            calibrated_magnitude_by_extraction_id[ext_id] = "large"
        elif value >= thresholds.get("moderate", float("inf")):
            calibrated_magnitude_by_extraction_id[ext_id] = "moderate"
        else:
            calibrated_magnitude_by_extraction_id[ext_id] = "marginal"

    theme_assignments: List[Dict] = []

    # Write issue themes
    for issue in final_state.get("aggregated_issues") or []:
        issue_dict = issue.model_dump() if hasattr(issue, "model_dump") else issue
        theme_id = str(uuid.uuid4())
        db.insert(
            "synthesis_themes",
            {
                "id": theme_id,
                "synthesis_run_id": run_id,
                "theme_type": "issue",
                "theme_name": issue_dict.get("issue_theme"),
                "summary_description": issue_dict.get("summary_description"),
                "frequency": issue_dict.get("frequency", 0),
                "source_doc_ids": db.PgArray(issue_dict.get("source_doc_ids") or []),
                "created_at": datetime.utcnow().isoformat(),
            },
        )
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
        db.insert(
            "synthesis_themes",
            {
                "id": theme_id,
                "synthesis_run_id": run_id,
                "theme_type": "intervention",
                "theme_name": intervention_name,
                "summary_description": intv_dict.get("brief_description"),
                "impact_summary": intv_dict.get("impact_summary"),
                "frequency": intv_dict.get("frequency", 0),
                "source_doc_ids": db.PgArray(intv_dict.get("supporting_doc_ids") or []),
                "effect_consensus": intv_dict.get("effect_consensus"),
                "positive_count": intv_dict.get("positive_count", 0),
                "negative_count": intv_dict.get("negative_count", 0),
                "null_count": intv_dict.get("null_count", 0),
                "sample_effect_sizes": db.PgArray(intv_dict.get("sample_effect_sizes") or []),
                "countries": db.PgArray(intv_dict.get("countries") or []),
                "study_types": intv_dict.get("study_types", {}),
                "transferability_rating": intv_dict.get("transferability_rating"),
                "transferability_note": intv_dict.get("transferability_note"),
                "transferability_breakdown": intv_dict.get("transferability_breakdown"),
                "impact_score": intv_dict.get("impact_score"),
                "impact_score_label": intv_dict.get("impact_score_label"),
                "impact_score_breakdown": intv_dict.get("impact_score_breakdown"),
                "created_at": datetime.utcnow().isoformat(),
            },
        )
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
        db.insert(
            "synthesis_outcome_themes",
            {
                "id": outcome_id,
                "synthesis_run_id": run_id,
                "outcome_name": out_dict.get("outcome_name"),
                "outcome_description": out_dict.get("outcome_description"),
                "effect_consensus": out_dict.get("effect_consensus"),
                "positive_count": out_dict.get("positive_count", 0),
                "negative_count": out_dict.get("negative_count", 0),
                "null_count": out_dict.get("null_count", 0),
                "sample_effect_sizes": db.PgArray(out_dict.get("sample_effect_sizes") or []),
                "frequency": out_dict.get("frequency", 0),
                "source_doc_ids": db.PgArray(out_dict.get("source_doc_ids") or []),
                "verdict_label": out_dict.get("verdict_label"),
                "verdict_description": out_dict.get("verdict_description"),
                "discord_flag": out_dict.get("discord_flag", False),
                "discord_reason": out_dict.get("discord_reason"),
                "predicted_magnitude": out_dict.get("predicted_magnitude"),
                "magnitude_detail": out_dict.get("magnitude_detail"),
                "primary_causal_mechanism": out_dict.get("primary_causal_mechanism"),
                "causal_mechanism_detail": out_dict.get("causal_mechanism_detail"),
                "intervention_theme_id": intervention_link,
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        for ex_id in theme_to_ex_ids.get(out_dict.get("outcome_name", ""), []):
            outcome_assignments.append(
                {
                    "id": str(uuid.uuid4()),
                    "synthesis_run_id": run_id,
                    "synthesis_outcome_theme_id": outcome_id,
                    "extraction_id": ex_id,
                    "calibrated_magnitude": calibrated_magnitude_by_extraction_id.get(
                        ex_id
                    ),
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

    # Batch insert assignments
    if theme_assignments:
        unique = _dedupe_assignments(theme_assignments, "synthesis_theme_id")
        db.insert_many("theme_assignments", unique)

    if outcome_assignments:
        unique = _dedupe_assignments(outcome_assignments, "synthesis_outcome_theme_id")
        db.insert_many("outcome_theme_assignments", unique)

    # Write risk themes
    for risk in final_state.get("final_risk_themes") or []:
        risk_dict = risk.model_dump() if hasattr(risk, "model_dump") else risk
        risk_theme_id = str(uuid.uuid4())
        linked = risk_dict.get("linked_intervention_theme_id")
        if linked in intervention_id_by_name:
            linked = intervention_id_by_name[linked]
        db.insert(
            "synthesis_themes",
            {
                "id": risk_theme_id,
                "synthesis_run_id": run_id,
                "theme_type": "risk",
                "theme_name": risk_dict.get("theme_name"),
                "summary_description": risk_dict.get("summary_description"),
                "frequency": risk_dict.get("frequency", 0),
                "source_doc_ids": db.PgArray(risk_dict.get("source_doc_ids") or []),
                "has_harm_warning": risk_dict.get("has_harm_warning", False),
                "linked_intervention_theme_id": linked,
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        linked_interventions = risk_dict.get("linked_interventions") or []
        for item in linked_interventions:
            intervention_name = item.get("intervention_name")
            link_strength = item.get("link_strength", "secondary")
            if intervention_name in intervention_id_by_name:
                db.insert(
                    "theme_intervention_links",
                    {
                        "theme_id": risk_theme_id,
                        "intervention_theme_id": intervention_id_by_name[
                            intervention_name
                        ],
                        "link_strength": link_strength,
                        "created_at": datetime.utcnow().isoformat(),
                    },
                )

    # Persist calibrated document scores
    doc_scores = final_state.get("doc_scores") or {}
    if doc_scores:
        for doc_uuid, score_entry in doc_scores.items():
            if not doc_uuid or not isinstance(score_entry, dict):
                continue
            impact_score = score_entry.get("impact_score")
            impact_label = score_entry.get("impact_score_label")
            impact_breakdown = score_entry.get("impact_score_breakdown")
            if impact_score is None:
                continue
            try:
                db.execute(
                    """
                    UPDATE analysis_documents
                    SET impact_score = %s,
                        impact_score_label = %s,
                        impact_score_breakdown = %s
                    WHERE id = %s::uuid
                    """,
                    [impact_score, impact_label, impact_breakdown, doc_uuid],
                )
            except Exception as exc:
                logger.warning(
                    f"Failed to persist document impact score for {doc_uuid}: {exc}"
                )


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
    row = db.fetchone(
        """
        SELECT status FROM synthesis_runs
        WHERE analysis_project_id = %s
        ORDER BY created_at DESC LIMIT 1
        """,
        [project_id],
    )
    return row.get("status", "none") if row else "none"


async def invalidate_cache(project_id: str) -> None:
    """Invalidate cached synthesis results for a project."""
    db.execute(
        """
        UPDATE synthesis_runs SET status = 'invalidated'
        WHERE analysis_project_id = %s AND status = 'completed'
        """,
        [project_id],
    )


async def create_synthesis_run_placeholder(project_id: str) -> str:
    """Create a 'running' synthesis run to prevent duplicates."""
    run_id = str(uuid.uuid4())
    db.insert(
        "synthesis_runs",
        {
            "id": run_id,
            "analysis_project_id": project_id,
            "status": "running",
            "version": 4,
            "executive_briefing": "",
            "model_info": {},
            "created_at": datetime.utcnow().isoformat(),
        },
    )
    return run_id


async def mark_synthesis_complete(run_id: str) -> None:
    """Mark a synthesis run as completed."""
    db.execute(
        "UPDATE synthesis_runs SET status = 'completed' WHERE id = %s::uuid",
        [run_id],
    )


async def mark_synthesis_failed(run_id: str, error: str) -> None:
    """Mark a synthesis run as failed."""
    db.execute(
        "UPDATE synthesis_runs SET status = 'failed', model_info = %s WHERE id = %s::uuid",
        [{"error": error[:500]}, run_id],
    )
