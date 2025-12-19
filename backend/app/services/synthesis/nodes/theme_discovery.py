"""
Theme discovery nodes for the synthesis workflow.

Phase 2: Discover themes from concepts using LLM, critique them,
and map concepts back to themes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List, Optional

from app.utils.llm.llm_utils import get_llm
from app.services.synthesis.state import (
    SynthesisState,
    Concept,
    DiscoveredTheme,
    FinalTheme,
    ThemesOut,
    ThemeBranch,
)
from app.services.synthesis.utils import (
    THEME_MODEL,
    MAPPING_MODEL,
    escape_braces,
    build_langfuse_config,
)
from app.services.synthesis.prompts import (
    build_discover_themes_prompt,
    make_discover_themes_instructions,
    build_theme_critique_prompt,
    build_classify_concept_prompt,
)

logger = logging.getLogger(__name__)


async def _discover_themes(
    concepts: List[Concept],
    rq: str,
    state: SynthesisState,
    branch: ThemeBranch,
) -> List[DiscoveredTheme]:
    """Discover themes for a set of concepts.

    Args:
        concepts: List of concepts to cluster into themes.
        rq: Research question for context.
        state: Current workflow state for Langfuse config.
        branch: Which branch (issue/intervention/outcome).

    Returns:
        List of discovered themes.
    """
    if not concepts:
        return []

    tags = [
        "component:synthesis",
        "component:synthesis.discover_themes",
        f"branch:{branch}",
        f"model:{THEME_MODEL}",
    ]
    instructions = make_discover_themes_instructions(None)
    prompt = build_discover_themes_prompt()
    llm = get_llm(THEME_MODEL, temperature=0.0).with_structured_output(ThemesOut)

    try:
        out: ThemesOut = await llm.ainvoke(
            prompt.format(
                critique_instruction=instructions,
                rq=escape_braces(rq),
                concepts=escape_braces(json.dumps([c.model_dump() for c in concepts])),
            ),
            config={
                **build_langfuse_config(state, tags, {"branch": branch}),
                "run_name": "synthesis.discover_themes",
            },
        )
        return out.themes or []
    except Exception as e:
        logger.warning(f"Theme discovery failed for {branch}: {e}")
        return [
            DiscoveredTheme(
                theme_name="General Theme",
                theme_description="Auto-generated placeholder",
            )
        ]


async def _critique_themes(
    themes: List[DiscoveredTheme],
    rq: str,
    state: SynthesisState,
    branch: ThemeBranch,
) -> None:
    """Critique themes for quality assurance.

    Args:
        themes: Themes to critique.
        rq: Research question for context.
        state: Current workflow state for Langfuse config.
        branch: Which branch (issue/intervention/outcome).
    """
    if not themes:
        return

    print(f"--- Critiquing {branch.title()} Themes ---")
    tags = [
        "component:synthesis",
        "component:synthesis.critique",
        f"branch:{branch}",
        f"model:{THEME_MODEL}",
    ]
    prompt = build_theme_critique_prompt(branch)
    llm = get_llm(THEME_MODEL, temperature=0.0)

    await llm.ainvoke(
        prompt.format(
            rq=escape_braces(rq),
            themes=escape_braces(json.dumps([t.model_dump() for t in themes])),
        ),
        config={
            **build_langfuse_config(state, tags, {"branch": branch}),
            "run_name": "synthesis.critique",
        },
    )


async def _map_concepts_to_themes(
    concepts: List[Concept],
    themes: List[DiscoveredTheme],
    state: SynthesisState,
    branch: ThemeBranch,
) -> List[FinalTheme]:
    """Map concepts to discovered themes via LLM classification.

    Args:
        concepts: Concepts to classify.
        themes: Available themes.
        state: Current workflow state for Langfuse config.
        branch: Which branch (issue/intervention/outcome).

    Returns:
        List of final themes with mapped concepts.
    """
    if not concepts or not themes:
        return []

    print(f"--- Mapping {branch.title()} Concepts ---")
    theme_defs = [
        {"name": t.theme_name, "description": t.theme_description} for t in themes
    ]
    tags = [
        "component:synthesis",
        "component:synthesis.map",
        f"branch:{branch}",
        f"model:{MAPPING_MODEL}",
    ]

    sem = asyncio.Semaphore(32)
    llm = get_llm(MAPPING_MODEL, temperature=0.0)

    async def classify(concept: Concept) -> Optional[int]:
        prompt = build_classify_concept_prompt()
        async with sem:
            try:
                r = await llm.ainvoke(
                    prompt.format(
                        themes=escape_braces(json.dumps(theme_defs)),
                        concept=escape_braces(json.dumps(concept.model_dump())),
                    ),
                    config={
                        **build_langfuse_config(state, tags, {"branch": branch}),
                        "run_name": "synthesis.map",
                    },
                )
                raw = (r.content if hasattr(r, "content") else str(r)).strip()
                idx = int(raw) - 1
                return idx if 0 <= idx < len(themes) else None
            except Exception:
                return None

    assignments = await asyncio.gather(*[classify(c) for c in concepts])

    buckets: Dict[int, List[Concept]] = {i: [] for i in range(len(themes))}
    for concept, idx in zip(concepts, assignments):
        if isinstance(idx, int):
            buckets[idx].append(concept)

    return [
        FinalTheme(
            name=t.theme_name,
            description=t.theme_description,
            concepts=buckets.get(i, []),
            frequency=len(buckets.get(i, [])),
        )
        for i, t in enumerate(themes)
    ]


async def process_issue_themes(state: SynthesisState) -> SynthesisState:
    """Process issue theme discovery, critique, and mapping.

    Args:
        state: Current workflow state.

    Returns:
        State update with discovered_issue_themes and final_issue_themes.
    """
    rq = state.get("research_question") or "Not specified"
    concepts = state.get("issue_concepts") or []
    themes = await _discover_themes(concepts, rq, state, "issue")
    await _critique_themes(themes, rq, state, "issue")
    finals = await _map_concepts_to_themes(concepts, themes, state, "issue")
    return {"discovered_issue_themes": themes, "final_issue_themes": finals}


async def process_intervention_themes(state: SynthesisState) -> SynthesisState:
    """Process intervention theme discovery, critique, and mapping.

    Args:
        state: Current workflow state.

    Returns:
        State update with discovered_intervention_themes and final_intervention_themes.
    """
    rq = state.get("research_question") or "Not specified"
    concepts = state.get("intervention_concepts") or []
    themes = await _discover_themes(concepts, rq, state, "intervention")
    await _critique_themes(themes, rq, state, "intervention")
    finals = await _map_concepts_to_themes(concepts, themes, state, "intervention")
    return {
        "discovered_intervention_themes": themes,
        "final_intervention_themes": finals,
    }


async def process_outcome_themes(state: SynthesisState) -> SynthesisState:
    """Process outcome theme discovery, critique, and mapping.

    Args:
        state: Current workflow state.

    Returns:
        State update with discovered_outcome_themes and final_outcome_themes.
    """
    rq = state.get("research_question") or "Not specified"
    concepts = state.get("outcome_concepts") or []
    if not concepts:
        return {"discovered_outcome_themes": [], "final_outcome_themes": []}
    themes = await _discover_themes(concepts, rq, state, "outcome")
    await _critique_themes(themes, rq, state, "outcome")
    finals = await _map_concepts_to_themes(concepts, themes, state, "outcome")
    return {"discovered_outcome_themes": themes, "final_outcome_themes": finals}
