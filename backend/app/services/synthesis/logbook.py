"""
Supabase-based caching for synthesis agent runs.

Handles reading/writing synthesis results to:
- synthesis_runs: Main run records
- synthesis_themes: Issue and intervention themes
- synthesis_outcome_themes: Outcome theme clusters
- synthesis_citations: Citation references
- theme_assignments: Extraction to theme mappings
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List, Set

from app.core.config import settings
from app.services.synthesis.schemas import (
    SynthesisSummary,
    KeyIssue,
    PolicyIntervention,
    OutcomeTheme,
    RiskTheme,
    CitationInfo,
    ClaimQuote,
    EvidenceCoverageSnapshot,
    StructuredBriefing,
)
from app.services.synthesis.nodes.impact_synthesis import (
    parse_effect_size_value,
    detect_scale_type,
    _normalise_unit_key,
)
from app.services.analysis.evidence.strength import get_or_calculate_document_evidence
from app.services.synthesis.utils import normalize_source_type
from supabase import create_client

logger = logging.getLogger(__name__)
CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def _confidence_from_attribution(attribution: str) -> float:
    """Map attribution label to legacy confidence values for compatibility."""
    if attribution == "direct":
        return 1.0
    if attribution == "synthesised":
        return 0.7
    if attribution == "inferred":
        return 0.4
    return 1.0


def _attribution_from_row(row: Dict) -> str:
    """Read attribution from row, with legacy confidence fallback."""
    attribution = row.get("attribution")
    if attribution in {"direct", "synthesised", "inferred"}:
        return attribution

    confidence = row.get("confidence")
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        conf = 1.0
    if conf >= 0.85:
        return "direct"
    if conf >= 0.55:
        return "synthesised"
    return "inferred"


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


def _accumulate_citation_usage(value: Any, usage_counts: Dict[int, int]) -> None:
    """Recursively count [N] citations across strings/lists/dicts."""
    if isinstance(value, str):
        for match in CITATION_PATTERN.finditer(value):
            citation_number = int(match.group(1))
            usage_counts[citation_number] = usage_counts.get(citation_number, 0) + 1
        return

    if isinstance(value, list):
        for item in value:
            _accumulate_citation_usage(item, usage_counts)
        return

    if isinstance(value, dict):
        for item in value.values():
            _accumulate_citation_usage(item, usage_counts)


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
                    magnitude_detail=_parse_json_field(ot.get("magnitude_detail")),
                    intervention_theme_id=ot.get("intervention_theme_id"),
                    primary_causal_mechanism=ot.get("primary_causal_mechanism"),
                    causal_mechanism_detail=_parse_json_field(
                        ot.get("causal_mechanism_detail")
                    ),
                )
            )

    # Build citation map (with per-claim quotes)
    citation_map: Dict[str, CitationInfo] = {}
    citation_rows: Dict[str, List[Dict]] = {}
    for cit in citations_res.data or []:
        cit_key = cit.get("citation_key", "")
        if cit_key:
            citation_rows.setdefault(cit_key, []).append(cit)

    for cit_key, rows in citation_rows.items():
        base_row = next((r for r in rows if not r.get("section")), rows[0])
        claim_quotes: List[ClaimQuote] = []
        for row in rows:
            if not row.get("section") or not row.get("claim_text"):
                continue
            claim_quotes.append(
                ClaimQuote(
                    claim_text=row.get("claim_text") or "",
                    supporting_quote=row.get("supporting_quote") or "",
                    attribution=_attribution_from_row(row),
                    chunk_id=row.get("chunk_id") or "",
                    section=row.get("section") or "",
                )
            )
        citation_map[cit_key] = CitationInfo(
            citation_key=cit_key,
            citation_number=base_row.get("citation_index") or 0,
            doc_id=base_row.get("doc_id"),
            analysis_document_id=str(base_row.get("analysis_document_id", "")),
            author_short=base_row.get("author_short"),
            year=base_row.get("year"),
            title=base_row.get("title"),
            url=base_row.get("url"),
            document_type=None,
            evidence_score=None,
            impact_score=None,
            supporting_quote=base_row.get("supporting_quote"),
            chunk_id=base_row.get("chunk_id"),
            claim_quotes=claim_quotes,
        )

    doc_ids = list(
        {
            cit.analysis_document_id
            for cit in citation_map.values()
            if cit.analysis_document_id
        }
    )
    doc_meta_by_id: Dict[str, Dict] = {}
    if doc_ids:
        docs_meta_res = (
            supabase.table("analysis_documents")
            .select(
                "id, source, document_type, evidence_category, evidence_category_reasoning, evidence_justification, extraction_results, impact_score, impact_score_label, impact_score_breakdown, transferability_score, transferability_breakdown, top_line, venue, source_country, source_type, author_institutions"
            )
            .in_("id", doc_ids)
            .execute()
        )
        doc_meta_by_id = {
            str(row.get("id")): row
            for row in (docs_meta_res.data or [])
            if row.get("id")
        }

    for cit in citation_map.values():
        doc_meta = doc_meta_by_id.get(cit.analysis_document_id)
        if not doc_meta:
            continue
        evidence_info = get_or_calculate_document_evidence(doc_meta)
        stars = evidence_info.get("stars")
        cit.evidence_score = int(stars) if isinstance(stars, (int, float)) else None
        cit.impact_score = doc_meta.get("impact_score")
        cit.impact_score_label = doc_meta.get("impact_score_label")
        cit.impact_score_breakdown = doc_meta.get("impact_score_breakdown")
        cit.transferability_score = doc_meta.get("transferability_score")
        cit.transferability_breakdown = doc_meta.get("transferability_breakdown")
        cit.document_type = doc_meta.get("document_type")
        cit.evidence_category = doc_meta.get("evidence_category")
        cit.evidence_category_reasoning = doc_meta.get("evidence_category_reasoning")
        cit.evidence_strength_justification = doc_meta.get("evidence_justification")
        cit.venue = doc_meta.get("venue")
        cit.country = doc_meta.get("source_country")
        source_value = str(doc_meta.get("source") or "").strip()
        if not source_value:
            doc_id_raw = str(cit.doc_id or "")
            if "openalex" in doc_id_raw.lower() or (
                doc_id_raw.startswith("W") and doc_id_raw[1:].isdigit()
            ):
                source_value = "openalex"
            elif "overton" in doc_id_raw.lower():
                source_value = "overton"
        cit.source_type = normalize_source_type(
            source_value, str(doc_meta.get("document_type") or "")
        )
        raw_institutions = doc_meta.get("author_institutions")
        if isinstance(raw_institutions, list):
            cit.author_institutions = [
                str(item).strip() for item in raw_institutions if str(item).strip()
            ]
        cit.top_line = doc_meta.get("top_line")

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

    citation_usage_counts: Dict[int, int] = {}
    if sb_data and isinstance(sb_data, dict):
        _accumulate_citation_usage(sb_data, citation_usage_counts)
    else:
        _accumulate_citation_usage(
            run.get("executive_briefing") or "", citation_usage_counts
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
        citation_usage_counts=citation_usage_counts,
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

            # Document-level fallback citation row
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
                    "section": None,
                    "claim_text": None,
                    "attribution": None,
                    "confidence": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            # Per-claim citation rows
            for claim_quote in info_dict.get("claim_quotes") or []:
                if not isinstance(claim_quote, dict):
                    continue
                attribution = str(claim_quote.get("attribution") or "direct")
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
                        "supporting_quote": claim_quote.get("supporting_quote"),
                        "chunk_id": claim_quote.get("chunk_id"),
                        "section": claim_quote.get("section"),
                        "claim_text": claim_quote.get("claim_text"),
                        "attribution": attribution,
                        "confidence": _confidence_from_attribution(attribution),
                        "created_at": datetime.now(timezone.utc).isoformat(),
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
        supabase.table("synthesis_themes").insert(
            {
                "id": theme_id,
                "synthesis_run_id": run_id,
                "theme_type": "issue",
                "theme_name": issue_dict.get("issue_theme"),
                "summary_description": issue_dict.get("summary_description"),
                "frequency": issue_dict.get("frequency", 0),
                "source_doc_ids": issue_dict.get("source_doc_ids", []),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

        for ex_id in theme_to_ex_ids.get(issue_dict.get("issue_theme", ""), []):
            theme_assignments.append(
                {
                    "id": str(uuid.uuid4()),
                    "synthesis_run_id": run_id,
                    "synthesis_theme_id": theme_id,
                    "extraction_id": ex_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
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
                "impact_score": intv_dict.get("impact_score"),
                "impact_score_label": intv_dict.get("impact_score_label"),
                "impact_score_breakdown": intv_dict.get("impact_score_breakdown"),
                "created_at": datetime.now(timezone.utc).isoformat(),
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
                    "created_at": datetime.now(timezone.utc).isoformat(),
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
                "magnitude_detail": out_dict.get("magnitude_detail"),
                "primary_causal_mechanism": out_dict.get("primary_causal_mechanism"),
                "causal_mechanism_detail": out_dict.get("causal_mechanism_detail"),
                "intervention_theme_id": intervention_link,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

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
                    "created_at": datetime.now(timezone.utc).isoformat(),
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
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

        linked_interventions = risk_dict.get("linked_interventions") or []
        for item in linked_interventions:
            intervention_name = item.get("intervention_name")
            link_strength = item.get("link_strength", "secondary")
            if intervention_name in intervention_id_by_name:
                supabase.table("theme_intervention_links").insert(
                    {
                        "theme_id": risk_theme_id,
                        "intervention_theme_id": intervention_id_by_name[
                            intervention_name
                        ],
                        "link_strength": link_strength,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).execute()

    # Persist calibrated document scores (overwrite strategy)
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
                supabase.table("analysis_documents").update(
                    {
                        "impact_score": impact_score,
                        "impact_score_label": impact_label,
                        "impact_score_breakdown": impact_breakdown,
                    }
                ).eq("id", doc_uuid).execute()
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
        "created_at": datetime.now(timezone.utc).isoformat(),
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
