"""Parametric LLM paper suggestions + source grounding (spec §4.3 Step 1; PF llm_suggestion).

One of the three initial-retrieval legs (§4.3 Step 1): gpt-5.5 names ~10–15 candidate papers
"from memory" (title + year), then each is GROUNDED against the live source — looked up by
title (±2-year window) and DOI — and any suggestion that can't be matched to a real record is
dropped. Ungrounded titles are exactly the LLM hallucinations grounding exists to filter, so a
suggestion only enters the pool once the source confirms it.

Two halves, split along the source axis (spec §5 "suggest.py"):
  - NAMING is source-agnostic (this module's `suggest_titles`, gpt-5.5, cached).
  - GROUNDING is source-specific, so the source client injects a `ground_fn`
    (OpenAlex title search for Arm B; S2 `/paper/search` match_title for Arm C).

Pre-registered caveat (§4.3 Step 1, §7): parametric suggestion is expected to be WEAKER on
policy/social-science literature than on the CS corpus PF was tuned for — it's cheap to run and
origin attribution (§4.7) will show whether it earns its place. We measure, not assume.

REPL usage (no main()/argparse — spec conventions):
    import asyncio
    from retrieval.suggest import suggest_titles, ground_suggestions
    titles = suggest_titles("effect of free school meals on attainment", n=15)
    cands = asyncio.run(ground_suggestions(titles, my_source.ground_one))   # drops ungrounded
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from statistics import median

from pydantic import BaseModel, Field

from _backend import get_llm
from config import CONFIG
from retrieval import _cache
from source import Candidate

logger = logging.getLogger(__name__)

# A grounding function maps one suggested (title, year) to a real source record, or None if the
# source can't confirm it. Injected by each SourceClient (OpenAlex vs S2 lookup).
GroundFn = Callable[["SuggestedPaper"], Awaitable[Candidate | None]]

# Grounding should CONFIRM the matched record is the paper the LLM named — not just the top
# relevance hit (which can share title words but be a different paper). Rather than hard-drop on
# a threshold guessed blind, we MEASURE FIRST (cf. the §4.4 enrichment decision): every grounding
# is kept, and its normalised title-similarity is recorded to disk + logs so the score
# distribution can be inspected after a real run and a cutoff chosen from data. A wrong grounding
# is low-cost in the meantime — the judge scores an unrelated paper level-0, so it self-corrects
# (it only costs a judge call + a `suggest` origin tag). This constant is therefore a PROVISIONAL
# analysis bar (used to flag/colour low-similarity matches in logs), NOT an enforced filter.
DEFAULT_TITLE_MATCH_THRESHOLD = 0.85
_TITLE_NORM = re.compile(r"[^a-z0-9]+")


class SuggestedPaper(BaseModel):
    """One LLM-named candidate paper, pre-grounding (PF parametric suggestion)."""

    title: str = Field(
        description="The paper's title, as accurately as you can recall it."
    )
    year: int | None = Field(
        default=None, description="Approximate publication year, or null if unsure."
    )


class SuggestionSet(BaseModel):
    """Structured-output target for the naming call."""

    papers: list[SuggestedPaper] = Field(
        description="Real academic papers relevant to the topic; empty if none recalled."
    )


# --------------------------------------------------------------------------- #
# Title similarity (pure — offline-testable). Used to RECORD how close each grounded match
# is to the named title (selection itself trusts the source's own fuzzy ranking, §_ground_one).
# --------------------------------------------------------------------------- #
def _normalise_title(t: str | None) -> str:
    """Lowercase, strip punctuation, collapse whitespace — so casing/punctuation don't sink a match."""
    return _TITLE_NORM.sub(" ", (t or "").lower()).strip()


def title_similarity(a: str | None, b: str | None) -> float:
    """Normalised title similarity in [0, 1] (`difflib` ratio; stdlib, no dependency).

    Exact (normalised) equality → 1.0. Substring containment (e.g. the LLM dropped a subtitle)
    is treated as a strong match (≥0.95). Empty either side → 0.0. This is the number recorded
    per grounding so the cutoff can be chosen from the observed distribution, not guessed.
    """
    na, nb = _normalise_title(a), _normalise_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return max(0.95, SequenceMatcher(None, na, nb).ratio())
    return SequenceMatcher(None, na, nb).ratio()


@dataclass
class GroundingRecord:
    """One suggestion→source match, with its title-similarity — the durable analysis signal."""

    suggested_title: str
    suggested_year: int | None
    matched_id: str
    matched_title: str | None
    similarity: float


# Port of PF's llm_suggestion intent, re-framed for policy research. Asks ONLY for papers the
# model is confident are real (the source still drops titles that match no real record; the
# title-similarity of those that DO match is recorded, not gated). No "papers about" phrasing.
_SUGGEST_SYSTEM_PROMPT = """\
You are an expert research and policy analyst with broad knowledge of the academic and \
policy-evidence literature. Name up to {n} real academic papers, reports, or evaluations that \
are most relevant to the research topic below — the kind a domain expert would cite when \
gathering evidence on it.

Rules:
- Name only works you are genuinely confident EXIST. Do not invent plausible-sounding titles; \
unverifiable suggestions are discarded downstream, so a confident shortlist beats a padded one.
- Give each paper's title as accurately as you can, plus its approximate publication year \
(null if unsure).
- Prefer empirical evaluations, systematic reviews, and influential studies on the topic over \
general commentary.
- Return an empty list rather than guessing if you cannot recall genuinely relevant works."""


def suggest_titles(
    content: str, n: int | None = None, *, force: bool = False
) -> list[SuggestedPaper]:
    """gpt-5.5 names up to `n` candidate papers for a topic (cached by content+n+model).

    Source-agnostic (Arm B and Arm C share the naming; only grounding differs). Determinism
    comes from the on-disk cache, not temperature — gpt-5.x reasoning models only accept the
    default temperature=1.0 (same rationale as query_analysis.py / judge.py).
    """
    n = n or CONFIG.budgets.n_parametric_suggestions
    model = CONFIG.models.formulation_model
    key = {"content": content, "n": n, "model": model}

    if not force:
        hit = _cache.load("suggest.titles", key)
        if hit is not None:
            logger.info("Suggestion cache hit for content=%r (n=%d)", content, n)
            return [SuggestedPaper(**p) for p in hit]

    logger.info(
        "Suggesting up to %d papers for content=%r (model=%s)", n, content, model
    )
    llm = get_llm(model, 1.0).with_structured_output(SuggestionSet)
    result: SuggestionSet = llm.invoke(
        [("system", _SUGGEST_SYSTEM_PROMPT.format(n=n)), ("user", content)]
    )
    papers = result.papers[:n]
    _cache.save("suggest.titles", key, [p.model_dump() for p in papers])
    logger.info("Suggested %d paper(s) for content=%r", len(papers), content)
    return papers


async def ground_suggestions(
    suggestions: list[SuggestedPaper],
    ground_fn: GroundFn,
    *,
    cache_key: str | None = None,
) -> list[Candidate]:
    """Ground each suggestion against the source; KEEP every match and RECORD its similarity.

    `ground_fn` (source-injected) returns the source's best record for a suggestion, or None if
    the source confirmed nothing (a genuinely non-existent title — still dropped). For every
    record returned we compute `title_similarity(suggested, matched)`, log it, and — when
    `cache_key` is given (the query content) — persist the `GroundingRecord`s to
    results/retrieval/suggest.groundings/ so the score distribution can be analysed after a real
    run. Nothing is dropped on the threshold here (see DEFAULT_TITLE_MATCH_THRESHOLD); the judge
    scores any mis-grounded paper level-0 downstream. Dedupe against the rest of the pool is the
    core's `dedupe` job (a suggestion matching an already-retrieved paper accretes the `suggest`
    origin there).
    """
    grounded: list[Candidate] = []
    records: list[GroundingRecord] = []
    for s in suggestions:
        cand = await ground_fn(s)
        if cand is None:
            continue
        sim = title_similarity(s.title, cand.title)
        records.append(
            GroundingRecord(
                suggested_title=s.title,
                suggested_year=s.year,
                matched_id=cand.paper_id,
                matched_title=cand.title,
                similarity=sim,
            )
        )
        flag = (
            ""
            if sim >= DEFAULT_TITLE_MATCH_THRESHOLD
            else "  <-- LOW (below provisional bar)"
        )
        logger.info(
            "suggest grounding: sim=%.3f | named=%r | matched=%r [%s]%s",
            sim,
            s.title,
            cand.title,
            cand.paper_id,
            flag,
        )
        grounded.append(cand)

    if records:
        sims = [r.similarity for r in records]
        logger.info(
            "Grounded %d/%d suggestion(s): similarity min/median/max = %.3f/%.3f/%.3f "
            "(%d below provisional bar %.2f)",
            len(grounded),
            len(suggestions),
            min(sims),
            median(sims),
            max(sims),
            sum(s < DEFAULT_TITLE_MATCH_THRESHOLD for s in sims),
            DEFAULT_TITLE_MATCH_THRESHOLD,
        )
        if cache_key is not None:
            _cache.save(
                "suggest.groundings",
                {"content": cache_key},
                [r.__dict__ for r in records],
            )
    else:
        logger.info("Grounded 0/%d suggestion(s) against the source", len(suggestions))
    return grounded
