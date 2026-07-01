"""Step 0 — ensemble-side query analysis (spec §4.3 Step 0; PF query_analyzer).

Two gpt-5.5 calls, run once per query and cached, that turn the raw research question into
the two things the shared core needs:

  1. *Content* — the topical core with all metadata stripped (authors, years/"recent",
     impact words, venues). This feeds query *generation* (Step 1) so we search the topic,
     not the noise. Port of PF `_content_extraction_prompt_tmpl`.
  2. *Intent* — does the query ask for recent/early work, and central/less-cited work?
     This feeds only the ranking *weights* (Step 5). Port of PF `_recency_extraction` +
     `_centrality_extraction`, merged into ONE structured call (they're independent flags,
     so one call with two fields is cheaper than two — and both are gpt-5.5 anyway).

This is the whole of the query-analyzer we keep: PF runs 11 parallel extractions, but the
router + author/venue/title-match/broad-vs-specific branches only fire for known-item and
metadata routes that our broad-by-description scope never takes (spec §4.3a "Scope"). So we
port content + recency + centrality and drop the other eight — fewer calls, no behaviour lost.

Arm B and Arm C share this verbatim (Arm C reuses the cached result, spec §4.3a Step 0), so
query understanding is held constant across the source axis.

> ★ Why two flags but one weight key. PF's ranking weight table (`SortPreferences
> .get_scoring_weights`) keys on whether recency/centrality were mentioned *at all*
> (`is_recent_explicit`), NOT on the direction. The *direction* ("recent" vs "early")
> only flips the sigmoid in ranking.py. So `QueryIntent` carries direction (ranking needs
> it) and `weight_key()` collapses it to presence (the weight table needs that).

REPL usage (no main()/argparse — spec conventions):
    from query_analysis import analyse_query, load_analysis
    a = analyse_query("q001", "latest RCTs on universal basic income and employment")
    a.content                 # "universal basic income and employment" (metadata stripped)
    a.intent.recency          # "recent"
    a.intent.weight_key()     # "recent"
    a.intent.weights()        # (0.80, 0.175, 0.025)  -> (w_content, w_recent, w_central)

Backend helpers (get_llm) are lazy-imported inside `analyse_query` so the pure dataclasses
here stay importable/testable without backend env vars (same pattern as judge.py).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from _backend import get_llm
from config import CONFIG

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent / "results"
ANALYSIS_DIR = RESULTS_DIR / "query_analysis"


# --------------------------------------------------------------------------- #
# Structured-output targets (one per LLM call)
# --------------------------------------------------------------------------- #
class ContentExtraction(BaseModel):
    """Topical core of the query, metadata stripped (PF ExtractedContent)."""

    content: str | None = Field(
        description=(
            "The query's topical content with ALL metadata removed (author names, "
            "years/time words, impact words, venues). Null if the query is metadata-only."
        )
    )


class IntentExtraction(BaseModel):
    """Recency + centrality preference (PF recency + centrality extractions, merged)."""

    recency: Literal["recent", "early"] | None = Field(
        description=(
            "'recent' if the query explicitly asks for recent/latest work, 'early' if it "
            "asks for early/classic work, else null. Do NOT infer from absolute years."
        )
    )
    centrality: Literal["central", "less"] | None = Field(
        description=(
            "'central' if the query asks for central/seminal/influential/highly-cited work, "
            "'less' if it asks for less-cited/lesser-known work, else null."
        )
    )


# --------------------------------------------------------------------------- #
# Intent — direction (ranking) + presence (weight table)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class QueryIntent:
    """Recency/centrality preference. `recency`/`centrality` carry DIRECTION (ranking.py
    flips a sigmoid on them); `weight_key()` collapses to PRESENCE (the §4.3 Step-5 table)."""

    recency: Literal["recent", "early"] | None = None
    centrality: Literal["central", "less"] | None = None

    def weight_key(self) -> str:
        """Map to the intent_weights key (PF get_scoring_weights branches on explicitness)."""
        has_recency = self.recency is not None
        has_centrality = self.centrality is not None
        if has_recency and has_centrality:
            return "recent_and_influential"
        if has_recency:
            return "recent"
        if has_centrality:
            return "influential"
        return "just_topic"

    def weights(self) -> tuple[float, float, float]:
        """(w_content, w_recent, w_central) for this intent (spec §4.3 Step 5 table)."""
        return CONFIG.blend.intent_weights[self.weight_key()]


@dataclass
class QueryAnalysis:
    """Step-0 output: the raw query, its stripped content, and its ranking intent."""

    raw_query: str
    content: str
    intent: QueryIntent


# --------------------------------------------------------------------------- #
# Prompts (ported from PF query_analyzer_prompts.py)
# --------------------------------------------------------------------------- #
# Port of PF `_content_extraction_prompt_tmpl` (query_analyzer_prompts.py:130-178), trimmed
# to the rules + a few examples and re-framed for policy research. We keep PF's metadata
# taxonomy verbatim because Step 1's query generation depends on the SAME notion of "topical
# core" PF's dense formulation used; the policy framing + examples (matching judge.py's light
# domain framing, spec §4.5) only nudge the model toward the substance a policy researcher
# means — the intervention, population, setting, and outcome — not toward any metadata route.
_CONTENT_SYSTEM_PROMPT = """\
You are helping a policy researcher gather evidence. The query below is a policy-research \
question; extract only its *content* — the substantive topic (the intervention or policy, \
the population/group, the setting, and the outcome of interest) — and ignore all *metadata*. \
Metadata is any of:
- Author / coauthor name(s)
- Year(s), or words describing time ("recent", "latest", "early", "classic")
- Words describing a paper's impact ("central", "seminal", "influential", "highly cited")
- Venues or publishers (e.g. The Lancet, a named think tank, a government department)
- Words describing how to search ("run an exhaustive search on...")

Rules:
- Keep phrases like "evaluations of", "studies measuring", "evidence on the effect of", \
"systematic reviews of" as content; bare "papers about" / "papers on" can be dropped.
- Preserve the RELATION the question is really asking about — keep "effect of X on Y" intact, \
not just "X" and "Y" separately.
- Where the question names a geography or population, KEEP it as part of the topic (it is a \
soft scoping prior, not metadata to strip).
- If the query is a question, return a coherent representation focused on its content.
- If you are unsure what the content is, return the original query unchanged.
- If the query is metadata only (no topic), return null.

Examples:
  "classic or early evaluations of conditional cash transfers" -> "effect of conditional cash transfers"
  "latest research on free school meals and pupil attainment in the UK" -> "effect of free school meals on pupil attainment in the UK"
  "what works to reduce rough sleeping among young people" -> "interventions to reduce rough sleeping among young people"
  "seminal Lancet papers from 2019" -> null"""

# Port of PF `_recency_extraction_prompt_tmpl` (276-298) + `_centrality_extraction_prompt_tmpl`
# (325-351), merged (independent flags -> one gpt-5.5 call) and re-framed for policy research.
_INTENT_SYSTEM_PROMPT = """\
You are helping a policy researcher gather evidence. For the policy-research question below, \
decide TWO things, ignoring all other information.

1. RECENCY — does the question explicitly ask for recent or early evidence?
   - "recent" for words like "recent", "latest", "up to date", "current".
   - "early" for words like "early", "earlier", "classic", "foundational", "first".
   - null otherwise. DO NOT assume recency from absolute years (a 2024 date is not "recent").

2. CENTRALITY — does the question ask for central or less-cited work?
   - "central" for words like "central", "seminal", "landmark", "highly influential", \
"highly cited", "key", "the most important".
   - "less" for words like "less cited", "lesser known", "overlooked", "emerging".
   - null otherwise.

Examples:
  "latest evidence on the minimum wage and employment"        -> recency=recent,  centrality=null
  "early / foundational studies of universal basic income"    -> recency=early,   centrality=null
  "the most important evaluations of Sure Start"              -> recency=null,    centrality=central
  "recent landmark trials of social prescribing"              -> recency=recent,  centrality=central
  "evidence on the effect of free school meals on attainment" -> recency=null,    centrality=null"""


# --------------------------------------------------------------------------- #
# Cache I/O (pure — offline-testable)
# --------------------------------------------------------------------------- #
def _to_payload(query_id: str, analysis: QueryAnalysis) -> dict:
    return {
        "query_id": query_id,
        "raw_query": analysis.raw_query,
        "content": analysis.content,
        "recency": analysis.intent.recency,
        "centrality": analysis.intent.centrality,
        "model": CONFIG.models.intent_model,
    }


def _from_payload(payload: dict) -> QueryAnalysis:
    return QueryAnalysis(
        raw_query=payload["raw_query"],
        content=payload["content"],
        intent=QueryIntent(
            recency=payload.get("recency"), centrality=payload.get("centrality")
        ),
    )


def load_analysis(query_id: str) -> QueryAnalysis:
    """Read cached query analysis (no LLM). Raises if not yet analysed."""
    path = ANALYSIS_DIR / f"{query_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No cached analysis for query {query_id!r} at {path}. "
            f"Run analyse_query({query_id!r}, query_text) first."
        )
    return _from_payload(json.loads(path.read_text()))


# --------------------------------------------------------------------------- #
# Step 0 — the two gpt-5.5 calls (cached)
# --------------------------------------------------------------------------- #
def analyse_query(
    query_id: str, query_text: str, *, force: bool = False
) -> QueryAnalysis:
    """Extract content + recency/centrality intent for a query (cached to disk).

    Two gpt-5.5 calls. gpt-5.x is a reasoning model with no usable temperature knob (the API
    only accepts the default 1.0), so determinism for this frozen-instrument front-end comes
    from the CACHE, not temperature=0: a query is analysed exactly once and the result frozen
    at results/query_analysis/{query_id}.json, then reused verbatim by Arm B and Arm C
    (spec §4.3a Step 0). `force=True` re-runs and overwrites.
    """
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    path = ANALYSIS_DIR / f"{query_id}.json"
    if path.exists() and not force:
        logger.info("Query-analysis cache hit for query %s", query_id)
        return load_analysis(query_id)

    model = CONFIG.models.intent_model
    logger.info("Analysing query %s (model=%s)", query_id, model)

    # temperature=1.0: gpt-5.x reasoning models reject any other value; get_llm requires the
    # arg, so we pass the model's only supported (default) temperature. Determinism is the
    # cache's job, not this knob's.
    # Call 1 — content extraction. Fall back to the raw query if the model nulls/empties it
    # (PF's "if unsure, return the query as-is"): an empty content would starve Step 1.
    content_llm = get_llm(model, 1.0).with_structured_output(ContentExtraction)
    content_res: ContentExtraction = content_llm.invoke(
        [("system", _CONTENT_SYSTEM_PROMPT), ("user", query_text)]
    )
    content = (content_res.content or "").strip() or query_text

    # Call 2 — recency + centrality intent (merged).
    intent_llm = get_llm(model, 1.0).with_structured_output(IntentExtraction)
    intent_res: IntentExtraction = intent_llm.invoke(
        [("system", _INTENT_SYSTEM_PROMPT), ("user", query_text)]
    )
    intent = QueryIntent(recency=intent_res.recency, centrality=intent_res.centrality)

    analysis = QueryAnalysis(raw_query=query_text, content=content, intent=intent)
    path.write_text(json.dumps(_to_payload(query_id, analysis), indent=2))
    logger.info(
        "Analysed query %s: content=%r intent=(recency=%s, centrality=%s) -> weights %s",
        query_id,
        content,
        intent.recency,
        intent.centrality,
        intent.weights(),
    )
    return analysis
