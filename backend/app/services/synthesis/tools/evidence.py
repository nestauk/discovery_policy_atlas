"""
Evidence retrieval tools for agentic briefing.

Provides tools to query pre-computed RCS scored contexts and
retrieve targeted evidence for specific themes.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Callable

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from app.services.synthesis.schemas import (
    ScoredContext,
    ThemeEvidence,
    InterventionDetails,
)
from app.services.synthesis.tools.base import (
    BaseTool,
    ToolResult,
    register_tool,
)

logger = logging.getLogger(__name__)


# Minimum fuzzy match ratio to consider a theme match
FUZZY_MATCH_THRESHOLD = 60


def _best_fuzzy_match(
    target: str, options: List[Any], key: Callable[[Any], str]
) -> tuple[Optional[Any], int]:
    """Return best fuzzy match for target from options."""
    best_item = None
    best_score = 0
    target_l = target.lower().strip()
    for opt in options:
        value = key(opt) or ""
        ratio = fuzz.ratio(target_l, value.lower())
        partial = fuzz.partial_ratio(target_l, value.lower())
        score = max(ratio, partial)
        if score > best_score:
            best_score = score
            best_item = opt
    return best_item, best_score


class ThemeEvidenceItem(BaseModel):
    """A single evidence item returned by get_theme_evidence.

    Attributes:
        summary: Contextualised summary of the evidence.
        citation_number: [N] citation for referencing.
        document_title: Source document title.
        relevance_score: RCS relevance score (0-10).
        document_quality: Evidence strength score (1-5), None if unavailable.
        chunk_text: Original chunk text (truncated).
    """

    summary: str
    citation_number: int
    document_title: str
    relevance_score: int
    document_quality: Optional[int] = None
    chunk_text: str = ""


class GetThemeEvidenceTool(BaseTool):
    """Tool to retrieve RCS-scored evidence for a specific theme.

    Queries pre-computed scored_theme_evidence, scored_issue_evidence, and
    scored_outcome_evidence
    from the synthesis state. Filters by relevance score and deduplicates
    by document.
    """

    name = "get_theme_evidence"
    description = (
        "Retrieve pre-scored evidence for a specific theme or intervention. "
        "Use when writing about a specific intervention or issue and need "
        "supporting evidence with citations. Returns evidence items sorted "
        "by relevance score, deduplicated by document."
    )
    max_results = 5

    async def execute(
        self,
        state: Dict[str, Any],
        theme_name: str,
        min_relevance: int = 5,
        max_results: Optional[int] = None,
    ) -> ToolResult:
        """Execute the get_theme_evidence tool.

        Args:
            state: Current synthesis state.
            theme_name: Name of intervention or issue theme.
            min_relevance: Minimum RCS relevance score (0-10), default 5.
            max_results: Maximum evidence items to return.

        Returns:
            ToolResult with list of ThemeEvidenceItem.
        """
        max_results = max_results or self.max_results

        # Get pre-computed evidence from state
        scored_theme_evidence: List[ThemeEvidence] = (
            state.get("scored_theme_evidence") or []
        )
        scored_issue_evidence: List[ThemeEvidence] = (
            state.get("scored_issue_evidence") or []
        )
        scored_outcome_evidence: List[ThemeEvidence] = (
            state.get("scored_outcome_evidence") or []
        )
        doc_citation_map: Dict[str, int] = state.get("doc_citation_map") or {}
        doc_scores: Dict[str, Dict[str, Any]] = state.get("doc_scores") or {}
        doc_metadata: Dict[str, Dict[str, Any]] = state.get("doc_metadata") or {}

        # Search theme, issue, and outcome evidence
        all_evidence = (
            scored_theme_evidence + scored_issue_evidence + scored_outcome_evidence
        )

        # Find matching theme using fuzzy matching
        matching_contexts: List[ScoredContext] = []
        theme_name_lower = theme_name.lower().strip()

        # First pass: exact/partial match
        for te in all_evidence:
            if (te.theme_id and te.theme_id.lower() == theme_name_lower) or (
                te.theme_name and theme_name_lower in te.theme_name.lower()
            ):
                matching_contexts.extend(te.scored_contexts)

        if not matching_contexts:
            best_match_theme, best_match_score = _best_fuzzy_match(
                theme_name_lower, all_evidence, key=lambda te: te.theme_name or ""
            )
            if best_match_theme and best_match_score >= FUZZY_MATCH_THRESHOLD:
                logger.info(
                    f"Fuzzy matched '{theme_name}' to '{best_match_theme.theme_name}' "
                    f"(score: {best_match_score})"
                )
                matching_contexts.extend(best_match_theme.scored_contexts)

        if not matching_contexts:
            # Fallback: use all_scored_contexts from state
            all_contexts: List[ScoredContext] = state.get("all_scored_contexts") or []
            if all_contexts:
                logger.info(
                    f"No theme match for '{theme_name}', "
                    f"falling back to all {len(all_contexts)} contexts"
                )
                matching_contexts = all_contexts
                fallback_used = True
            else:
                return ToolResult.ok([], fallback_used=True)
        else:
            fallback_used = False

        # Filter by relevance score
        filtered = [
            ctx for ctx in matching_contexts if ctx.relevance_score >= min_relevance
        ]

        # Optional: boost contexts that match the user's stated population/outcomes
        target_population = state.get("target_population") or []
        target_outcomes = state.get("target_outcomes") or []

        pop_terms = [str(p).lower() for p in target_population if p]
        out_terms = [str(o).lower() for o in target_outcomes if o]

        def _intent_bonus(ctx: ScoredContext) -> int:
            if not (pop_terms or out_terms):
                return 0
            hay = f"{ctx.summary or ''} {ctx.chunk_text or ''}".lower()
            bonus = 0
            # Small, bounded bonuses; relevance_score remains the primary ordering.
            if pop_terms and any(t in hay for t in pop_terms):
                bonus += 1
            if out_terms and any(t in hay for t in out_terms):
                bonus += 1
            return bonus

        # Sort by relevance (descending), then intent bonus, then stable doc_id
        sorted_contexts = sorted(
            filtered,
            key=lambda c: (-(c.relevance_score), -_intent_bonus(c), c.document_id),
        )

        # Deduplicate by document_id (keep highest scoring)
        seen_docs: set = set()
        deduped: List[ScoredContext] = []
        for ctx in sorted_contexts:
            if ctx.document_id not in seen_docs:
                deduped.append(ctx)
                seen_docs.add(ctx.document_id)

        # Limit results
        final_contexts = deduped[:max_results]

        # Convert to output format - DO NOT drop evidence without citations
        evidence_items: List[ThemeEvidenceItem] = []
        uncited_counter = 100  # Start uncited at 100+ to distinguish

        for ctx in final_contexts:
            # Get citation number - assign temporary if missing
            cit_num = doc_citation_map.get(ctx.document_id, 0)
            if cit_num == 0:
                # Don't drop - assign temporary citation number and log
                uncited_counter += 1
                cit_num = uncited_counter
                logger.debug(
                    f"No citation for doc {ctx.document_id}, "
                    f"assigning temporary [{cit_num}]"
                )

            # Get document quality
            doc_score_info = doc_scores.get(ctx.document_id, {})
            evidence_strength = doc_score_info.get("evidence_score")

            # Get document title
            doc_meta = doc_metadata.get(ctx.document_id, {})
            doc_title = doc_meta.get("title") or ctx.document_title or "Unknown"

            evidence_items.append(
                ThemeEvidenceItem(
                    summary=ctx.summary,
                    citation_number=cit_num,
                    document_title=doc_title,
                    relevance_score=ctx.relevance_score,
                    document_quality=evidence_strength,
                    chunk_text=ctx.chunk_text[:500] if ctx.chunk_text else "",
                )
            )

        logger.info(
            f"get_theme_evidence('{theme_name}'): "
            f"found {len(evidence_items)} items "
            f"(filtered from {len(matching_contexts)}, fallback={fallback_used})"
        )

        return ToolResult.ok(
            [item.model_dump() for item in evidence_items],
            fallback_used=fallback_used,
        )

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "theme_name": {
                    "type": "string",
                    "description": (
                        "Name of intervention or issue theme to retrieve evidence for. "
                        "Examples: 'Physical activity interventions', "
                        "'School-based programmes', 'Dietary interventions'"
                    ),
                },
                "min_relevance": {
                    "type": "integer",
                    "description": (
                        "Minimum RCS relevance score (0-10). "
                        "Default is 5. Use higher values (6-8) for more precise evidence."
                    ),
                    "default": 5,
                    "minimum": 0,
                    "maximum": 10,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of evidence items to return.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["theme_name"],
        }


# Functional interface for direct use
async def get_theme_evidence(
    state: Dict[str, Any],
    theme_name: str,
    min_relevance: int = 5,
    max_results: int = 5,
) -> ToolResult:
    """Retrieve RCS-scored evidence for a specific theme.

    Convenience function wrapping GetThemeEvidenceTool.

    Args:
        state: Current synthesis state.
        theme_name: Name of intervention or issue theme.
        min_relevance: Minimum RCS relevance score (0-10).
        max_results: Maximum evidence items to return.

    Returns:
        ToolResult with list of evidence items.
    """
    tool = GetThemeEvidenceTool()
    return await tool.execute(
        state,
        theme_name=theme_name,
        min_relevance=min_relevance,
        max_results=max_results,
    )


class CitationContextItem(BaseModel):
    """Full context for a specific citation.

    Attributes:
        citation_number: The [N] citation number.
        document_title: Title of the source document.
        full_text: Full chunk text (not truncated).
        summary: RCS contextual summary.
        relevance_score: RCS relevance score (0-10).
        document_quality: Evidence strength score (1-5).
        author_year: Author and year string.
        url: Document URL if available.
    """

    citation_number: int
    document_title: str
    full_text: str
    summary: str = ""
    relevance_score: int = 0
    document_quality: Optional[int] = None
    author_year: str = ""
    url: Optional[str] = None


class GetCitationContextTool(BaseTool):
    """Tool to retrieve full context for a specific citation number.

    Useful during verification to check if a claim matches the cited evidence.
    Returns the full chunk text and metadata for a given citation.
    """

    name = "get_citation_context"
    description = (
        "Get full context for a specific citation number [N]. "
        "Use during verification to check if a claim matches the cited evidence. "
        "Returns the full chunk text, summary, and document metadata."
    )
    max_results = 1

    async def execute(
        self,
        state: Dict[str, Any],
        citation_number: int,
    ) -> ToolResult:
        """Execute the get_citation_context tool.

        Args:
            state: Current synthesis state.
            citation_number: The [N] citation number to look up.

        Returns:
            ToolResult with CitationContextItem.
        """
        # Get grounded citations from state
        grounded_citations = state.get("grounded_citations") or []
        all_scored_contexts: List[ScoredContext] = (
            state.get("all_scored_contexts") or []
        )
        doc_scores: Dict[str, Dict[str, Any]] = state.get("doc_scores") or {}
        doc_metadata: Dict[str, Dict[str, Any]] = state.get("doc_metadata") or {}

        # Find the citation info
        citation_info = None
        for cit in grounded_citations:
            if getattr(cit, "citation_number", 0) == citation_number:
                citation_info = cit
                break

        if not citation_info:
            return ToolResult.fail(f"Citation [{citation_number}] not found")

        # Get document ID from citation
        doc_id = getattr(citation_info, "analysis_document_id", None)
        if not doc_id:
            return ToolResult.fail(f"Citation [{citation_number}] has no document ID")

        # Find scored context for this document (for full text)
        matching_context = None
        for ctx in all_scored_contexts:
            if ctx.document_id == doc_id:
                matching_context = ctx
                break

        # Build response
        doc_meta = doc_metadata.get(doc_id, {})
        doc_score_info = doc_scores.get(doc_id, {})

        # Get supporting quote from citation or chunk text from context
        full_text = getattr(citation_info, "supporting_quote", "") or ""
        if not full_text and matching_context:
            full_text = matching_context.chunk_text or ""

        # Build author_year string
        author = doc_meta.get("author_short") or getattr(
            citation_info, "author_short", ""
        )
        year = doc_meta.get("year") or getattr(citation_info, "year", "")
        author_year = f"{author}, {year}" if author and year else (author or str(year))

        result = CitationContextItem(
            citation_number=citation_number,
            document_title=getattr(citation_info, "title", "")
            or doc_meta.get("title", "Unknown"),
            full_text=full_text,
            summary=matching_context.summary if matching_context else "",
            relevance_score=(
                matching_context.relevance_score if matching_context else 0
            ),
            document_quality=doc_score_info.get("evidence_score"),
            author_year=author_year,
            url=getattr(citation_info, "url", None) or doc_meta.get("url"),
        )

        logger.info(
            f"get_citation_context([{citation_number}]): "
            f"found '{result.document_title}' ({len(full_text)} chars)"
        )

        return ToolResult.ok(result.model_dump())

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "citation_number": {
                    "type": "integer",
                    "description": (
                        "The citation number [N] to look up. " "Example: 3 for [3]"
                    ),
                },
            },
            "required": ["citation_number"],
        }


# Functional interface for direct use
async def get_citation_context(
    state: Dict[str, Any],
    citation_number: int,
) -> ToolResult:
    """Get full context for a specific citation number.

    Convenience function wrapping GetCitationContextTool.

    Args:
        state: Current synthesis state.
        citation_number: The [N] citation number to look up.

    Returns:
        ToolResult with citation context.
    """
    tool = GetCitationContextTool()
    return await tool.execute(state, citation_number=citation_number)


class InterventionOutcomeItem(BaseModel):
    """Aggregated outcome data for an intervention.

    Attributes:
        intervention_name: Name of the intervention.
        brief_description: One-sentence description.
        effect_consensus: Overall effect direction (increase/decrease/mixed/no change/insufficient).
        positive_count: Number of studies showing positive effects.
        negative_count: Number of studies showing negative effects.
        null_count: Number of studies showing null effects.
        sample_effect_sizes: Example effect sizes from studies.
        related_outcomes: List of outcome themes this intervention affects.
        countries: Countries where intervention was studied.
        study_types: Count of each study type (e.g., {"RCT": 3, "Systematic Review": 2}).
        frequency: Number of documents mentioning this intervention.
        supporting_doc_ids: Document UUIDs supporting this intervention.
    """

    intervention_name: str
    brief_description: str = ""
    effect_consensus: Optional[str] = None
    positive_count: int = 0
    negative_count: int = 0
    null_count: int = 0
    sample_effect_sizes: List[str] = []
    related_outcomes: List[str] = []
    countries: List[str] = []
    study_types: Dict[str, int] = {}
    frequency: int = 0
    supporting_doc_ids: List[str] = []


class GetInterventionOutcomesTool(BaseTool):
    """Tool to get aggregated outcome data for interventions.

    Queries pre-computed aggregated_interventions from synthesis state.
    Returns rich outcome data including effect consensus, effect sizes,
    related outcomes, and study types.
    """

    name = "get_intervention_outcomes"
    description = (
        "Get aggregated outcome data for interventions. "
        "Returns effect consensus (positive/negative/mixed), effect sizes, "
        "related outcomes, study types, and countries. "
        "Use to populate the interventions table with rich outcome information."
    )
    max_results = 10

    async def execute(
        self,
        state: Dict[str, Any],
        intervention_name: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> ToolResult:
        """Execute the get_intervention_outcomes tool.

        Args:
            state: Current synthesis state.
            intervention_name: Optional filter by intervention name (fuzzy match).
            max_results: Maximum interventions to return.

        Returns:
            ToolResult with list of InterventionOutcomeItem.
        """
        max_results = max_results or self.max_results

        # Get aggregated interventions from state
        aggregated_interventions = state.get("aggregated_interventions") or []

        if not aggregated_interventions:
            return ToolResult.ok([], fallback_used=True)

        results: List[InterventionOutcomeItem] = []

        filtered_interventions = aggregated_interventions
        if intervention_name:
            match, score = _best_fuzzy_match(
                intervention_name,
                aggregated_interventions,
                key=lambda i: getattr(i, "intervention_name", "") or "",
            )
            filtered_interventions = (
                [match] if match and score >= FUZZY_MATCH_THRESHOLD else []
            )

        for intervention in filtered_interventions:
            results.append(
                InterventionOutcomeItem(
                    intervention_name=getattr(intervention, "intervention_name", ""),
                    brief_description=getattr(intervention, "brief_description", ""),
                    effect_consensus=getattr(intervention, "effect_consensus", None),
                    positive_count=getattr(intervention, "positive_count", 0),
                    negative_count=getattr(intervention, "negative_count", 0),
                    null_count=getattr(intervention, "null_count", 0),
                    sample_effect_sizes=getattr(
                        intervention, "sample_effect_sizes", []
                    ),
                    related_outcomes=getattr(intervention, "related_outcomes", []),
                    countries=getattr(intervention, "countries", []),
                    study_types=getattr(intervention, "study_types", {}),
                    frequency=getattr(intervention, "frequency", 0),
                    supporting_doc_ids=getattr(intervention, "supporting_doc_ids", []),
                )
            )

            if len(results) >= max_results:
                break

        # Sort by frequency (most evidence first)
        results.sort(key=lambda x: x.frequency, reverse=True)

        logger.info(
            f"get_intervention_outcomes('{intervention_name or 'all'}'): "
            f"found {len(results)} interventions"
        )

        return ToolResult.ok([r.model_dump() for r in results])

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "intervention_name": {
                    "type": "string",
                    "description": (
                        "Optional: filter by intervention name (fuzzy match). "
                        "Leave empty to get all interventions sorted by evidence frequency."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum interventions to return.",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": [],
        }


class GetInterventionDetailsTool(BaseTool):
    """Tool to extract richer delivery/features/subgroup detail for interventions.

    Combines aggregated intervention data with scored contexts and document metadata
    to surface delivery methods, target populations, subgroup effects, and example
    effect sizes for interventions.
    """

    name = "get_intervention_details"
    description = (
        "Retrieve intervention delivery features, target populations, subgroup effects, "
        "and effect-size snippets by combining aggregated intervention data with scored "
        "contexts and document metadata."
    )
    max_results = 10
    max_contexts_per_item = 5

    FEATURE_KEYWORDS = {
        "school": "School-based",
        "family": "Family involvement",
        "community": "Community-based",
        "digital": "Digital/online delivery",
        "home": "Home-based",
        "clinic": "Clinic/primary care",
        "policy": "Policy/regulatory",
        "tax": "Fiscal/price measure",
        "marketing": "Marketing/advertising control",
        "physical activity": "Physical activity structured sessions",
        "nutrition": "Nutrition education",
        "behaviour": "Behavioural counselling",
    }

    POPULATION_KEYWORDS = {
        "children": "Children",
        "adolescent": "Adolescents",
        "youth": "Adolescents",
        "girls": "Girls",
        "boys": "Boys",
        "overweight": "Overweight/obese",
        "obese": "Overweight/obese",
        "low-income": "Low-income",
        "deprived": "Deprived communities",
    }

    SUBGROUP_KEYWORDS = {
        "girls": "More effective in girls",
        "boys": "More effective in boys",
        "younger": "More effective in younger children",
        "older": "More effective in older children",
        "overweight": "Greater effects in overweight/obese",
        "obese": "Greater effects in overweight/obese",
        "low-income": "Effects in low-income populations",
        "deprived": "Effects in deprived settings",
    }

    async def execute(
        self,
        state: Dict[str, Any],
        intervention_name: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> ToolResult:
        max_results = max_results or self.max_results

        aggregated_interventions = state.get("aggregated_interventions") or []
        all_contexts: List[ScoredContext] = state.get("all_scored_contexts") or []
        doc_citation_map: Dict[str, int] = state.get("doc_citation_map") or {}
        doc_metadata: Dict[str, Dict[str, Any]] = state.get("doc_metadata") or {}

        if not aggregated_interventions and not all_contexts:
            return ToolResult.ok([], fallback_used=True)

        # Map external doc_id -> internal doc_uuid when needed
        doc_id_to_uuid: Dict[str, str] = {}
        for doc_uuid, meta in (doc_metadata or {}).items():
            ext_id = meta.get("doc_id")
            if ext_id:
                doc_id_to_uuid[str(ext_id)] = str(doc_uuid)

        results: List[InterventionDetails] = []

        if intervention_name:
            match, score = _best_fuzzy_match(
                intervention_name,
                aggregated_interventions,
                key=lambda i: getattr(i, "intervention_name", "") or "",
            )
            candidates = [match] if match and score >= FUZZY_MATCH_THRESHOLD else []
        else:
            candidates = aggregated_interventions

        for intervention in candidates:
            name = getattr(intervention, "intervention_name", "")
            if not name:
                continue

            supporting_doc_ids = getattr(intervention, "supporting_doc_ids", []) or []
            # Normalise to internal doc UUIDs (all_scored_contexts/document_id and doc_citation_map are UUID-keyed)
            supporting_doc_uuids: List[str] = []
            for sid in supporting_doc_ids:
                sid_str = str(sid)
                if sid_str in doc_citation_map or sid_str in doc_metadata:
                    supporting_doc_uuids.append(sid_str)
                elif sid_str in doc_id_to_uuid:
                    supporting_doc_uuids.append(doc_id_to_uuid[sid_str])

            matched_contexts = [
                ctx
                for ctx in all_contexts
                if (not supporting_doc_uuids or ctx.document_id in supporting_doc_uuids)
                and (
                    name.lower() in (ctx.summary or "").lower()
                    or name.lower() in (ctx.chunk_text or "").lower()
                )
            ]

            if not matched_contexts and not supporting_doc_ids:
                # Fallback: any context mentioning the intervention name
                matched_contexts = [
                    ctx
                    for ctx in all_contexts
                    if name.lower() in (ctx.summary or "").lower()
                    or name.lower() in (ctx.chunk_text or "").lower()
                ]

            matched_contexts = matched_contexts[: self.max_contexts_per_item]

            delivery_features = self._extract_delivery_features(matched_contexts)
            target_population = self._extract_population(matched_contexts)
            subgroup_effects = self._extract_subgroups(matched_contexts)

            effect_sizes = list(getattr(intervention, "sample_effect_sizes", []) or [])
            if not effect_sizes:
                effect_sizes = self._extract_effect_sizes(matched_contexts)

            supporting_citations = [
                doc_citation_map[doc_id]
                for doc_id in supporting_doc_uuids
                if doc_id in doc_citation_map
            ]

            results.append(
                InterventionDetails(
                    intervention_name=name,
                    delivery_features=delivery_features,
                    target_population=target_population,
                    subgroup_effects=subgroup_effects,
                    effect_sizes=effect_sizes,
                    supporting_citations=supporting_citations,
                )
            )

            if len(results) >= max_results:
                break

        logger.info(
            f"get_intervention_details('{intervention_name or 'all'}'): "
            f"found {len(results)} items"
        )

        return ToolResult.ok([r.model_dump() for r in results])

    def _extract_delivery_features(self, contexts: List[ScoredContext]) -> List[str]:
        feats: set = set()
        for ctx in contexts:
            text = f"{ctx.summary} {ctx.chunk_text}".lower()
            for kw, label in self.FEATURE_KEYWORDS.items():
                if kw in text:
                    feats.add(label)
        return list(feats)[:5]

    def _extract_population(self, contexts: List[ScoredContext]) -> List[str]:
        pops: set = set()
        for ctx in contexts:
            text = f"{ctx.summary} {ctx.chunk_text}".lower()
            for kw, label in self.POPULATION_KEYWORDS.items():
                if kw in text:
                    pops.add(label)
        return list(pops)[:5]

    def _extract_subgroups(self, contexts: List[ScoredContext]) -> List[str]:
        subs: set = set()
        for ctx in contexts:
            text = f"{ctx.summary} {ctx.chunk_text}".lower()
            for kw, label in self.SUBGROUP_KEYWORDS.items():
                if kw in text:
                    subs.add(label)
        return list(subs)[:5]

    def _extract_effect_sizes(self, contexts: List[ScoredContext]) -> List[str]:
        sizes: List[str] = []
        for ctx in contexts:
            text = f"{ctx.summary} {ctx.chunk_text}"
            matches = re.findall(r"([-+]?\d+\.?\d*\s*(?:kg/m²|kg|%))", text)
            for m in matches:
                snippet = m.strip()
                if snippet not in sizes:
                    sizes.append(snippet)
            if len(sizes) >= 5:
                break
        return sizes[:5]

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "intervention_name": {
                    "type": "string",
                    "description": (
                        "Optional: filter by intervention name (fuzzy match). "
                        "Leave empty to get all interventions sorted by evidence frequency."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum interventions to return.",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": [],
        }


class TopStudyItem(BaseModel):
    """A top-ranked study supporting an intervention category.

    Attributes:
        citation_number: The [N] citation number for this study (0 if unknown).
        title: Document title.
        author_year: Short author/year string for display.
        evidence_strength: Evidence quality rating (1-5), if available.
        predicted_impact: Predicted policy impact rating (1-5), if available.
        study_type: Study type/category (if available from metadata).
        key_context_summary: Highest-relevance RCS summary for this document.
        relevance_score: RCS relevance score (0-10) for the selected context.
        url: Canonical URL/PDF URL, if available.
        key_context_chunk_text: Truncated supporting text from the highest-relevance context.
        study_location: Where the study took place (country/city) if available from extracted intervention metadata.
    """

    citation_number: int
    title: str
    author_year: str = ""
    evidence_strength: Optional[int] = None
    predicted_impact: Optional[int] = None
    study_type: Optional[str] = None
    key_context_summary: str = ""
    relevance_score: int = 0
    url: Optional[str] = None
    key_context_chunk_text: str = ""
    study_location: str = ""
    extracted_outcomes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Structured outcome results extracted from upstream analysis_extractions for this "
            "document, filtered to intervention_idx values that belong to the requested "
            "intervention theme (option C)."
        ),
    )


class GetTopStudiesTool(BaseTool):
    """Tool to retrieve top studies for an intervention category.

    Selects studies using deterministic doc quality signals from synthesis state:
    - evidence_score (1-5)
    - impact_score (1-5) aka predicted impact

    Returns 1-2 studies with their highest-relevance RCS context, enabling the
    generator to write a concrete 'Key Study' implementation description.
    """

    name = "get_top_studies"
    description = (
        "Get the top 1-2 studies supporting an intervention category, ranked by "
        "evidence strength and predicted policy impact (doc_scores). "
        "Returns study metadata plus the highest-relevance contextual summary and "
        "supporting text snippet to describe concrete implementation details."
    )
    max_results = 2

    async def execute(
        self,
        state: Dict[str, Any],
        intervention_name: str,
        max_results: Optional[int] = None,
    ) -> ToolResult:
        """Execute get_top_studies.

        Args:
            state: Current synthesis state.
            intervention_name: Intervention category name (e.g., "Diet-only interventions").
            max_results: Maximum studies to return (default 2).

        Returns:
            ToolResult with list of TopStudyItem.
        """
        max_results = max_results or self.max_results
        intervention_name = (intervention_name or "").strip()
        if not intervention_name:
            return ToolResult.ok([], fallback_used=True)

        aggregated_interventions = state.get("aggregated_interventions") or []
        doc_scores: Dict[str, Dict[str, Any]] = state.get("doc_scores") or {}
        doc_metadata: Dict[str, Dict[str, Any]] = state.get("doc_metadata") or {}
        doc_citation_map: Dict[str, int] = state.get("doc_citation_map") or {}
        all_contexts: List[ScoredContext] = state.get("all_scored_contexts") or []
        raw_extractions = state.get("raw_extractions") or []
        final_intervention_themes = state.get("final_intervention_themes") or []
        # External doc_id -> internal doc_uuid (doc_metadata is keyed by doc_uuid)
        doc_id_to_uuid: Dict[str, str] = {}
        for doc_uuid, meta in (doc_metadata or {}).items():
            ext_id = meta.get("doc_id")
            if ext_id:
                doc_id_to_uuid[str(ext_id)] = str(doc_uuid)

        # doc_uuid -> observed study countries (from intervention extractions; closer to study setting than publication)
        doc_uuid_to_countries: Dict[str, List[str]] = {}
        for ext in raw_extractions:
            if not isinstance(ext, dict):
                continue
            if ext.get("type") != "intervention":
                continue
            doc_uuid = str(ext.get("doc_uuid") or "")
            country = str(ext.get("country") or "").strip()
            if not doc_uuid or not country:
                continue
            doc_uuid_to_countries.setdefault(doc_uuid, [])
            if country not in doc_uuid_to_countries[doc_uuid]:
                doc_uuid_to_countries[doc_uuid].append(country)

        # Find the best matching intervention category (by name)
        best_match, best_score = _best_fuzzy_match(
            intervention_name,
            aggregated_interventions,
            key=lambda i: getattr(i, "intervention_name", "") or "",
        )

        supporting_doc_ids: List[str] = []
        fallback_used = False

        if best_match and best_score >= FUZZY_MATCH_THRESHOLD:
            supporting_doc_ids = getattr(best_match, "supporting_doc_ids", []) or []
        else:
            fallback_used = True
            # Fallback: use any document contexts that mention the intervention label
            candidate_docs = []
            needle = intervention_name.lower()
            for ctx in all_contexts:
                hay = f"{ctx.summary} {ctx.chunk_text}".lower()
                if needle in hay:
                    candidate_docs.append(ctx.document_id)
            # Deduplicate while preserving order
            supporting_doc_ids = list(dict.fromkeys(candidate_docs))

        if not supporting_doc_ids:
            return ToolResult.ok([], fallback_used=True)

        # Normalise supporting doc ids to internal UUIDs
        supporting_doc_uuids: List[str] = []
        for sid in supporting_doc_ids:
            sid_str = str(sid)
            if (
                sid_str in doc_scores
                or sid_str in doc_metadata
                or sid_str in doc_citation_map
            ):
                supporting_doc_uuids.append(sid_str)
            elif sid_str in doc_id_to_uuid:
                supporting_doc_uuids.append(doc_id_to_uuid[sid_str])

        # Prefer documents that we can actually cite (avoid citation_number=0 -> [0])
        citable_doc_uuids = [u for u in supporting_doc_uuids if doc_citation_map.get(u)]
        candidates = citable_doc_uuids or supporting_doc_uuids
        if not candidates:
            return ToolResult.ok([], fallback_used=True)

        # Build quick lookup: doc_id -> best context (highest relevance_score)
        best_context_by_doc: Dict[str, ScoredContext] = {}
        for ctx in all_contexts:
            doc_id = ctx.document_id
            if doc_id not in candidates:
                continue
            current = best_context_by_doc.get(doc_id)
            if current is None or ctx.relevance_score > current.relevance_score:
                best_context_by_doc[doc_id] = ctx

        def _rank_tuple(doc_id: str) -> tuple:
            scores = doc_scores.get(doc_id, {}) or {}
            evidence = scores.get("evidence_score") or 0
            impact = scores.get("impact_score") or 0
            ctx = best_context_by_doc.get(doc_id)
            rel = ctx.relevance_score if ctx else 0
            # Optional: boost studies whose best context matches the user's stated population/outcomes
            target_population = state.get("target_population") or []
            target_outcomes = state.get("target_outcomes") or []
            pop_terms = [str(p).lower() for p in target_population if p]
            out_terms = [str(o).lower() for o in target_outcomes if o]
            hay = f"{(ctx.summary if ctx else '')} {(ctx.chunk_text if ctx else '')}".lower()
            intent_bonus = 0
            if pop_terms and any(t in hay for t in pop_terms):
                intent_bonus += 1
            if out_terms and any(t in hay for t in out_terms):
                intent_bonus += 1

            # Primary: evidence+impact; then intent match; then evidence; then impact; then relevance
            return (evidence + impact, intent_bonus, evidence, impact, rel)

        ranked_doc_ids = sorted(candidates, key=_rank_tuple, reverse=True)[:max_results]

        def _extract_key_study_outcomes(doc_uuid: str) -> List[Dict[str, Any]]:
            """Extract structured outcomes for a key study document for the requested theme.

            Uses upstream analysis_extractions fields (already in state.raw_extractions) and
            matches results by intervention_idx for interventions that belong to the theme
            within this document (option C).
            """
            # 1) Find matching intervention theme by name (exact/partial, then fuzzy).
            theme = None
            name_lower = intervention_name.lower().strip()
            for t in final_intervention_themes:
                t_name = (
                    getattr(t, "name", None)
                    or getattr(t, "theme_name", None)
                    or getattr(t, "intervention_name", None)
                    or ""
                )
                if t_name and t_name.lower().strip() == name_lower:
                    theme = t
                    break

            if theme is None:
                best = None
                best_score_local = 0
                for t in final_intervention_themes:
                    t_name = (
                        getattr(t, "name", None)
                        or getattr(t, "theme_name", None)
                        or getattr(t, "intervention_name", None)
                        or ""
                    )
                    if not t_name:
                        continue
                    ratio = fuzz.ratio(name_lower, t_name.lower())
                    partial = fuzz.partial_ratio(name_lower, t_name.lower())
                    score = max(ratio, partial)
                    if score > best_score_local:
                        best_score_local = score
                        best = t
                if best and best_score_local >= FUZZY_MATCH_THRESHOLD:
                    theme = best

            if theme is None:
                return []

            concepts = getattr(theme, "concepts", None) or []
            concept_ids: set = set()
            for c in concepts:
                cid = getattr(c, "id", None) or (
                    c.get("id") if isinstance(c, dict) else None
                )
                if cid:
                    concept_ids.add(str(cid))

            if not concept_ids:
                return []

            # 2) For this document, collect intervention_idx values for intervention extractions
            # that belong to this theme.
            idxs: set = set()
            for ext in raw_extractions:
                if not isinstance(ext, dict):
                    continue
                if ext.get("type") != "intervention":
                    continue
                if str(ext.get("doc_uuid") or "") != str(doc_uuid):
                    continue
                if str(ext.get("id") or "") not in concept_ids:
                    continue
                idx = ext.get("intervention_idx")
                if idx is None:
                    continue
                try:
                    idxs.add(int(idx))
                except (TypeError, ValueError):
                    continue

            if not idxs:
                return []

            # 3) Collect result extractions for all matching idxs (option C).
            seen: set = set()
            outcomes: List[Dict[str, Any]] = []
            for ext in raw_extractions:
                if not isinstance(ext, dict):
                    continue
                if ext.get("type") != "result":
                    continue
                if str(ext.get("doc_uuid") or "") != str(doc_uuid):
                    continue
                idx = ext.get("intervention_idx")
                try:
                    idx_int = int(idx) if idx is not None else None
                except (TypeError, ValueError):
                    idx_int = None
                if idx_int is None or idx_int not in idxs:
                    continue

                outcome_var = str(ext.get("outcome_variable") or "").strip()
                effect_dir = str(ext.get("effect_direction") or "").strip()
                effect_size = str(ext.get("effect_size") or "").strip()
                if effect_size.lower() in {"null", "none", "n/a"}:
                    effect_size = ""

                item = {
                    "intervention_idx": idx_int,
                    "outcome_variable": outcome_var,
                    "effect_direction": effect_dir,
                    "effect_size": effect_size,
                    "effect_size_type": str(ext.get("effect_size_type") or "").strip(),
                    "population_measured": str(
                        ext.get("population_measured") or ""
                    ).strip(),
                    "subgroup_or_dose": str(ext.get("subgroup_or_dose") or "").strip(),
                    "supporting_quote": str(ext.get("supporting_quote") or "").strip(),
                    "result_text": str(ext.get("result_text") or "").strip(),
                }
                key = (
                    item["intervention_idx"],
                    item["outcome_variable"],
                    item["effect_direction"],
                    item["effect_size"],
                )
                if key in seen:
                    continue
                seen.add(key)
                outcomes.append(item)

            # Prefer explicit effect sizes, then keep a small capped set.
            outcomes.sort(
                key=lambda o: (
                    0 if (o.get("effect_size") or "").strip() else 1,
                    (o.get("outcome_variable") or "").lower(),
                )
            )
            return outcomes[:8]

        results: List[TopStudyItem] = []
        for doc_id in ranked_doc_ids:
            meta = doc_metadata.get(doc_id, {}) or {}
            scores = doc_scores.get(doc_id, {}) or {}
            ctx = best_context_by_doc.get(doc_id)

            author = meta.get("author_short") or ""
            year = meta.get("year")
            author_year = (
                f"{author}, {year}"
                if author and year
                else (author or (str(year) if year else ""))
            )

            results.append(
                TopStudyItem(
                    citation_number=int(doc_citation_map.get(doc_id) or 0),
                    title=meta.get("title") or "Unknown",
                    author_year=author_year,
                    evidence_strength=scores.get("evidence_score"),
                    predicted_impact=scores.get("impact_score"),
                    study_type=meta.get("document_type"),
                    key_context_summary=(ctx.summary if ctx else ""),
                    relevance_score=(ctx.relevance_score if ctx else 0),
                    url=meta.get("url")
                    or meta.get("pdf_url")
                    or meta.get("landing_page_url"),
                    key_context_chunk_text=(
                        (ctx.chunk_text or "")[:600] if ctx else ""
                    ),
                    study_location=", ".join(doc_uuid_to_countries.get(doc_id, [])[:2]),
                    extracted_outcomes=_extract_key_study_outcomes(doc_id),
                )
            )

        logger.info(
            f"get_top_studies('{intervention_name}'): returned {len(results)} studies "
            f"(fallback={fallback_used}, best_match_score={best_score})"
        )

        return ToolResult.ok(
            [r.model_dump() for r in results], fallback_used=fallback_used
        )

    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "intervention_name": {
                    "type": "string",
                    "description": (
                        "Intervention category name to retrieve top studies for. "
                        "Example: 'Multi-component behavioural programmes'."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum studies to return (default 2).",
                    "default": 2,
                    "minimum": 1,
                    "maximum": 5,
                },
            },
            "required": ["intervention_name"],
        }


# Functional interface for direct use
async def get_top_studies(
    state: Dict[str, Any],
    intervention_name: str,
    max_results: int = 2,
) -> ToolResult:
    """Get the top studies supporting an intervention category.

    Convenience function wrapping GetTopStudiesTool.

    Args:
        state: Current synthesis state.
        intervention_name: Intervention category name.
        max_results: Maximum studies to return.

    Returns:
        ToolResult with list of top studies.
    """
    tool = GetTopStudiesTool()
    return await tool.execute(
        state,
        intervention_name=intervention_name,
        max_results=max_results,
    )


# Functional interface for direct use
async def get_intervention_outcomes(
    state: Dict[str, Any],
    intervention_name: Optional[str] = None,
    max_results: int = 10,
) -> ToolResult:
    """Get aggregated outcome data for interventions.

    Convenience function wrapping GetInterventionOutcomesTool.

    Args:
        state: Current synthesis state.
        intervention_name: Optional filter by intervention name.
        max_results: Maximum interventions to return.

    Returns:
        ToolResult with list of intervention outcome data.
    """
    tool = GetInterventionOutcomesTool()
    return await tool.execute(
        state, intervention_name=intervention_name, max_results=max_results
    )


# Register tools with global registry
_theme_evidence_tool = GetThemeEvidenceTool()
_citation_context_tool = GetCitationContextTool()
_intervention_outcomes_tool = GetInterventionOutcomesTool()
_intervention_details_tool = GetInterventionDetailsTool()
_top_studies_tool = GetTopStudiesTool()
register_tool(_theme_evidence_tool)
register_tool(_citation_context_tool)
register_tool(_intervention_outcomes_tool)
register_tool(_intervention_details_tool)
register_tool(_top_studies_tool)
