"""Phase 5 — faithful PICO fold: research_question + content-PICO → one NL query_text (spec §4.1).

Production users typed a `research_question` and, separately, structured PICO fields
(geography/population/outcome/inner_setting/implementation_constraints). v3's conversational users
will type ONE natural-language question instead. This merges the two into that single question —
the arm input that gets frozen in queries.jsonl.

FAITHFULNESS IS THE WHOLE POINT. This is a MERGE, not a rewrite: weave in only the PICO content
that is actually present, add nothing, infer nothing, expand nothing, and keep the researcher's own
wording/intent. If a field is empty or a placeholder ("All", None, []), ignore it. If the question
already states the context, don't duplicate it. No recency/date words (time is metadata → recency
intent, never folded here). The output should read like the question the person would have typed if
they'd put their geography/population into prose — not an "improved" question.

Determinism comes from the on-disk cache (gpt-5.x reasoning models only accept temperature=1.0),
same pattern as dense_s2.py / keyword_s2.py. Backend `get_llm` is lazy-imported.

REPL usage (no main()/argparse — spec conventions):
    from queries.fold_query import fold_query
    qt = fold_query("Interventions to treat venous leg ulcer", {"population": ["adults"], ...})
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from _backend import get_llm
from config import CONFIG
from retrieval import _cache

logger = logging.getLogger(__name__)

# Content-PICO fields we fold (must match export_search_contexts.CONTENT_PICO). Time/config excluded.
CONTENT_PICO = (
    "geography",
    "population",
    "outcome",
    "inner_setting",
    "implementation_constraints",
)
_PLACEHOLDERS = (None, "", [], ["All"], "None", "All")
# Bump when _SYSTEM_PROMPT changes — it's part of the cache key so prompt edits force a re-fold
# (the rq/fields/model key alone wouldn't notice a prompt change). v2: geography = evidence-scope.
_PROMPT_VERSION = 2


class FoldedQuery(BaseModel):
    """Structured-output target — the single merged natural-language question."""

    query_text: str = Field(
        description="The research question with PICO context folded into prose."
    )


_SYSTEM_PROMPT = """\
You merge a policy researcher's free-text research question with a few structured context fields \
into ONE natural-language question — the question they would have typed if they'd written the \
context into prose instead of filling in form fields.

This is a FAITHFUL MERGE, not a rewrite. Rules, in priority order:
1. Add NOTHING that is not in the research question or the provided context fields. Do not infer, \
generalise, narrow, or introduce new concepts, methods, examples, or scope.
2. Keep the researcher's own wording and intent. Make the minimal edits needed to read as one \
fluent question.
3. Fold in a context field ONLY if it carries real content. Ignore empty/placeholder values \
("All", none, empty). If the question already expresses that context, do not duplicate it.
4. Integrate context naturally (e.g. weave population/outcome into the sentence); do NOT append \
a mechanical list of fields.
5. Treat the `geography` field as the geographies the EVIDENCE should be drawn from — render it as \
"drawing on evidence from <geographies>", NOT as a claim that the intervention or policy is located \
there. Preserve any policy locus the research question itself states (e.g. a UK policy stays a UK \
policy, even if evidence is sought from OECD countries).
6. Do NOT add recency/date wording ("recent", "latest", "since 2016") — timeframe is handled \
separately, not here.
7. Output ONLY the merged question, nothing else."""

_USER_TMPL = """\
Research question:
{rq}

Context fields (fold in only those with real content):
{fields}

Return the single merged natural-language question."""


def _has_content(v) -> bool:
    return v not in _PLACEHOLDERS and not (
        isinstance(v, list) and all(x in _PLACEHOLDERS for x in v)
    )


def _fields_block(content_pico: dict) -> str:
    """Render the non-empty content-PICO fields for the prompt; '(none)' if nothing to fold."""
    lines = []
    for k in CONTENT_PICO:
        v = content_pico.get(k)
        if _has_content(v):
            val = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
            lines.append(f"- {k}: {val}")
    return "\n".join(lines) if lines else "(none)"


def fold_query(
    research_question: str, content_pico: dict, *, force: bool = False
) -> str:
    """Merge research_question + content-PICO into one faithful NL query_text (gpt-5.5, cached).

    No content-PICO to fold → returns the research_question unchanged (no LLM call). Falls back to
    the research_question if the model returns empty.
    """
    rq = (research_question or "").strip()
    fields = _fields_block(content_pico or {})
    if fields == "(none)":
        return rq  # nothing to fold — faithful pass-through, no cost

    model = CONFIG.models.formulation_model
    key = {"rq": rq, "fields": fields, "model": model, "pv": _PROMPT_VERSION}
    if not force:
        hit = _cache.load("query.fold", key)
        if hit is not None:
            logger.info("Fold cache hit for rq=%r", rq[:60])
            return hit

    logger.info("Folding PICO into research_question=%r", rq[:60])
    llm = get_llm(model, 1.0).with_structured_output(FoldedQuery)
    result: FoldedQuery = llm.invoke(
        [("system", _SYSTEM_PROMPT), ("user", _USER_TMPL.format(rq=rq, fields=fields))]
    )
    query_text = (result.query_text or "").strip() or rq
    _cache.save("query.fold", key, query_text)
    return query_text
