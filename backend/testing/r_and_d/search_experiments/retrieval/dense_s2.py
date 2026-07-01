"""Arm C dense-query formulation + reformulation (spec §4.3a Step 1/3; PF dense/formulation_prompts.py).

The S2 source queries its dense/snippet index in a different idiom from Arm B's boolean
generator: natural-language queries, no logical operators. These two gpt-5.5 calls produce
them, ported from PF:

  - `formulate_dense_queries`  ← PF `_dense_formulation_prompt_multiple_tmpl` (one call → N
    diverse NL queries from the topic).
  - `reformulate_dense_queries` ← PF `_dense_reformulate_prompt_tmpl` (N new queries informed by
    the top judged-relevant papers as exemplars — PF's reformulate-from-exemplars strategy).

`S2Source.formulate_dense_queries` / `.reformulate_dense_queries` (s2_client.py) delegate here for
the DENSE leg only (`/snippet/search`); the KEYWORD leg (`/paper/search`) is formulated separately
by `keyword_s2.py`, because S2's relevance endpoint is keyword-ish and starves on dense NL queries
(PF's two-agent split; FINDINGS 2026-06-23).

> Domain reframing (deliberate, same category as judge.py / query_analysis.py): PF's prompts
> name "arXiv and ACL Anthology" (its STEM dense index). We reframe to research + policy-evidence
> literature for S2's general corpus. The MECHANISM is verbatim PF — N diverse NL queries, drop
> "a paper about…"/"studies showing…", no recency/impact words, no logical operators (the dense
> index can't use them). Only the corpus framing changes, like the other ported prompts.

Determinism comes from the on-disk cache (gpt-5.x reasoning models only accept temperature=1.0),
same pattern as suggest.py / query_analysis.py. Backend `get_llm` is lazy-imported.

REPL usage (no main()/argparse — spec conventions):
    from retrieval.dense_s2 import formulate_dense_queries, reformulate_dense_queries
    qs = formulate_dense_queries("effect of free school meals on attainment", 5)
    qs2 = reformulate_dense_queries("…", exemplars, 5)   # exemplars: list[Candidate]
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


class DenseQueries(BaseModel):
    """Structured-output target (PF `DenseQueries`)."""

    alternative_queries: list[str] = Field(
        description="Diverse natural-language dense-retrieval queries; no logical operators."
    )


# Port of PF `_dense_formulation_prompt_multiple_tmpl`, reframed for policy/research (see docstring).
_FORMULATE_SYSTEM_PROMPT = """\
You are helping a policy researcher gather evidence. Given the search topic below, formulate \
{n} different natural-language queries to run on a dense (semantic) retrieval index to find \
papers that match the topic.

The index contains academic research papers and policy-evidence literature; each passage in it \
is a short span of paper text. Rules:
- Be creative: make the {n} queries genuinely DIFFERENT from one another (different angles, \
sub-aspects, phrasings) — not synonym paraphrases.
- Phrase each as a statement of the topic, NOT as "a paper about…" or "studies showing…". \
For "papers about efficient language modeling" a good query is "methods for efficient language \
modeling"; a bad one is "papers that talk about efficient language modeling".
- Do NOT include preferences like "recent", "latest", or "highly-cited" — these do not appear \
in the text of a paper.
- The index does NOT support logical operators (AND, OR, NOT, -, +, &). Use plain language.
- Keep any geography/population that is part of the topic (it is content, not metadata)."""

# Port of PF `_dense_reformulate_prompt_tmpl`, reframed for policy/research.
_REFORMULATE_SYSTEM_PROMPT = """\
You are helping a policy researcher gather evidence. Formulate {n} natural-language queries to \
run on a dense (semantic) retrieval index to find further papers relevant to the search topic:
{content}

The index contains full-text academic + policy-evidence papers; each passage is a short span \
of text, so you may query specific details that indicate relevance, not just the headline topic.

The papers below were judged relevant. Use their content to formulate {n} NEW queries that will \
surface further relevant work — be creative and do not simply repeat the obvious topic terms. \
Same rules as before: natural language only, no logical operators, no recency/impact words.

Relevant papers:
{papers}"""


def formulate_dense_queries(
    content: str, n: int | None = None, *, force: bool = False
) -> list[str]:
    """N diverse natural-language dense queries for a topic (gpt-5.5, cached by content+n+model).

    Port of PF `_dense_formulation_prompt_multiple_tmpl`. Falls back to `[content]` if the model
    returns nothing (an empty list would starve the dense leg), mirroring v2's generator fallback.
    """
    n = n or CONFIG.budgets.n_initial_queries
    model = CONFIG.models.formulation_model
    key = {"content": content, "n": n, "model": model}

    if not force:
        hit = _cache.load("dense.formulate", key)
        if hit is not None:
            logger.info("Dense-formulation cache hit for content=%r (n=%d)", content, n)
            return hit

    logger.info(
        "Formulating %d dense queries for content=%r (model=%s)", n, content, model
    )
    llm = get_llm(model, 1.0).with_structured_output(DenseQueries)
    result: DenseQueries = llm.invoke(
        [("system", _FORMULATE_SYSTEM_PROMPT.format(n=n)), ("user", content)]
    )
    queries = [q.strip() for q in result.alternative_queries if q.strip()][:n] or [
        content
    ]
    _cache.save("dense.formulate", key, queries)
    logger.info("Formulated %d dense queries for content=%r", len(queries), content)
    return queries


def reformulate_dense_queries(
    content: str,
    exemplars: list[Candidate],
    n: int | None = None,
    *,
    force: bool = False,
) -> list[str]:
    """N dense queries reformulated from judged-relevant exemplars (gpt-5.5, cached).

    Port of PF `_dense_reformulate_prompt_tmpl` (PF's reformulate-from-exemplars strategy).
    Cache key includes the exemplar paper_ids so an identical iteration is free but a changed
    exemplar set re-runs. With no exemplars, degrades to a fresh formulation.
    """
    n = n or CONFIG.budgets.n_initial_queries
    if not exemplars:
        return formulate_dense_queries(content, n, force=force)
    model = CONFIG.models.formulation_model
    key = {
        "content": content,
        "exemplars": sorted(e.paper_id for e in exemplars),
        "n": n,
        "model": model,
    }

    if not force:
        hit = _cache.load("dense.reformulate", key)
        if hit is not None:
            logger.info("Dense-reformulation cache hit for content=%r", content)
            return hit

    logger.info("Reformulating %d dense queries from %d exemplars", n, len(exemplars))
    llm = get_llm(model, 1.0).with_structured_output(DenseQueries)
    prompt = _REFORMULATE_SYSTEM_PROMPT.format(
        n=n, content=content, papers=exemplar_block(exemplars)
    )
    result: DenseQueries = llm.invoke([("system", prompt), ("user", content)])
    queries = [q.strip() for q in result.alternative_queries if q.strip()][:n] or [
        content
    ]
    _cache.save("dense.reformulate", key, queries)
    logger.info("Reformulated %d dense queries for content=%r", len(queries), content)
    return queries
