"""Arm C keyword-leg formulation (spec §4.3a; PF `broad_search_by_keyword_prompts.py`).

S2 has TWO retrieval legs that want DIFFERENT query idioms, and PF formulates for each separately
(two agents): the dense leg (`/snippet/search`) wants verbose natural-language queries
(`dense_s2.py` ← PF `DenseAgent`), while the relevance leg (`/paper/search`) is keyword-ish — it
returns ~nothing for a long NL sentence (FINDINGS.md, 2026-06-23). PF feeds `/paper/search` a SHORT
content-keyword query produced by `BroadSearchByKeywordAgent` (`_broad_search_prompt_tmpl`), which
strips descriptive words down to the keywords that actually appear in paper text.

This module ports that prompt. `S2Source.formulate_queries` / `.reformulate` (s2_client.py) delegate
here for the KEYWORD leg, while `.formulate_dense_queries` / `.reformulate_dense_queries` delegate to
`dense_s2.py` for the dense leg — the shared loop (broad_search.py) now formulates per leg and feeds
each its own idiom, mirroring PF's two-agent split.

> Faithful extension: PF's keyword agent emits ONE keyword query; we emit {n} DIVERSE keyword
> queries (one LLM call, structured list) so the keyword leg has the same per-query bandit arms the
> dense leg does (each (keyword, query) is a §4.7 origin). Same idea as our N-diverse dense queries.
>
> Domain reframing (same category as judge.py / dense_s2.py): PF says "scientific papers"; we say
> "research and policy-evidence papers" for S2's general corpus. The MECHANISM is verbatim PF —
> content-keywords only, plain text, no special syntax, no hyphens (S2 rejects them). Only the
> corpus framing changes.

Determinism comes from the on-disk cache (gpt-5.x reasoning models only accept temperature=1.0),
same pattern as dense_s2.py / suggest.py. Backend `get_llm` is lazy-imported.

REPL usage (no main()/argparse — spec conventions):
    from retrieval.keyword_s2 import formulate_keyword_queries, reformulate_keyword_queries
    qs = formulate_keyword_queries("effect of free school meals on attainment in the UK", 5)
    qs2 = reformulate_keyword_queries("…", exemplars, 5)   # exemplars: list[Candidate]
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from _backend import get_llm
from config import CONFIG
from retrieval import _cache
from retrieval._formulation import exemplar_block
from source import Candidate

logger = logging.getLogger(__name__)


class KeywordQueries(BaseModel):
    """Structured-output target (PF `BroadSearchSuggestedQueries`, pluralised to N)."""

    keyword_queries: list[str] = Field(
        description="Diverse content-keyword queries; plain text, no logical operators or syntax."
    )


# Port of PF `_broad_search_prompt_tmpl`, pluralised to N + reframed for policy/research (see docstring).
_FORMULATE_SYSTEM_PROMPT = """\
You are helping a policy researcher gather evidence. Given the search topic below, reformulate it \
into {n} different KEYWORD search queries to run on the Semantic Scholar search engine.

Turn the natural-language topic into keyword queries: remove unnecessary descriptive words that \
won't show up in the paper text itself, and keep only the content-keywords to look for. Rules:
- Use only content-keywords — do NOT emit metadata or non-keyword-y wordings.
- Be creative: make the {n} queries genuinely DIFFERENT (different angles, sub-aspects, term sets) \
— not synonym paraphrases of one another.
- Use PLAIN TEXT — Semantic Scholar does NOT support special syntax (no AND/OR/NOT, no quotes, no \
+/-). Avoid hyphens (Semantic Scholar does not support them).
- Do NOT include preferences like "recent", "latest", or "highly-cited".
- Keep any geography/population that is part of the topic (it is content, not metadata)."""

# Reformulate from judged-relevant exemplars (PF's reformulate-from-exemplars strategy, keyword idiom).
_REFORMULATE_SYSTEM_PROMPT = """\
You are helping a policy researcher gather evidence. Reformulate the search topic into {n} KEYWORD \
search queries for the Semantic Scholar search engine, to find FURTHER papers relevant to:
{content}

The papers below were judged relevant. Use their content to choose {n} NEW keyword queries that \
will surface further relevant work — be creative, do not simply repeat the obvious topic terms. \
Same rules as before: content-keywords only, plain text, no special syntax, no hyphens, no \
recency/impact words.

Relevant papers:
{papers}"""


def formulate_keyword_queries(
    content: str, n: int | None = None, *, force: bool = False
) -> list[str]:
    """N diverse S2 keyword queries for a topic (gpt-5.5, cached by content+n+model).

    Port of PF `_broad_search_prompt_tmpl` (pluralised). Falls back to `[content]` if the model
    returns nothing (an empty list would starve the keyword leg), mirroring dense_s2's fallback.
    """
    n = n or CONFIG.budgets.n_initial_queries
    model = CONFIG.models.formulation_model
    key = {"content": content, "n": n, "model": model}

    if not force:
        hit = _cache.load("keyword.formulate", key)
        if hit is not None:
            logger.info(
                "Keyword-formulation cache hit for content=%r (n=%d)", content, n
            )
            return hit

    logger.info(
        "Formulating %d keyword queries for content=%r (model=%s)", n, content, model
    )
    llm = get_llm(model, 1.0).with_structured_output(KeywordQueries)
    result: KeywordQueries = llm.invoke(
        [("system", _FORMULATE_SYSTEM_PROMPT.format(n=n)), ("user", content)]
    )
    queries = [q.strip() for q in result.keyword_queries if q.strip()][:n] or [content]
    _cache.save("keyword.formulate", key, queries)
    logger.info("Formulated %d keyword queries for content=%r", len(queries), content)
    return queries


def reformulate_keyword_queries(
    content: str,
    exemplars: list[Candidate],
    n: int | None = None,
    *,
    force: bool = False,
) -> list[str]:
    """N keyword queries reformulated from judged-relevant exemplars (gpt-5.5, cached).

    Cache key includes the exemplar paper_ids so an identical iteration is free but a changed
    exemplar set re-runs. With no exemplars, degrades to a fresh formulation.
    """
    n = n or CONFIG.budgets.n_initial_queries
    if not exemplars:
        return formulate_keyword_queries(content, n, force=force)
    model = CONFIG.models.formulation_model
    key = {
        "content": content,
        "exemplars": sorted(e.paper_id for e in exemplars),
        "n": n,
        "model": model,
    }

    if not force:
        hit = _cache.load("keyword.reformulate", key)
        if hit is not None:
            logger.info("Keyword-reformulation cache hit for content=%r", content)
            return hit

    logger.info("Reformulating %d keyword queries from %d exemplars", n, len(exemplars))
    llm = get_llm(model, 1.0).with_structured_output(KeywordQueries)
    prompt = _REFORMULATE_SYSTEM_PROMPT.format(
        n=n, content=content, papers=exemplar_block(exemplars)
    )
    result: KeywordQueries = llm.invoke([("system", prompt), ("user", content)])
    queries = [q.strip() for q in result.keyword_queries if q.strip()][:n] or [content]
    _cache.save("keyword.reformulate", key, queries)
    logger.info("Reformulated %d keyword queries for content=%r", len(queries), content)
    return queries
