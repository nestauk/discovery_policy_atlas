"""
Aggregation nodes for the synthesis workflow.

Phase 3: Compute evidence coverage statistics and build aggregated tables
from themes.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List

from app.services.vectorization import vectorization_service
from app.services.synthesis.state import SynthesisState
from app.services.synthesis.utils import normalize_study_type, normalize_source_type
from app.services.synthesis.schemas import (
    EvidenceCoverageSnapshot,
    KeyIssue,
    PolicyIntervention,
    OutcomeTheme,
)


async def compute_evidence_coverage(state: SynthesisState) -> SynthesisState:
    """Compute evidence coverage statistics (deterministic, no LLM).

    Args:
        state: Current workflow state with raw_extractions and doc_metadata.

    Returns:
        State update with evidence_coverage.
    """
    print("--- Computing Evidence Coverage ---")
    raw_extractions = state.get("raw_extractions") or []
    doc_metadata = state.get("doc_metadata") or {}

    study_types: Counter = Counter()
    countries: Counter = Counter()
    source_types: Counter = Counter()
    evidence_categories: Counter = Counter()

    for ext in raw_extractions:
        if ext.get("type") == "intervention":
            st = ext.get("study_type")
            if st:
                study_types[normalize_study_type(st)] += 1
            country = ext.get("country")
            if country:
                countries[country] += 1

    years: Counter = Counter()
    for doc in doc_metadata.values():
        if doc.get("year"):
            years[doc["year"]] += 1
        # Count source types (institutional: Academic, Government, NGO, etc.)
        src_type = normalize_source_type(doc.get("source"), doc.get("type"))
        source_types[src_type] += 1
        # Count evidence categories (methodological: Systematic Review, RCT, etc.)
        ev_cat = doc.get("evidence_category")
        if ev_cat:
            evidence_categories[ev_cat] += 1

    # Determine strength based on study design quality
    rct_count = sum(c for st, c in study_types.items() if "rct" in st.lower())
    meta_count = sum(c for st, c in study_types.items() if "meta" in st.lower())

    if meta_count >= 3 or rct_count >= 5:
        strength = "High"
    elif meta_count >= 1 or rct_count >= 2:
        strength = "Moderate"
    else:
        strength = "Low"

    gaps = []
    if rct_count == 0:
        gaps.append("No RCTs found in evidence base")
    if meta_count == 0:
        gaps.append("No meta-analyses found")

    # Filter out null/None/empty values from display collections
    null_values = {"null", "none", "", "unknown", "n/a"}
    filtered_study_types = {
        k: v for k, v in study_types.items() if k.lower() not in null_values
    }
    filtered_countries = {
        k: v for k, v in countries.items() if k.lower() not in null_values
    }

    coverage = EvidenceCoverageSnapshot(
        total_sources=len(doc_metadata),
        study_types=filtered_study_types,
        source_types=dict(source_types),
        evidence_categories=dict(evidence_categories),
        countries=filtered_countries,
        years={int(k): v for k, v in years.items()},
        overall_strength=strength,
        gaps=gaps,
    )
    return {"evidence_coverage": coverage}


async def build_aggregated_tables(state: SynthesisState) -> SynthesisState:
    """Build aggregated issues, interventions, and outcomes from themes.

    Args:
        state: Current workflow state with final themes and raw extractions.

    Returns:
        State update with aggregated_issues, aggregated_interventions,
        aggregated_outcomes, extraction_quotes, outcome_doc_effects.
    """
    print("--- Building Aggregated Tables ---")
    final_issue_themes = state.get("final_issue_themes") or []
    final_intervention_themes = state.get("final_intervention_themes") or []
    final_outcome_themes = state.get("final_outcome_themes") or []
    raw_extractions = state.get("raw_extractions") or []

    project_id = state.get("project_id", "")
    supabase = vectorization_service.supabase

    # Build extraction metadata lookup
    all_ex_ids = []
    for t in final_issue_themes + final_intervention_themes + final_outcome_themes:
        all_ex_ids.extend([c.id for c in t.concepts])
    all_ex_ids = list(set(all_ex_ids))

    ex_metadata: Dict[str, Dict] = {}
    if all_ex_ids:
        docs_res = (
            supabase.table("analysis_documents")
            .select("id, doc_id")
            .eq("analysis_project_id", project_id)
            .execute()
        )
        uuid_to_doc_id = {
            str(d["id"]): str(d.get("doc_id") or "") for d in (docs_res.data or [])
        }

        for i in range(0, len(all_ex_ids), 500):
            chunk = all_ex_ids[i : i + 500]
            exts_res = (
                supabase.table("analysis_extractions")
                .select("id, analysis_document_id, raw_data")
                .in_("id", chunk)
                .execute()
            )
            for r in exts_res.data or []:
                doc_uuid = str(r.get("analysis_document_id") or "")
                ex_metadata[str(r["id"])] = {
                    "doc_uuid": doc_uuid,
                    "doc_id": uuid_to_doc_id.get(doc_uuid, ""),
                    "raw_data": r.get("raw_data") or {},
                }

    raw_ext_by_id = {str(e["id"]): e for e in raw_extractions}

    # Build doc_uuid -> result extractions mapping (for effect data)
    doc_to_results: Dict[str, List[Dict]] = {}
    for ext in raw_extractions:
        if ext.get("type") == "result" and ext.get("effect_direction"):
            meta = ex_metadata.get(ext.get("id", ""), {})
            doc_uuid = meta.get("doc_uuid", "")
            if doc_uuid:
                if doc_uuid not in doc_to_results:
                    doc_to_results[doc_uuid] = []
                doc_to_results[doc_uuid].append(ext)
    print(f"Built result mappings for {len(doc_to_results)} documents")

    # Build issues
    issues: List[KeyIssue] = []
    for t in final_issue_themes:
        doc_ids = set()
        for c in t.concepts:
            meta = ex_metadata.get(c.id, {})
            if meta.get("doc_id"):
                doc_ids.add(meta["doc_id"])
        if doc_ids:
            issues.append(
                KeyIssue(
                    issue_theme=t.name,
                    summary_description=t.description,
                    frequency=len(doc_ids),
                    source_doc_ids=sorted(doc_ids),
                )
            )

    # Build interventions
    interventions: List[PolicyIntervention] = []
    for t in final_intervention_themes:
        doc_ids, doc_uuids, countries_set, study_types_counter = (
            set(),
            set(),
            set(),
            Counter(),
        )

        for c in t.concepts:
            meta = ex_metadata.get(c.id, {})
            raw = meta.get("raw_data", {})
            raw_ext = raw_ext_by_id.get(c.id, {})

            if meta.get("doc_id"):
                doc_ids.add(meta["doc_id"])
            if meta.get("doc_uuid"):
                doc_uuids.add(meta["doc_uuid"])
            if raw.get("country") or raw_ext.get("country"):
                countries_set.add(raw.get("country") or raw_ext.get("country"))
            if raw.get("study_type") or raw_ext.get("study_type"):
                study_types_counter[
                    raw.get("study_type") or raw_ext.get("study_type")
                ] += 1

        # Aggregate effect counts and sizes from result extractions
        pos, neg, null = 0, 0, 0
        effect_sizes: List[str] = []
        related_outcomes: List[str] = []
        for doc_uuid in doc_uuids:
            for result_ext in doc_to_results.get(doc_uuid, []):
                effect_dir = result_ext.get("effect_direction", "").lower()
                if effect_dir in ("increase", "positive"):
                    pos += 1
                elif effect_dir in ("decrease", "negative"):
                    neg += 1
                elif effect_dir in ("null", "none", "no effect"):
                    null += 1
                effect_size = result_ext.get("effect_size", "")
                if effect_size and len(effect_size) > 2:
                    effect_sizes.append(effect_size[:100])
                outcome_var = result_ext.get("outcome_variable", "")
                if outcome_var and outcome_var not in related_outcomes:
                    related_outcomes.append(outcome_var)

        if not doc_ids:
            continue

        total = pos + neg + null
        if total == 0:
            consensus = "insufficient"
        elif pos > neg * 2:
            consensus = "increase"
        elif neg > pos * 2:
            consensus = "decrease"
        elif null > pos and null > neg:
            consensus = "no change"
        else:
            consensus = "mixed"

        interventions.append(
            PolicyIntervention(
                intervention_name=t.name,
                brief_description=t.description,
                impact_summary=f"Evidence from {len(doc_ids)} studies ({pos}↑ {neg}↓ {null}—)",
                frequency=len(doc_ids),
                supporting_doc_ids=sorted(doc_ids),
                effect_consensus=consensus,
                positive_count=pos,
                negative_count=neg,
                null_count=null,
                sample_effect_sizes=effect_sizes[:5],
                countries=sorted(countries_set),
                study_types=dict(study_types_counter),
                related_outcomes=related_outcomes[:10],
            )
        )

    # Build outcomes and per-doc effect mapping
    outcomes: List[OutcomeTheme] = []
    outcome_doc_effects: Dict[str, Dict[str, List[str]]] = {}

    for t in final_outcome_themes:
        doc_ids = set()
        pos, neg, null = 0, 0, 0
        doc_effect_list: Dict[str, List[str]] = {}

        for c in t.concepts:
            meta = ex_metadata.get(c.id, {})
            raw_ext = raw_ext_by_id.get(c.id, {})
            doc_id = meta.get("doc_id")
            if doc_id:
                doc_ids.add(doc_id)
            effect_dir = raw_ext.get("effect_direction")
            if effect_dir == "increase":
                pos += 1
                if doc_id:
                    doc_effect_list.setdefault(doc_id, []).append("positive")
            elif effect_dir == "decrease":
                neg += 1
                if doc_id:
                    doc_effect_list.setdefault(doc_id, []).append("negative")
            elif effect_dir == "null":
                null += 1
                if doc_id:
                    doc_effect_list.setdefault(doc_id, []).append("null")

        if not doc_ids:
            continue

        total = pos + neg + null
        if total == 0:
            consensus = "insufficient"
        elif pos > neg * 2:
            consensus = "increase"
        elif neg > pos * 2:
            consensus = "decrease"
        elif null > pos and null > neg:
            consensus = "no change"
        else:
            consensus = "mixed"

        outcomes.append(
            OutcomeTheme(
                outcome_name=t.name,
                outcome_description=t.description,
                effect_consensus=consensus,
                positive_count=pos,
                negative_count=neg,
                null_count=null,
                frequency=len(doc_ids),
                source_doc_ids=sorted(doc_ids),
            )
        )
        outcome_doc_effects[t.name] = doc_effect_list

    # Build extraction quotes mapping
    extraction_quotes: Dict[str, List[str]] = {}
    for ex_id, meta in ex_metadata.items():
        doc_uuid = meta.get("doc_uuid", "")
        raw = meta.get("raw_data", {})
        quote = raw.get("supporting_quote")
        if doc_uuid and quote and isinstance(quote, str) and len(quote) > 20:
            if doc_uuid not in extraction_quotes:
                extraction_quotes[doc_uuid] = []
            extraction_quotes[doc_uuid].append(quote)

    # Build theme -> doc_uuid mapping for constrained RAG retrieval
    theme_to_doc_uuids: Dict[str, List[str]] = {}

    for t in final_intervention_themes:
        uuids = []
        for c in t.concepts:
            meta = ex_metadata.get(c.id, {})
            if meta.get("doc_uuid"):
                uuids.append(meta["doc_uuid"])
        theme_to_doc_uuids[t.name] = list(set(uuids))

    for t in final_issue_themes:
        uuids = []
        for c in t.concepts:
            meta = ex_metadata.get(c.id, {})
            if meta.get("doc_uuid"):
                uuids.append(meta["doc_uuid"])
        theme_to_doc_uuids[t.name] = list(set(uuids))

    print(
        f"Built {len(issues)} issues, {len(interventions)} interventions, {len(outcomes)} outcomes"
    )
    print(f"Collected extraction quotes for {len(extraction_quotes)} documents")
    print(f"Built theme->doc mappings for {len(theme_to_doc_uuids)} themes")
    return {
        "aggregated_issues": issues,
        "aggregated_interventions": interventions,
        "aggregated_outcomes": outcomes,
        "extraction_quotes": extraction_quotes,
        "outcome_doc_effects": outcome_doc_effects,
        "theme_to_doc_uuids": theme_to_doc_uuids,
    }
